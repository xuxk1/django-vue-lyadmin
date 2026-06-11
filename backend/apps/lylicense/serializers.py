from rest_framework import serializers
from utils.serializers import CustomModelSerializer
from apps.lylicense.models import LicenseApplication, LicenseRecord, LicenseFieldMapping


class LicenseApplicationSerializer(CustomModelSerializer):
    """
    License申请-序列化器
    """
    application_type_display = serializers.SerializerMethodField(read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)
    
    def get_application_type_display(self, obj):
        return obj.get_application_type_display()
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    
    class Meta:
        model = LicenseApplication
        read_only_fields = ["id"]
        fields = [
            'id', 'applicant', 'applicant_id', 'application_type', 'feature',
            'product', 'serial_number', 'keyword', 'customer_name', 'mac_address', 'hostname',
            'start_time', 'end_time', 'quantity',
            'json_data', 'status', 'fail_reason', 'retry_count', 'max_retry_count',
            'application_type_display', 'status_display',
            'create_datetime', 'update_datetime'
        ]
        extra_kwargs = {
            'applicant': {'required': True},
            'application_type': {'required': True},
            'feature': {'required': True},
            'customer_name': {'required': True},
            'mac_address': {'required': True},
        }


class LicenseApplicationCreateSerializer(CustomModelSerializer):
    """
    License申请-新增序列化器
    """
    def validate_serial_number(self, value):
        """
        验证序列号唯一性
        """
        if value:
            # 检查是否已存在相同的序列号
            existing = LicenseApplication.objects.filter(serial_number=value).first()
            if existing:
                raise serializers.ValidationError(f'序列号 {value} 已被使用，申请记录ID: {existing.id}')
        return value
    
    class Meta:
        model = LicenseApplication
        read_only_fields = ["id"]
        fields = [
            'id', 'applicant', 'applicant_id', 'application_type', 'feature',
            'product', 'serial_number', 'keyword', 'customer_name', 'mac_address', 'hostname',
            'start_time', 'end_time', 'quantity', 'file_hash',
            'json_data', 'status', 'fail_reason', 'retry_count', 'max_retry_count',
            'create_datetime', 'update_datetime'
        ]
        extra_kwargs = {
            'applicant': {'required': True},
            'application_type': {'required': True},
            'feature': {'required': True},
            'customer_name': {'required': True},
            'mac_address': {'required': True},
        }


class LicenseRecordSerializer(CustomModelSerializer):
    """
    License记录-序列化器
    """
    license_type_display = serializers.SerializerMethodField(read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)
    applicant = serializers.SerializerMethodField(read_only=True)
    customer_name = serializers.SerializerMethodField(read_only=True)
    
    def get_license_type_display(self, obj):
        return obj.get_license_type_display()
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    
    def get_applicant(self, obj):
        """获取申请人（从关联的申请记录中获取）"""
        if obj.application:
            return obj.application.applicant
        return ''
    
    def get_customer_name(self, obj):
        """获取客户名称（从关联的申请记录中获取）"""
        if obj.application:
            return obj.application.customer_name
        return ''
    
    class Meta:
        model = LicenseRecord
        read_only_fields = ["id"]
        fields = [
            'id', 'application', 'license_id', 'license_type', 'file_name',
            'file_relative_path', 'directory', 'full_path', 'feature', 'vendor',
            'version', 'host_id', 'start_time', 'end_time', 'start_date_str', 'end_date_str',
            'remaining_days', 'quantity', 'status', 'extra_info',
            'license_type_display', 'status_display', 'applicant', 'customer_name',
            'create_datetime', 'update_datetime'
        ]
        extra_kwargs = {
            'application': {'required': True},
            'license_id': {'required': True},
            'license_type': {'required': True},
            'file_name': {'required': True},
            'feature': {'required': True},
            'host_id': {'required': True},
            'start_time': {'required': True},
            'end_time': {'required': True},
        }


class LicenseFieldMappingSerializer(CustomModelSerializer):
    """
    License字段映射-序列化器
    """
    license_type_name = serializers.SerializerMethodField(read_only=True)
    user_type_name = serializers.SerializerMethodField(read_only=True)
    field_type_name = serializers.SerializerMethodField(read_only=True)
    product_name = serializers.SerializerMethodField(read_only=True)
    creator_name = serializers.SerializerMethodField(read_only=True)
    
    def get_license_type_name(self, obj):
        return obj.get_license_type_display()
    
    def get_user_type_name(self, obj):
        return obj.get_user_type_display()
    
    def get_field_type_name(self, obj):
        return obj.get_field_type_display()
    
    def get_product_name(self, obj):
        return obj.product or ''
    
    def get_creator_name(self, obj):
        if obj.creator:
            return obj.creator.username
        return ''
    
    class Meta:
        model = LicenseFieldMapping
        read_only_fields = ["id"]
        fields = [
            'id', 'license_type', 'user_type', 'product', 'field_type', 'field', 'name', 'real_key', 'remark',
            'is_deleted', 'license_type_name', 'user_type_name', 'product_name', 'field_type_name',
            'create_datetime', 'update_datetime',
            'creator', 'creator_name'
        ]
        extra_kwargs = {
            'license_type': {'required': True},
            'user_type': {'required': True},
            'field_type': {'required': True},
            'field': {'required': True},
            'name': {'required': True},
            'real_key': {'required': True},
        }


class LicenseFieldMappingCreateSerializer(CustomModelSerializer):
    """
    License字段映射-新增序列化器
    """
    def validate(self, attrs):
        """验证字段唯一性"""
        license_type = attrs.get('license_type')
        user_type = attrs.get('user_type')
        field = attrs.get('field')
        
        # 检查是否存在相同的 license_type + user_type + field 组合
        if LicenseFieldMapping.objects.filter(
            license_type=license_type,
            user_type=user_type,
            field=field,
            is_deleted=False
        ).exists():
            raise serializers.ValidationError(
                f'字段名 "{field}" 在 {license_type} - {user_type} 类型中已存在，请勿重复添加！'
            )
        
        return attrs
    
    class Meta:
        model = LicenseFieldMapping
        read_only_fields = ["id"]
        fields = [
            'id', 'license_type', 'user_type', 'product', 'field_type', 'field', 'name', 'real_key', 'remark',
            'is_deleted',
            'create_datetime', 'update_datetime',
            'creator', 'description'
        ]
        extra_kwargs = {
            'license_type': {'required': True},
            'user_type': {'required': True},
            'field_type': {'required': True},
            'field': {'required': True},
            'name': {'required': True},
            'real_key': {'required': True},
        }


class LicenseFieldMappingUpdateSerializer(CustomModelSerializer):
    """
    License字段映射-更新序列化器
    """
    class Meta:
        model = LicenseFieldMapping
        read_only_fields = ["id"]
        fields = [
            'id', 'license_type', 'user_type', 'product', 'field_type', 'field', 'name', 'real_key', 'remark',
            'is_deleted',
            'create_datetime', 'update_datetime',
            'creator', 'description'
        ]
        extra_kwargs = {
            'license_type': {'required': True},
            'user_type': {'required': True},
            'field_type': {'required': True},
            'field': {'required': True},
            'name': {'required': True},
            'real_key': {'required': True},
        }
