from django.db import models
from django.contrib.auth import get_user_model
from utils.models import CoreModel

User = get_user_model()


class ApprovalGroup(CoreModel):
    """自定义审批组
    
    用于按产品线等维度维护一组可动态调整的审批人。
    例如："RC产品负责人" 组，可随时增加/删除组成员，
    流程节点引用审批组后，审批人随组成员变化自动更新。
    """
    name = models.CharField(max_length=100, verbose_name="审批组名称")
    product_line = models.CharField(max_length=100, null=True, blank=True, verbose_name="产品线",
                                    help_text="该审批组对应的产品线标识，如 RC、EMIR&Grid、STA、Phybolt")
    description = models.TextField(null=True, blank=True, verbose_name="审批组说明")
    members = models.ManyToManyField('mysystem.Users', blank=True, related_name='approval_groups', verbose_name="组成员")

    class Meta:
        db_table = 'lyworkflow_approval_group'
        verbose_name = '自定义审批组'
        verbose_name_plural = verbose_name
        ordering = ('id',)

    def __str__(self):
        return self.name


class WorkflowType(CoreModel):
    """流程类型配置"""
    name = models.CharField(max_length=100, verbose_name="流程名称")
    code = models.CharField(max_length=50, unique=True, verbose_name="流程编码")
    description = models.TextField(null=True, blank=True, verbose_name="流程描述")
    icon = models.CharField(max_length=100, null=True, blank=True, verbose_name="图标")
    status = models.SmallIntegerField(default=1, verbose_name="状态（0禁用/1启用）")
    sort = models.IntegerField(default=1, verbose_name="排序")
    
    # 动态表单配置（JSON格式存储表单字段定义）
    form_schema = models.JSONField(null=True, blank=True, verbose_name="表单配置")

    # 允许发起的部门（JSON格式存储部门ID列表，为空表示所有部门均可发起）
    allowed_initiator_depts = models.JSONField(null=True, blank=True, verbose_name="允许发起的部门",
                                               help_text="存储部门ID列表，如 [1, 2]。为空或不配置表示所有部门均可发起")

    class Meta:
        db_table = 'lyworkflow_type'
        verbose_name = '流程类型'
        verbose_name_plural = verbose_name
        ordering = ('sort',)

    def __str__(self):
        return self.name


