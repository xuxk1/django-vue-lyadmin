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
        """获取流程列表（根据用户角色过滤）"""
        # 超级管理员查看所有
        if request.user.is_superuser:
            return super().list(request, *args, **kwargs)
        
        # 非超级管理员：查看自己发起的 + 待自己审批的 + 抄送给自己的
        user_id = request.user.id
        
        # 自己发起的流程
        my_apply = WorkflowInstance.objects.filter(applicant_id=user_id)
        
        # 待自己审批的流程
        pending_task_ids = WorkflowTask.objects.filter(
            approver_id=user_id,
            status=0
        ).values_list('instance_id', flat=True)
        pending_instances = WorkflowInstance.objects.filter(id__in=pending_task_ids)
        
        # 抄送给自己的流程
        cc_instance_ids = WorkflowCCInstance.objects.filter(
            cc_user_id=user_id
        ).values_list('instance_id', flat=True)
        cc_instances = WorkflowInstance.objects.filter(id__in=cc_instance_ids)
        
        # 合并查询集
        self.queryset = (my_apply | pending_instances | cc_instances).distinct()
        
        return super().list(request, *args, **kwargs)

    @action(methods=['post'], detail=True)
    def submit(self, request, pk=None):
        """提交流程"""
        instance = self.get_object()
        
        if instance.status != 0:  # 只有草稿状态可以提交
            return ErrorResponse(msg='只有草稿状态的流程可以提交')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以提交流程')
        
        try:
            with transaction.atomic():
                # 更新流程状态
                instance.status = 1  # 审批中
                instance.current_step = 1
                instance.save()
                
                # 创建第一步的审批任务
                self._create_tasks(instance, step_order=1)
                
                # 通知抄送人员
                self._notify_cc_users(instance)
                
                # 记录日志
                self._create_log(instance, request.user, 'submit', '提交流程')
                
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
                instance.save()
                
                # 取消所有待审批任务
                WorkflowTask.objects.filter(instance=instance, status=0).update(status=3)
                
                # 记录日志
                self._create_log(instance, request.user, 'withdraw', '撤回流程')
                
            return SuccessResponse(msg='流程撤回成功')
        except Exception as e:
            logger.error(f'撤回流程失败: {str(e)}')
            return ErrorResponse(msg=f'撤回流程失败: {str(e)}')

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
                instance.save()
                
                # 取消所有待审批任务
                WorkflowTask.objects.filter(instance=instance, status=0).update(status=3)
                
                # 记录日志
                self._create_log(instance, request.user, 'cancel', '取消流程')
                
            return SuccessResponse(msg='流程取消成功')
        except Exception as e:
            logger.error(f'取消流程失败: {str(e)}')
            return ErrorResponse(msg=f'取消流程失败: {str(e)}')

    @action(methods=['get'], detail=False)
    def my_apply(self, request):
        """我发起的流程"""
        self.queryset = WorkflowInstance.objects.filter(applicant=request.user)
        return super().list(request)

    @action(methods=['get'], detail=False)
    def my_approve(self, request):
        """待我审批的流程"""
        pending_task_ids = WorkflowTask.objects.filter(
            approver=request.user,
            status=0
        ).values_list('instance_id', flat=True)
        
        self.queryset = WorkflowInstance.objects.filter(id__in=pending_task_ids)
        return super().list(request)

    @action(methods=['get'], detail=False)
    def my_cc(self, request):
        """抄送给我的流程"""
        cc_instance_ids = WorkflowCCInstance.objects.filter(
            cc_user=request.user
        ).values_list('instance_id', flat=True)
        
        self.queryset = WorkflowInstance.objects.filter(id__in=cc_instance_ids)
        return super().list(request)

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
                
                # 发送通知（异步）
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    send_workflow_notification.delay(user.id, instance.id, 'approve')
                except Exception as e:
                    logger.warning(f'发送审批通知失败: {str(e)}')
                    
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
                
                # 发送通知（异步）
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    send_workflow_notification.delay(user.id, instance.id, 'cc')
                except Exception as e:
                    logger.warning(f'发送抄送通知失败: {str(e)}')

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
        if not request.user.is_superuser:
            self.queryset = self.queryset.filter(approver=request.user)
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
        """处理审批操作"""
        task = self.get_object()
        
        # 验证权限
        if task.approver != request.user:
            return ErrorResponse(msg='您没有权限审批该任务')
        
        if task.status != 0:
            return ErrorResponse(msg='该任务已处理')
        
        serializer = WorkflowApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        approve_comment = serializer.validated_data.get('approve_comment', '')
        
        try:
            with transaction.atomic():
                instance = task.instance
                
                # 更新任务状态
                task.approve_result = approve_result
                task.approve_comment = approve_comment
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
                self._create_log(instance, request.user, action_map[approve_result], desc_map[approve_result], approve_comment)
                
                # 根据审批结果处理流程状态
                if approve_result == 1:  # 通过
                    # 检查是否有下一步
                    next_step_order = task.step_order + 1
                    next_step = WorkflowStep.objects.filter(
                        workflow_type=instance.workflow_type,
                        step_order=next_step_order
                    ).first()
                    
                    if next_step:
                        # 还有下一步，创建新的审批任务
                        instance.current_step = next_step_order
                        instance.save()
                        instance_viewset = WorkflowInstanceViewSet()
                        instance_viewset._create_tasks(instance, next_step_order)
                    else:
                        # 所有步骤完成，流程通过
                        instance.status = 2  # 已通过
                        instance.save()
                elif approve_result == 2:  # 驳回
                    # 流程直接结束
                    instance.status = 3  # 已驳回
                    instance.save()
                    
                    # 取消后续所有待审批任务
                    WorkflowTask.objects.filter(
                        instance=instance,
                        step_order__gt=task.step_order,
                        status=0
                    ).update(status=2)
                elif approve_result == 3:  # 退回
                    # 退回到申请人
                    instance.status = 1  # 保持审批中状态，但退回到申请人修改
                    instance.save()
                
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
