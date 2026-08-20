from rest_framework import serializers
from utils.serializers import CustomModelSerializer
from apps.lyworkflow.models import (
    WorkflowType, WorkflowStep, WorkflowCC,
    WorkflowInstance, WorkflowTask, WorkflowCCInstance, WorkflowLog, WorkflowComment,
    ApprovalGroup
)
from mysystem.models import Users, Role, Dept


class ApprovalGroupSerializer(CustomModelSerializer):
    """自定义审批组序列化器"""
    members_info = serializers.SerializerMethodField(read_only=True)
    members_count = serializers.SerializerMethodField(read_only=True)

    def get_members_info(self, obj):
        """获取组成员信息"""
        users = obj.members.all()
        return [{'id': user.id, 'name': user.name,
                 'dept_name': user.dept.name if getattr(user, 'dept', None) else None} for user in users]

    def get_members_count(self, obj):
        """获取组成员数量"""
        return obj.members.count()

    class Meta:
        model = ApprovalGroup
        fields = ['id', 'name', 'product_line', 'description', 'members',
                  'members_info', 'members_count',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowTypeSerializer(CustomModelSerializer):
    """流程类型序列化器"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    steps_count = serializers.SerializerMethodField(read_only=True)
    allowed_initiator_depts_name = serializers.SerializerMethodField(read_only=True)
    # 软件包共享路径与软件包名称字段 key：供前端手动创建时按"自动回填"开关自动填写"软件包存放路径"
    # （"共享路径 + 软件包名称"拼接，与后端 config.PACKAGE_SCAN_SHARED_PATH /
    # PACKAGE_SCAN_PACKAGE_NAME_FIELD 保持一致，避免前端硬编码路径）
    package_scan_shared_path = serializers.SerializerMethodField(read_only=True)
    package_scan_package_name_field = serializers.SerializerMethodField(read_only=True)
    # 软件包存放路径字段 key：发起前自动填写接口按此识别路径类字段（开启"自动回填"开关时）拼接校验文件存在
    # （从 config.DELIVERY_AUTO_FILL_FIELDS 中回填来源为 package_path 的字段解析，与后端发包链路保持一致）
    package_scan_path_field = serializers.SerializerMethodField(read_only=True)

    def get_steps_count(self, obj):
        """获取步骤数量"""
        return obj.steps.count()

    def get_package_scan_shared_path(self, obj):
        """获取软件包共享路径（config.PACKAGE_SCAN_SHARED_PATH，发起前自动填写用）"""
        import config
        return getattr(config, 'PACKAGE_SCAN_SHARED_PATH', '') or ''

    def get_package_scan_package_name_field(self, obj):
        """获取审批表单中"软件包名称"字段 key（config.PACKAGE_SCAN_PACKAGE_NAME_FIELD）"""
        import config
        return getattr(config, 'PACKAGE_SCAN_PACKAGE_NAME_FIELD', '') or ''

    def get_package_scan_path_field(self, obj):
        """获取审批表单中"软件包存放路径"字段 key（config.DELIVERY_AUTO_FILL_FIELDS 中回填来源为 package_path 的字段）"""
        import config
        fields = getattr(config, 'DELIVERY_AUTO_FILL_FIELDS', {}) or {}
        for key, source in fields.items():
            if source == 'package_path':
                return key
        return ''

    def get_allowed_initiator_depts_name(self, obj):
        """获取允许发起的部门名称"""
        dept_ids = obj.allowed_initiator_depts
        if not dept_ids:
            return '全部部门'
        try:
            if isinstance(dept_ids, list):
                depts = Dept.objects.filter(id__in=dept_ids)
            else:
                depts = Dept.objects.filter(id=dept_ids)
            return ', '.join([d.name for d in depts])
        except Exception:
            return None

    class Meta:
        model = WorkflowType
        fields = ['id', 'name', 'code', 'description', 'icon', 'status', 'status_display', 'sort', 'steps_count',
                  'form_schema',  # 添加表单配置字段
                  'package_scan_shared_path', 'package_scan_package_name_field', 'package_scan_path_field',  # 自动回填配置（软件包共享路径/包名字段/路径字段key，供手动创建时按"自动回填"开关填写路径）
                  'allowed_initiator_depts', 'allowed_initiator_depts_name',  # 新增：允许发起的部门
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowStepSerializer(CustomModelSerializer):
    """流程步骤序列化器（节点配置）"""
    workflow_type_name = serializers.CharField(source='workflow_type.name', read_only=True)
    approver_type_display = serializers.CharField(source='get_approver_type_display', read_only=True)
    approver_role_name = serializers.CharField(source='approver_role.name', read_only=True)
    approver_group_name = serializers.CharField(source='approver_group.name', read_only=True, default=None)
    approver_group_members_info = serializers.SerializerMethodField(read_only=True)
    approver_dept_name = serializers.SerializerMethodField(read_only=True)
    approver_users_info = serializers.SerializerMethodField(read_only=True)
    sign_mode_display = serializers.CharField(source='get_sign_mode_display', read_only=True)
    auto_action_display = serializers.CharField(source='get_auto_action_display', read_only=True)
    node_type_display = serializers.CharField(source='get_node_type_display', read_only=True)
    approval_mode_display = serializers.CharField(source='get_approval_mode_display', read_only=True)
    next_step_on_pass_name = serializers.CharField(source='next_step_on_pass.step_name', read_only=True)
    next_step_on_reject_name = serializers.CharField(source='next_step_on_reject.step_name', read_only=True)
    # 新增：审批人显示文本（用于列表展示）
    approvers_display = serializers.SerializerMethodField(read_only=True)
    # 新增：level_order 字段，用于多级审批和普通步骤的统一处理
    level_order = serializers.SerializerMethodField(read_only=True)
    # 节点级抄送人信息
    cc_type_display = serializers.CharField(source='get_cc_type_display', read_only=True, default=None)
    cc_role_name = serializers.CharField(source='cc_role.name', read_only=True, default=None)
    cc_dept_name = serializers.SerializerMethodField(read_only=True)
    cc_users_info = serializers.SerializerMethodField(read_only=True)
    cc_group_name = serializers.CharField(source='cc_group.name', read_only=True, default=None)

    def validate(self, attrs):
        """验证节点配置数据"""
        node_type = attrs.get('node_type')
        
        # 普通审批节点 (node_type=1) 需要配置审批人
        if node_type == 1 or node_type is None:
            approver_type = attrs.get('approver_type')
            if approver_type == 1 and not attrs.get('approver_role'):
                raise serializers.ValidationError({
                    'approver_role': '指定角色类型必须选择审批角色'
                })
            elif approver_type == 2 and not attrs.get('approver_dept'):
                # 支持单个部门ID或部门ID数组
                approver_dept = attrs.get('approver_dept')
                if not approver_dept:
                    raise serializers.ValidationError({
                        'approver_dept': '指定部门类型必须选择审批部门'
                    })
            # 注意：approver_type == 3（部门负责人）不再强制要求选择部门
            # 未选择部门时，将自动使用申请人的实际部门
            elif approver_type == 4 and not attrs.get('approver_users'):
                raise serializers.ValidationError({
                    'approver_users': '指定人员类型必须选择审批人员'
                })
            elif approver_type == 10 and not attrs.get('approver_group'):
                raise serializers.ValidationError({
                    'approver_group': '自定义审批组类型必须选择审批组'
                })
            # 多级审批（approver_type=6）的验证在multi_level_config中
            elif approver_type == 6:
                multi_level_config = attrs.get('multi_level_config')
                if not multi_level_config:
                    raise serializers.ValidationError({
                        'multi_level_config': '多级审批类型必须配置层级信息'
                    })
                if isinstance(multi_level_config, str):
                    import json
                    try:
                        multi_level_config = json.loads(multi_level_config)
                    except:
                        raise serializers.ValidationError({
                            'multi_level_config': '多级审批配置格式错误'
                        })
                
                if not isinstance(multi_level_config, list) or len(multi_level_config) == 0:
                    raise serializers.ValidationError({
                        'multi_level_config': '多级审批至少需要配置一个层级'
                    })
                
                # 验证每个层级的配置
                for idx, level in enumerate(multi_level_config):
                    level_approver_type = level.get('approver_type')
                    if level_approver_type == 1 and not level.get('approver_role'):
                        raise serializers.ValidationError({
                            'multi_level_config': f'第{idx+1}级指定角色类型必须选择审批角色'
                        })
                    elif level_approver_type == 2 and not level.get('approver_dept'):
                        # 支持单个部门ID或部门ID数组
                        dept_val = level.get('approver_dept')
                        if not dept_val:
                            raise serializers.ValidationError({
                                'multi_level_config': f'第{idx+1}级指定部门类型必须选择审批部门'
                            })
                    # 注意：多级审批中 approver_type == 3（部门负责人）不再强制要求选择部门
                    # 未选择部门时，将自动使用申请人的实际部门
                    elif level_approver_type == 4 and not level.get('approver_users'):
                        raise serializers.ValidationError({
                            'multi_level_config': f'第{idx+1}级指定人员类型必须选择审批人员'
                        })
        
        # 抄送节点 (node_type=2) 需要 condition_rules 配置
        elif node_type == 2:
            if not attrs.get('condition_rules'):
                raise serializers.ValidationError({
                    'condition_rules': '抄送节点必须配置 condition_rules（包含 cc_type 等抄送人员配置）'
                })
            
            # 验证抄送配置的完整性
            condition_rules = attrs['condition_rules']
            if isinstance(condition_rules, str):
                import json
                try:
                    condition_rules = json.loads(condition_rules)
                except:
                    raise serializers.ValidationError({
                        'condition_rules': '抄送配置格式错误，应为JSON格式'
                    })
            
            cc_type = condition_rules.get('cc_type')
            if not cc_type:
                raise serializers.ValidationError({
                    'condition_rules': '抄送节点必须指定抄送人类型(cc_type)'
                })
            
            if cc_type == 1 and not condition_rules.get('cc_role'):
                raise serializers.ValidationError({
                    'condition_rules': '指定角色类型必须选择抄送角色'
                })
            elif cc_type == 2 and not condition_rules.get('cc_dept'):
                raise serializers.ValidationError({
                    'condition_rules': '指定部门类型必须选择抄送部门'
                })
            elif cc_type == 4:
                cc_users = condition_rules.get('cc_users', [])
                if not cc_users or len(cc_users) == 0:
                    raise serializers.ValidationError({
                        'condition_rules': '指定人员类型必须选择抄送人员'
                    })
            elif cc_type == 6 and not condition_rules.get('cc_group'):
                raise serializers.ValidationError({
                    'condition_rules': '自定义审批组类型必须选择抄送审批组'
                })
        
        # 条件分支节点 (node_type=3) 需要 condition_rules 和 next_step_on_pass
        elif node_type == 3:
            if not attrs.get('condition_rules'):
                raise serializers.ValidationError({
                    'condition_rules': '条件分支节点必须配置 condition_rules（包含条件判断规则）'
                })
            
            # 验证条件分支配置的完整性
            condition_rules = attrs['condition_rules']
            if isinstance(condition_rules, str):
                import json
                try:
                    condition_rules = json.loads(condition_rules)
                except:
                    raise serializers.ValidationError({
                        'condition_rules': '条件分支配置格式错误，应为JSON数组格式'
                    })
            
            if not isinstance(condition_rules, list) or len(condition_rules) == 0:
                raise serializers.ValidationError({
                    'condition_rules': '条件分支节点至少需要配置一个条件'
                })
            
            # 验证每个条件的完整性
            for idx, cond in enumerate(condition_rules):
                if not cond.get('field'):
                    raise serializers.ValidationError({
                        'condition_rules': f'第{idx+1}个条件缺少字段名(field)'
                    })
                if not cond.get('operator'):
                    raise serializers.ValidationError({
                        'condition_rules': f'第{idx+1}个条件缺少操作符(operator)'
                    })
                if cond.get('value') is None:
                    raise serializers.ValidationError({
                        'condition_rules': f'第{idx+1}个条件缺少比较值(value)'
                    })
                if not cond.get('target_step'):
                    raise serializers.ValidationError({
                        'condition_rules': f'第{idx+1}个条件缺少目标步骤(target_step)'
                    })
            
            # 建议配置 next_step_on_pass 作为默认分支
        
        # 并行网关节点 (node_type=4) 需要 condition_rules 配置 branches
        elif node_type == 4:
            if not attrs.get('condition_rules'):
                raise serializers.ValidationError({
                    'condition_rules': '并行网关节点必须配置 condition_rules（包含 branches 分支配置）'
                })
            
            # 验证并行分支配置的完整性
            condition_rules = attrs['condition_rules']
            if isinstance(condition_rules, str):
                import json
                try:
                    condition_rules = json.loads(condition_rules)
                except:
                    raise serializers.ValidationError({
                        'condition_rules': '并行网关配置格式错误，应为JSON格式'
                    })
            
            branches = condition_rules.get('branches', [])
            if not isinstance(branches, list) or len(branches) == 0:
                raise serializers.ValidationError({
                    'condition_rules': '并行网关节点至少需要配置一个分支'
                })
            
            # 验证每个分支的完整性
            for idx, branch in enumerate(branches):
                if not branch.get('target_step'):
                    raise serializers.ValidationError({
                        'condition_rules': f'第{idx+1}个分支缺少目标步骤(target_step)'
                    })
        
        # 结束节点 (node_type=5) 不需要特殊验证
        elif node_type == 5:
            pass
        
        # 节点级抄送人配置验证：自定义审批组类型必须选择审批组
        cc_type = attrs.get('cc_type')
        if cc_type is None and self.instance is not None:
            cc_type = getattr(self.instance, 'cc_type', None)
        if cc_type == 6:
            cc_group = attrs.get('cc_group')
            if cc_group is None and getattr(self.instance, 'cc_group', None) is None:
                raise serializers.ValidationError({
                    'cc_group': '抄送人类型为自定义审批组时必须选择抄送审批组'
                })
        
        return attrs

    def get_cc_dept_name(self, obj):
        """获取抄送部门名称（支持多部门）"""
        dept_ids = obj.cc_dept
        if not dept_ids:
            return None
        try:
            if isinstance(dept_ids, list):
                depts = Dept.objects.filter(id__in=dept_ids)
            else:
                depts = Dept.objects.filter(id=dept_ids)
            return ', '.join([d.name for d in depts])
        except Exception:
            return None

    def get_cc_users_info(self, obj):
        """获取抄送人员信息"""
        users = obj.cc_users.all()
        return [{'id': user.id, 'name': user.name} for user in users]

    def get_approver_users_info(self, obj):
        """获取审批人员信息"""
        users = obj.approver_users.all()
        return [{'id': user.id, 'name': user.name} for user in users]

    def get_approver_group_members_info(self, obj):
        """获取审批组成员信息（自定义审批组节点显示用）"""
        if obj.approver_group:
            return [{'id': u.id, 'name': u.name} for u in obj.approver_group.members.all()]
        return []

    def get_approver_dept_name(self, obj):
        """获取审批部门名称（支持多部门）"""
        dept_ids = obj.approver_dept
        if not dept_ids:
            return None
        try:
            # 兼容：支持单个ID或ID数组
            if isinstance(dept_ids, list):
                depts = Dept.objects.filter(id__in=dept_ids)
            else:
                depts = Dept.objects.filter(id=dept_ids)
            return ', '.join([d.name for d in depts])
        except Exception:
            return None

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
                elif approver_type == 2:  # 指定部门（支持多部门）
                    dept_ids = level.get('approver_dept')
                    if dept_ids:
                        try:
                            from mysystem.models import Dept
                            # 兼容：支持单个ID或ID数组
                            if isinstance(dept_ids, list):
                                depts = Dept.objects.filter(id__in=dept_ids)
                            else:
                                depts = Dept.objects.filter(id=dept_ids)
                            dept_names = [d.name for d in depts]
                            levels.append(f"{level_name}: {', '.join(dept_names)}")
                        except:
                            levels.append(f"{level_name}: 部门")
                    else:
                        levels.append(f"{level_name}: 未配置")
                elif approver_type == 3:  # 部门负责人（支持多部门，未配置时自动使用申请人部门）
                    dept_ids = level.get('approver_dept')
                    if dept_ids:
                        try:
                            from mysystem.models import Dept
                            # 兼容：支持单个ID或ID数组
                            if isinstance(dept_ids, list):
                                depts = Dept.objects.filter(id__in=dept_ids)
                            else:
                                depts = Dept.objects.filter(id=dept_ids)
                            dept_names = [d.name for d in depts]
                            levels.append(f"{level_name}: {', '.join(dept_names)}负责人")
                        except:
                            levels.append(f"{level_name}: 部门负责人")
                    else:
                        levels.append(f"{level_name}: 申请人部门负责人")
                elif approver_type == 4:  # 指定人员
                    user_ids = level.get('approver_users', [])
                    if user_ids:
                        try:
                            # from lyusers.models import Users
                            users = Users.objects.filter(id__in=user_ids).values_list('name', flat=True)
                            levels.append(f"{level_name}: {', '.join(users)}")
                        except:
                            levels.append(f"{level_name}: 人员")
                    else:
                        levels.append(f"{level_name}: 未配置")
                elif approver_type == 5:  # 申请人自选
                    levels.append(f"{level_name}: 申请人自选")
                elif approver_type == 7:  # 发起人
                    levels.append(f"{level_name}: 发起人")
                elif approver_type == 9:  # 直接上级
                    levels.append(f"{level_name}: 直接上级")
                else:
                    levels.append(f"{level_name}: 未配置")
            
            return '; '.join(levels) if levels else '未配置'
        
        # 普通审批逻辑（原有逻辑）
        if obj.approver_type == 1:  # 指定角色
            return f"角色: {obj.approver_role.name}" if obj.approver_role else '未配置'
        elif obj.approver_type == 2:  # 指定部门（支持多部门）
            dept_ids = obj.approver_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    dept_names = [d.name for d in depts]
                    return f"部门: {', '.join(dept_names)}"
                except:
                    return '未配置'
            return '未配置'
        elif obj.approver_type == 3:  # 部门负责人（支持多部门，未配置时自动使用申请人部门）
            dept_ids = obj.approver_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    dept_names = [d.name for d in depts]
                    return f"{', '.join(dept_names)}负责人"
                except:
                    return '未配置'
            return '申请人部门负责人'
        elif obj.approver_type == 4:  # 指定人员
            users = obj.approver_users.all()
            if users:
                return ', '.join([user.name for user in users])
            return '未配置'
        elif obj.approver_type == 5:  # 申请人自选
            return '申请人自选'
        elif obj.approver_type == 7:  # 发起人
            return '发起人（流程申请人）'
        elif obj.approver_type == 10:  # 自定义审批组
            if obj.approver_group:
                member_names = ', '.join([u.name for u in obj.approver_group.members.all()])
                return f"审批组: {obj.approver_group.name}" + (f"（{member_names}）" if member_names else '')
            return '审批组: 未配置'
        else:
            return '未配置'
    
    def get_level_order(self, obj):
        """获取 level_order：对于普通步骤，level_order = step_order；对于多级审批子步骤，在 get_steps_info 中单独设置"""
        # 这里只处理普通步骤的情况
        # 多级审批的子步骤会在 WorkflowInstanceSerializer.get_steps_info 中单独设置
        return float(obj.step_order)

    class Meta:
        model = WorkflowStep
        fields = ['id', 'workflow_type', 'workflow_type_name', 'step_name', 'step_order', 'level_order',
                  'node_type', 'node_type_display',
                  'approval_mode', 'approval_mode_display',
                  'approver_type', 'approver_type_display', 'approver_role', 'approver_role_name',
                  'approver_dept', 'approver_dept_name', 'approver_users', 'approver_users_info',
                  'approver_group', 'approver_group_name', 'approver_group_members_info',
                  'sign_mode', 'sign_mode_display',
                  'allow_return', 'allow_reject',
                  'timeout_hours', 'auto_action', 'auto_action_display',
                  'notify_email', 'notify_message', 'notify_sms',
                  'condition_rules',
                  'next_step_on_pass', 'next_step_on_pass_name',
                  'next_step_on_reject', 'next_step_on_reject_name',
                  'description',
                  'multi_level_config',
                  'internal_conditions',  # 新增：节点内部条件配置
                  'approvers_display',  # 新增：审批人显示文本
                  'cc_type', 'cc_type_display', 'cc_role', 'cc_role_name',
                  'cc_dept', 'cc_dept_name', 'cc_users', 'cc_users_info',
                  'cc_group', 'cc_group_name',
                  'product_line', 'product_line_cc_rules',  # 新增：产品线标识和抄送规则
                  'skip_approval_config',  # 新增：自动跳过审批配置
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowCCSerializer(CustomModelSerializer):
    """流程抄送配置序列化器"""
    workflow_type_name = serializers.CharField(source='workflow_type.name', read_only=True)
    step_name = serializers.CharField(source='step.step_name', read_only=True)
    cc_type_display = serializers.CharField(source='get_cc_type_display', read_only=True)
    cc_role_name = serializers.CharField(source='cc_role.name', read_only=True)
    cc_dept_name = serializers.SerializerMethodField(read_only=True)
    cc_users_info = serializers.SerializerMethodField(read_only=True)
    cc_group_name = serializers.CharField(source='cc_group.name', read_only=True, default=None)

    def validate(self, attrs):
        """验证抄送配置：自定义审批组类型必须选择审批组"""
        cc_type = attrs.get('cc_type')
        if cc_type == 6:
            cc_group = attrs.get('cc_group')
            if cc_group is None and getattr(self.instance, 'cc_group', None) is None:
                raise serializers.ValidationError({
                    'cc_group': '自定义审批组类型必须选择抄送审批组'
                })
        return attrs

    def get_cc_dept_name(self, obj):
        """获取抄送部门名称（支持多部门）"""
        dept_ids = obj.cc_dept
        if not dept_ids:
            return None
        try:
            if isinstance(dept_ids, list):
                depts = Dept.objects.filter(id__in=dept_ids)
            else:
                depts = Dept.objects.filter(id=dept_ids)
            return ', '.join([d.name for d in depts])
        except Exception:
            return None

    def get_cc_users_info(self, obj):
        """获取抄送人员信息"""
        users = obj.cc_users.all()
        return [{'id': user.id, 'name': user.name} for user in users]

    class Meta:
        model = WorkflowCC
        fields = ['id', 'workflow_type', 'workflow_type_name', 'step', 'step_name',
                  'cc_type', 'cc_type_display', 'cc_role', 'cc_role_name',
                  'cc_dept', 'cc_dept_name', 'cc_users', 'cc_users_info',
                  'cc_group', 'cc_group_name',
                  'can_approve',
                  'create_datetime', 'update_datetime']
        read_only_fields = ['id', 'create_datetime', 'update_datetime']


class WorkflowTaskSerializer(CustomModelSerializer):
    """审批任务序列化器"""
    instance_no = serializers.CharField(source='instance.instance_no', read_only=True)
    instance_title = serializers.CharField(source='instance.title', read_only=True)
    step_name = serializers.SerializerMethodField(read_only=True)  # 修改为动态计算
    approver_name = serializers.CharField(source='approver.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    approve_result_display = serializers.CharField(source='get_approve_result_display', read_only=True)

    # 流程实例当前状态（用于我的已办追溯流程最终走向）
    instance_status = serializers.IntegerField(source='instance.status', read_only=True)
    instance_status_display = serializers.CharField(source='instance.get_status_display', read_only=True)
    applicant_name = serializers.CharField(source='instance.applicant.name', read_only=True)
    
    # 添加步骤配置信息（用于前端判断是否显示退回/驳回按钮）
    allow_return = serializers.BooleanField(source='step.allow_return', read_only=True)
    allow_reject = serializers.BooleanField(source='step.allow_reject', read_only=True)
    
    # 添加唯一节点标识（用于区分同一审批人在不同层级的任务）
    node_key = serializers.SerializerMethodField(read_only=True)
    
    # 添加当前用户是否为申请人的标识（用于前端判断使用确认还是审批接口）
    is_applicant = serializers.SerializerMethodField(read_only=True)
    
    # 添加节点类型和审批人类型（用于前端判断显示确认还是审批按钮）
    step_node_type = serializers.IntegerField(source='step.node_type', read_only=True)
    step_approver_type = serializers.IntegerField(source='step.approver_type', read_only=True)
    
    # 添加层级审批人类型（用于多级审批时区分每个层级的审批人类型）
    level_approver_type = serializers.SerializerMethodField(read_only=True)
    level_approver_type_display = serializers.SerializerMethodField(read_only=True)
    
    def get_node_key(self, obj):
        """生成唯一节点标识：step_order-level_order-approver_id"""
        if not obj.step or not obj.approver:
            return ''
        return f"{obj.step.step_order}-{obj.level_order}-{obj.approver.id}"
    
    def get_is_applicant(self, obj):
        """判断当前用户是否为流程申请人"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.instance.applicant == request.user
        return False
    
    def get_step_name(self, obj):
        """获取步骤名称（多级审批时返回层级名称）"""
        if not obj.step:
            return ''
        
        # 如果是多级审批，返回层级名称
        if obj.step.approver_type == 6 and obj.step.multi_level_config:
            import json
            config = obj.step.multi_level_config
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except (json.JSONDecodeError, ValueError):
                    config = None
            
            if isinstance(config, list):
                # 计算当前是第几个层级（idx从0开始）
                base_step_order = obj.step.step_order
                idx = obj.level_order - base_step_order
                
                # 获取对应层级的名称
                if 0 <= idx < len(config) and isinstance(config[idx], dict):
                    level_name = config[idx].get('name', '')
                    if level_name:
                        return level_name
        
        # 普通步骤或找不到层级名称时，返回步骤名称
        return obj.step.step_name
    
    def get_level_approver_type(self, obj):
        """获取层级审批人类型（多级审批时返回该层级的approver_type）"""
        if not obj.step:
            return None
        
        # 如果是多级审批，返回该层级的approver_type
        if obj.step.approver_type == 6 and obj.step.multi_level_config:
            import json
            config = obj.step.multi_level_config
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except (json.JSONDecodeError, ValueError):
                    config = None
            
            if isinstance(config, list) and len(config) > 0:
                base_step_order = obj.step.step_order
                idx = obj.level_order - base_step_order
                
                if 0 <= idx < len(config) and isinstance(config[idx], dict):
                    level_approver_type = config[idx].get('approver_type')
                    if level_approver_type is not None:
                        return level_approver_type
        
        # 条件化审批人：根据任务审批人反推实际使用的审批人类型
        if obj.step.approver_type == 8 or obj.step.internal_conditions:
            resolved = self._resolve_condition_approver_type(obj)
            if resolved is not None:
                return resolved
        
        # 普通步骤或多级审批解析失败时，返回步骤的approver_type
        return obj.step.approver_type
    
    def _resolve_condition_approver_type(self, obj):
        """条件化审批人节点：根据任务审批人反推其实际归属的审批人类型
        
        匹配优先级：指定人员 > 发起人 > 指定角色 > 指定部门/部门负责人 > 直接上级
        
        Returns:
            审批人类型(int)或 None
        """
        import json
        conditions = obj.step.internal_conditions
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except (json.JSONDecodeError, ValueError):
                return None
        if not isinstance(conditions, list):
            return None
        
        has_direct_superior = False
        applicant_id = getattr(obj.instance, 'applicant_id', None) if obj.instance else None
        
        for group in conditions:
            if not isinstance(group, dict):
                continue
            approvers_config = group.get('approvers_config') or []
            if isinstance(approvers_config, dict):
                approvers_config = [approvers_config]
            for config in approvers_config:
                if not isinstance(config, dict):
                    continue
                atype = config.get('approver_type')
                if atype == 4:  # 指定人员：审批人ID在配置人员列表中
                    user_ids = config.get('approver_users') or []
                    if obj.approver_id in user_ids:
                        return 4
                elif atype == 7:  # 发起人：审批人即申请人
                    if applicant_id is not None and obj.approver_id == applicant_id:
                        return 7
                elif atype == 1:  # 指定角色：审批人角色匹配
                    role_id = config.get('approver_role')
                    if role_id and obj.approver is not None and getattr(obj.approver, 'role_id', None) == role_id:
                        return 1
                elif atype in (2, 3):  # 指定部门/部门负责人：审批人部门匹配
                    dept_ids = config.get('approver_dept') or []
                    if not isinstance(dept_ids, list):
                        dept_ids = [dept_ids]
                    approver_dept_id = getattr(obj.approver, 'dept_id', None) if obj.approver else None
                    if approver_dept_id and approver_dept_id in dept_ids:
                        return atype
                elif atype == 10:  # 自定义审批组：审批人是审批组成员
                    group_id = config.get('approver_group')
                    if group_id:
                        try:
                            group = ApprovalGroup.objects.get(id=group_id)
                            if obj.approver_id and group.members.filter(id=obj.approver_id).exists():
                                return 10
                        except ApprovalGroup.DoesNotExist:
                            pass
                elif atype == 9:  # 直接上级（候选，其他类型都未命中时归属）
                    has_direct_superior = True
        
        if has_direct_superior:
            return 9
        return None
    
    def get_level_approver_type_display(self, obj):
        """获取层级审批人类型显示文本"""
        approver_type = self.get_level_approver_type(obj)
        type_map = {
            1: '指定角色',
            2: '指定部门',
            3: '部门负责人',
            4: '指定人员',
            5: '申请人自选',
            6: '多级审批',
            7: '发起人',
            9: '直接上级',
            10: '自定义审批组'
        }
        return type_map.get(approver_type, '未知')

    class Meta:
        model = WorkflowTask
        fields = ['id', 'instance', 'instance_no', 'instance_title', 'step', 'step_name',
                  'step_order', 'level_order', 'approver', 'approver_name',
                  'instance_status', 'instance_status_display', 'applicant_name',
                  'status', 'status_display', 'approve_result', 'approve_result_display',
                  'approve_comment', 'approve_time', 'is_cc',
                  'allow_return', 'allow_reject', 'node_key', 'is_applicant',
                  'step_node_type', 'step_approver_type',
                  'level_approver_type', 'level_approver_type_display',
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


class WorkflowCommentSerializer(CustomModelSerializer):
    """审批节点评论序列化器"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    step_name = serializers.SerializerMethodField(read_only=True)

    def get_step_name(self, obj):
        """获取评论所在节点名称（多级审批时返回层级名称，逻辑与 WorkflowTaskSerializer 一致）"""
        task = obj.task
        if not task or not task.step:
            return ''
        if task.step.approver_type == 6 and task.step.multi_level_config:
            import json
            config = task.step.multi_level_config
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except (json.JSONDecodeError, ValueError):
                    config = None
            if isinstance(config, list):
                idx = task.level_order - task.step.step_order
                if 0 <= idx < len(config) and isinstance(config[idx], dict):
                    level_name = config[idx].get('name', '')
                    if level_name:
                        return level_name
        return task.step.step_name

    class Meta:
        model = WorkflowComment
        fields = ['id', 'instance', 'task', 'step_name', 'user', 'user_name', 'content',
                  'attachments', 'create_datetime', 'update_datetime']
        # user 由后端在创建时自动填充（当前登录用户），前端不需要也不能指定
        read_only_fields = ['id', 'user', 'create_datetime', 'update_datetime']


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
    # 自动跳过的步骤
    skipped_steps = serializers.SerializerMethodField(read_only=True)
    # 审批评论（按时间正序展示，便于按节点串读沟通记录）
    comments = serializers.SerializerMethodField(read_only=True)
    # 是否允许发表评论（流程已通过或所有节点已完成时禁止）
    can_comment = serializers.SerializerMethodField(read_only=True)

    def get_comments(self, obj):
        """获取流程全部评论（按时间正序）"""
        comments = obj.comments.all().order_by('create_datetime')
        return WorkflowCommentSerializer(comments, many=True).data

    def get_can_comment(self, obj):
        """是否允许发表评论：状态为已通过或当前轮次已无待审批任务时禁止"""
        if obj.status == 2:
            return False
        return WorkflowTask.objects.filter(
            instance=obj, status=0, round=obj.submit_round
        ).exists()

    def get_my_pending_task(self, obj):
        """获取当前用户的待审批任务"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if request.user.is_superuser:
                # 超级管理员查看所有待审批任务（包括申请人自己的确认任务）
                task = obj.tasks.filter(
                    status=0,
                    approver__isnull=False
                ).first()
                if task:
                    return WorkflowTaskSerializer(task).data
            else:
                # 普通用户只能看到分配给自己的任务
                task = obj.tasks.filter(approver=request.user, status=0).first()
                if task:
                    return WorkflowTaskSerializer(task).data
        return None

    def get_steps_info(self, obj):
        """获取流程步骤信息（支持多级审批展开）"""
        steps = obj.workflow_type.steps.all()
        expanded_steps = []
        
        import logging
        import json
        logger = logging.getLogger(__name__)
        logger.info(f'get_steps_info - 流程实例: {obj.instance_no}, 步骤数量: {steps.count()}')
        
        for step in steps:
            logger.info(f'get_steps_info - 步骤: step_order={step.step_order}, approver_type={step.approver_type}, step_name={step.step_name}')
            
            # 如果是多级审批（approver_type=6），需要展开为多个子层级
            if step.approver_type == 6 and step.multi_level_config:
                # 解析multi_level_config（可能是JSON字符串或已解析的列表）
                config = step.multi_level_config
                if isinstance(config, str):
                    try:
                        config = json.loads(config)
                    except (json.JSONDecodeError, ValueError):
                        logger.warning(f'get_steps_info - multi_level_config JSON解析失败: {config}')
                        config = None
                
                if isinstance(config, list) and len(config) > 0:
                    logger.info(f'get_steps_info - 多级审批步骤，子层级数量: {len(config)}')
                    # 遍历多级配置，创建虚拟的子步骤
                    for idx, level in enumerate(config):
                        if not isinstance(level, dict):
                            continue
                        # 创建虚拟步骤对象
                        virtual_step = {
                            'id': f"{step.id}_level_{idx}",  # 虚拟ID
                            'workflow_type': step.workflow_type.id,
                            'workflow_type_name': step.workflow_type.name,
                            'step_name': level.get('name', f'{step.step_name}-第{idx+1}级'),
                            'step_order': step.step_order,  # 整数，表示原始步骤顺序
                            'level_order': step.step_order + idx,  # 整数，表示层级顺序（如 2, 3, 4）
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
                        logger.info(f'get_steps_info - 子层级 {idx}: level_order={virtual_step["level_order"]}, step_name={virtual_step["step_name"]}, approver_type={virtual_step["approver_type"]}')
                else:
                    logger.warning(f'get_steps_info - 多级审批步骤但config无效，作为普通步骤处理')
                    step_data = WorkflowStepSerializer(step).data
                    expanded_steps.append(step_data)
            else:
                # 普通步骤，直接序列化
                step_data = WorkflowStepSerializer(step).data
                # 条件化审批人：根据表单数据匹配实际命中的条件组，只展示命中条件组的审批人类型
                if step.approver_type == 8 or step.internal_conditions:
                    step_data['matched_condition_types'] = self._get_matched_condition_types(obj, step)
                expanded_steps.append(step_data)
                logger.info(f'get_steps_info - 普通步骤: level_order={step_data.get("level_order")}, step_name={step_data.get("step_name")}')
        
        logger.info(f'get_steps_info - 最终展开的步骤数量: {len(expanded_steps)}')
        return expanded_steps

    def _get_matched_condition_types(self, obj, step):
        """根据流程实例的表单数据，评估条件化审批人节点命中的条件组，
        返回命中条件组中的审批人类型列表（去重、保序）。
        无命中条件组时返回空列表。
        """
        import json
        try:
            conditions = step.internal_conditions
            if isinstance(conditions, str):
                conditions = json.loads(conditions)
            if not isinstance(conditions, list) or not conditions:
                return []

            form_data = obj.form_data or {}
            if isinstance(form_data, str):
                try:
                    form_data = json.loads(form_data)
                except (json.JSONDecodeError, ValueError):
                    form_data = {}

            # 复用流程引擎的条件评估逻辑，保证与运行时一致
            from .engine import FlowEngine
            engine = FlowEngine(obj)

            matched_types = []
            for group in conditions:
                if not isinstance(group, dict):
                    continue
                if engine._check_condition_group(group, form_data):
                    configs = group.get('approvers_config') or []
                    if not isinstance(configs, list):
                        configs = [configs]
                    for config in configs:
                        if isinstance(config, dict) and config.get('approver_type') not in matched_types:
                            matched_types.append(config.get('approver_type'))
                    break  # 与引擎一致：只取第一个匹配的条件组
            return matched_types
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'get_steps_info - 评估条件化审批人匹配类型失败: {e}')
            return []
    
    def _get_approver_type_display(self, approver_type):
        """获取审批人类型显示文本"""
        type_map = {
            1: '指定角色',
            2: '指定部门',
            3: '部门负责人',
            4: '指定人员',
            5: '申请人自选',
            6: '多级审批（组合）',
            7: '发起人',
            9: '直接上级',
            10: '自定义审批组'
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
    
    def _get_dept_name(self, dept_ids):
        """根据部门ID获取部门名称（支持单个ID或ID列表）"""
        if not dept_ids:
            return None
        try:
            from mysystem.models import Dept
            if isinstance(dept_ids, list):
                depts = Dept.objects.filter(id__in=dept_ids)
                return ', '.join([d.name for d in depts])
            else:
                dept = Dept.objects.get(id=dept_ids)
                return dept.name
        except Exception:
            return None
    
    def _get_users_info(self, user_ids):
        """根据用户ID列表获取用户信息"""
        if not user_ids:
            return []
        try:
            # from lyusers.models import Users
            users = Users.objects.filter(id__in=user_ids)
            return [{'id': user.id, 'name': user.name} for user in users]
        except:
            return []

    def get_approval_history(self, obj):
        """获取审批历史（仅当前提交轮次的任务，避免重新发起后旧轮任务叠加导致审批人重复展示）"""
        # 返回当前轮次的所有任务，按 level_order 和创建时间排序
        # 注意：这里返回当前轮次的所有任务是为了让前端能够判断每个层级的状态
        tasks = obj.tasks.filter(round=obj.submit_round).order_by('level_order', 'create_datetime')
        return WorkflowTaskSerializer(tasks, many=True).data
    
    def get_skipped_steps(self, obj):
        """获取自动跳过的步骤ID列表
        
        判断逻辑：检查每个步骤是否被自动跳过
        关键修复：使用正确的字段名 skip_approval_config（而非 auto_skip_config）
        """
        import logging
        logger = logging.getLogger(__name__)
        skipped_step_ids = []
        
        try:
            current_step = obj.current_step  # 当前正在处理的步骤顺序号
            steps = obj.workflow_type.steps.all()
            
            for step in steps:
                # 关键修复：使用正确的字段名 skip_approval_config
                if hasattr(step, 'skip_approval_config') and step.skip_approval_config:
                    skip_config = step.skip_approval_config
                    if isinstance(skip_config, str):
                        import json
                        skip_config = json.loads(skip_config)
                    
                    if skip_config.get('enabled'):
                        step_order = step.step_order
                        
                        # 如果步骤顺序号小于当前步骤，说明可能已经被跳过
                        if step_order < current_step:
                            # 进一步验证 - 检查该步骤当前轮次是否有实际的非申请人任务
                            step_tasks = obj.tasks.filter(step_order=step_order, round=obj.submit_round)
                            
                            # 如果没有非申请人的待审批/已通过任务，说明被跳过了
                            has_non_applicant_task = step_tasks.exclude(approver=obj.applicant).exists()
                            
                            if not has_non_applicant_task:
                                # 确认该步骤是普通审批节点(node_type=1)，而不是结束节点等
                                if step.node_type == 1:
                                    skipped_step_ids.append(step.id)
                                    logger.info(f'步骤 {step.step_name} (id={step.id}, step_order={step_order}) 被标记为已跳过')
                                    
        except Exception as e:
            logger.warning(f'获取跳过步骤失败: {str(e)}')
        
        return skipped_step_ids

    class Meta:
        model = WorkflowInstance
        fields = ['id', 'instance_no', 'workflow_type', 'workflow_type_name',
                  'title', 'applicant', 'applicant_name', 'applicant_dept', 'applicant_dept_name',
                  'status', 'status_display', 'current_step', 'total_steps',
                  'form_data', 'remark',
                  'my_pending_task', 'steps_info', 'approval_history', 'skipped_steps', 'comments',
                  'can_comment',
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
        
        # 检查发起人部门权限
        workflow_type = validated_data.get('workflow_type')
        if workflow_type and workflow_type.allowed_initiator_depts:
            user = request.user
            # 超级管理员不受限制
            if not user.is_superuser:
                user_dept = validated_data.get('applicant_dept')
                allowed_depts = workflow_type.allowed_initiator_depts
                
                if not user_dept:
                    raise serializers.ValidationError('您没有所属部门，无法发起该流程')
                
                # 检查部门是否在允许列表中
                if isinstance(allowed_depts, list):
                    if user_dept.id not in allowed_depts:
                        raise serializers.ValidationError('您的部门不在该流程的允许发起部门列表中')
                else:
                    if user_dept.id != allowed_depts:
                        raise serializers.ValidationError('您的部门不在该流程的允许发起部门列表中')
        
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