class WorkflowStep(CoreModel):
    """流程步骤配置（节点配置）"""
    APPROVER_TYPE_CHOICES = (
        (1, '指定角色'),
        (2, '指定部门'),
        (3, '部门负责人'),
        (4, '指定人员'),
        (5, '申请人自选'),
        (6, '多级审批（组合）'),
        (7, '发起人'),
        (8, '条件化审批人'),
        (10, '自定义审批组'),
    )

    SIGN_MODE_CHOICES = (
        (1, '或签（一人审批即可）'),
        (2, '会签（所有人都需审批）'),
        (3, '顺序审批（按顺序依次审批）'),
    )

    APPROVAL_MODE_CHOICES = (
        (1, '自动流转'),
        (2, '手动配置'),
    )

    NODE_TYPE_CHOICES = (
        (1, '普通审批节点'),
        (2, '抄送节点'),
        (3, '条件分支节点'),
        (4, '并行网关节点'),
        (5, '结束节点'),
    )

    AUTO_ACTION_CHOICES = (
        (0, '不自动处理'),
        (1, '自动通过'),
        (2, '自动退回'),
    )

    workflow_type = models.ForeignKey(WorkflowType, on_delete=models.CASCADE, verbose_name="流程类型", related_name='steps')
    step_name = models.CharField(max_length=100, verbose_name="步骤名称")
    step_order = models.IntegerField(verbose_name="步骤顺序")

    # 节点类型
    node_type = models.SmallIntegerField(default=1, choices=NODE_TYPE_CHOICES, verbose_name="节点类型")
    
    # 审批模式（自动流转/手动配置）
    approval_mode = models.SmallIntegerField(default=1, choices=APPROVAL_MODE_CHOICES, verbose_name="审批模式", help_text="1=自动流转，2=手动配置")

    # 审批人配置方式
    approver_type = models.SmallIntegerField(choices=APPROVER_TYPE_CHOICES, verbose_name="审批人类型")

    # 关联的角色/部门/人员
    approver_role = models.ForeignKey('mysystem.Role', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="审批角色")
    approver_dept = models.JSONField(null=True, blank=True, verbose_name="审批部门", help_text="存储部门ID列表，如 [1, 2] 或单个ID")
    approver_users = models.ManyToManyField('mysystem.Users', blank=True, related_name='approved_workflow_steps', verbose_name="审批人员")
    # 自定义审批组（当 approver_type=10 时使用）
    approver_group = models.ForeignKey('ApprovalGroup', null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name='workflow_steps', verbose_name="审批组")

    # 多人审批模式
    sign_mode = models.SmallIntegerField(default=1, choices=SIGN_MODE_CHOICES, verbose_name="审批模式")

    # 退回设置
    allow_return = models.BooleanField(default=True, verbose_name="是否允许退回")
    allow_reject = models.BooleanField(default=False, verbose_name="是否允许驳回（直接结束）")

    # 超时设置
    timeout_hours = models.IntegerField(null=True, blank=True, verbose_name="超时时间（小时）")
    auto_action = models.SmallIntegerField(default=0, choices=AUTO_ACTION_CHOICES, verbose_name="超时自动处理")

    # 通知设置
    notify_email = models.BooleanField(default=True, verbose_name="邮件通知")
    notify_message = models.BooleanField(default=True, verbose_name="站内信通知")
    notify_sms = models.BooleanField(default=False, verbose_name="短信通知")

    # 条件分支（JSON格式存储条件规则）
    condition_rules = models.JSONField(null=True, blank=True, verbose_name="条件分支规则")

    # 下一步骤（用于条件分支）
    next_step_on_pass = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, 
                                          verbose_name="通过后下一步骤", related_name='prev_steps_pass')
    next_step_on_reject = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL,
                                            verbose_name="驳回后下一步骤", related_name='prev_steps_reject')

    # 备注说明
    description = models.TextField(null=True, blank=True, verbose_name="节点说明")
    
    # 多级审批配置（JSON格式存储层级信息）
    multi_level_config = models.JSONField(null=True, blank=True, verbose_name="多级审批配置", help_text="当approver_type=6时使用，存储多个审批层级的配置")

    # 节点内部条件配置（用于动态审批人）
    internal_conditions = models.JSONField(null=True, blank=True, verbose_name="节点内部条件配置",
                                          help_text="当需要条件化审批人时使用，存储条件与审批人配置的映射。格式: [{condition_group, condition_relation, conditions, approvers_config}]")

    # 节点级抄送人配置（普通审批节点也可配置抄送人）
    cc_type = models.SmallIntegerField(null=True, blank=True, verbose_name="抄送人类型", help_text="1=指定角色,2=指定部门,3=部门负责人,4=指定人员,5=发起人,6=自定义审批组")
    cc_role = models.ForeignKey('mysystem.Role', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="抄送角色", related_name='cc_workflow_steps')
    cc_dept = models.JSONField(null=True, blank=True, verbose_name="抄送部门", help_text="存储部门ID列表")
    cc_users = models.ManyToManyField('mysystem.Users', blank=True, related_name='cc_workflow_steps', verbose_name="抄送人员")
    # 抄送审批组（当 cc_type=6 时使用），抄送人随审批组成员动态更新
    cc_group = models.ForeignKey('ApprovalGroup', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='cc_steps', verbose_name="抄送审批组")

    # 产品线标识（用于区分不同产品线的确认节点，如 RC、EMIR&Grid、STA、Phybolt）
    product_line = models.CharField(max_length=100, null=True, blank=True, verbose_name="产品线", help_text="标识该节点所属的产品线，如 RC、EMIR&Grid、STA、Phybolt")

    # 产品线抄送规则 (JSON格式，用于发起人确认节点根据产品线判断抄送人)
    # 格式: [{"product_line": "RC", "cc_type": 1, "cc_role": 1, "cc_dept": [1], "cc_users": [1,2], "cc_group": 1}, ...]
    product_line_cc_rules = models.JSONField(null=True, blank=True, verbose_name="产品线抄送规则",
                                             help_text="当approver_type=7（发起人）时使用，根据已完成的产品线节点确定抄送人。格式: [{product_line, cc_type, cc_role, cc_dept, cc_users, cc_group}]，cc_type=6时使用cc_group引用自定义审批组")

    # 自动跳过审批配置（JSON格式）
    # 当发起人满足指定条件时，自动跳过当前审批节点，直接流转到目标步骤
    # 格式: {"enabled": true, "skip_conditions": {"is_dept_owner": true, "specified_users": [1,2], "specified_roles": [1]}, "target_step_id": 5}
    skip_approval_config = models.JSONField(null=True, blank=True, verbose_name="自动跳过审批配置",
                                            help_text="当发起人满足条件时自动跳过审批。格式: {enabled, skip_conditions: {is_dept_owner, specified_users, specified_roles}, target_step_id}")

    class Meta:
        db_table = 'lyworkflow_step'
        verbose_name = '流程步骤（节点配置）'
        verbose_name_plural = verbose_name
        ordering = ('step_order',)

    def __str__(self):
        return f'{self.workflow_type.name} - {self.step_name}'


