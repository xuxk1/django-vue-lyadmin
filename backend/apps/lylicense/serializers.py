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
    class Meta:
        model = LicenseApplication
        read_only_fields = ["id"]
        fields = [
            'id', 'applicant', 'applicant_id', 'application_type', 'feature',
            'product', 'serial_number', 'keyword', 'customer_name', 'mac_address', 'hostname',
            'start_time', 'end_time', 'quantity',
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
    application_info = serializers.SerializerMethodField(read_only=True)
    
    def get_license_type_display(self, obj):
        return obj.get_license_type_display()
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    
    def get_application_info(self, obj):
        if obj.application:
            return {
                'id': obj.application.id,
                'applicant': obj.application.applicant,
                'customer_name': obj.application.customer_name
            }
        return None
    
    class Meta:
        model = LicenseRecord
        read_only_fields = ["id"]
        fields = [
            'id', 'application', 'license_id', 'license_type', 'file_name',
            'file_relative_path', 'directory', 'full_path', 'feature', 'vendor',
            'version', 'host_id', 'start_time', 'end_time', 'start_date_str', 'end_date_str',
            'remaining_days', 'quantity', 'status', 'extra_info',
            'license_type_display', 'status_display', 'application_info',
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
    creator_name = serializers.SerializerMethodField(read_only=True)
    
    def get_license_type_name(self, obj):
        return obj.get_license_type_display()
    
    def get_user_type_name(self, obj):
        return obj.get_user_type_display()
    
    def get_field_type_name(self, obj):
        return obj.get_field_type_display()
    
    def get_creator_name(self, obj):
        if obj.creator:
            return obj.creator.username
        return ''
    
    class Meta:
        model = LicenseFieldMapping
        read_only_fields = ["id"]
        fields = [
            'id', 'license_type', 'user_type', 'field_type', 'field', 'name', 'real_key', 'remark',
            'is_deleted', 'license_type_name', 'user_type_name', 'field_type_name',
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
            'id', 'license_type', 'user_type', 'field_type', 'field', 'name', 'real_key', 'remark',
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
            'id', 'license_type', 'user_type', 'field_type', 'field', 'name', 'real_key', 'remark',
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
