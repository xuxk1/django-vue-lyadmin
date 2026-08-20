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
    WorkflowCC, WorkflowCCInstance, WorkflowLog,
    ApprovalGroup
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
    
    def _get_applicant_dept(self):
        """获取申请人的实际部门
        
        Returns:
            Dept 对象或 None
        """
        try:
            applicant = self.instance.applicant
            if hasattr(applicant, 'dept') and applicant.dept:
                return applicant.dept
        except Exception as e:
            logger.warning(f'获取申请人部门失败: {str(e)}')
        return None
        
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
                self._create_tasks_for_step(first_step.step_order, first_level_order, _allow_empty=True)
                
                # 验证任务是否创建成功
                task_count = WorkflowTask.objects.filter(
                    instance=self.instance,
                    status=0
                ).count()
                
                if task_count == 0:
                    # 关键修复：当第一个步骤是条件化审批人且触发自动跳过时，允许没有待审批任务
                    # 这种情况是正常的，流程会自动流转到有审批人的步骤
                    logger.warning(f"没有创建任何待审批任务，可能是条件化审批人被自动跳过")
                
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
            # 行锁防并发：或签节点多人同时操作时，仅第一个生效
            task = WorkflowTask.objects.select_for_update().get(pk=task.pk)
            if task.status != 0:
                raise RuntimeError('该任务已处理')
            self.instance = WorkflowInstance.objects.select_for_update().get(pk=self.instance.pk)
            if self.instance.status != 1:
                raise RuntimeError('流程状态已变更，无法执行审批操作')
            
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
                skip_count = other_pending_tasks.update(status=1, approve_result=0, approve_comment='[自动跳过] 或签模式，其他人已通过，自动跳过')
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
        
        # 将同步骤同层级的其他待审批任务标记为已跳过（或签/会签：一人驳回即终止该节点，其他人不可再操作）
        WorkflowTask.objects.filter(
            instance=instance,
            step_order=current_task.step_order,
            level_order=current_task.level_order,
            status=0
        ).exclude(id=current_task.id).update(
            status=1, approve_result=0, approve_comment='[自动跳过] 或签模式，其他审批人已驳回，自动跳过'
        )
        
        # 取消其余所有剩余待审批任务（后续层级、后续步骤）
        WorkflowTask.objects.filter(
            instance=instance,
            status=0
        ).exclude(id=current_task.id).update(status=2)
        
        self._create_log('rejected', '流程已驳回')
        
        # 通知申请人流程已被驳回
        try:
            self._batch_send_notifications([instance.applicant], 'reject', '流程驳回', step=current_task.step)
        except Exception as e:
            logger.warning(f'发送驳回通知失败: {str(e)}')
    
    def _handle_return(self, current_task: WorkflowTask):
        """处理退回操作（退回到申请人，等待修改后重新提交）"""
        instance = self.instance
        
        # 流程置为已退回状态，等待申请人修改后重新提交
        instance.status = 6  # 已退回
        # 注意：不更新 current_step，保持在退回所在节点，便于前端展示退回位置
        instance.save()
        
        # 将同步骤同层级的其他待审批任务标记为已跳过（或签/会签：一人退回即终止该节点，其他人不可再操作）
        WorkflowTask.objects.filter(
            instance=instance,
            step_order=current_task.step_order,
            level_order=current_task.level_order,
            status=0
        ).exclude(id=current_task.id).update(
            status=1, approve_result=0, approve_comment='[自动跳过] 或签模式，其他审批人已退回，自动跳过'
        )
        
        # 取消所有剩余待审批任务（后续层级、后续步骤）
        WorkflowTask.objects.filter(
            instance=instance,
            status=0
        ).exclude(id=current_task.id).update(status=2)
        
        self._create_log('returned', '流程已退回给申请人，等待重新提交')
        
        # 通知申请人流程已被退回
        try:
            self._batch_send_notifications([instance.applicant], 'return', '流程退回', step=current_task.step)
        except Exception as e:
            logger.warning(f'发送退回通知失败: {str(e)}')
    
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
    
    def _create_tasks_for_step(self, step_order: int, level_order: int = None, _skip_stack: set = None, _allow_empty: bool = False):
        """为指定步骤创建审批任务（支持多级审批展开）
        
        Args:
            step_order: 步骤顺序（整数，表示原始步骤顺序）
            level_order: 层级顺序（整数，多级审批时使用，如 2, 3, 4；普通步骤等于 step_order）
            _skip_stack: 内部递归追踪栈（不对外暴露）
            _allow_empty: 是否允许不创建任务（用于启动流程时的第一步检查）
        """
        try:
            # 如果未传入 level_order，默认等于 step_order
            if level_order is None:
                level_order = step_order
            
            step = WorkflowStep.objects.get(
                workflow_type=self.workflow_type,
                step_order=step_order
            )
            
            # 根据节点类型处理不同的逻辑
            if step.node_type == 2:  # 抄送节点
                self._handle_cc_node(step)
            elif step.node_type == 3:  # 条件分支节点
                self._handle_condition_node(step, level_order)
            elif step.node_type == 4:  # 并行网关节点
                self._handle_parallel_gateway(step, level_order)
            elif step.node_type == 5:  # 结束节点
                self._handle_end_node(step)
            else:  # 普通审批节点 (node_type=1) 或默认情况
                self._handle_normal_approval(step, step_order, level_order, _skip_stack=_skip_stack)
                    
        except WorkflowStep.DoesNotExist:
            logger.warning(f'未找到步骤 {step_order}，流程类型: {self.workflow_type.name}')
    
    def _create_skipped_task_record(self, step: WorkflowStep, step_order: int, level_order: int, skip_reason: str):
        """为被自动跳过的步骤创建任务记录（用于审批历史显示）
        
        Args:
            step: 被跳过的步骤
            step_order: 步骤顺序
            level_order: 层级顺序
            skip_reason: 跳过原因
        """
        # 创建任务记录：审批人为申请人，状态为已完成(1)，审批结果为未审批(0)
        # approve_comment 存储跳过原因，前端据此判断并显示"已跳过"
        WorkflowTask.objects.create(
            instance=self.instance,
            step=step,
            step_order=step_order,
            level_order=level_order,
            approver=self.instance.applicant,
            status=1,  # 已完成
            approve_result=0,  # 未审批（跳过）
            approve_comment=f'[自动跳过] {skip_reason}',
            round=self.instance.submit_round or 0
        )
        logger.info(f'已为跳过的步骤 {step.step_name} 创建任务记录，原因: {skip_reason}')
    
    def _handle_normal_approval(self, step: WorkflowStep, step_order: int, level_order: int,
                                 _skip_stack: set = None):
        """处理普通审批节点（包括多级审批和内部条件）"""
        
        # 初始化跳过栈（用于检测无限递归）
        if _skip_stack is None:
            _skip_stack = set()
        
        # 防止无限递归：检查是否已经处理过这个步骤
        skip_key = (step.id, step_order)
        if skip_key in _skip_stack:
            logger.warning(f'检测到无限递归，停止处理步骤 {step.step_name} (order={step_order})，回退到正常流程')
            # 无限递归保护触发时，强制走正常流程
            self._handle_normal_approval_create_tasks(step, step_order, level_order)
            return
        _skip_stack.add(skip_key)
        
        # 检查是否配置了自动跳过审批
        if step.skip_approval_config:
            skip_config = step.skip_approval_config
            if isinstance(skip_config, str):
                import json
                skip_config = json.loads(skip_config)
            
            if skip_config.get('enabled'):
                # 关键优化：在尝试跳过之前，先检查正常流程是否能创建任务
                # 如果正常流程能获取到审批人，就不需要跳过
                normal_approvers = self._get_approver_users(step)
                
                # 关键修复：如果正常流程获取到的审批人只有申请人自己，则触发自动跳过
                # 避免申请人审批自己的流程申请的冲突
                has_non_applicant_approvers = any(approver != self.instance.applicant for approver in normal_approvers)
                
                # 动态条件优先检查：配置了"包扫描状态为PASS"条件且扫描已通过时，
                # 无论审批人是否为申请人都跳过（扫描状态由异步任务回填 form_data，配置驱动，不硬编码节点类型）
                if skip_config.get('skip_conditions', {}).get('scan_status_pass') and self._is_scan_status_pass():
                    should_skip, skip_reason = True, '包扫描状态为PASS'
                    logger.info(f'步骤 {step.step_name} 包扫描状态为PASS，满足动态跳过条件')
                elif normal_approvers and has_non_applicant_approvers:
                    # 正常流程能获取到非申请人的审批人，走正常流程
                    should_skip, skip_reason = False, ''
                    logger.info(f'步骤 {step.step_name} 成功获取到 {len(normal_approvers)} 个审批人，不走自动跳过')
                else:
                    # 正常流程无法获取到审批人，或审批人只有申请人自己，检查是否需要跳过
                    should_skip, skip_reason = self._check_skip_approval(step, skip_config)
                
                if should_skip:
                    logger.info(f'步骤 {step.step_name} 满足自动跳过条件: {skip_reason}')
                    target_step_id = skip_config.get('target_step_id')
                    if target_step_id:
                        try:
                            target_step = WorkflowStep.objects.get(id=target_step_id)
                            # 关键修复：如果跳过的目标步骤就是当前步骤本身或顺序相同，跳过这个目标
                            # 继续往后查找下一个有效步骤
                            if target_step.id == step.id or target_step.step_order == step_order:
                                logger.warning(f'步骤 {step.step_name} 的自动跳过目标是自身，查找下一个有效步骤')
                                # 查找下一个不同于当前步骤的步骤
                                next_effective_step = WorkflowStep.objects.filter(
                                    workflow_type=self.workflow_type,
                                    step_order__gt=step_order
                                ).order_by('step_order').first()
                                
                                if next_effective_step:
                                    logger.info(f'找到下一个有效步骤: {next_effective_step.step_name} (step_order={next_effective_step.step_order})')
                                    # 为被跳过的步骤创建任务记录（用于审批历史显示）
                                    self._create_skipped_task_record(step, step_order, level_order, skip_reason)
                                    # 流转到下一个有效步骤
                                    self._create_tasks_for_step(next_effective_step.step_order, next_effective_step.step_order, _skip_stack=_skip_stack)
                                    self.instance.current_step = next_effective_step.step_order
                                    self.instance.save()
                                    self._create_log('skip_approval', f'自动跳过审批: {step.step_name} -> {next_effective_step.step_name}（{skip_reason}，原目标为自身）')
                                else:
                                    # 没有后续步骤，说明流程已经结束，不创建任务即可
                                    logger.info(f'没有后续步骤可流转，流程可能已结束')
                                    # 仍然创建跳过记录
                                    self._create_skipped_task_record(step, step_order, level_order, skip_reason)
                                return
                            
                            # 为被跳过的步骤创建任务记录（用于审批历史显示）
                            self._create_skipped_task_record(step, step_order, level_order, skip_reason)
                            # 流转到目标步骤
                            self._create_tasks_for_step(target_step.step_order, target_step.step_order, _skip_stack=_skip_stack)
                            self.instance.current_step = target_step.step_order
                            self.instance.save()
                            self._create_log('skip_approval', f'自动跳过审批: {step.step_name} -> {target_step.step_name}（{skip_reason}）')
                            logger.info(f'已自动跳过审批节点 {step.step_name}，直接流转到 {target_step.step_name}')
                        except WorkflowStep.DoesNotExist:
                            logger.error(f'跳过审批的目标步骤不存在: id={target_step_id}')
                            # 目标步骤不存在时，查找下一个有效步骤
                            next_effective_step = WorkflowStep.objects.filter(
                                workflow_type=self.workflow_type,
                                step_order__gt=step_order
                            ).order_by('step_order').first()
                            if next_effective_step:
                                # 为被跳过的步骤创建任务记录
                                self._create_skipped_task_record(step, step_order, level_order, skip_reason)
                                self._create_tasks_for_step(next_effective_step.step_order, next_effective_step.step_order, _skip_stack=_skip_stack)
                                self.instance.current_step = next_effective_step.step_order
                                self.instance.save()
                                self._create_log('skip_approval', f'自动跳过审批: {step.step_name} -> {next_effective_step.step_name}（目标步骤不存在）')
                            return  # ⚠️ 跳过后立即return，不再执行后面的代码
                    else:
                        # 没有配置目标步骤，走正常流程
                        logger.warning(f'步骤 {step.step_name} 没有配置目标步骤，走正常流程')
                        self._handle_normal_approval_create_tasks(step, step_order, level_order)
                    return
                else:
                    logger.warning(f'步骤 {step.step_name} 不满足跳过条件: {skip_reason}，尝试走正常流程')
        
        self._handle_normal_approval_create_tasks(step, step_order, level_order)
    
    def _handle_normal_approval_create_tasks(self, step: WorkflowStep, step_order: int, level_order: int, _skip_stack: set = None):
        """普通审批节点创建审批任务（包括多级审批和内部条件）"""
        approver_users = []
        
        # 首先检查是否是条件化审批人类型（approver_type=8）
        is_condition_based = (step.approver_type == 8)
        
        # 检查是否有内部条件配置
        if is_condition_based or step.internal_conditions:
            logger.info(f"步骤 {step.step_name} 使用条件化审批人{'（approver_type=8）' if is_condition_based else '有内部条件配置'}，开始评估条件")
            approver_users = self._get_approvers_by_internal_conditions(step)
            
            # 关键修复：如果没有匹配的审批人，不要立即跳过，而是尝试从默认逻辑获取审批人
            if not approver_users:
                logger.warning(f'步骤 {step.step_name} 条件化审批人未匹配任何条件组（form_data={self.instance.form_data}），'
                               f'尝试从默认逻辑获取审批人')
                # 优先使用申请人的直接上级（与"直接上级审批"节点语义一致），
                # 避免回退到"部门其他人员"等随机兜底导致审批人错乱（如只通知一人、漏掉节点配置的其他审批人）
                approver_users = self._get_direct_superior()
                if not approver_users:
                    logger.warning(f'步骤 {step.step_name} 未获取到申请人的直接上级，回退到申请人部门负责人')
                    approver_users = self._get_dept_leaders_from_instance()
                logger.warning(f'步骤 {step.step_name} 使用兜底审批人: {[u.name for u in approver_users]}')
        
        # 如果不是条件化审批人，走原有逻辑
        if not is_condition_based and not approver_users:
            if step.approver_type == 6 and step.multi_level_config:
                # 原有的多级审批逻辑
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
                return  # 多级审批任务已在 _create_single_level_task 中创建，直接返回
            else:
                # 普通步骤，直接获取审批人
                approver_users = self._get_approver_users(step)
        
        # 为找到的审批人创建任务（内部条件和普通步骤共用此逻辑）
        if approver_users:
            # 收集需要通知的用户列表
            users_to_notify = []

            # 防重复创建：同一节点同一层级同一轮次已存在待审批任务时（扫描驱动重复执行、
            # 异步任务重复投递等场景），不再重复创建任务与重复发送通知，避免审批人收到多封相同邮件
            task_round = self.instance.submit_round or 0
            if WorkflowTask.objects.filter(
                instance=self.instance, step=step, step_order=step_order,
                level_order=level_order, status=0, round=task_round
            ).exists():
                logger.warning(f'步骤 {step.step_name} 已存在待审批任务，跳过重复创建与通知')
            else:
                for user in approver_users:
                    WorkflowTask.objects.create(
                        instance=self.instance,
                        step=step,
                        step_order=step_order,  # 整数
                        level_order=level_order,  # 整数（普通步骤等于 step_order）
                        approver=user,
                        round=task_round
                    )
                    users_to_notify.append(user)

                logger.info(f'为步骤 {step.step_name} 创建了 {len(users_to_notify)} 个审批任务')

                # 批量发送通知（异步优先，失败则同步）
                self._batch_send_notifications(users_to_notify, 'approve', step=step)
        
        # 处理节点级抄送人（普通审批节点也可以配置抄送人）
        self._handle_step_cc_users(step)
        
        # 处理发起人确认节点的产品线抄送逻辑
        if step.approver_type == 7 and step.product_line_cc_rules:
            self._handle_product_line_cc(step)

    def _is_scan_status_pass(self):
        """判断流程实例的包扫描状态是否为PASS（读取 form_data 固定字段 package_scan_status）

        包扫描状态由异步扫描任务回填到 form_data 的固定 key（config.PACKAGE_SCAN_STATUS_FIELD），
        返回 True 时表示扫描已通过，用于驱动配置了"包扫描状态为PASS"跳过条件的审批节点自动跳过。
        """
        try:
            import json
            import config
            form_data = self.instance.form_data
            if isinstance(form_data, str):
                try:
                    form_data = json.loads(form_data) or {}
                except (TypeError, ValueError):
                    form_data = {}
            status = str((form_data or {}).get(config.PACKAGE_SCAN_STATUS_FIELD, '') or '').strip().upper()
            return status == 'PASS'
        except Exception as e:
            logger.warning(f'读取包扫描状态失败: {str(e)}')
            return False

    def _is_waiting_scan_result(self):
        """判断流程是否处于"等待包扫描结果"状态（发包流程已提交但扫描状态未回填）

        该状态下创建审批任务时不发送邮件/站内信通知，等扫描结果回填后由扫描任务统一驱动：
        - PASS：跳过配置了跳过条件的节点并流转下一节点（下一节点创建任务时自动发送通知）
        - 非PASS：补发当前待办审批人的审批通知
        """
        try:
            import json
            import config
            form_data = self.instance.form_data
            if isinstance(form_data, str):
                try:
                    form_data = json.loads(form_data) or {}
                except (TypeError, ValueError):
                    form_data = {}
            form_data = form_data or {}
            # 未填写软件包名称（非发包流程）→ 不等待，正常发送通知
            if not str(form_data.get(config.PACKAGE_SCAN_PACKAGE_NAME_FIELD) or '').strip():
                return False
            # 扫描状态已回填 → 不等待
            if str(form_data.get(config.PACKAGE_SCAN_STATUS_FIELD) or '').strip():
                return False
            return True
        except Exception as e:
            logger.warning(f'判断等待包扫描状态失败: {str(e)}')
            return False

    def _handle_scan_pass_skip_nodes(self):
        """包扫描状态为PASS时，自动跳过当前待审批的、配置了"包扫描状态为PASS"跳过条件的审批节点并流转到下一节点

        由包安全扫描异步回填任务在扫描状态为PASS时驱动调用：
        - 将配置了 scan_status_pass 跳过条件（skip_approval_config.skip_conditions.scan_status_pass）的节点的待审批任务标记为已跳过
        - 流转到下一节点并为下一节点审批人创建任务（创建任务时自动发送邮件通知）
        - 节点已是最后节点时，流程直接完成

        并发安全：同一实例可能被重复/并发投递的扫描任务重复驱动（如任务重投、重复触发），
        方法内使用行锁 + form_data 幂等标记（_scan_skip_driven）保证只有首次驱动生效，
        避免同一节点重复创建审批任务、重复发送通知。

        Returns:
            bool: 是否执行了跳过操作
        """
        instance = self.instance
        # 仅审批中的流程可驱动跳过（已通过/驳回/退回的流程不处理）
        if instance.status != 1:
            return False
        try:
            import json
            with transaction.atomic():
                # 行锁防并发：多个重复投递的扫描任务同时驱动时，只有拿到锁的第一个执行者完成跳过
                locked = WorkflowInstance.objects.select_for_update().get(pk=instance.pk)
                self.instance = locked
                # form_data 可能存在双重 JSON 编码（字符串中嵌套字符串），循环解码到 dict 保证标记读取可靠
                form_data = locked.form_data
                while isinstance(form_data, str):
                    try:
                        form_data = json.loads(form_data)
                    except (TypeError, ValueError):
                        form_data = {}
                        break
                if not isinstance(form_data, dict):
                    form_data = {}
                # 已驱动过（首次回填后完成跳过/补发）→ 忽略重复驱动，避免重复创建任务与通知
                if (form_data or {}).get('_scan_skip_driven'):
                    logger.info(f'流程 {locked.instance_no} 已完成包扫描PASS驱动，忽略重复驱动')
                    return False

                # 查找当前待审批任务（或签/会签可能多人）
                pending_tasks = WorkflowTask.objects.filter(
                    instance=locked,
                    status=0
                ).select_related('step').distinct()
                if not pending_tasks.exists():
                    return False

                # 筛选出配置了"包扫描状态为PASS"跳过条件的步骤（配置驱动，不硬编码节点类型）
                # 注意：WorkflowTask.Meta.ordering 会把排序字段带入 SELECT 导致 DISTINCT 失效
                # （SQL 变为 SELECT DISTINCT step_id, step_order, create_datetime），必须先用 order_by()
                # 清空排序再去重，并对结果再 set 去重兜底，否则同一 step_id 重复会循环两次
                skip_step_ids = []
                for step_id in set(pending_tasks.order_by().values_list('step_id', flat=True).distinct()):
                    step = WorkflowStep.objects.get(id=step_id)
                    skip_config = step.skip_approval_config
                    if isinstance(skip_config, str):
                        try:
                            skip_config = json.loads(skip_config)
                        except Exception:
                            skip_config = None
                    if skip_config and skip_config.get('enabled') and (skip_config.get('skip_conditions') or {}).get('scan_status_pass'):
                        skip_step_ids.append(step_id)

                if not skip_step_ids:
                    return False

                for step_id in skip_step_ids:
                    step = WorkflowStep.objects.get(id=step_id)
                    # 1. 将该步骤的待审批任务标记为已跳过
                    skip_count = pending_tasks.filter(step_id=step_id).update(
                        status=1, approve_result=0,
                        approve_comment='[自动跳过] 包扫描状态为PASS，自动跳过审批'
                    )

                    # 该节点已无待审批任务（可能已被并发/重复驱动的扫描任务处理过）→
                    # 不再流转、不再创建下一节点任务，避免重复创建审批任务与重复发送通知
                    if skip_count <= 0:
                        continue

                    logger.info(f'包扫描PASS：已跳过节点 {step.step_name} 的 {skip_count} 个待审批任务')

                    # 2. 流转到下一节点（创建任务时自动给下一节点审批人发送邮件通知）
                    next_step = self._get_next_step(step.step_order)
                    if next_step:
                        logger.info(f'包扫描PASS：节点 {step.step_name} 已跳过，流转到 {next_step.step_name}')
                        locked.current_step = next_step.step_order
                        locked.save(update_fields=['current_step'])
                        self._create_tasks_for_step(next_step.step_order, next_step.step_order)
                        self._create_log('skip_approval', f'自动跳过审批: {step.step_name} -> {next_step.step_name}（包扫描状态为PASS）')
                    else:
                        # 节点已是最后节点：流程直接完成
                        logger.info(f'包扫描PASS：节点 {step.step_name} 是最后节点，流程直接完成')
                        locked.status = 2
                        locked.current_step = step.step_order
                        locked.save(update_fields=['status', 'current_step'])
                        self._create_log('complete', '流程已完成（包扫描PASS自动跳过审批）')
                        try:
                            self._batch_send_notifications([locked.applicant], 'approved', '流程通过', step=step)
                        except Exception as e:
                            logger.warning(f'发送流程通过通知失败: {str(e)}')

                # 3. 打幂等标记：本次驱动完成，后续重复驱动（重复投递/重复触发的扫描任务）直接忽略
                form_data = form_data or {}
                form_data['_scan_skip_driven'] = True
                locked.form_data = form_data
                locked.save(update_fields=['form_data'])
                return True
        except Exception as e:
            logger.error(f'包扫描PASS跳过审批节点失败: {str(e)}', exc_info=True)
            return False

    def _resume_notifications_after_scan(self):
        """包扫描结果非PASS时，补发流程创建时因等待扫描结果而延后的审批通知

        由包安全扫描异步回填任务在扫描状态非PASS时驱动调用：给当前所有待审批任务的审批人
        补发审批邮件/站内信（PASS 时由 _handle_scan_pass_skip_nodes 跳过节点，
        下一节点任务创建时自动发送通知，无需补发）。

        并发安全：与 _handle_scan_pass_skip_nodes 共用行锁 + form_data 幂等标记
        （_scan_skip_driven），重复投递的扫描任务只补发一次，避免重复通知。

        Returns:
            bool: 是否补发了通知
        """
        if self._is_waiting_scan_result():
            logger.warning(f'流程 {self.instance.instance_no} 仍处于等待包扫描状态，跳过通知补发')
            return False
        try:
            import json
            with transaction.atomic():
                # 行锁防并发：与跳过驱动共用同一把锁，后续重复驱动的扫描任务串行等待
                locked = WorkflowInstance.objects.select_for_update().get(pk=self.instance.pk)
                self.instance = locked
                # form_data 可能存在双重 JSON 编码（字符串中嵌套字符串），循环解码到 dict 保证标记读取可靠
                form_data = locked.form_data
                while isinstance(form_data, str):
                    try:
                        form_data = json.loads(form_data)
                    except (TypeError, ValueError):
                        form_data = {}
                        break
                if not isinstance(form_data, dict):
                    form_data = {}
                # 已驱动过（跳过或补发）→ 忽略重复驱动，避免重复补发通知
                if (form_data or {}).get('_scan_skip_driven'):
                    logger.info(f'流程 {locked.instance_no} 已驱动过扫描结果通知，忽略重复补发')
                    return False
                pending_tasks = WorkflowTask.objects.filter(
                    instance=locked, status=0
                ).select_related('step').order_by().distinct()
                if not pending_tasks.exists():
                    return False
                users = []
                step = None
                for task in pending_tasks:
                    step = task.step
                    if task.approver not in users:
                        users.append(task.approver)
                if users:
                    self._batch_send_notifications(users, 'approve', step=step)
                    logger.info(f'流程 {locked.instance_no} 包扫描结果非PASS，已补发 {len(users)} 个审批人的通知')
                # 打幂等标记：后续重复驱动不再补发（与跳过驱动共用同一标记）
                form_data = form_data or {}
                form_data['_scan_skip_driven'] = True
                locked.form_data = form_data
                locked.save(update_fields=['form_data'])
                return True
        except Exception as e:
            logger.error(f'补发审批通知失败: {str(e)}', exc_info=True)
            return False

    def _handle_cc_node(self, step: WorkflowStep):
        """处理抄送节点：自动通知指定人员，不阻塞流程"""
        logger.info(f'处理抄送节点: {step.step_name}')
        
        # 获取抄送人员
        cc_users = self._get_cc_users_from_step(step)
        
        if not cc_users:
            logger.warning(f'抄送节点 {step.step_name} 没有配置抄送人员')
            # 即使没有抄送人员，也继续流转到下一步骤
            self._auto_flow_to_next_step(step)
            return
        
        # 为每个抄送人员创建抄送记录
        for user in cc_users:
            WorkflowCCInstance.objects.create(
                instance=self.instance,
                cc_user=user,
                step=step
            )
            logger.info(f'已创建抄送记录: {user.name} -> {step.step_name}')
        
        # 发送抄送通知
        self._batch_send_notifications(cc_users, 'cc', f'抄送节点: {step.step_name}', step=step)
        
        # 抄送节点不需要等待，自动流转到下一步骤
        self._auto_flow_to_next_step(step)
    
    def _handle_step_cc_users(self, step: WorkflowStep):
        """处理节点级抄送人（普通审批节点配置的抄送人）"""
        if not step.cc_type:
            return
        
        logger.info(f'处理节点 {step.step_name} 的抄送人配置')
        cc_users = self._get_step_cc_users(step)
        
        if not cc_users:
            logger.warning(f'节点 {step.step_name} 的抄送人配置未获取到人员')
            return
        
        for user in cc_users:
            WorkflowCCInstance.objects.create(
                instance=self.instance,
                cc_user=user,
                step=step
            )
            logger.info(f'已创建节点抄送记录: {user.name} -> {step.step_name}')
        
        self._batch_send_notifications(cc_users, 'cc', f'节点抄送: {step.step_name}', step=step)
    
    def _get_step_cc_users(self, step: WorkflowStep):
        """从步骤配置中获取节点级抄送人员列表"""
        cc_users = []
        cc_type = step.cc_type
        
        if cc_type == 1:  # 指定角色
            if step.cc_role:
                try:
                    from mysystem.models import DeptRole
                    role = DeptRole.objects.get(id=step.cc_role.id if hasattr(step.cc_role, 'id') else step.cc_role)
                    cc_users = list(Users.objects.filter(role=role))
                except Exception as e:
                    logger.error(f'获取节点抄送角色人员失败: {str(e)}')
        elif cc_type == 2:  # 指定部门
            dept_ids = step.cc_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    cc_users = list(Users.objects.filter(dept__in=depts).distinct())
                except Exception as e:
                    logger.error(f'获取节点抄送部门人员失败: {str(e)}')
        elif cc_type == 3:  # 部门负责人
            applicant_dept = self._get_applicant_dept()
            if applicant_dept:
                cc_users = list(Users.objects.filter(
                    dept=applicant_dept,
                    role__name__icontains='负责人'
                ))
        elif cc_type == 4:  # 指定人员
            cc_users = list(step.cc_users.all())
        elif cc_type == 5:  # 发起人（流程申请人）
            cc_users = [self.instance.applicant]
        elif cc_type == 6:  # 自定义审批组（按审批组动态获取成员）
            cc_users = self._get_approval_group_members(step.cc_group_id)
        
        return cc_users
    
    def _handle_product_line_cc(self, step: WorkflowStep):
        """处理发起人确认节点的产品线抄送逻辑
        
        当发起人确认节点(approver_type=7)配置了product_line_cc_rules时，
        根据已完成的产品线节点确定抄送人。
        """
        if not step.product_line_cc_rules:
            return
        
        logger.info(f'处理发起人确认节点 {step.step_name} 的产品线抄送逻辑')
        
        # 查找已完成的产品线节点
        product_line = self._get_completed_product_line(step)
        if not product_line:
            logger.warning(f'未找到已完成的产品线节点，跳过产品线抄送')
            return
        
        logger.info(f'已完成的产品线: {product_line}')
        
        # 根据产品线匹配抄送规则
        cc_rule = self._match_product_line_cc_rule(step.product_line_cc_rules, product_line)
        if not cc_rule:
            logger.warning(f'未找到产品线 {product_line} 的抄送规则')
            return
        
        # 获取抄送人员
        cc_users = self._get_cc_users_from_product_line_rule(cc_rule)
        if not cc_users:
            logger.warning(f'产品线 {product_line} 的抄送规则未获取到人员')
            return
        
        # 创建抄送记录并发送通知
        for user in cc_users:
            WorkflowCCInstance.objects.create(
                instance=self.instance,
                cc_user=user,
                step=step
            )
            logger.info(f'已创建产品线抄送记录: {user.name} -> {step.step_name} (产品线: {product_line})')
        
        self._batch_send_notifications(cc_users, 'cc', f'产品线抄送({product_line}): {step.step_name}', step=step)
    
    def _get_completed_product_line(self, current_step: WorkflowStep):
        """从已完成的任务中查找产品线节点
        
        查找当前步骤之前已完成（status=1）的、配置了product_line的节点
        """
        # 获取当前步骤之前已完成的任务
        completed_tasks = WorkflowTask.objects.filter(
            instance=self.instance,
            status=1,  # 已通过
            step_order__lt=current_step.step_order
        ).select_related('step')
        
        # 查找配置了product_line的已完成步骤
        for task in completed_tasks:
            if task.step.product_line:
                logger.info(f'找到已完成的产品线节点: {task.step.step_name}, product_line={task.step.product_line}')
                return task.step.product_line
        
        return None
    
    def _match_product_line_cc_rule(self, cc_rules, product_line):
        """根据产品线匹配抄送规则
        
        Args:
            cc_rules: 产品线抄送规则列表
            product_line: 产品线标识
            
        Returns:
            匹配的抄送规则字典，未匹配返回None
        """
        import json
        if isinstance(cc_rules, str):
            try:
                cc_rules = json.loads(cc_rules)
            except:
                logger.error(f'解析product_line_cc_rules失败: {cc_rules}')
                return None
        
        if not isinstance(cc_rules, list):
            return None
        
        for rule in cc_rules:
            if rule.get('product_line') == product_line:
                return rule
        
        return None
    
    def _get_cc_users_from_product_line_rule(self, rule):
        """从产品线抄送规则中获取抄送人员
        
        Args:
            rule: 抄送规则字典，包含cc_type, cc_role, cc_dept, cc_users等字段
            
        Returns:
            抄送人员列表
        """
        cc_users = []
        cc_type = rule.get('cc_type')
        
        if cc_type == 1:  # 指定角色
            role_id = rule.get('cc_role')
            if role_id:
                try:
                    from mysystem.models import DeptRole
                    role = DeptRole.objects.get(id=role_id)
                    cc_users = list(Users.objects.filter(role=role))
                except Exception as e:
                    logger.error(f'获取产品线抄送角色人员失败: {str(e)}')
        elif cc_type == 2:  # 指定部门
            dept_ids = rule.get('cc_dept')
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    cc_users = list(Users.objects.filter(dept__in=depts).distinct())
                except Exception as e:
                    logger.error(f'获取产品线抄送部门人员失败: {str(e)}')
        elif cc_type == 3:  # 部门负责人
            applicant_dept = self._get_applicant_dept()
            if applicant_dept:
                cc_users = list(Users.objects.filter(
                    dept=applicant_dept,
                    role__name__icontains='负责人'
                ))
        elif cc_type == 4:  # 指定人员
            user_ids = rule.get('cc_users', [])
            if user_ids:
                try:
                    cc_users = list(Users.objects.filter(id__in=user_ids))
                except Exception as e:
                    logger.error(f'获取产品线抄送指定人员失败: {str(e)}')
        elif cc_type == 5:  # 发起人（流程申请人）
            cc_users = [self.instance.applicant]
        elif cc_type == 6:  # 自定义审批组（按审批组动态获取成员）
            cc_users = self._get_approval_group_members(rule.get('cc_group'))
        
        return cc_users
    
    def _get_cc_users_from_step(self, step: WorkflowStep):
        """从步骤配置中获取抄送人员列表"""
        cc_users = []
        
        # 使用 condition_rules 存储抄送节点的配置
        if not step.condition_rules:
            logger.warning(f'抄送节点 {step.step_name} 没有配置 condition_rules')
            return cc_users
        
        import json
        config = step.condition_rules
        if isinstance(config, str):
            config = json.loads(config)
        
        cc_type = config.get('cc_type')
        
        if cc_type == 1:  # 指定角色
            role_id = config.get('cc_role')
            if role_id:
                try:
                    from mysystem.models import DeptRole
                    role = DeptRole.objects.get(id=role_id)
                    cc_users = list(Users.objects.filter(role=role))
                except Exception as e:
                    logger.error(f'获取抄送角色人员失败: {str(e)}')
        elif cc_type == 2:  # 指定部门
            dept_id = config.get('cc_dept')
            if dept_id:
                try:
                    from mysystem.models import Dept
                    dept = Dept.objects.get(id=dept_id)
                    cc_users = list(Users.objects.filter(dept=dept))
                except Exception as e:
                    logger.error(f'获取抄送部门人员失败: {str(e)}')
        elif cc_type == 3:  # 部门负责人
            if self.instance.applicant_dept:
                cc_users = list(Users.objects.filter(
                    dept=self.instance.applicant_dept,
                    role__name__icontains='负责人'
                ))
        elif cc_type == 4:  # 指定人员
            user_ids = config.get('cc_users', [])
            if user_ids:
                try:
                    cc_users = list(Users.objects.filter(id__in=user_ids))
                except Exception as e:
                    logger.error(f'获取抄送指定人员失败: {str(e)}')
        elif cc_type == 5:  # 发起人（流程申请人）
            cc_users = [self.instance.applicant]
        elif cc_type == 6:  # 自定义审批组（按审批组动态获取成员）
            cc_users = self._get_approval_group_members(config.get('cc_group'))
        
        return cc_users
    
    def _handle_condition_node(self, step: WorkflowStep, level_order: int):
        """处理条件分支节点：根据表单数据判断流向"""
        logger.info(f'处理条件分支节点: {step.step_name}')
        
        if not step.condition_rules:
            logger.warning(f'条件分支节点 {step.step_name} 没有配置 condition_rules')
            # 如果没有配置条件，默认流转到 next_step_on_pass
            if step.next_step_on_pass:
                self._create_tasks_for_step(step.next_step_on_pass.step_order, step.next_step_on_pass.step_order)
            else:
                # 尝试按顺序查找下一步骤
                next_step = self._get_next_step(step.step_order)
                if next_step:
                    self._create_tasks_for_step(next_step.step_order, next_step.step_order)
            return
        
        import json
        conditions = step.condition_rules
        if isinstance(conditions, str):
            conditions = json.loads(conditions)
        
        # 获取表单数据
        form_data = self.instance.form_data or {}
        if isinstance(form_data, str):
            form_data = json.loads(form_data)
        
        # 评估条件，确定流向
        matched_branch = self._evaluate_conditions(conditions, form_data)
        
        if matched_branch:
            target_step_order = matched_branch.get('target_step')
            if target_step_order:
                logger.info(f'条件匹配成功，流转到步骤: {target_step_order}')
                self._create_tasks_for_step(target_step_order, target_step_order)
                return
        
        # 如果没有匹配的条件，使用默认分支（next_step_on_pass）
        if step.next_step_on_pass:
            logger.info(f'无匹配条件，使用默认分支: {step.next_step_on_pass.step_name}')
            self._create_tasks_for_step(step.next_step_on_pass.step_order, step.next_step_on_pass.step_order)
        else:
            logger.warning(f'条件分支节点 {step.step_name} 没有默认分支配置')
    
    def _evaluate_conditions(self, conditions: list, form_data: dict):
        """评估条件列表，返回匹配的分支"""
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            target_step = condition.get('target_step')
            
            if not field or not operator:
                continue
            
            # 获取表单字段值
            field_value = form_data.get(field)
            
            # 根据操作符进行比较
            if self._compare_values(field_value, operator, value):
                return {'target_step': target_step}
        
        return None
    
    def _compare_values(self, field_value, operator: str, compare_value):
        """比较两个值（字符串比较不区分大小写）"""
        if field_value is None:
            return False
        
        try:
            if operator == '==':
                # 字符串比较不区分大小写
                return str(field_value).lower() == str(compare_value).lower()
            elif operator == '!=':
                # 字符串比较不区分大小写
                return str(field_value).lower() != str(compare_value).lower()
            elif operator == '>':
                return float(field_value) > float(compare_value)
            elif operator == '<':
                return float(field_value) < float(compare_value)
            elif operator == '>=':
                return float(field_value) >= float(compare_value)
            elif operator == '<=':
                return float(field_value) <= float(compare_value)
            elif operator == 'contains':
                # 包含比较不区分大小写
                return str(compare_value).lower() in str(field_value).lower()
            elif operator == 'not_contains':
                # 不包含比较不区分大小写
                return str(compare_value).lower() not in str(field_value).lower()
            elif operator == 'in':
                return field_value in compare_value
            elif operator == 'not_in':
                return field_value not in compare_value
        except (ValueError, TypeError) as e:
            logger.warning(f'条件比较失败: {str(e)}')
            return False
        
        return False
    
    def _get_approvers_by_internal_conditions(self, step: WorkflowStep):
        """根据内部条件获取审批人
        
        Args:
            step: 工作流步骤
            
        Returns:
            匹配的审批人列表，如果没有匹配则返回空列表
        """
        import json
        
        conditions = step.internal_conditions
        if isinstance(conditions, str):
            conditions = json.loads(conditions)
        
        # 获取表单数据
        form_data = self.instance.form_data or {}
        if isinstance(form_data, str):
            form_data = json.loads(form_data)
        
        logger.info(f'评估内部条件，表单数据: {form_data}')
        
        # 遍历条件组，找到第一个匹配的条件
        for group in conditions:
            if self._check_condition_group(group, form_data):
                logger.info(f'条件组匹配成功: {group.get("condition_group", "未命名")}')
                # 匹配成功，返回该组的审批人配置
                approvers_config = group.get('approvers_config', {})
                return self._get_approvers_from_config(approvers_config)
        
        # 没有匹配的条件，返回空列表
        logger.info('没有匹配的条件组')
        return []
    
    def _check_condition_group(self, group: dict, form_data: dict):
        """检查条件组是否满足
        
        Args:
            group: 条件组配置
            form_data: 表单数据
            
        Returns:
            bool: 条件组是否满足
        """
        conditions = group.get('conditions', [])
        relation = group.get('condition_relation', 'and')  # and/or
        
        if not conditions:
            return True  # 没有条件，默认匹配
        
        results = []
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
            
            if not field or not operator:
                continue
            
            # 从表单数据中获取字段值
            field_value = form_data.get(field)
            
            # 比较
            result = self._compare_values(field_value, operator, value)
            results.append(result)
        
        # 根据关系判断
        if relation == 'or':
            return any(results)
        else:  # and
            return all(results)
    
    def _get_approvers_from_config(self, config):
        """从配置中获取审批人列表
        
        Args:
            config: 审批人配置，可以是单个配置对象或配置对象数组
            
        Returns:
            审批人用户列表
        """
        # 支持数组格式（新）和单个对象格式（旧，向后兼容）
        if isinstance(config, list):
            # 新格式：数组，遍历所有配置并合并审批人
            all_approvers = []
            seen_ids = set()
            for single_config in config:
                approvers = self._get_approvers_from_single_config(single_config)
                for user in approvers:
                    if user.id not in seen_ids:
                        all_approvers.append(user)
                        seen_ids.add(user.id)
            return all_approvers
        elif isinstance(config, dict):
            # 旧格式：单个配置对象，向后兼容
            return self._get_approvers_from_single_config(config)
        
        return []
    
    def _get_dept_with_children_ids(self, dept_ids):
        """获取部门及其所有子部门的ID列表（递归）
        
        Args:
            dept_ids: 部门ID或部门ID列表
            
        Returns:
            包含所有部门及子部门的ID列表
        """
        from mysystem.models import Dept
        if not dept_ids:
            return []
        
        if isinstance(dept_ids, list):
            all_ids = set(dept_ids)
        else:
            all_ids = {dept_ids}
        
        # BFS 递归查找所有子部门
        queue = list(all_ids)
        while queue:
            parent_id = queue.pop(0)
            children = Dept.objects.filter(parent_id=parent_id).values_list('id', flat=True)
            for child_id in children:
                if child_id not in all_ids:
                    all_ids.add(child_id)
                    queue.append(child_id)
        
        return list(all_ids)
    
    def _find_dept_leader_by_hierarchy(self, start_dept=None):
        """从指定部门开始，沿部门层级向上查找负责人
        
        查找优先级：
        1. 部门 owner 字段
        2. 角色名称包含"负责人"的用户
        3. 向上遍历父部门，重复1-2
        
        Args:
            start_dept: 起始部门（默认使用申请人部门）
            
        Returns:
            负责人用户列表（通常只有1人）
        """
        from mysystem.models import Dept
        
        dept = start_dept or self._get_applicant_dept()
        if not dept:
            logger.warning('无法获取起始部门，无法沿层级查找负责人')
            return []
        
        visited_dept_ids = set()
        current_dept = dept
        
        while current_dept and current_dept.id not in visited_dept_ids:
            visited_dept_ids.add(current_dept.id)
            logger.info(f'沿部门层级查找负责人，当前部门: {current_dept.name} (id={current_dept.id})')
            
            # 1. 优先检查部门 owner 字段
            if current_dept.owner:
                try:
                    owner_user = Users.objects.get(name=current_dept.owner)
                    # 确保不是申请人自己
                    if owner_user != self.instance.applicant:
                        logger.info(f'找到部门负责人(owner): {owner_user.name} (部门: {current_dept.name})')
                        return [owner_user]
                except Users.DoesNotExist:
                    logger.warning(f'部门 owner 用户不存在: {current_dept.owner}')
            
            # 2. 查找角色名称包含"负责人"的用户（只取第一个，避免返回多人）
            dept_leaders = list(Users.objects.filter(
                dept=current_dept,
                role__name__icontains='负责人'
            ).exclude(id=self.instance.applicant.id))
            
            if dept_leaders:
                # 关键修复：只返回第一个负责人，避免返回多个团队负责人
                logger.info(f'找到部门负责人(角色): {dept_leaders[0].name} (部门: {current_dept.name})')
                return [dept_leaders[0]]
            
            # 3. 向上遍历到父部门
            if current_dept.parent:
                logger.info(f'当前部门 {current_dept.name} 未找到负责人，继续查找父部门: {current_dept.parent.name}')
                current_dept = current_dept.parent
            else:
                logger.info(f'已到达部门层级顶端 {current_dept.name}，未找到负责人')
                break
        
        return []
    
    def _get_dept_leaders(self, dept):
        """获取部门负责人（仅返回申请人的直接领导）
        
        Args:
            dept: Dept 对象
            
        Returns:
            负责人用户列表（优先返回部门owner，最多返回1人）
        """
        approver_users = []
        # 优先使用部门的 owner 字段（这是最准确的直接领导）
        if dept.owner:
            try:
                owner_user = Users.objects.get(name=dept.owner)
                # 确保不是申请人自己
                if owner_user != self.instance.applicant:
                    approver_users.append(owner_user)
                    logger.info(f'使用部门 owner 作为审批人: {owner_user.name} (部门: {dept.name})')
                    return approver_users  # 找到owner后立即返回，不再查找其他人
            except Users.DoesNotExist:
                logger.warning(f'部门 owner 用户不存在: {dept.owner}')
        
        # 如果没有 owner，查找角色名称包含"负责人"的用户（但只取第一个，避免返回多人）
        if not approver_users:
            dept_leaders = list(Users.objects.filter(
                dept=dept,
                role__name__icontains='负责人'
            ).exclude(id=self.instance.applicant.id))
            
            if dept_leaders:
                # 关键修复：只返回第一个负责人，避免返回多个团队负责人
                approver_users.append(dept_leaders[0])
                logger.info(f'使用部门负责人(角色)作为审批人: {dept_leaders[0].name} (部门: {dept.name})')
                return approver_users
        
        # 如果还是没有找到负责人，使用部门其他人（排除申请人）
        if not approver_users:
            dept_users = list(Users.objects.filter(dept=dept).exclude(id=self.instance.applicant.id))
            if dept_users:
                # 只返回第一个用户作为备选
                approver_users.append(dept_users[0])
                logger.info(f'使用部门其他人员作为审批人: {dept_users[0].name} (部门: {dept.name})')
        
        return approver_users
    
    def _get_approvers_from_single_config(self, config):
        """从单个配置对象中获取审批人列表
        
        Args:
            config: 单个审批人配置对象
            
        Returns:
            审批人用户列表
        """
        approver_type = config.get('approver_type')
        
        if approver_type == 1:  # 指定角色
            role_id = config.get('approver_role')
            if role_id:
                try:
                    from mysystem.models import DeptRole
                    role = DeptRole.objects.get(id=role_id)
                    return list(Users.objects.filter(role=role))
                except Exception as e:
                    logger.error(f'获取角色人员失败: {str(e)}')
                    return []
        elif approver_type == 2:  # 指定部门（支持单个部门ID或多个部门ID数组，未配置时自动使用申请人部门，包含子部门）
            dept_ids = config.get('approver_dept')
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 获取部门及其所有子部门的ID
                    all_dept_ids = self._get_dept_with_children_ids(dept_ids)
                    depts = Dept.objects.filter(id__in=all_dept_ids)
                    # 获取所有选中部门（含子部门）的用户（去重）
                    approver_users = list(Users.objects.filter(dept__in=depts).distinct())
                    logger.info(f'内部条件指定部门审批人（含子部门）: {[u.name for u in approver_users]}')
                    
                    # 回退：如果指定部门中没有找到用户，沿部门层级查找负责人
                    if not approver_users:
                        logger.info(f'内部条件指定部门中未找到用户，尝试沿部门层级查找负责人')
                        approver_users = self._find_dept_leader_by_hierarchy()
                    return approver_users
                except Exception as e:
                    logger.error(f'获取部门人员失败: {str(e)}')
                    return []
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = self._get_applicant_dept()
                if applicant_dept:
                    logger.info(f'未配置指定部门，自动使用申请人部门: {applicant_dept.name}')
                    return list(Users.objects.filter(dept=applicant_dept))
                else:
                    logger.warning('未配置指定部门，且无法获取申请人部门')
                    return []
        elif approver_type == 3:  # 部门负责人（支持单个部门ID或多个部门ID数组，未配置时自动使用申请人部门）
            dept_ids = config.get('approver_dept')
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    # 获取所有选中部门的负责人（去重）
                    approver_users = []
                    for dept in depts:
                        leaders = self._get_dept_leaders(dept)
                        for leader in leaders:
                            if leader not in approver_users:
                                approver_users.append(leader)
                    return approver_users
                except Exception as e:
                    logger.error(f'获取部门负责人失败: {str(e)}')
                    return []
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = self._get_applicant_dept()
                if applicant_dept:
                    logger.info(f'未配置部门负责人，自动使用申请人部门: {applicant_dept.name}')
                    return self._get_dept_leaders(applicant_dept)
                else:
                    logger.warning('未配置部门负责人，且无法获取申请人部门')
                    return []
        elif approver_type == 4:  # 指定人员
            user_ids = config.get('approver_users', [])
            if user_ids:
                try:
                    return list(Users.objects.filter(id__in=user_ids))
                except Exception as e:
                    logger.error(f'获取指定人员失败: {str(e)}')
                    return []
        elif approver_type == 5:  # 申请人自选
            # 从流程实例中获取申请人选择的审批人
            selected_approvers = self.instance.selected_approvers or {}
            if isinstance(selected_approvers, str):
                selected_approvers = json.loads(selected_approvers)
            
            # 使用步骤顺序作为key
            step_order = self.instance.current_step
            user_ids = selected_approvers.get(str(step_order), [])
            if user_ids:
                return list(Users.objects.filter(id__in=user_ids))
        elif approver_type == 7:  # 发起人（流程申请人）
            return [self.instance.applicant]
        elif approver_type == 9:  # 直接上级（申请人的直接领导）
            return self._get_direct_superior()
        elif approver_type == 10:  # 自定义审批组（按审批组动态获取成员）
            return self._get_approval_group_members(config.get('approver_group'))
        elif approver_type == 6:  # 多级审批（组合）
            # 对于内部条件，简化处理：只使用第一级
            multi_level_config = config.get('multi_level_config')
            if multi_level_config:
                if isinstance(multi_level_config, str):
                    multi_level_config = json.loads(multi_level_config)
                
                if multi_level_config and len(multi_level_config) > 0:
                    first_level = multi_level_config[0]
                    return self._get_approvers_from_config(first_level)
        
        return []
    
    def _get_approval_group_members(self, group_id):
        """获取自定义审批组的成员列表
        
        审批组成员可动态增删，每次创建任务时实时读取最新成员。
        
        Args:
            group_id: 审批组ID
            
        Returns:
            审批组成员用户列表
        """
        if not group_id:
            logger.warning('自定义审批组未配置 approver_group')
            return []
        try:
            group = ApprovalGroup.objects.get(id=group_id)
            members = list(group.members.all())
            logger.info(f'自定义审批组 [{group.name}] 成员: {[u.name for u in members]}')
            return members
        except ApprovalGroup.DoesNotExist:
            logger.error(f'审批组不存在: {group_id}')
            return []
        except Exception as e:
            logger.error(f'获取审批组成员失败: {str(e)}')
            return []
    
    def _get_direct_superior(self):
        """获取申请人的直接上级（直接领导）
        
        查找优先级：
        1. 申请人所在部门的 owner 字段（最准确的直接领导）
        2. 申请人所在部门中角色名称包含"负责人"的第一个用户
        3. 沿部门层级向上查找负责人（兜底）
        
        注意：始终排除申请人自身
        
        Returns:
            直接上级用户列表（最多1人），未找到时返回空列表
        """
        applicant = self.instance.applicant
        applicant_dept = self._get_applicant_dept()
        
        if not applicant_dept:
            logger.warning('无法获取申请人部门，无法确定直接上级')
            return []
        
        logger.info(f'查找申请人 {applicant.name} 的直接上级，所在部门: {applicant_dept.name}')
        
        # 1. 优先使用部门 owner 字段
        if applicant_dept.owner:
            try:
                owner_user = Users.objects.get(name=applicant_dept.owner)
                if owner_user.id != applicant.id:
                    logger.info(f'使用部门 owner 作为直接上级: {owner_user.name} (部门: {applicant_dept.name})')
                    return [owner_user]
                else:
                    logger.warning(f'部门 owner 是申请人本人，继续查找其他负责人')
            except Users.DoesNotExist:
                logger.warning(f'部门 owner 用户不存在: {applicant_dept.owner}')
        
        # 2. 查找角色名称包含"负责人"的用户（只取第一个，排除申请人自身）
        dept_leaders = list(Users.objects.filter(
            dept=applicant_dept,
            role__name__icontains='负责人'
        ).exclude(id=applicant.id))
        
        if dept_leaders:
            logger.info(f'使用部门负责人(角色)作为直接上级: {dept_leaders[0].name} (部门: {applicant_dept.name})')
            return [dept_leaders[0]]
        
        # 3. 兜底：从父部门开始沿部门层级向上查找负责人
        logger.info(f'部门 {applicant_dept.name} 未找到直接上级，沿部门层级向上查找')
        if applicant_dept.parent:
            superiors = self._find_dept_leader_by_hierarchy(applicant_dept.parent)
            if superiors:
                logger.info(f'沿部门层级找到直接上级: {superiors[0].name}')
                return superiors
        
        logger.warning(f'未找到申请人 {applicant.name} 的直接上级')
        return []
    
    def _handle_parallel_gateway(self, step: WorkflowStep, level_order: int):
        """处理并行网关节点：同时创建多个分支任务"""
        logger.info(f'处理并行网关节点: {step.step_name}')
        
        if not step.condition_rules:
            logger.warning(f'并行网关节点 {step.step_name} 没有配置 condition_rules')
            return
        
        import json
        config = step.condition_rules
        if isinstance(config, str):
            config = json.loads(config)
        
        # 获取并行分支配置
        parallel_branches = config.get('branches', [])
        
        if not parallel_branches:
            logger.warning(f'并行网关节点 {step.step_name} 没有配置分支')
            return
        
        # 为每个分支创建任务
        for branch in parallel_branches:
            target_step_order = branch.get('target_step')
            if target_step_order:
                logger.info(f'创建并行分支任务: {target_step_order}')
                self._create_tasks_for_step(target_step_order, target_step_order)
        
        # 记录日志
        self._create_log('parallel_gateway', f'并行网关创建了 {len(parallel_branches)} 个分支')
    
    def _handle_end_node(self, step: WorkflowStep):
        """处理结束节点：标记流程完成"""
        logger.info(f'处理结束节点: {step.step_name}')
        
        # 更新流程状态为已完成
        self.instance.status = 2  # 已通过
        # 关键修复：current_step 应该设置为 total_steps，表示所有步骤都已完成
        # 这样前端就不会把结束节点显示为"当前"节点
        self.instance.current_step = self.instance.total_steps
        self.instance.save()
        
        # 记录日志
        self._create_log('end', '流程已结束')
        
        logger.info(f'流程 {self.instance.instance_no} 已通过结束节点完成，current_step={self.instance.current_step}, total_steps={self.instance.total_steps}')
    
    def _auto_flow_to_next_step(self, current_step: WorkflowStep):
        """自动流转到下一步骤（用于抄送节点等不需要审批的节点）"""
        logger.info(f'自动流转到下一步骤: {current_step.step_name}')
        
        # 查找下一步骤
        next_step = self._get_next_step(current_step.step_order)
        
        if next_step:
            logger.info(f'流转到下一步骤: {next_step.step_name} (order={next_step.step_order})')
            self._create_tasks_for_step(next_step.step_order, next_step.step_order)
            self._create_log('auto_flow', f'自动流转至: {next_step.step_name}')
        else:
            # 没有下一步骤，流程完成
            logger.info('没有下一步骤，流程完成')
            self.instance.status = 2  # 已通过
            self.instance.current_step = current_step.step_order
            self.instance.save()
            self._create_log('complete', '流程已完成（自动流转）')
    
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
        
        # 检查层级条件是否满足
        conditions = level.get('conditions', [])
        if conditions and len(conditions) > 0:
            logger.info(f'检查第{idx+1}级条件: {conditions}')
            if not self._check_level_conditions(level, step):
                logger.info(f'第{idx+1}级条件不满足，跳过该层级')
                # 条件不满足，直接流转到下一层级
                next_level_order = level_order + 1
                # 检查是否还有下一层级
                if idx + 1 < len(config):
                    logger.info(f'流转到下一层级: {next_level_order}')
                    self._create_single_level_task(step, idx + 1, next_level_order)
                else:
                    # 所有层级都处理完了，流转到下一个步骤
                    logger.info('所有层级都已处理完毕，流转到下一个步骤')
                    next_step = self._get_next_step(step.step_order)
                    if next_step:
                        self._create_tasks_for_step(next_step.step_order, next_step.step_order)
                return
        
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
                approve_comment=f'多级审批第{idx+1}级: {level.get("name", f"第{idx+1}级")}',
                round=self.instance.submit_round or 0
            )
            users_to_notify.append(user)
        
        # 批量发送通知（异步优先，失败则同步）
        self._batch_send_notifications(users_to_notify, 'approve', f'多级审批第{idx+1}级', step=step)
    
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
                approve_comment=f'多级审批第{idx+1}级: {level.get("name", f"第{idx+1}级")}',
                round=self.instance.submit_round or 0
            )
            users_to_notify.append(user)
        
        # 批量发送通知（异步优先，失败则同步）
        self._batch_send_notifications(users_to_notify, 'approve', f'多级审批第{idx+1}级', step=step)
    
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
        elif approver_type == 2:  # 指定部门（支持单个部门ID或多个部门ID数组，未配置时自动使用申请人部门，包含子部门）
            dept_ids = level.get('approver_dept')
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 获取部门及其所有子部门的ID
                    all_dept_ids = self._get_dept_with_children_ids(dept_ids)
                    depts = Dept.objects.filter(id__in=all_dept_ids)
                    # 获取所有选中部门（含子部门）的用户（去重）
                    approver_users = list(Users.objects.filter(dept__in=depts).distinct())
                    logger.info(f'多级审批指定部门审批人（含子部门）: {[u.name for u in approver_users]}')
                    
                    # 回退：如果指定部门中没有找到用户，沿部门层级查找负责人
                    if not approver_users:
                        logger.info(f'多级审批指定部门中未找到用户，尝试沿部门层级查找负责人')
                        approver_users = self._find_dept_leader_by_hierarchy()
                except Exception as e:
                    logger.error(f'获取部门审批人失败: {str(e)}')
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = self._get_applicant_dept()
                if applicant_dept:
                    logger.info(f'多级审批: 未配置指定部门，自动使用申请人部门: {applicant_dept.name}')
                    approver_users = list(Users.objects.filter(dept=applicant_dept))
                else:
                    logger.warning('多级审批: 未配置指定部门，且无法获取申请人部门')
        elif approver_type == 3:  # 部门负责人（支持单个部门ID或多个部门ID数组，未配置时自动使用申请人部门）
            dept_ids = level.get('approver_dept')
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                            
                    # 获取所有选中部门的负责人（去重）
                    for dept in depts:
                        leaders = self._get_dept_leaders(dept)
                        for leader in leaders:
                            if leader not in approver_users:
                                approver_users.append(leader)
                except Exception as e:
                    logger.error(f'获取部门负责人失败: {str(e)}')
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = self._get_applicant_dept()
                if applicant_dept:
                    logger.info(f'多级审批: 未配置部门负责人，自动使用申请人部门: {applicant_dept.name}')
                    approver_users = self._get_dept_leaders(applicant_dept)
                else:
                    logger.warning('多级审批: 未配置部门负责人，且无法获取申请人部门')
        elif approver_type == 4:  # 指定人员
            user_ids = level.get('approver_users', [])
            if user_ids:
                try:
                    approver_users = list(Users.objects.filter(id__in=user_ids))
                except Exception as e:
                    logger.error(f'获取指定人员失败: {str(e)}')
        elif approver_type == 10:  # 自定义审批组
            approver_users = self._get_approval_group_members(level.get('approver_group'))
        elif approver_type == 7:  # 发起人（流程申请人）
            approver_users = [self.instance.applicant]
        else:
            logger.warning(f'未知的审批人类型: {approver_type}')
            
        return approver_users
        
    def _check_level_conditions(self, level: dict, step: WorkflowStep) -> bool:
        """检查层级条件是否满足
            
        Args:
            level: 层级配置字典，包含 conditions 和 condition_relation
            step: 当前步骤
                
        Returns:
            bool: 条件是否满足
        """
        import json
            
        conditions = level.get('conditions', [])
        if not conditions or len(conditions) == 0:
            return True  # 没有条件，默认满足
            
        relation = level.get('condition_relation', 'and')  # and/or
            
        # 获取表单数据
        form_data = self.instance.form_data or {}
        if isinstance(form_data, str):
            form_data = json.loads(form_data)
            
        logger.info(f'评估层级条件，表单数据: {form_data}')
            
        results = []
        for condition in conditions:
            field = condition.get('field')
            operator = condition.get('operator')
            value = condition.get('value')
                
            if not field or not operator:
                continue
                
            # 从表单数据中获取字段值
            field_value = form_data.get(field)
                
            # 比较
            result = self._compare_values(field_value, operator, value)
            results.append(result)
            logger.info(f'条件 [{field} {operator} {value}] => {result}, 实际值: {field_value}')
            
        # 根据关系判断
        if relation == 'or':
            satisfied = any(results)
        else:  # and
            satisfied = all(results)
            
        logger.info(f'条件关系: {relation}, 结果: {satisfied}')
        return satisfied
    
    def _get_dept_leaders_from_instance(self):
        """从流程实例中获取部门负责人
        
        主要用于条件化审批人没有匹配到条件时的回退逻辑
        
        Returns:
            部门负责人用户列表
        """
        from mysystem.models import Dept
        
        # 获取申请人部门
        applicant_dept = self._get_applicant_dept()
        if not applicant_dept:
            logger.warning('无法获取申请人部门')
            return []
        
        # 获取部门负责人
        leaders = self._get_dept_leaders(applicant_dept)
        logger.info(f'从申请人部门 {applicant_dept.name} 获取到部门负责人: {[u.name for u in leaders]}')
        return leaders
    
    def _check_skip_approval(self, step: WorkflowStep, skip_config: dict):
        """
        检查是否满足自动跳过审批的条件
        
        Args:
            step: 当前步骤
            skip_config: 跳过配置，格式: {enabled, skip_conditions: {is_dept_owner, specified_users, specified_roles}, target_step_id}
        
        Returns:
            (should_skip: bool, reason: str)
        """
        applicant = self.instance.applicant
        skip_conditions = skip_config.get('skip_conditions', {})
        
        if not skip_conditions:
            return False, '未配置跳过条件'
        
        # 条件1：检查发起人是否为部门负责人
        if skip_conditions.get('is_dept_owner'):
            applicant_dept = self._get_applicant_dept()
            if applicant_dept and applicant_dept.owner:
                try:
                    owner_user = Users.objects.get(name=applicant_dept.owner)
                    if owner_user == applicant:
                        return True, f'发起人是部门 {applicant_dept.name} 的负责人'
                except Users.DoesNotExist:
                    pass
        
        # 条件2：检查发起人是否在指定人员列表中
        specified_users = skip_conditions.get('specified_users', [])
        if specified_users and applicant.id in specified_users:
            return True, f'发起人在指定人员列表中'
        
        # 条件3：检查发起人角色是否在指定角色列表中
        specified_roles = skip_conditions.get('specified_roles', [])
        if specified_roles:
            user_role_ids = list(applicant.role.values_list('id', flat=True))
            if any(rid in specified_roles for rid in user_role_ids):
                return True, f'发起人角色在指定角色列表中'
        
        # 说明："包扫描状态为PASS"条件不在此处判断，由 _handle_normal_approval 的动态条件优先分支统一处理
        # （该分支在获取审批人之前先判断，确保扫描PASS时无论审批人是否为申请人都跳过）
        return False, '发起人不满足任何跳过条件'
    
    def _get_approver_users(self, step: WorkflowStep):
        """根据步骤配置获取审批人列表"""
        approver_users = []
        
        if step.approver_type == 1:  # 指定角色
            if step.approver_role:
                approver_users = list(Users.objects.filter(role=step.approver_role))
        elif step.approver_type == 2:  # 指定部门（未配置时自动使用申请人部门，包含子部门）
            dept_ids = step.approver_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 获取部门及其所有子部门的ID
                    all_dept_ids = self._get_dept_with_children_ids(dept_ids)
                    depts = Dept.objects.filter(id__in=all_dept_ids)
                    approver_users = list(Users.objects.filter(dept__in=depts).distinct())
                    logger.info(f'指定部门审批人（含子部门）: {[u.name for u in approver_users]}')
                    
                    # 关键优化：如果指定部门中没有找到用户，沿部门层级查找负责人
                    # 场景1：节点配置了父部门，但申请人在子部门，直属领导可能在部门层级的owner字段中
                    # 场景2：发起人是部门负责人，虽然部门没有普通用户，但可以找部门负责人或其上级部门负责人
                    if not approver_users:
                        logger.info(f'指定部门中未找到用户，尝试沿部门层级查找负责人')
                        approver_users = self._find_dept_leader_by_hierarchy()
                    # 仍然找不到：回退到申请人的部门负责人
                    elif not approver_users and hasattr(self.instance.applicant, 'dept') and self.instance.applicant.dept:
                        logger.info(f'找到部门用户但为空，尝试获取申请人部门负责人')
                        approver_users = self._get_dept_leaders(self.instance.applicant.dept)
                except Exception as e:
                    logger.error(f'获取部门审批人失败: {str(e)}', exc_info=True)
                    # 异常时回退到申请人部门负责人
                    try:
                        if hasattr(self.instance.applicant, 'dept') and self.instance.applicant.dept:
                            approver_users = self._get_dept_leaders(self.instance.applicant.dept)
                    except:
                        pass
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = self._get_applicant_dept()
                if applicant_dept:
                    logger.info(f'未配置指定部门，自动使用申请人部门: {applicant_dept.name}')
                    approver_users = list(Users.objects.filter(dept=applicant_dept))
                    # 如果没有部门用户，获取部门负责人
                    if not approver_users:
                        approver_users = self._get_dept_leaders(applicant_dept)
                else:
                    logger.warning('未配置指定部门，且无法获取申请人部门')
        elif step.approver_type == 3:  # 部门负责人（未配置时自动使用申请人部门）
            dept_ids = step.approver_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    
                    # 获取所有选中部门的负责人（去重）
                    for dept in depts:
                        leaders = self._get_dept_leaders(dept)
                        for leader in leaders:
                            if leader not in approver_users:
                                approver_users.append(leader)
                except Exception as e:
                    logger.error(f'获取部门负责人失败: {str(e)}')
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = self._get_applicant_dept()
                if applicant_dept:
                    logger.info(f'步骤审批: 未配置部门负责人，自动使用申请人部门: {applicant_dept.name}')
                    approver_users = self._get_dept_leaders(applicant_dept)
                else:
                    logger.warning('步骤审批: 未配置部门负责人，且无法获取申请人部门')
        elif step.approver_type == 4:  # 指定人员
            approver_users = list(step.approver_users.all())
        elif step.approver_type == 10:  # 自定义审批组
            approver_users = self._get_approval_group_members(step.approver_group_id)
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
        elif step.approver_type == 7:  # 发起人（流程申请人）
            approver_users = [self.instance.applicant]
        elif step.approver_type == 6:  # 多级审批（组合）
            # TODO: 实现多级审批逻辑
            pass
        elif step.approver_type == 8:  # 条件化审批人
            # 只从条件配置中获取审批人，不使用默认审批人类型
            logger.info(f'步骤 {step.step_name} 使用条件化审批人类型，优先从 internal_conditions 获取审批人')
            # 注意：这里返回空列表，让调用方走 _handle_normal_approval_create_tasks 中的内部条件逻辑
            approver_users = []
        
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
        elif cc_config.cc_type == 5:  # 发起人（流程申请人）
            cc_users = [self.instance.applicant]
        
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
            # 流程已终止（如或签节点已被他人操作）时不再自动处理剩余任务
            if self.instance.status != 1:
                break
            
            step = task.step
            timeout_threshold = task.create_datetime + timedelta(hours=step.timeout_hours)
            
            if now >= timeout_threshold:
                # 任务已超时，执行自动处理
                if step.auto_action == 1:  # 自动通过
                    self.approve_task(task, 1, '超时自动通过')
                elif step.auto_action == 2:  # 自动退回
                    self.approve_task(task, 3, '超时自动退回')
                
                logger.info(f"任务 {task.id} 超时，已自动处理")
    
    def _batch_send_notifications(self, users: list, notification_type: str, level_info: str = '', step: WorkflowStep = None):
        """
        批量发送通知（完全异步，不阻塞主流程）
        
        Args:
            users: 需要通知的用户列表
            notification_type: 通知类型 ('approve', 'reject', 'return' 等)
            level_info: 层级信息（用于日志）
            step: 流程步骤（节点配置），用于读取邮件通知/站内信通知开关
        """
        if not users:
            return

        # 审批人去重兜底：同一用户可能因 M2M 配置/多级展开等原因在列表中出现多次，
        # 若不先去重会对同一用户入队多个通知任务，导致审批人收到重复邮件
        # （站内信有 get_or_create 去重但邮件没有，重复入队会直接造成重复邮件）
        users = list({u.id: u for u in users}.values())
        if not users:
            return

        # 等待包扫描结果的发包流程不发送审批待办通知（approve）：等扫描结果回填后由扫描任务统一驱动
        # （PASS 时跳过节点并流转下一节点，创建任务时自动通知；非 PASS 时补发当前待办审批人）；
        # 抄送通知（cc）不受影响照常发送，避免延后后无补发路径导致通知丢失
        if notification_type == 'approve' and self._is_waiting_scan_result():
            logger.info(f'流程 {self.instance.instance_no} 等待包扫描结果，{notification_type}通知延后发送（{level_info}）')
            return

        # 从节点配置中读取通知开关（默认开启）
        notify_email = bool(getattr(step, 'notify_email', True)) if step else True
        notify_message = bool(getattr(step, 'notify_message', True)) if step else True
        
        if not notify_email and not notify_message:
            logger.info(f'节点未开启任何通知方式，跳过发送{notification_type}通知 ({level_info})')
            return
        
        # 将所有通知任务放入 Celery 队列，完全不阻塞当前响应
        try:
            from apps.lyworkflow.tasks import send_workflow_notification
            
            for user in users:
                # 异步发送通知，立即返回，不等待结果
                send_workflow_notification.delay(
                    user.id, self.instance.id, notification_type,
                    notify_email=notify_email, notify_message=notify_message
                )
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