class WorkflowCC(CoreModel):
    """流程抄送配置"""
    CC_TYPE_CHOICES = (
        (1, '指定角色'),
        (2, '指定部门'),
        (3, '部门负责人'),
        (4, '指定人员'),
        (5, '发起人'),
        (6, '自定义审批组'),
    )

    workflow_type = models.ForeignKey(WorkflowType, on_delete=models.CASCADE, verbose_name="流程类型", related_name='cc_configs')
    step = models.ForeignKey(WorkflowStep, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="关联步骤（为空表示全局抄送）")

    cc_type = models.SmallIntegerField(choices=CC_TYPE_CHOICES, verbose_name="抄送人类型")
    cc_role = models.ForeignKey('mysystem.Role', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="抄送角色")
    cc_dept = models.JSONField(null=True, blank=True, verbose_name="抄送部门", help_text="存储部门ID列表，如 [1, 2] 或单个ID")
    cc_users = models.ManyToManyField('mysystem.Users', blank=True, related_name='cc_workflow_configs', verbose_name="抄送人员")
    # 抄送审批组（当 cc_type=6 时使用），抄送人随审批组成员动态更新
    cc_group = models.ForeignKey('ApprovalGroup', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='cc_configs', verbose_name="抄送审批组")

    # 抄送人员是否可以审批
    can_approve = models.BooleanField(default=True, verbose_name="是否可审批")

    class Meta:
        db_table = 'lyworkflow_cc'
        verbose_name = '流程抄送配置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.workflow_type.name} - 抄送配置'


class WorkflowInstance(CoreModel):
    """流程实例"""
    STATUS_CHOICES = (
        (0, '草稿'),
        (1, '审批中'),
        (2, '已通过'),
        (3, '已驳回'),
        (4, '已撤回'),
        (5, '已取消'),
        (6, '已退回'),
    )

    instance_no = models.CharField(max_length=50, unique=True, verbose_name="流程编号")
    workflow_type = models.ForeignKey(WorkflowType, on_delete=models.CASCADE, verbose_name="流程类型")
    title = models.CharField(max_length=200, verbose_name="流程标题")
    applicant = models.ForeignKey('mysystem.Users', on_delete=models.CASCADE, verbose_name="申请人", related_name='workflow_instances')
    applicant_dept = models.ForeignKey('mysystem.Dept', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="申请部门")

    # 流程状态
    status = models.SmallIntegerField(default=0, choices=STATUS_CHOICES, verbose_name="流程状态")

    current_step = models.IntegerField(default=1, verbose_name="当前步骤")  # 整数，表示原始步骤顺序
    total_steps = models.IntegerField(default=0, verbose_name="总步骤数")

    # 提交轮次：每次提交(含重新提交)+1，用于区分重新发起后新旧两轮任务记录
    submit_round = models.IntegerField(default=0, verbose_name="提交轮次")

    # 申请数据（JSON格式，支持不同类型的申请表单）
    form_data = models.JSONField(null=True, blank=True, verbose_name="表单数据")
    
    # 申请人自选审批人（JSON格式，存储每个节点选择的审批人ID列表）
    selected_approvers = models.JSONField(null=True, blank=True, verbose_name="申请人自选审批人")

    # 备注
    remark = models.TextField(null=True, blank=True, verbose_name="备注")

    class Meta:
        db_table = 'lyworkflow_instance'
        verbose_name = '流程实例'
        verbose_name_plural = verbose_name
        ordering = ('-create_datetime',)

    def __str__(self):
        return f'{self.instance_no} - {self.title}'


