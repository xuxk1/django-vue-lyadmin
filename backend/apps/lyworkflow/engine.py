"""
流程引擎核心模块
借鉴 Django-Viewflow 的设计理念，提供声明式的流程编排能力
"""
import logging
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from apps.lyworkflow.models import (
    WorkflowInstance, WorkflowTask, WorkflowStep, 
    WorkflowCC, WorkflowCCInstance, WorkflowLog
)
from mysystem.models import Users

logger = logging.getLogger(__name__)


class FlowEngine:
    """
    流程引擎核心类
    
    设计理念：
    - 声明式流程定义（通过数据库配置）
    - 自动化的任务分发
    - 灵活的条件分支
    - 完善的日志追踪
    """
    
    def __init__(self, instance: WorkflowInstance):
        self.instance = instance
        self.workflow_type = instance.workflow_type
        
    def start(self):
        """启动流程"""
        logger.info(f"启动流程: {self.instance.instance_no}")
        
        # 先验证流程配置
        try:
            # 获取第一个步骤（按step_order排序后的第一个）
            first_step = WorkflowStep.objects.filter(
                workflow_type=self.workflow_type
            ).order_by('step_order').first()
            
            if not first_step:
                logger.error(f"流程 {self.workflow_type.name} 没有配置任何步骤")
                raise ValueError(f"流程 {self.workflow_type.name} 没有配置任何步骤")
            
            logger.info(f"第一步配置: {first_step.step_name}, step_order={first_step.step_order}, 审批人类型: {first_step.approver_type}")
            
            # 如果是多级审批，验证配置是否完整
            if first_step.approver_type == 6:
                if not first_step.multi_level_config:
                    raise ValueError(f"多级审批步骤 {first_step.id} 没有配置层级信息")
                
                import json
                config = first_step.multi_level_config
                if isinstance(config, str):
                    config = json.loads(config)
                
                if not config or len(config) == 0:
                    raise ValueError(f"多级审批步骤 {first_step.id} 的层级配置为空")
                
                logger.info(f"多级审批配置: {len(config)} 个层级")
                for idx, level in enumerate(config):
                    approver_type = level.get('approver_type')
                    if approver_type == 2:  # 指定部门
                        dept_id = level.get('approver_dept')
                        if not dept_id:
                            raise ValueError(f"第{idx+1}级 '{level.get('name')}' 的审批部门未配置")
        except Exception as e:
            logger.error(f"流程配置验证失败: {str(e)}")
            raise
        
        with transaction.atomic():
            try:
                # 创建第一步的审批任务（使用实际的step_order和对应的level_order）
                # 对于多级审批，第一个层级的 level_order = step_order
                first_level_order = first_step.step_order
                self._create_tasks_for_step(first_step.step_order, first_level_order)
                
                # 验证任务是否创建成功
                task_count = WorkflowTask.objects.filter(
                    instance=self.instance,
                    status=0
                ).count()
                
                if task_count == 0:
                    raise ValueError("任务创建失败：没有生成任何待审批任务")
                
                logger.info(f"成功创建 {task_count} 个待审批任务")
                
                # 更新流程状态
                self.instance.status = 1  # 审批中
                # current_step 应该存储 level_order（整数），与 level_order 字段类型保持一致
                self.instance.current_step = first_level_order
                self.instance.save()
                
                # 通知抄送人员
                self._notify_cc_users()
                
                # 记录日志
                self._create_log('start', '启动流程')
                
                logger.info(f"流程启动成功: {self.instance.instance_no}")
                
            except Exception as e:
                logger.error(f"流程启动过程中发生错误: {str(e)}")
                # 回滚事务，不更新流程状态
                raise
    
    def approve_task(self, task: WorkflowTask, approve_result: int, comment: str = '', operator: Users = None):
        """
        审批任务
        
        Args:
            task: 审批任务
            approve_result: 审批结果 (1=通过, 2=驳回, 3=退回)
            comment: 审批意见
            operator: 操作人
        """
        logger.info(f"审批任务: {task.id}, 结果: {approve_result}")
        
        with transaction.atomic():
            # 更新任务状态
            task.approve_result = approve_result
            task.approve_comment = comment
            task.approve_time = datetime.now()
            
            if approve_result == 1:  # 通过
                task.status = 1
            elif approve_result == 2:  # 驳回
                task.status = 2
            elif approve_result == 3:  # 退回
                task.status = 3
            
            task.save()
            
            # 记录日志
            action_map = {1: 'approve', 2: 'reject', 3: 'return'}
            desc_map = {1: '审批通过', 2: '驳回流程', 3: '退回流程'}
            self._create_log(action_map[approve_result], desc_map[approve_result], comment, operator)
            
            # 根据审批结果处理流程流转
            if approve_result == 1:  # 通过
                self._handle_approve_pass(task)
            elif approve_result == 2:  # 驳回
                self._handle_reject(task)
            elif approve_result == 3:  # 退回
                self._handle_return(task)
        
        logger.info(f"任务审批完成: {task.id}")
    
    def _handle_approve_pass(self, current_task: WorkflowTask):
        """处理审批通过后的流程流转（支持多级审批）"""
        instance = self.instance
        current_step_order = current_task.step_order
        current_level_order = current_task.level_order if hasattr(current_task, 'level_order') else current_task.step_order
        
        logger.info(f"_handle_approve_pass - 当前任务: {current_task.id}, step_order={current_step_order}, level_order={current_level_order}")
        
        # 检查当前步骤是否为会签模式
        current_step = current_task.step
        if current_step.sign_mode == 2:  # 会签
            # 检查是否所有人都已审批
            pending_tasks = WorkflowTask.objects.filter(
                instance=instance,
                step_order=current_step_order,
                level_order=current_level_order,
                status=0
            ).count()
            
            if pending_tasks > 0:
                # 还有人未审批，等待
                logger.info(f"会签模式，还有 {pending_tasks} 人未审批")
                return
        elif current_step.sign_mode == 1:  # 或签
            # 或签模式：一人审批通过即可流转到下一层级
            # 需要将该层级其他待审批的任务标记为"已跳过"
            logger.info(f"或签模式，一人审批通过即可流转到下一层级/步骤")
            
            # 将该层级其他待审批的任务标记为已跳过
            other_pending_tasks = WorkflowTask.objects.filter(
                instance=instance,
                step_order=current_task.step_order,
                level_order=current_level_order,
                status=0
            ).exclude(id=current_task.id)
            
            if other_pending_tasks.exists():
                skip_count = other_pending_tasks.update(status=2, approve_result=0, approve_comment='或签模式，其他人已通过，自动跳过')
                logger.info(f'或签模式：已将 {skip_count} 个待审批任务标记为已跳过')
        
        # 检查当前步骤是否为多级审批
        if current_step.approver_type == 6 and current_step.multi_level_config:
            logger.info(f"多级审批模式 detected")
            # 多级审批：检查当前层级是否还有未完成的任务
            import json
            config = current_step.multi_level_config
            if isinstance(config, str):
                config = json.loads(config)
            
            # 计算当前是第几个层级（idx从0开始）
            base_step_order = current_task.step_order
            current_level_idx = current_level_order - base_step_order
            
            logger.info(f"当前层级索引: {current_level_idx}, 总层级数: {len(config)}")
            
            # 检查是否还有下一个层级
            if current_level_idx + 1 < len(config):
                logger.info(f"有下一个层级 (idx={current_level_idx + 1})")
                # 有下一个层级，检查当前层级是否所有任务都已完成（或签模式下只需要一人通过即可）
                # 对于或签和顺序审批，只要当前任务通过了，就可以流转
                # 对于会签，需要所有人都通过（上面已经检查过了）
                
                # 获取下一个层级的 level_order：base_step_order + (idx + 1)
                next_level_order = base_step_order + (current_level_idx + 1)
                
                # 检查下一个层级是否已经有任务
                existing_next_level_tasks = WorkflowTask.objects.filter(
                    instance=instance,
                    step_order=current_step_order,
                    level_order=next_level_order
                ).exists()
                
                logger.info(f"下一个层级 level_order={next_level_order}, 已有任务: {existing_next_level_tasks}")
                
                if not existing_next_level_tasks:
                    # 下一个层级还没有任务，创建它
                    logger.info(f"创建下一个层级的任务: level_order={next_level_order}")
                    self._create_tasks_for_step(current_step_order, next_level_order)
                    self._create_log('next_level', f'流转到多级审批下一层级 (level_order={next_level_order})')
                else:
                    logger.info(f"下一个层级 (level_order={next_level_order}) 已有任务，跳过创建")
                
                # 关键修复：无论下一个层级是否已有任务，都需要更新 current_step
                instance.current_step = next_level_order
                instance.save()
                logger.info(f'已更新 current_step 为: {instance.current_step}')
                return
            else:
                logger.info(f"已是最后一个层级，准备流转到下一步骤或完成流程")
        
        # 普通步骤或多级审批的最后一个层级完成：查找下一步骤
        next_step = self._get_next_step(current_step_order)
        
        logger.info(f'审批通过 - 当前步骤: {current_step_order}, current_level_order: {current_level_order}')
        logger.info(f'下一步骤: {next_step.step_order if next_step else None} ({next_step.step_name if next_step else "无"})')
        
        if next_step:
            # 有下一步骤，创建新的审批任务
            logger.info(f'审批通过 - 当前步骤: {current_step_order}, 下一步骤: {next_step.step_order} ({next_step.step_name})')
            # 关键修复：current_step 应该设置为下一个步骤的第一个层级的 level_order（整数）
            # 对于普通步骤，level_order = step_order；对于多级审批，第一个层级 level_order = step_order
            instance.current_step = next_step.step_order
            instance.save()
            logger.info(f'已更新 current_step 为: {instance.current_step}')
            
            self._create_tasks_for_step(next_step.step_order, next_step.step_order)  # 普通步骤 level_order = step_order
            self._create_log('next_step', f'流转到下一步骤: {next_step.step_name}')
        else:
            # 所有步骤完成，流程通过
            logger.info(f'所有步骤完成，流程通过')
            instance.status = 2  # 已通过
            # current_step 应该设置为最后一个层级的 level_order（整数）
            # 获取当前任务的 step_order，作为最后一个步骤的标识
            last_step_order = current_task.step_order
            
            # 如果当前步骤是多级审批，获取最后一个层级的 level_order
            if current_step.approver_type == 6 and current_step.multi_level_config:
                import json
                config = current_step.multi_level_config
                if isinstance(config, str):
                    config = json.loads(config)
                # 最后一个层级的 level_order = step_order + (len(config) - 1)
                last_level_order = last_step_order + (len(config) - 1)
                instance.current_step = last_level_order
            else:
                # 普通步骤，level_order = step_order
                instance.current_step = last_step_order
            
            instance.save()
            logger.info(f'流程完成，current_step 设置为: {instance.current_step}')
            self._create_log('complete', '流程已完成')
    
    def _get_next_multi_level_order(self, step: WorkflowStep, current_level_order: int):
        """
        获取多级审批的下一个层级顺序
        
        Args:
            step: 多级审批步骤
            current_level_order: 当前层级的 level_order（整数）
            
        Returns:
            下一个层级的 level_order，如果没有则返回 None
        """
        if not step.multi_level_config:
            return None
        
        # 从当前层级顺序中提取原始 step_order
        base_step_order = step.step_order
        
        # 计算当前是第几个层级（idx从0开始）
        current_level_idx = current_level_order - base_step_order
        
        # 检查是否还有下一个层级
        if current_level_idx + 1 < len(step.multi_level_config):
            # 有下一个层级，返回其 level_order
            next_level_order = base_step_order + (current_level_idx + 1)
            return next_level_order
        else:
            # 已经是最后一个层级，返回 None
            return None
    
    def _handle_reject(self, current_task: WorkflowTask):
        """处理驳回操作"""
        instance = self.instance
        
        # 流程直接结束
        instance.status = 3  # 已驳回
        # 注意：不更新 current_step，保持在当前驳回的节点
        # 这样前端可以正确显示 "当前步骤" 为驳回所在节点（如 1/2）
        instance.save()
        
        # 取消后续所有待审批任务
        WorkflowTask.objects.filter(
            instance=instance,
            step_order__gt=current_task.step_order,
            status=0
        ).update(status=2)
        
        self._create_log('rejected', '流程已驳回')
    
    def _handle_return(self, current_task: WorkflowTask):
        """处理退回操作"""
        instance = self.instance
        
        # 退回到申请人（保持审批中状态）
        instance.status = 1
        instance.save()
        
        self._create_log('returned', '流程已退回给申请人')
    
    def _get_next_step(self, current_step_order: int):
        """
        获取下一步骤（支持条件分支）
        
        Args:
            current_step_order: 当前步骤顺序
            
        Returns:
            WorkflowStep 或 None
        """
        # 首先尝试从当前步骤的配置中获取下一步骤
        current_step = WorkflowStep.objects.filter(
            workflow_type=self.workflow_type,
            step_order=current_step_order
        ).first()
        
        if not current_step:
            return None
        
        # 如果有明确的下一步骤配置，优先使用
        if current_step.next_step_on_pass:
            return current_step.next_step_on_pass
        
        # 否则按顺序查找下一步骤
        next_step = WorkflowStep.objects.filter(
            workflow_type=self.workflow_type,
            step_order__gt=current_step_order
        ).order_by('step_order').first()
        
        return next_step
    
    def _create_sync_notification(self, user, instance, notification_type):
        """
        同步创建站内消息通知
        
        Args:
            user: 接收通知的用户对象
            instance: 流程实例对象
            notification_type: 通知类型 (approve, cc, reject, return, approved)
        """
        from apps.lymessages.models import MyMessage, MyMessageUser
        
        # 根据通知类型生成消息内容
        message_title = ''
        message_content = ''
        
        if notification_type == 'approve':
            message_title = f'流程审批通知 - {instance.title}'
            message_content = f'您有一个流程需要审批：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'cc':
            message_title = f'流程抄送通知 - {instance.title}'
            message_content = f'您被抄送了一个流程：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'reject':
            message_title = f'流程驳回通知 - {instance.title}'
            message_content = f'您的流程申请已被驳回：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'return':
            message_title = f'流程退回通知 - {instance.title}'
            message_content = f'您的流程申请已被退回：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'approved':
            message_title = f'流程通过通知 - {instance.title}'
            message_content = f'您的流程申请已通过审批：{instance.title}，流程编号：{instance.instance_no}'
        else:
            message_title = f'流程通知 - {instance.title}'
            message_content = f'流程状态更新：{instance.title}'
        
        # 创建站内消息
        message = MyMessage.objects.create(
            msg_title=message_title,
            msg_content=message_content,
            msg_chanel=1,  # 系统通知
            public=False,
            status=True
        )
        
        # 创建用户消息关联
        MyMessageUser.objects.create(
            messageid=message,
            revuserid=user,
            is_read=False,
            is_delete=False
        )
    
    def _create_tasks_for_step(self, step_order: int, level_order: int = None):
        """为指定步骤创建审批任务（支持多级审批展开）
        
        Args:
            step_order: 步骤顺序（整数，表示原始步骤顺序）
            level_order: 层级顺序（整数，多级审批时使用，如 2, 3, 4；普通步骤等于 step_order）
        """
        try:
            # 如果未传入 level_order，默认等于 step_order
            if level_order is None:
                level_order = step_order
            
            step = WorkflowStep.objects.get(
                workflow_type=self.workflow_type,
                step_order=step_order
            )
            
            # 如果是多级审批（approver_type=6），需要展开处理
            if step.approver_type == 6 and step.multi_level_config:
                # 计算应该创建哪个层级的任务
                # level_order = step_order + idx（idx从0开始）
                # 所以 idx = level_order - step_order
                base_step_order = step.step_order
                idx = level_order - base_step_order
                
                # 验证 idx 是否在有效范围内
                import json
                config = step.multi_level_config
                if isinstance(config, str):
                    config = json.loads(config)
                
                if idx < 0 or idx >= len(config):
                    logger.error(f'无效的层级索引: idx={idx}, multi_level_config长度={len(config)}, level_order={level_order}')
                    return
                
                # 只创建指定层级的任务
                self._create_single_level_task(step, idx, level_order)
            else:
                # 普通步骤，直接创建任务
                approver_users = self._get_approver_users(step)
                
                # 收集需要通知的用户列表
                users_to_notify = []
                
                for user in approver_users:
                    WorkflowTask.objects.create(
                        instance=self.instance,
                        step=step,
                        step_order=step_order,  # 整数
                        level_order=level_order,  # 整数（普通步骤等于 step_order）
                        approver=user
                    )
                    users_to_notify.append(user)
                
                # 批量发送通知（异步优先，失败则同步）
                self._batch_send_notifications(users_to_notify, 'approve')
                    
        except WorkflowStep.DoesNotExist:
            logger.warning(f'未找到步骤 {step_order}，流程类型: {self.workflow_type.name}')
    
    def _create_single_level_task(self, step: WorkflowStep, idx: int, level_order: int):
        """
        为多级审批的单个层级创建任务
        
        Args:
            step: 多级审批步骤
            idx: 层级索引（从0开始）
            level_order: 层级顺序（整数，如 2, 3, 4）
        """
        if not step.multi_level_config:
            logger.warning(f'多级审批步骤 {step.id} 没有配置层级')
            return
        
        import json
        config = step.multi_level_config
        if isinstance(config, str):
            config = json.loads(config)
        
        # 获取对应层级的配置
        level = config[idx]
        logger.info(f'创建多级审批第{idx+1}级任务: {level.get("name", f"第{idx+1}级")}, level_order={level_order}')
        
        # 根据层级配置获取审批人
        approver_users = self._get_level_approver_users(level, step)
        
        # 收集需要通知的用户列表
        users_to_notify = []
        
        for user in approver_users:
            WorkflowTask.objects.create(
                instance=self.instance,
                step=step,  # 使用原始步骤
                step_order=step.step_order,  # 整数，表示原始步骤顺序
                level_order=level_order,  # 整数，表示层级顺序
                approver=user,
                approve_comment=f'多级审批第{idx+1}级: {level.get("name", f"第{idx+1}级")}'
            )
            users_to_notify.append(user)
        
        # 批量发送通知（异步优先，失败则同步）
        self._batch_send_notifications(users_to_notify, 'approve', f'多级审批第{idx+1}级')
    
    def _create_multi_level_tasks(self, step: WorkflowStep, target_level_order: int):
        """
        为多级审批创建任务
        
        Args:
            step: 多级审批步骤
            target_level_order: 目标层级顺序（整数，如 2, 3, 4）
        """
        if not step.multi_level_config:
            logger.warning(f'多级审批步骤 {step.id} 没有配置层级')
            return
        
        # 从 target_level_order 中提取 idx
        # target_level_order = step.step_order + idx
        # 所以 idx = target_level_order - step.step_order
        base_step_order = step.step_order
        idx = target_level_order - base_step_order
        
        # 验证 idx 是否在有效范围内
        if idx < 0 or idx >= len(step.multi_level_config):
            logger.error(f'无效的层级索引: idx={idx}, multi_level_config长度={len(step.multi_level_config)}')
            return
        
        # 获取对应层级的配置
        level = step.multi_level_config[idx]
        logger.info(f'创建多级审批第{idx+1}级任务: {level.get("name", f"第{idx+1}级")}')
        
        # 根据层级配置获取审批人
        approver_users = self._get_level_approver_users(level, step)
        
        # 收集需要通知的用户列表
        users_to_notify = []
        
        for user in approver_users:
            WorkflowTask.objects.create(
                instance=self.instance,
                step=step,  # 使用原始步骤
                step_order=step.step_order,  # 整数，表示原始步骤顺序
                level_order=target_level_order,  # 整数，直接使用传入的 target_level_order
                approver=user,
                # 可以在 remark 中记录这是哪一级
                approve_comment=f'多级审批第{idx+1}级: {level.get("name", f"第{idx+1}级")}'
            )
            users_to_notify.append(user)
        
        # 批量发送通知（异步优先，失败则同步）
        self._batch_send_notifications(users_to_notify, 'approve', f'多级审批第{idx+1}级')
    
    def _get_level_approver_users(self, level: dict, parent_step: WorkflowStep):
        """
        根据层级配置获取审批人列表
        
        Args:
            level: 层级配置字典
            parent_step: 父步骤（用于继承某些配置）
            
        Returns:
            审批人用户列表
        """
        approver_users = []
        approver_type = level.get('approver_type')
        
        if approver_type == 1:  # 指定角色
            role_id = level.get('approver_role')
            if role_id:
                try:
                    from mysystem.models import DeptRole
                    role = DeptRole.objects.get(id=role_id)
                    approver_users = list(Users.objects.filter(role=role))
                except Exception as e:
                    logger.error(f'获取角色审批人失败: {str(e)}')
        elif approver_type == 2:  # 指定部门
            dept_id = level.get('approver_dept')
            if dept_id:
                try:
                    from mysystem.models import Dept
                    dept = Dept.objects.get(id=dept_id)
                    approver_users = list(Users.objects.filter(dept=dept))
                except Exception as e:
                    logger.error(f'获取部门审批人失败: {str(e)}')
        elif approver_type == 3:  # 部门负责人
            dept_id = level.get('approver_dept')
            if dept_id:
                try:
                    from mysystem.models import Dept
                    dept = Dept.objects.get(id=dept_id)
                    
                    # 使用部门的 owner 字段（存储的是用户名）
                    if dept.owner:
                        # owner 是用户名字符串
                        try:
                            owner_user = Users.objects.get(name=dept.owner)
                            approver_users = [owner_user]
                            logger.info(f'使用部门 owner 作为审批人: {owner_user.name} (ID: {owner_user.id})')
                        except Users.DoesNotExist:
                            logger.warning(f'部门 owner 用户不存在: {dept.owner}')
                            approver_users = []
                    else:
                        # 如果没有设置 owner，查找角色名称包含"负责人"的用户
                        approver_users = list(Users.objects.filter(
                            dept=dept,
                            role__name__icontains='负责人'
                        ))
                        
                        # 如果还是没有找到负责人，使用部门其他人（排除申请人）
                        if not approver_users:
                            approver_users = list(Users.objects.filter(dept=dept))
                            # 排除申请人自己
                            if self.instance.applicant in approver_users:
                                approver_users.remove(self.instance.applicant)
                                logger.info(f'排除申请人 {self.instance.applicant.name} 作为审批人')
                except Exception as e:
                    logger.error(f'获取部门负责人失败: {str(e)}')
        elif approver_type == 4:  # 指定人员
            user_ids = level.get('approver_users', [])
            if user_ids:
                try:
                    approver_users = list(Users.objects.filter(id__in=user_ids))
                except Exception as e:
                    logger.error(f'获取指定人员失败: {str(e)}')
        else:
            logger.warning(f'未知的审批人类型: {approver_type}')
        
        return approver_users
    
    def _get_approver_users(self, step: WorkflowStep):
        """根据步骤配置获取审批人列表"""
        approver_users = []
        
        if step.approver_type == 1:  # 指定角色
            if step.approver_role:
                approver_users = list(Users.objects.filter(role=step.approver_role))
        elif step.approver_type == 2:  # 指定部门
            if step.approver_dept:
                approver_users = list(Users.objects.filter(dept=step.approver_dept))
        elif step.approver_type == 3:  # 部门负责人
            if self.instance.applicant_dept:
                # 优先使用部门的 owner 字段（部门负责人）
                if self.instance.applicant_dept.owner:
                    # owner 是字符串类型的用户ID
                    try:
                        owner_user = Users.objects.get(id=self.instance.applicant_dept.owner)
                        approver_users = [owner_user]
                        logger.info(f'使用部门 owner 作为审批人: {owner_user.name}')
                    except Users.DoesNotExist:
                        logger.warning(f'部门 owner 用户不存在: {self.instance.applicant_dept.owner}')
                        approver_users = []
                else:
                    # 如果没有设置 owner，查找角色名称包含"负责人"的用户
                    approver_users = list(Users.objects.filter(
                        dept=self.instance.applicant_dept,
                        role__name__icontains='负责人'
                    ))
                    
                    # 如果还是没有找到负责人，使用部门其他人（排除申请人）
                    if not approver_users:
                        approver_users = list(Users.objects.filter(dept=self.instance.applicant_dept))
                        # 排除申请人自己
                        if self.instance.applicant in approver_users:
                            approver_users.remove(self.instance.applicant)
                            logger.info(f'排除申请人 {self.instance.applicant.name} 作为审批人')
        elif step.approver_type == 4:  # 指定人员
            approver_users = list(step.approver_users.all())
        elif step.approver_type == 5:  # 申请人自选
            # 从实例的 selected_approvers 字段中获取
            if self.instance.selected_approvers:
                import json
                # 处理 selected_approvers 可能是 JSON 字符串的情况
                selected_approvers = self.instance.selected_approvers
                if isinstance(selected_approvers, str):
                    try:
                        selected_approvers = json.loads(selected_approvers)
                    except:
                        logger.warning(f'解析 selected_approvers 失败: {selected_approvers}')
                        return approver_users
                
                # 确保是字典类型
                if isinstance(selected_approvers, dict):
                    selected_user_ids = selected_approvers.get(str(step.step_order), [])
                    if selected_user_ids:
                        approver_users = list(Users.objects.filter(id__in=selected_user_ids))
                else:
                    logger.warning(f'selected_approvers 不是字典类型: {type(selected_approvers)}')
        elif step.approver_type == 6:  # 多级审批（组合）
            # TODO: 实现多级审批逻辑
            pass
        
        return approver_users
    
    def _notify_cc_users(self):
        """通知抄送人员"""
        cc_configs = WorkflowCC.objects.filter(
            workflow_type=self.workflow_type
        )
        
        for cc_config in cc_configs:
            cc_users = self._get_cc_users(cc_config)
            for user in cc_users:
                WorkflowCCInstance.objects.create(
                    instance=self.instance,
                    cc_user=user,
                    step=None
                )
                
                # 发送通知（异步）
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    send_workflow_notification.delay(user.id, self.instance.id, 'cc')
                except Exception as e:
                    logger.warning(f'发送抄送通知失败: {str(e)}')
    
    def _get_cc_users(self, cc_config: WorkflowCC):
        """根据抄送配置获取抄送人员列表"""
        cc_users = []
        
        if cc_config.cc_type == 1:  # 指定角色
            if cc_config.cc_role:
                cc_users = list(Users.objects.filter(role=cc_config.cc_role))
        elif cc_config.cc_type == 2:  # 指定部门
            if cc_config.cc_dept:
                cc_users = list(Users.objects.filter(dept=cc_config.cc_dept))
        elif cc_config.cc_type == 3:  # 部门负责人
            if self.instance.applicant_dept:
                cc_users = list(Users.objects.filter(
                    dept=self.instance.applicant_dept,
                    role__name__icontains='负责人'
                ))
        elif cc_config.cc_type == 4:  # 指定人员
            cc_users = list(cc_config.cc_users.all())
        
        return cc_users
    
    def _create_log(self, action: str, action_desc: str, remark: str = '', operator: Users = None):
        """创建流程日志"""
        if operator is None:
            operator = self.instance.applicant
            
        WorkflowLog.objects.create(
            instance=self.instance,
            operator=operator,
            action=action,
            action_desc=action_desc,
            remark=remark
        )
    
    def check_timeout_tasks(self):
        """检查超时的任务并自动处理"""
        now = timezone.now()
        
        # 查找超时的待审批任务
        timeout_tasks = WorkflowTask.objects.filter(
            instance=self.instance,
            status=0,
            step__timeout_hours__isnull=False
        )
        
        for task in timeout_tasks:
            step = task.step
            timeout_threshold = task.create_datetime + timedelta(hours=step.timeout_hours)
            
            if now >= timeout_threshold:
                # 任务已超时，执行自动处理
                if step.auto_action == 1:  # 自动通过
                    self.approve_task(task, 1, '超时自动通过')
                elif step.auto_action == 2:  # 自动退回
                    self.approve_task(task, 3, '超时自动退回')
                
                logger.info(f"任务 {task.id} 超时，已自动处理")
    
    def _batch_send_notifications(self, users: list, notification_type: str, level_info: str = ''):
        """
        批量发送通知（完全异步，不阻塞主流程）
        
        Args:
            users: 需要通知的用户列表
            notification_type: 通知类型 ('approve', 'reject', 'return' 等)
            level_info: 层级信息（用于日志）
        """
        if not users:
            return
        
        # 将所有通知任务放入 Celery 队列，完全不阻塞当前响应
        try:
            from apps.lyworkflow.tasks import send_workflow_notification
            
            for user in users:
                # 异步发送通知，立即返回，不等待结果
                send_workflow_notification.delay(user.id, self.instance.id, notification_type)
                logger.info(f'已将{notification_type}通知加入队列：用户 {user.name} ({level_info})')
            
            logger.info(f'共 {len(users)} 个通知任务已加入异步队列')
        except Exception as e:
            # 如果 Celery 不可用，记录警告但不阻塞响应
            logger.warning(f'Celery 队列添加失败（可能是 Celery 服务未启动），通知将在后台重试: {str(e)}')


class FlowBuilder:
    """
    流程构建器
    
    用于以声明式的方式定义流程（未来可扩展）
    """
    
    def __init__(self, workflow_type):
        self.workflow_type = workflow_type
        self.steps = []
    
    def add_step(self, name, order, approver_type, **kwargs):
        """添加步骤"""
        step_data = {
            'step_name': name,
            'step_order': order,
            'approver_type': approver_type,
            **kwargs
        }
        self.steps.append(step_data)
        return self
    
    def build(self):
        """构建流程"""
        # 这里可以实现从声明式定义到数据库记录的转换
        pass
