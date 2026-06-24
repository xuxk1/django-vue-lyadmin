import logging
from datetime import datetime
from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.decorators import action
from utils.viewset import CustomModelViewSet
from utils.jsonResponse import SuccessResponse, ErrorResponse
from apps.lyworkflow.models import (
    WorkflowType, WorkflowStep, WorkflowCC,
    WorkflowInstance, WorkflowTask, WorkflowCCInstance, WorkflowLog
)
from apps.lyworkflow.serializers import (
    WorkflowTypeSerializer, WorkflowStepSerializer, WorkflowCCSerializer,
    WorkflowInstanceSerializer, WorkflowInstanceCreateSerializer,
    WorkflowTaskSerializer, WorkflowLogSerializer, WorkflowApproveSerializer
)
from apps.lyworkflow.filters import WorkflowTypeFilter, WorkflowInstanceFilter, WorkflowTaskFilter
from apps.lyworkflow.engine import FlowEngine
from mysystem.models import Users

logger = logging.getLogger(__name__)


class WorkflowTypeViewSet(CustomModelViewSet):
    """流程类型视图集"""
    queryset = WorkflowType.objects.all()
    serializer_class = WorkflowTypeSerializer
    filterset_class = WorkflowTypeFilter
    search_fields = ['name', 'code']
    ordering_fields = ['sort', 'create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []


class WorkflowStepViewSet(CustomModelViewSet):
    """流程步骤视图集"""
    queryset = WorkflowStep.objects.all()
    serializer_class = WorkflowStepSerializer
    search_fields = ['step_name']
    ordering_fields = ['step_order']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取步骤列表（支持按流程类型筛选）"""
        workflow_type_id = request.query_params.get('workflow_type')
        if workflow_type_id:
            self.queryset = self.queryset.filter(workflow_type_id=workflow_type_id)
        return super().list(request, *args, **kwargs)

    @action(methods=['post'], detail=False)
    def batch_update(self, request):
        """批量更新步骤顺序"""
        steps_data = request.data.get('steps', [])
        if not steps_data:
            return ErrorResponse(msg='步骤数据不能为空')

        try:
            with transaction.atomic():
                for step_data in steps_data:
                    step_id = step_data.get('id')
                    step_order = step_data.get('step_order')
                    if step_id and step_order is not None:
                        WorkflowStep.objects.filter(id=step_id).update(step_order=step_order)
            
            return SuccessResponse(msg='批量更新成功')
        except Exception as e:
            logger.error(f'批量更新步骤失败: {str(e)}')
            return ErrorResponse(msg=f'批量更新失败: {str(e)}')


class WorkflowCCViewSet(CustomModelViewSet):
    """流程抄送配置视图集"""
    queryset = WorkflowCC.objects.all()
    serializer_class = WorkflowCCSerializer
    search_fields = ['workflow_type__name']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取抄送配置列表（支持按流程类型筛选）"""
        workflow_type_id = request.query_params.get('workflow_type')
        if workflow_type_id:
            self.queryset = self.queryset.filter(workflow_type_id=workflow_type_id)
        return super().list(request, *args, **kwargs)


class WorkflowInstanceViewSet(CustomModelViewSet):
    """流程实例视图集"""
    queryset = WorkflowInstance.objects.all()
    serializer_class = WorkflowInstanceSerializer
    filterset_class = WorkflowInstanceFilter
    search_fields = ['instance_no', 'title']
    ordering_fields = ['create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def get_serializer_class(self):
        """根据动作返回不同的序列化器"""
        if self.action == 'create':
            return WorkflowInstanceCreateSerializer
        return WorkflowInstanceSerializer

    def list(self, request, *args, **kwargs):
        """获取流程列表（显示用户相关的流程）"""
        # 超级管理员查看所有
        if request.user.is_superuser:
            return super().list(request, *args, **kwargs)
        
        # 非超级管理员：查看自己发起的 + 待自己审批的
        user_id = request.user.id
        
        # 获取查询参数
        show_only_pending = request.query_params.get('show_only_pending', 'false').lower() == 'true'
        
        # 待自己审批的流程ID
        pending_task_ids = set(WorkflowTask.objects.filter(
            approver_id=user_id,
            status=0  # status=0 表示待审批
        ).values_list('instance_id', flat=True))
        
        # 合并查询集
        if show_only_pending:
            # 只显示有待审批任务的流程
            self.queryset = WorkflowInstance.objects.filter(id__in=pending_task_ids).distinct()
        else:
            # 默认显示：自己发起的未完成流程 + 有待审批任务的流程
            from django.db.models import Q
            
            # 条件1：自己发起且未完成（status in [0, 1]）
            # status: 0=草稿, 1=审批中
            condition1 = Q(applicant_id=user_id) & Q(status__in=[0, 1])
            
            # 条件2：有待审批任务（无论是否是自己发起）
            condition2 = Q(id__in=pending_task_ids)
            
            # 合并所有条件
            self.queryset = WorkflowInstance.objects.filter(
                condition1 | condition2
            ).distinct()
        
        return super().list(request, *args, **kwargs)

    @action(methods=['post'], detail=True)
    def submit(self, request, pk=None):
        """提交流程（使用新的流程引擎）"""
        instance = self.get_object()
        
        if instance.status != 0:  # 只有草稿状态可以提交
            return ErrorResponse(msg='只有草稿状态的流程可以提交')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以提交流程')
        
        try:
            # 使用流程引擎启动流程
            engine = FlowEngine(instance)
            engine.start()
            
            return SuccessResponse(msg='流程提交成功')
        except Exception as e:
            logger.error(f'提交流程失败: {str(e)}')
            return ErrorResponse(msg=f'提交流程失败: {str(e)}')

    @action(methods=['post'], detail=True)
    def withdraw(self, request, pk=None):
        """撤回流程"""
        instance = self.get_object()
        
        if instance.status != 1:  # 只有审批中可以撤回
            return ErrorResponse(msg='只有审批中的流程可以撤回')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以撤回流程')
        
        if instance.current_step > 1:
            return ErrorResponse(msg='流程已进入后续审批环节，无法撤回')
        
        try:
            with transaction.atomic():
                # 更新流程状态
                instance.status = 4  # 已撤回
                instance.current_step = instance.total_steps  # 更新当前步骤为总步骤数
                instance.save()
                
                # 取消所有待审批任务
                WorkflowTask.objects.filter(instance=instance, status=0).update(status=3)
                
                # 记录日志
                self._create_log(instance, request.user, 'withdraw', '撤回流程')
                
            return SuccessResponse(msg='流程撤回成功')
        except Exception as e:
            logger.error(f'撤回流程失败: {str(e)}')
            return ErrorResponse(msg=f'撤回流程失败: {str(e)}')

    @action(methods=['put'], detail=True)
    def reinitiate(self, request, pk=None):
        """重新发起流程（支持草稿和已撤回状态）"""
        instance = self.get_object()
        
        # 只有草稿(0)或已撤回(4)状态的流程可以重新发起
        if instance.status not in [0, 4]:
            return ErrorResponse(msg='只有草稿或已撤回状态的流程可以重新发起')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以重新发起流程')
        
        # 保存原始状态，用于出错时恢复
        original_status = instance.status
        original_current_step = instance.current_step
        
        try:
            with transaction.atomic():
                # 处理请求数据（可能是 JSON 字符串或字典）
                import json
                data = request.data
                logger.info(f'重新发起流程 - 原始数据类型: {type(data)}, 内容: {data}')
                
                if isinstance(data, str):
                    data = json.loads(data)
                    logger.info(f'重新发起流程 - 解析后数据类型: {type(data)}, 内容: {data}')
                
                # 验证数据格式
                if not isinstance(data, dict):
                    raise ValueError(f'请求数据格式错误，应为 JSON 对象，实际为: {type(data)}')
                
                # 更新流程数据（只更新允许的字段）
                serializer = WorkflowInstanceCreateSerializer(instance, data=data, partial=True, context={'request': request})
                serializer.is_valid(raise_exception=True)
                logger.info(f'重新发起流程 - 验证通过，准备保存')
                serializer.save()
                logger.info(f'重新发起流程 - 保存成功')
                
                # 重置流程状态为草稿
                instance.status = 0
                instance.current_step = 1
                instance.save()
                logger.info(f'重新发起流程 - 状态重置成功')
                
                # 注意：不删除之前的审批任务，保留历史记录
                # 已完成的审批任务（status != 0）会保留在数据库中作为历史记录
                # 新的流程发起会创建新的审批任务（status = 0）
                
                # 记录日志
                action_type = 'reinitiate' if original_status == 4 else 'submit'
                action_msg = '重新发起流程' if original_status == 4 else '提交流程'
                self._create_log(instance, request.user, action_type, action_msg)
                logger.info(f'重新发起流程 - 完成')
                
            return SuccessResponse(msg='流程发起成功')
        except Exception as e:
            logger.error(f'重新发起流程失败: {str(e)}', exc_info=True)
            # 出错时恢复原始状态
            try:
                instance.status = original_status
                instance.current_step = original_current_step
                instance.save(update_fields=['status', 'current_step'])
                logger.info(f'重新发起流程 - 状态已恢复为: {original_status}')
            except Exception as restore_error:
                logger.error(f'重新发起流程 - 状态恢复失败: {str(restore_error)}')
            return ErrorResponse(msg=f'流程发起失败: {str(e)}')

    @action(methods=['post'], detail=True)
    def cancel(self, request, pk=None):
        """取消流程"""
        instance = self.get_object()
        
        if instance.status not in [0, 1]:  # 只有草稿和审批中可以取消
            return ErrorResponse(msg='只有草稿或审批中的流程可以取消')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以取消流程')
        
        try:
            with transaction.atomic():
                # 更新流程状态
                instance.status = 5  # 已取消
                instance.current_step = instance.total_steps  # 更新当前步骤为总步骤数
                instance.save()
                
                # 取消所有待审批任务
                WorkflowTask.objects.filter(instance=instance, status=0).update(status=3)
                
                # 记录日志
                self._create_log(instance, request.user, 'cancel', '取消流程')
                
            return SuccessResponse(msg='流程取消成功')
        except Exception as e:
            logger.error(f'取消流程失败: {str(e)}')
            return ErrorResponse(msg=f'取消流程失败: {str(e)}')

    @action(methods=['delete'], detail=True)
    def delete_instance(self, request, pk=None):
        """删除流程（仅草稿状态且是申请人）"""
        instance = self.get_object()
        
        if instance.status != 0:  # 只有草稿状态可以删除
            return ErrorResponse(msg='只有草稿状态的流程可以删除')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以删除流程')
        
        try:
            with transaction.atomic():
                # 删除相关的任务
                WorkflowTask.objects.filter(instance=instance).delete()
                
                # 删除相关的抄送记录
                WorkflowCCInstance.objects.filter(instance=instance).delete()
                
                # 删除相关的日志
                WorkflowLog.objects.filter(instance=instance).delete()
                
                # 删除流程实例
                instance.delete()
                
            return SuccessResponse(msg='删除成功')
        except Exception as e:
            logger.error(f'删除流程失败: {str(e)}')
            return ErrorResponse(msg=f'删除流程失败: {str(e)}')
    def _create_tasks(self, instance, step_order):
        """创建审批任务"""
        from mysystem.models import Users
        
        try:
            step = WorkflowStep.objects.get(
                workflow_type=instance.workflow_type,
                step_order=step_order
            )
            
            approver_users = self._get_approver_users(step, instance)
            
            for user in approver_users:
                WorkflowTask.objects.create(
                    instance=instance,
                    step=step,
                    step_order=step_order,
                    approver=user
                )
                
                # 发送通知：优先使用 Celery 异步，失败则同步创建站内消息
                # try:
                #     from apps.lyworkflow.tasks import send_workflow_notification
                #     send_workflow_notification.delay(user.id, instance.id, 'approve')
                #     logger.info(f'已通过 Celery 异步发送审批通知给用户 {user.name}')
                # except Exception as e:
                #     # Celery 不可用时，同步创建站内消息
                #     logger.warning(f'Celery 异步通知失败: {str(e)}，改用同步方式创建站内消息')
                #     try:
                #         self._create_sync_notification(user, instance, 'approve')
                #         logger.info(f'已同步创建站内消息给用户 {user.name}')
                #     except Exception as sync_error:
                #         logger.error(f'同步创建站内消息也失败: {str(sync_error)}')
                    
        except WorkflowStep.DoesNotExist:
            logger.warning(f'未找到步骤 {step_order}，流程类型: {instance.workflow_type.name}')

    def _get_approver_users(self, step, instance):
        """根据步骤配置获取审批人列表"""
        approver_users = []
        
        if step.approver_type == 1:  # 指定角色
            if step.approver_role:
                approver_users = list(Users.objects.filter(role=step.approver_role))
        elif step.approver_type == 2:  # 指定部门
            if step.approver_dept:
                approver_users = list(Users.objects.filter(dept=step.approver_dept))
        elif step.approver_type == 3:  # 部门负责人
            # 查找申请人的部门负责人
            if instance.applicant_dept:
                # 假设部门负责人的角色名称包含"负责人"
                approver_users = list(Users.objects.filter(
                    dept=instance.applicant_dept,
                    role__name__icontains='负责人'
                ))
                # 如果没找到，尝试查找该部门的所有用户
                if not approver_users:
                    approver_users = list(Users.objects.filter(dept=instance.applicant_dept))
        elif step.approver_type == 4:  # 指定人员
            approver_users = list(step.approver_users.all())
        
        return approver_users

    def _notify_cc_users(self, instance):
        """通知抄送人员"""
        cc_configs = WorkflowCC.objects.filter(
            workflow_type=instance.workflow_type
        ).filter(Q(step__isnull=True) | Q(step__isnull=False))
        
        for cc_config in cc_configs:
            cc_users = self._get_cc_users(cc_config, instance)
            for user in cc_users:
                WorkflowCCInstance.objects.create(
                    instance=instance,
                    cc_user=user,
                    step=None
                )
                
                # 发送通知：优先使用 Celery 异步，失败则同步创建站内消息
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    send_workflow_notification.delay(user.id, instance.id, 'cc')
                    logger.info(f'已通过 Celery 异步发送抄送通知给用户 {user.name}')
                except Exception as e:
                    # Celery 不可用时，同步创建站内消息
                    logger.warning(f'Celery 异步通知失败: {str(e)}，改用同步方式创建站内消息')
                    try:
                        self._create_sync_notification(user, instance, 'cc')
                        logger.info(f'已同步创建站内消息给用户 {user.name}')
                    except Exception as sync_error:
                        logger.error(f'同步创建站内消息也失败: {str(sync_error)}')

    def _get_cc_users(self, cc_config, instance):
        """根据抄送配置获取抄送人员列表"""
        cc_users = []
        
        if cc_config.cc_type == 1:  # 指定角色
            if cc_config.cc_role:
                cc_users = list(Users.objects.filter(role=cc_config.cc_role))
        elif cc_config.cc_type == 2:  # 指定部门
            if cc_config.cc_dept:
                cc_users = list(Users.objects.filter(dept=cc_config.cc_dept))
        elif cc_config.cc_type == 3:  # 部门负责人
            if instance.applicant_dept:
                cc_users = list(Users.objects.filter(
                    dept=instance.applicant_dept,
                    role__name__icontains='负责人'
                ))
        elif cc_config.cc_type == 4:  # 指定人员
            cc_users = list(cc_config.cc_users.all())
        
        return cc_users

    def _create_log(self, instance, operator, action, action_desc, remark=''):
        """创建流程日志"""
        WorkflowLog.objects.create(
            instance=instance,
            operator=operator,
            action=action,
            action_desc=action_desc,
            remark=remark
        )

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


class WorkflowTaskViewSet(CustomModelViewSet):
    """审批任务视图集"""
    queryset = WorkflowTask.objects.all()
    serializer_class = WorkflowTaskSerializer
    filterset_class = WorkflowTaskFilter
    search_fields = ['instance__instance_no', 'instance__title']
    ordering_fields = ['step_order', 'create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取任务列表（只返回当前用户的任务）"""
        # 超级管理员查看所有待审批任务
        if request.user.is_superuser:
            # 超级管理员需要按流程实例去重，避免同一个流程显示多次
            from django.db.models import Min
            
            # 获取所有待审批的流程实例ID（去重）
            distinct_instance_ids = WorkflowTask.objects.filter(
                status=0
            ).values_list('instance_id', flat=True).distinct()
            
            # 对于每个流程实例，只取第一个待审批任务
            first_task_ids = WorkflowTask.objects.filter(
                instance_id__in=distinct_instance_ids,
                status=0
            ).values('instance_id').annotate(
                min_id=Min('id')
            ).values_list('min_id', flat=True)
            
            self.queryset = self.queryset.filter(id__in=first_task_ids)
        else:
            # 普通用户只显示分配给自己的任务
            self.queryset = self.queryset.filter(approver=request.user)
        
        # 如果前端传入了 instance 参数，则进一步过滤
        instance_id = request.query_params.get('instance')
        if instance_id:
            self.queryset = self.queryset.filter(instance_id=instance_id)
        
        # 如果前端传入了 status 参数，则进一步过滤
        status = request.query_params.get('status')
        if status is not None:
            self.queryset = self.queryset.filter(status=status)
        
        return super().list(request, *args, **kwargs)

    @action(methods=['post'], detail=True)
    def approve(self, request, pk=None):
        """审批通过"""
        return self._handle_approval(request, pk, approve_result=1)

    @action(methods=['post'], detail=True)
    def reject(self, request, pk=None):
        """驳回流程"""
        return self._handle_approval(request, pk, approve_result=2)

    @action(methods=['post'], detail=True)
    def return_back(self, request, pk=None):
        """退回上一步"""
        return self._handle_approval(request, pk, approve_result=3)

    def _handle_approval(self, request, pk, approve_result):
        """处理审批操作（使用新的流程引擎）"""
        task = self.get_object()
        
        # 验证权限
        if task.approver != request.user and not request.user.is_superuser:
            return ErrorResponse(msg='您没有权限审批该任务')
        
        if task.status != 0:
            return ErrorResponse(msg='该任务已处理')
        
        # 关键安全检查：申请人不能审批自己的流程
        if task.instance.applicant == request.user:
            return ErrorResponse(msg='申请人不能审批自己的流程申请')
        
        serializer = WorkflowApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        approve_comment = serializer.validated_data.get('approve_comment', '').strip()
        
        # 驳回(2)和退回(3)时必须填写审批意见
        if approve_result in [2, 3]:
            if not approve_comment:
                return ErrorResponse(msg='选择驳回或退回时，审批意见为必填项')

        try:
            # 使用流程引擎处理审批
            engine = FlowEngine(task.instance)
            engine.approve_task(
                task=task,
                approve_result=approve_result,
                comment=approve_comment,
                operator=request.user
            )
            
            return SuccessResponse(msg='审批操作成功')
        except Exception as e:
            logger.error(f'审批操作失败: {str(e)}')
            return ErrorResponse(msg=f'审批操作失败: {str(e)}')

    def _create_log(self, instance, operator, action, action_desc, remark=''):
        """创建流程日志"""
        WorkflowLog.objects.create(
            instance=instance,
            operator=operator,
            action=action,
            action_desc=action_desc,
            remark=remark
        )


class WorkflowLogViewSet(CustomModelViewSet):
    """流程日志视图集"""
    queryset = WorkflowLog.objects.all()
    serializer_class = WorkflowLogSerializer
    search_fields = ['instance__instance_no', 'action']
    ordering_fields = ['create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取日志列表（按流程实例筛选）"""
        instance_id = request.query_params.get('instance')
        if instance_id:
            self.queryset = self.queryset.filter(instance_id=instance_id)
        return super().list(request, *args, **kwargs)


class WorkflowDashboardViewSet(CustomModelViewSet):
    """流程监控大屏视图集"""
    queryset = WorkflowInstance.objects.none()
    serializer_class = WorkflowInstanceSerializer
    # 不需要数据权限过滤
    extra_filter_backends = []

    @action(methods=['get'], detail=False)
    def statistics(self, request):
        """获取流程统计数据"""
        from django.db import models
        import logging
        logger = logging.getLogger(__name__)
        
        user = request.user
        
        # 基础统计
        stats = {
            'total': WorkflowInstance.objects.count(),
            'draft': WorkflowInstance.objects.filter(status=0).count(),
            'pending': WorkflowInstance.objects.filter(status=1).count(),
            'approved': WorkflowInstance.objects.filter(status=2).count(),
            'rejected': WorkflowInstance.objects.filter(status=3).count(),
            'withdrawn': WorkflowInstance.objects.filter(status=4).count(),
        }
        
        logger.info(f'流程统计数据: {stats}')
        
        # 用户相关统计
        if not user.is_superuser:
            stats['my_apply'] = WorkflowInstance.objects.filter(applicant=user).count()
            stats['my_pending_tasks'] = WorkflowTask.objects.filter(
                approver=user,
                status=0
            ).count()
        
        # 按流程类型统计
        type_stats = WorkflowInstance.objects.values('workflow_type__name').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        stats['by_type'] = list(type_stats)
        
        # 最近7天的流程趋势
        from datetime import timedelta
        from django.utils import timezone
        
        today = timezone.now().date()
        trends = []
        for i in range(7):
            date = today - timedelta(days=6-i)
            count = WorkflowInstance.objects.filter(
                create_datetime__date=date
            ).count()
            trends.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        
        stats['trends'] = trends
        
        logger.info(f'最终返回数据: total={stats["total"]}, rejected={stats["rejected"]}, by_type={len(stats["by_type"])}, trends={len(stats["trends"])}')
        
        return SuccessResponse(data=stats)