class WorkflowTask(CoreModel):
    """审批任务"""
    TASK_STATUS_CHOICES = (
        (0, '待审批'),
        (1, '已通过'),
        (2, '已驳回'),
        (3, '已退回'),
    )

    APPROVE_CHOICES = (
        (0, '未审批'),
        (1, '通过'),
        (2, '驳回'),
        (3, '退回'),
    )

    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, verbose_name="流程实例", related_name='tasks')
    step = models.ForeignKey(WorkflowStep, on_delete=models.CASCADE, verbose_name="流程步骤")
    step_order = models.IntegerField(verbose_name="步骤顺序")  # 整数，表示原始步骤顺序
    level_order = models.IntegerField(default=0, verbose_name="层级顺序", help_text="多级审批时使用，如 1, 2, 3；普通步骤为 0")

    approver = models.ForeignKey('mysystem.Users', on_delete=models.CASCADE, verbose_name="审批人", related_name='workflow_tasks')

    # 任务状态
    status = models.SmallIntegerField(default=0, choices=TASK_STATUS_CHOICES, verbose_name="任务状态")

    # 任务所属提交轮次（与流程实例 submit_round 对应，重新发起后旧轮任务不参与当前展示）
    round = models.IntegerField(default=0, verbose_name="提交轮次")

    # 审批结果
    approve_result = models.SmallIntegerField(default=0, choices=APPROVE_CHOICES, verbose_name="审批结果")
    approve_comment = models.TextField(null=True, blank=True, verbose_name="审批意见")
    approve_time = models.DateTimeField(null=True, blank=True, verbose_name="审批时间")

    is_cc = models.BooleanField(default=False, verbose_name="是否抄送人员")

    class Meta:
        db_table = 'lyworkflow_task'
        verbose_name = '审批任务'
        verbose_name_plural = verbose_name
        ordering = ('step_order', 'create_datetime')

    def __str__(self):
        return f'{self.instance.instance_no} - {self.step.step_name} - {self.approver.name}'


class WorkflowCCInstance(CoreModel):
    """流程抄送实例"""
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, verbose_name="流程实例", related_name='cc_instances')
    cc_user = models.ForeignKey('mysystem.Users', on_delete=models.CASCADE, verbose_name="抄送人员", related_name='workflow_cc_instances')
    step = models.ForeignKey(WorkflowStep, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="关联步骤")
    notify_time = models.DateTimeField(auto_now_add=True, verbose_name="通知时间")
    is_read = models.BooleanField(default=False, verbose_name="是否已读")

    class Meta:
        db_table = 'lyworkflow_cc_instance'
        verbose_name = '流程抄送实例'
        verbose_name_plural = verbose_name
        ordering = ('-notify_time',)

    def __str__(self):
        return f'{self.instance.instance_no} - {self.cc_user.name}'


class WorkflowComment(CoreModel):
    """审批节点评论（可在任意节点下发表评论，邮件通知当前待审批节点的审批人）"""
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, verbose_name="流程实例", related_name='comments')
    task = models.ForeignKey(WorkflowTask, on_delete=models.CASCADE, verbose_name="关联审批任务", related_name='comments')
    user = models.ForeignKey('mysystem.Users', on_delete=models.CASCADE, verbose_name="评论人", related_name='workflow_comments')
    content = models.TextField(verbose_name="评论内容")
    # 附件列表：存储 [{name: 原始文件名, path: 相对MEDIA_ROOT路径, size: 文件大小(字节)}]
    attachments = models.JSONField(null=True, blank=True, verbose_name="附件列表", help_text='附件信息列表：[{"name": "原始文件名", "path": "相对media路径", "size": "文件大小"}]')

    class Meta:
        db_table = 'lyworkflow_comment'
        verbose_name = '审批评论'
        verbose_name_plural = verbose_name
        ordering = ('create_datetime',)

    def __str__(self):
        return f'{self.instance.instance_no} - {self.user.name} - {self.content[:20]}'


class WorkflowLog(CoreModel):
    """流程操作日志"""
    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, verbose_name="流程实例", related_name='logs')
    operator = models.ForeignKey('mysystem.Users', on_delete=models.CASCADE, verbose_name="操作人", related_name='workflow_logs')
    action = models.CharField(max_length=50, verbose_name="操作类型")
    action_desc = models.CharField(max_length=200, verbose_name="操作描述")
    remark = models.TextField(null=True, blank=True, verbose_name="备注")

    class Meta:
        db_table = 'lyworkflow_log'
        verbose_name = '流程操作日志'
        verbose_name_plural = verbose_name
        ordering = ('-create_datetime',)

    def __str__(self):
        return f'{self.instance.instance_no} - {self.action} - {self.operator.name}'
