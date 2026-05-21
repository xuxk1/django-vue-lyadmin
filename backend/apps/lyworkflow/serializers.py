from rest_framework import serializers
from utils.serializers import CustomModelSerializer
from apps.lyworkflow.models import (
    WorkflowType, WorkflowStep, WorkflowCC,
    WorkflowInstance, WorkflowTask, WorkflowCCInstance, WorkflowLog
)
from mysystem.models import Users, Role, Dept


class WorkflowTypeSerializer(CustomModelSerializer):
    """流程类型序列化器"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    steps_count = serializers.SerializerMethodField(read_only=True)

    def get_steps_count(self, obj):
        """获取步骤数量"""
        return obj.steps.count()

    class Meta:
        model = WorkflowType
        fields = ['id', 'name', 'code', 'description', 'icon', 'status', 'status_display', 'sort', 'steps_count',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowStepSerializer(CustomModelSerializer):
    """流程步骤序列化器"""
    workflow_type_name = serializers.CharField(source='workflow_type.name', read_only=True)
    approver_type_display = serializers.CharField(source='get_approver_type_display', read_only=True)
    approver_role_name = serializers.CharField(source='approver_role.name', read_only=True)
    approver_dept_name = serializers.CharField(source='approver_dept.name', read_only=True)
    approver_users_info = serializers.SerializerMethodField(read_only=True)

    def get_approver_users_info(self, obj):
        """获取审批人员信息"""
        users = obj.approver_users.all()
        return [{'id': user.id, 'name': user.name} for user in users]

    class Meta:
        model = WorkflowStep
        fields = ['id', 'workflow_type', 'workflow_type_name', 'step_name', 'step_order',
                  'approver_type', 'approver_type_display', 'approver_role', 'approver_role_name',
                  'approver_dept', 'approver_dept_name', 'approver_users', 'approver_users_info',
                  'allow_return', 'allow_reject',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowCCSerializer(CustomModelSerializer):
    """流程抄送配置序列化器"""
    workflow_type_name = serializers.CharField(source='workflow_type.name', read_only=True)
    step_name = serializers.CharField(source='step.step_name', read_only=True)
    cc_type_display = serializers.CharField(source='get_cc_type_display', read_only=True)
    cc_role_name = serializers.CharField(source='cc_role.name', read_only=True)
    cc_dept_name = serializers.CharField(source='cc_dept.name', read_only=True)
    cc_users_info = serializers.SerializerMethodField(read_only=True)

    def get_cc_users_info(self, obj):
        """获取抄送人员信息"""
        users = obj.cc_users.all()
        return [{'id': user.id, 'name': user.name} for user in users]

    class Meta:
        model = WorkflowCC
        fields = ['id', 'workflow_type', 'workflow_type_name', 'step', 'step_name',
                  'cc_type', 'cc_type_display', 'cc_role', 'cc_role_name',
                  'cc_dept', 'cc_dept_name', 'cc_users', 'cc_users_info',
                  'can_approve',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowTaskSerializer(CustomModelSerializer):
    """审批任务序列化器"""
    instance_no = serializers.CharField(source='instance.instance_no', read_only=True)
    instance_title = serializers.CharField(source='instance.title', read_only=True)
    step_name = serializers.CharField(source='step.step_name', read_only=True)
    approver_name = serializers.CharField(source='approver.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approve_result_display = serializers.CharField(source='get_approve_result_display', read_only=True)

    class Meta:
        model = WorkflowTask
        fields = ['id', 'instance', 'instance_no', 'instance_title', 'step', 'step_name',
                  'step_order', 'approver', 'approver_name',
                  'status', 'status_display', 'approve_result', 'approve_result_display',
                  'approve_comment', 'approve_time', 'is_cc',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowLogSerializer(CustomModelSerializer):
    """流程日志序列化器"""
    instance_no = serializers.CharField(source='instance.instance_no', read_only=True)
    operator_name = serializers.CharField(source='operator.name', read_only=True)

    class Meta:
        model = WorkflowLog
        fields = ['id', 'instance', 'instance_no', 'operator', 'operator_name',
                  'action', 'action_desc', 'remark',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowInstanceSerializer(CustomModelSerializer):
    """流程实例序列化器"""
    workflow_type_name = serializers.CharField(source='workflow_type.name', read_only=True)
    applicant_name = serializers.CharField(source='applicant.name', read_only=True)
    applicant_dept_name = serializers.CharField(source='applicant_dept.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    # 当前用户的待审批任务
    my_pending_task = serializers.SerializerMethodField(read_only=True)
    # 流程步骤信息
    steps_info = serializers.SerializerMethodField(read_only=True)
    # 审批历史记录
    approval_history = serializers.SerializerMethodField(read_only=True)

    def get_my_pending_task(self, obj):
        """获取当前用户的待审批任务"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            task = obj.tasks.filter(approver=request.user, status=0).first()
            if task:
                return WorkflowTaskSerializer(task).data
        return None

    def get_steps_info(self, obj):
        """获取流程步骤信息"""
        steps = obj.workflow_type.steps.all()
        return WorkflowStepSerializer(steps, many=True).data

    def get_approval_history(self, obj):
        """获取审批历史"""
        tasks = obj.tasks.exclude(status=0).order_by('step_order', 'approve_time')
        return WorkflowTaskSerializer(tasks, many=True).data

    class Meta:
        model = WorkflowInstance
        fields = ['id', 'instance_no', 'workflow_type', 'workflow_type_name',
                  'title', 'applicant', 'applicant_name', 'applicant_dept', 'applicant_dept_name',
                  'status', 'status_display', 'current_step', 'total_steps',
                  'form_data', 'remark',
                  'my_pending_task', 'steps_info', 'approval_history',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowInstanceCreateSerializer(CustomModelSerializer):
    """流程实例创建序列化器"""
    class Meta:
        model = WorkflowInstance
        fields = ['id', 'workflow_type', 'title', 'form_data', 'remark']
        read_only_fields = ['id']

    def create(self, validated_data):
        """创建流程实例"""
        request = self.context.get('request')
        validated_data['applicant'] = request.user
        validated_data['applicant_dept'] = request.user.dept if hasattr(request.user, 'dept') else None
        
        # 生成流程编号
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        validated_data['instance_no'] = f'WF{timestamp}{validated_data["workflow_type"].code}'
        
        # 计算总步骤数
        validated_data['total_steps'] = validated_data['workflow_type'].steps.count()
        
        return super().create(validated_data)


class WorkflowApproveSerializer(CustomModelSerializer):
    """审批操作序列化器"""
    approve_result = serializers.IntegerField(write_only=True)
    approve_comment = serializers.CharField(write_only=True, allow_blank=True, required=False)

    class Meta:
        model = WorkflowTask
        fields = ['approve_result', 'approve_comment']
