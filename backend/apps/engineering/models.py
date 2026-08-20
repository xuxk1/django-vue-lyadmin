from django.conf import settings
from django.db import models
from utils.models import CoreModel


class PackageBuild(CoreModel):
    """打包构建记录"""
    BUILD_STATUS_CHOICES = (
        (0, '构建中'),
        (1, '成功'),
        (2, '失败'),
        (3, '未构建'),
    )

    BUILD_TYPE_CHOICES = (
        ('Release', 'Release'),
        ('Debug', 'Debug'),
        ('Test', 'Test'),
    )

    DELIVERY_WORKFLOW_STATUS_CHOICES = (
        (0, '未启用/待发起'),
        (1, '已自动发起'),
        (2, '自动发起失败'),
    )

    # 项目信息
    project_name = models.CharField(max_length=200, verbose_name="项目名称")
    project_version = models.CharField(max_length=50, null=True, blank=True, verbose_name="项目版本")
    build_type = models.CharField(max_length=20, default='Release', choices=BUILD_TYPE_CHOICES, verbose_name="构建类型")

    # Jenkins信息
    jenkins_job_name = models.CharField(max_length=200, verbose_name="Jenkins任务名称")
    jenkins_build_number = models.IntegerField(null=True, blank=True, verbose_name="Jenkins构建编号")
    jenkins_build_url = models.URLField(null=True, blank=True, verbose_name="Jenkins构建URL")

    # 构建状态
    build_status = models.SmallIntegerField(default=0, choices=BUILD_STATUS_CHOICES, verbose_name="构建状态")
    build_log = models.TextField(null=True, blank=True, verbose_name="构建日志")
    # 构建日志是否为完整全量（True=已全量拉取过；False=仅同步时的尾部摘要，详情页需从 Jenkins 全量拉取）
    build_log_complete = models.BooleanField(default=False, verbose_name="构建日志是否完整")

    # 构建参数
    build_params = models.JSONField(null=True, blank=True, verbose_name="构建参数")

    # 是否需要传包
    need_delivery = models.BooleanField(default=False, verbose_name="是否需要传包")

    # 自动传包时填写的"软件包(D包)发包流程"申请表单数据（构建成功后自动回填软件包存放路径并发起流程）
    delivery_form_data = models.JSONField(null=True, blank=True, verbose_name="发包审批表单数据")

    # 自动发起发包审批流状态：0=未启用/待发起, 1=已自动发起, 2=自动发起失败
    delivery_workflow_status = models.SmallIntegerField(default=0, choices=DELIVERY_WORKFLOW_STATUS_CHOICES, verbose_name="自动发起审批流状态")

    # 关联的审批流程实例（如果需要传包）
    workflow_instance = models.ForeignKey(
        'lyworkflow.WorkflowInstance',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name="关联审批流程",
        related_name='package_builds'
    )

    # 包安全扫描信息（提交审批流/发包时触发 package_security_scan 扫描后记录）
    scan_job_name = models.CharField(max_length=200, null=True, blank=True, verbose_name="扫描Jenkins任务名称")
    scan_build_number = models.IntegerField(null=True, blank=True, verbose_name="扫描Jenkins构建编号")
    scan_status = models.CharField(max_length=50, null=True, blank=True, verbose_name="包扫描状态")

    class Meta:
        db_table = 'engineering_package_build'
        verbose_name = '打包构建记录'
        verbose_name_plural = verbose_name
        ordering = ('-create_datetime',)

    def __str__(self):
        # 展示用项目名 + 构建编号：每次构建编号唯一，便于日志/下拉等区分同一项目的多次构建；
        # 构建编号可能为空（如从未构建），为空时不拼接，避免对象展示出现 'None' 占位
        if self.jenkins_build_number:
            return f'{self.project_name} - #{self.jenkins_build_number}'
        return self.project_name


class PackageProjectPermission(CoreModel):
    """打包项目可见性授权：控制 Jenkins 项目在打包管理列表中的可见范围

    按 Jenkins 任务名（job）维度存储，每个 job 一条记录；未授权项目默认仅管理员可见。
    可见规则：is_public（公共可见）或 部门/角色/用户 任一维度命中即可见。
    """

    job_name = models.CharField(max_length=200, unique=True, verbose_name="Jenkins任务名称", help_text="Jenkins任务名称")
    is_public = models.BooleanField(default=False, verbose_name="公共可见", help_text="勾选后所有用户可见")
    visible_depts = models.ManyToManyField(to='mysystem.Dept', db_constraint=False, blank=True,
                                           verbose_name="可见部门", help_text="可见部门")
    visible_roles = models.ManyToManyField(to='mysystem.Role', db_constraint=False, blank=True,
                                           verbose_name="可见角色", help_text="可见角色")
    visible_users = models.ManyToManyField(to=settings.AUTH_USER_MODEL, db_constraint=False, blank=True,
                                           verbose_name="可见用户", help_text="可见用户",
                                           related_name='visible_users_permissions')
    remark = models.TextField(null=True, blank=True, verbose_name="备注", help_text="备注")

    class Meta:
        db_table = 'engineering_package_project_permission'
        verbose_name = '打包项目可见性授权'
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.job_name
