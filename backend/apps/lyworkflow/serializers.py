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
                  'form_schema',  # 添加表单配置字段
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowStepSerializer(CustomModelSerializer):
    """流程步骤序列化器（节点配置）"""
    workflow_type_name = serializers.CharField(source='workflow_type.name', read_only=True)
    approver_type_display = serializers.CharField(source='get_approver_type_display', read_only=True)
    approver_role_name = serializers.CharField(source='approver_role.name', read_only=True)
    approver_dept_name = serializers.CharField(source='approver_dept.name', read_only=True)
    approver_users_info = serializers.SerializerMethodField(read_only=True)
    sign_mode_display = serializers.CharField(source='get_sign_mode_display', read_only=True)
    auto_action_display = serializers.CharField(source='get_auto_action_display', read_only=True)
    node_type_display = serializers.CharField(source='get_node_type_display', read_only=True)
    approval_mode_display = serializers.CharField(source='get_approval_mode_display', read_only=True)
    next_step_on_pass_name = serializers.CharField(source='next_step_on_pass.step_name', read_only=True)
    next_step_on_reject_name = serializers.CharField(source='next_step_on_reject.step_name', read_only=True)
    # 新增：审批人显示文本（用于列表展示）
    approvers_display = serializers.SerializerMethodField(read_only=True)

    def get_approver_users_info(self, obj):
        """获取审批人员信息"""
        users = obj.approver_users.all()
        return [{'id': user.id, 'name': user.name} for user in users]

    def get_approvers_display(self, obj):
        """获取审批人显示文本（用于列表展示）"""
        # 如果是多级审批（approver_type=6），解析 multi_level_config
        if obj.approver_type == 6 and obj.multi_level_config:
            levels = []
            for level in obj.multi_level_config:
                level_name = level.get('name', f'第{len(levels)+1}级')
                approver_type = level.get('approver_type')
                
                # 根据审批人类型生成显示文本
                if approver_type == 1:  # 指定角色
                    role_id = level.get('approver_role')
                    if role_id:
                        try:
                            from mysystem.models import DeptRole
                            role = DeptRole.objects.get(id=role_id)
                            levels.append(f"{level_name}: {role.name}")
                        except:
                            levels.append(f"{level_name}: 角色")
                    else:
                        levels.append(f"{level_name}: 未配置")
                elif approver_type == 2:  # 指定部门
                    dept_id = level.get('approver_dept')
                    if dept_id:
                        try:
                            from mysystem.models import Dept
                            dept = Dept.objects.get(id=dept_id)
                            levels.append(f"{level_name}: {dept.name}")
                        except:
                            levels.append(f"{level_name}: 部门")
                    else:
                        levels.append(f"{level_name}: 未配置")
                elif approver_type == 3:  # 部门负责人
                    dept_id = level.get('approver_dept')
                    if dept_id:
                        try:
                            from mysystem.models import Dept
                            dept = Dept.objects.get(id=dept_id)
                            levels.append(f"{level_name}: {dept.name}负责人")
                        except:
                            levels.append(f"{level_name}: 部门负责人")
                    else:
                        levels.append(f"{level_name}: 未配置")
                elif approver_type == 4:  # 指定人员
                    user_ids = level.get('approver_users', [])
                    if user_ids:
                        try:
                            from lyusers.models import Users
                            users = Users.objects.filter(id__in=user_ids).values_list('name', flat=True)
                            levels.append(f"{level_name}: {', '.join(users)}")
                        except:
                            levels.append(f"{level_name}: 人员")
                    else:
                        levels.append(f"{level_name}: 未配置")
                else:
                    levels.append(f"{level_name}: 未配置")
            
            return '; '.join(levels) if levels else '未配置'
        
        # 普通审批逻辑（原有逻辑）
        if obj.approver_type == 1:  # 指定角色
            return f"角色: {obj.approver_role.name}" if obj.approver_role else '未配置'
        elif obj.approver_type == 2:  # 指定部门
            return f"部门: {obj.approver_dept.name}" if obj.approver_dept else '未配置'
        elif obj.approver_type == 3:  # 部门负责人
            return f"{obj.approver_dept.name}负责人" if obj.approver_dept else '未配置'
        elif obj.approver_type == 4:  # 指定人员
            users = obj.approver_users.all()
            if users:
                return ', '.join([user.name for user in users])
            return '未配置'
        elif obj.approver_type == 5:  # 申请人自选
            return '申请人自选'
        else:
            return '未配置'

    class Meta:
        model = WorkflowStep
        fields = ['id', 'workflow_type', 'workflow_type_name', 'step_name', 'step_order',
                  'node_type', 'node_type_display',
                  'approval_mode', 'approval_mode_display',
                  'approver_type', 'approver_type_display', 'approver_role', 'approver_role_name',
                  'approver_dept', 'approver_dept_name', 'approver_users', 'approver_users_info',
                  'sign_mode', 'sign_mode_display',
                  'allow_return', 'allow_reject',
                  'timeout_hours', 'auto_action', 'auto_action_display',
                  'notify_email', 'notify_message', 'notify_sms',
                  'condition_rules',
                  'next_step_on_pass', 'next_step_on_pass_name',
                  'next_step_on_reject', 'next_step_on_reject_name',
                  'description',
                  'multi_level_config',
                  'approvers_display',  # 新增：审批人显示文本
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
    
    # 添加步骤配置信息（用于前端判断是否显示退回/驳回按钮）
    allow_return = serializers.BooleanField(source='step.allow_return', read_only=True)
    allow_reject = serializers.BooleanField(source='step.allow_reject', read_only=True)

    class Meta:
        model = WorkflowTask
        fields = ['id', 'instance', 'instance_no', 'instance_title', 'step', 'step_name',
                  'step_order', 'level_order', 'approver', 'approver_name',
                  'status', 'status_display', 'approve_result', 'approve_result_display',
                  'approve_comment', 'approve_time', 'is_cc',
                  'allow_return', 'allow_reject',
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
        """获取流程步骤信息（支持多级审批展开）"""
        steps = obj.workflow_type.steps.all()
        expanded_steps = []
        
        for step in steps:
            # 如果是多级审批（approver_type=6），需要展开为多个子层级
            if step.approver_type == 6 and step.multi_level_config:
                # 遍历多级配置，创建虚拟的子步骤
                for idx, level in enumerate(step.multi_level_config):
                    # 创建虚拟步骤对象
                    virtual_step = {
                        'id': f"{step.id}_level_{idx}",  # 虚拟ID
                        'workflow_type': step.workflow_type.id,
                        'workflow_type_name': step.workflow_type.name,
                        'step_name': level.get('name', f'{step.step_name}-第{idx+1}级'),
                        'step_order': step.step_order,  # 整数，表示原始步骤顺序
                        'level_order': step.step_order + (idx * 0.1),  # 浮点数，表示层级顺序
                        'node_type': step.node_type,
                        'node_type_display': step.get_node_type_display(),
                        'approval_mode': step.approval_mode,
                        'approval_mode_display': step.get_approval_mode_display(),
                        'approver_type': level.get('approver_type'),
                        'approver_type_display': self._get_approver_type_display(level.get('approver_type')),
                        'approver_role': level.get('approver_role'),
                        'approver_role_name': self._get_role_name(level.get('approver_role')),
                        'approver_dept': level.get('approver_dept'),
                        'approver_dept_name': self._get_dept_name(level.get('approver_dept')),
                        'approver_users': [],
                        'approver_users_info': self._get_users_info(level.get('approver_users', [])),
                        'sign_mode': step.sign_mode,
                        'sign_mode_display': step.get_sign_mode_display(),
                        'allow_return': step.allow_return,
                        'allow_reject': step.allow_reject,
                        'timeout_hours': step.timeout_hours,
                        'auto_action': step.auto_action,
                        'auto_action_display': step.get_auto_action_display(),
                        'notify_email': step.notify_email,
                        'notify_message': step.notify_message,
                        'notify_sms': step.notify_sms,
                        'condition_rules': step.condition_rules,
                        'next_step_on_pass': step.next_step_on_pass.id if step.next_step_on_pass else None,
                        'next_step_on_pass_name': step.next_step_on_pass.step_name if step.next_step_on_pass else None,
                        'next_step_on_reject': step.next_step_on_reject.id if step.next_step_on_reject else None,
                        'next_step_on_reject_name': step.next_step_on_reject.step_name if step.next_step_on_reject else None,
                        'description': f"{step.description or ''}\n多级审批第{idx+1}级",
                        'multi_level_config': None,  # 子层级不再包含multi_level_config
                        'create_datetime': step.create_datetime,
                        'update_datetime': step.update_datetime,
                        # 额外字段用于前端显示
                        'is_multi_level_child': True,  # 标记这是多级审批的子层级
                        'parent_step_id': step.id,  # 父步骤ID
                        'parent_step_name': step.step_name,  # 父步骤名称
                    }
                    expanded_steps.append(virtual_step)
            else:
                # 普通步骤，直接序列化
                expanded_steps.append(WorkflowStepSerializer(step).data)
        
        return expanded_steps
    
    def _get_approver_type_display(self, approver_type):
        """获取审批人类型显示文本"""
        type_map = {
            1: '指定角色',
            2: '指定部门',
            3: '部门负责人',
            4: '指定人员',
            5: '申请人自选',
            6: '多级审批（组合）'
        }
        return type_map.get(approver_type, '未知')
    
    def _get_role_name(self, role_id):
        """根据角色ID获取角色名称"""
        if not role_id:
            return None
        try:
            from mysystem.models import DeptRole
            role = DeptRole.objects.get(id=role_id)
            return role.name
        except:
            return None
    
    def _get_dept_name(self, dept_id):
        """根据部门ID获取部门名称"""
        if not dept_id:
            return None
        try:
            from mysystem.models import Dept
            dept = Dept.objects.get(id=dept_id)
            return dept.name
        except:
            return None
    
    def _get_users_info(self, user_ids):
        """根据用户ID列表获取用户信息"""
        if not user_ids:
            return []
        try:
            from lyusers.models import Users
            users = Users.objects.filter(id__in=user_ids)
            return [{'id': user.id, 'name': user.name} for user in users]
        except:
            return []

    def get_approval_history(self, obj):
        """获取审批历史"""
        tasks = obj.tasks.exclude(status=0).order_by('step_order', 'level_order', 'approve_time')
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
    selected_approvers = serializers.JSONField(required=False, allow_null=True)
    
    class Meta:
        model = WorkflowInstance
        fields = ['id', 'workflow_type', 'title', 'form_data', 'remark', 'selected_approvers']
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
        
        # 计算总步骤数（考虑多级审批展开）
        validated_data['total_steps'] = self._calculate_total_steps(validated_data['workflow_type'])
        
        return super().create(validated_data)
    
    def _calculate_total_steps(self, workflow_type):
        """计算流程的总步骤数（考虑多级审批展开）"""
        total = 0
        steps = workflow_type.steps.all()
        
        for step in steps:
            # 如果是多级审批（approver_type=6），计算其层级数
            if step.approver_type == 6 and step.multi_level_config:
                total += len(step.multi_level_config)
            else:
                # 普通步骤，计为1
                total += 1
        
        return total


class WorkflowApproveSerializer(CustomModelSerializer):
    """审批操作序列化器"""
    # approve_result 由后端视图集根据 URL 路径确定，前端可以不传
    approve_result = serializers.IntegerField(write_only=True, required=False)
    approve_comment = serializers.CharField(write_only=True, allow_blank=True, required=False)

    class Meta:
        model = WorkflowTask
        fields = ['approve_result', 'approve_comment']
    
    def validate(self, attrs):
        """验证审批数据"""
        # approve_result 由后端视图集提供，这里只验证 approve_comment
        approve_comment = attrs.get('approve_comment', '').strip()
        
        # 注意：驳回(2)和退回(3)时的验证在后端视图集中进行
        # 因为 approve_result 不在 attrs 中
        
        return attrs
