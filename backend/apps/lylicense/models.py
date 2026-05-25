from django.db import models
from utils.models import BaseModel, CoreModel
import os


class LicenseApplication(BaseModel):
    """
    License申请表
    从JSON文件解析后存储申请信息
    """
    APPLICATION_TYPE = (
        ('flexnet', 'FlexNet'),
        ('bitanswer', 'Bitanswer'),
    )
    
    STATUS = (
        (3, '待制作'),
        (2, '制作中'),
        (1, '制作成功'),
        (0, '制作失败'),
    )
    
    # 申请人信息
    applicant = models.CharField(max_length=100, verbose_name="申请人")
    applicant_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="申请人ID")
    
    # License类型
    application_type = models.CharField(max_length=20, choices=APPLICATION_TYPE, verbose_name="License类型")
    
    # 功能特性
    feature = models.JSONField(null=True, blank=True, verbose_name="Feature列表")  # 存储 Feature 名称列表
    product = models.CharField(max_length=200, null=True, blank=True, verbose_name="产品名称")
    serial_number = models.CharField(max_length=100, null=True, blank=True, verbose_name="序列号")
    keyword = models.CharField(max_length=200, null=True, blank=True, verbose_name="关键字/匹配标识")  # 用于与映射表中的selectField字段匹配
    
    # 客户信息
    customer_name = models.CharField(max_length=200, verbose_name="客户名称")
    mac_address = models.CharField(max_length=100, verbose_name="MAC Address/HostID")
    hostname = models.CharField(max_length=200, null=True, blank=True, verbose_name="主机名")
    
    # 授权信息
    start_time = models.DateField(null=True, blank=True, verbose_name="开始时间")
    end_time = models.DateField(null=True, blank=True, verbose_name="结束时间")
    quantity = models.JSONField(null=True, blank=True, verbose_name="授权数量")  # 存储 Feature 数量字典，如 {"GloryEX": 10, "GloryEX_Basic": 5}
    
    # JSON原始数据
    json_data = models.JSONField(null=True, blank=True, verbose_name="JSON原始数据")
    
    # 制作状态
    status = models.IntegerField(default=0, choices=STATUS, verbose_name="状态")
    
    # 失败原因
    fail_reason = models.TextField(null=True, blank=True, verbose_name="失败原因")
    retry_count = models.IntegerField(default=0, verbose_name="重试次数")
    max_retry_count = models.IntegerField(default=3, verbose_name="最大重试次数")
    
    class Meta:
        db_table = 'lylicense_application'
        verbose_name = "License申请"
        verbose_name_plural = verbose_name
        ordering = ['-create_datetime']

class LicenseRecord(BaseModel):
    """
    License制作记录表
    存储制作完成后的License详细信息
    """
    LICENSE_TYPE = (
        ('flexnet', 'FlexNet'),
        ('bitanswer', 'Bitanswer'),
    )
    
    STATUS = (
        (1, '有效'),
        (2, '已过期'),
        (3, '即将到期'),
        (0, '已撤销'),
    )
    
    # 关联申请
    application = models.ForeignKey(LicenseApplication, on_delete=models.CASCADE, verbose_name="关联申请", related_name='licenses')
    
    # 基本信息
    license_id = models.CharField(max_length=100, unique=True, verbose_name="License ID")
    license_type = models.CharField(max_length=20, choices=LICENSE_TYPE, verbose_name="类型")
    file_name = models.CharField(max_length=200, verbose_name="文件名称")
    file_relative_path = models.CharField(max_length=500, verbose_name="文件相对路径")
    directory = models.CharField(max_length=500, verbose_name="目录")
    full_path = models.CharField(max_length=500, verbose_name="完整路径")
    
    # License详细信息
    feature = models.CharField(max_length=500, verbose_name="Feature")
    vendor = models.CharField(max_length=200, null=True, blank=True, verbose_name="Vendor")
    version = models.CharField(max_length=50, null=True, blank=True, verbose_name="Version")
    host_id = models.CharField(max_length=100, verbose_name="HostID")
    
    # 时间信息
    start_time = models.DateField(verbose_name="开始时间")
    end_time = models.DateField(verbose_name="过期时间")
    start_date_str = models.CharField(max_length=50, null=True, blank=True, verbose_name="开始日期(格式化)")  # 格式: 2024年01月15日
    end_date_str = models.CharField(max_length=50, null=True, blank=True, verbose_name="过期日期(格式化)")  # 格式: 2024年01月15日
    remaining_days = models.IntegerField(default=0, verbose_name="剩余天数")
    
    # 授权信息
    quantity = models.IntegerField(default=1, verbose_name="授权数量")
    
    # 状态
    status = models.IntegerField(default=0, choices=STATUS, verbose_name="状态")
    
    # 其他信息
    extra_info = models.JSONField(null=True, blank=True, verbose_name="额外信息")
    
    class Meta:
        db_table = 'lylicense_record'
        verbose_name = "License记录"
        verbose_name_plural = verbose_name
        ordering = ['-create_datetime']
    
    def save(self, *args, **kwargs):
        """保存时自动计算剩余天数和格式化日期"""
        from datetime import datetime
        
        # 项目USE_TZ=False，使用本地时间
        if self.end_time:
            now = datetime.now()
            delta = self.end_time - now
            self.remaining_days = max(0, delta.days)
        
        # 格式化日期为"年月日"格式
        if self.start_time:
            self.start_date_str = self.start_time.strftime('%Y年%m月%d日')
        
        if self.end_time:
            self.end_date_str = self.end_time.strftime('%Y年%m月%d日')
        
        super().save(*args, **kwargs)


class LicenseFieldMapping(CoreModel):
    """
    License字段映射表
    用于将JSON中的字段映射为新的JSON格式中的真实key
    """
    
    # 重写id字段为自增主键
    id = models.BigAutoField(primary_key=True, verbose_name='ID')
    
    # License类型
    LICENSE_TYPE = (
        ('bitanswer', 'Bitanswer'),
        ('flexnet', 'FlexNet'),
    )
    
    # 用户类型（申请时用的类型）
    USER_TYPE = (
        ('internal', '内部'),
        ('external', '外部'),
    )
    
    # 字段类型枚举
    FIELD_TYPE = (
        ('feature', 'Feature'),
        ('customer_info', 'CustomerInfo'),
        ('applicant_info', 'ApplicantInfo'),
        ('common', 'Common'),
    )
    
    # 字段映射信息
    license_type = models.CharField(max_length=20, choices=LICENSE_TYPE, verbose_name="License类型")
    user_type = models.CharField(max_length=20, choices=USER_TYPE, verbose_name="用户类型")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE, default='common', verbose_name="字段类型")
    field = models.CharField(max_length=100, verbose_name="原始字段名")
    name = models.CharField(max_length=200, verbose_name="字段含义")
    real_key = models.CharField(max_length=100, verbose_name="映射后的真实key")
    remark = models.TextField(null=True, blank=True, verbose_name="备注")
    
    # 是否废弃
    is_deleted = models.BooleanField(default=False, verbose_name="是否废弃")
    
    # 覆盖基类字段，隐藏 dept_belong_id
    dept_belong_id = None
    
    class Meta:
        db_table = 'lylicense_field_mapping'
        verbose_name = "License字段映射"
        verbose_name_plural = verbose_name
        ordering = ['license_type', 'user_type', 'field_type', 'field']
        unique_together = ['license_type', 'user_type', 'field']
    
    def __str__(self):
        return f"{self.get_license_type_display()} - {self.get_user_type_display()} - {self.field}"
