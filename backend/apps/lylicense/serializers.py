from rest_framework import serializers
from utils.serializers import CustomModelSerializer
from apps.lylicense.models import LicenseApplication, LicenseRecord, LicenseFieldMapping


class LicenseApplicationSerializer(CustomModelSerializer):
    """
    License申请-序列化器
    """
    application_type_display = serializers.SerializerMethodField(read_only=True)
    status_display = serializers.SerializerMethodField(read_only=True)
    user_info_list = serializers.SerializerMethodField(read_only=True)
    
    def get_application_type_display(self, obj):
        return obj.get_application_type_display()
    
    def get_status_display(self, obj):
        return obj.get_status_display()
    
    def get_user_info_list(self, obj):
        """
        提取并格式化 user_info_list 数据
        ✅ 【修复】对所有有 user_info_list 的数据都进行格式化，不仅限于产品组
        ✅ 【新增】智能处理公共部分（GloryEX/GloryEX3D-公共部分）的产品归属
        
        【数据来源】直接从数据库的 user_info_list 字段读取（已存储转换后的 UserInfo）
        """
        # ✅ 直接从数据库字段读取
        if not obj.user_info_list or not isinstance(obj.user_info_list, list):
            return []
        
        user_info_list = obj.user_info_list
        
        # ✅ 【关键修复】获取当前申请的主要产品类型
        current_product = obj.product or ''
        
        # ✅ 【新增】定义公共部分产品的映射关系
        # 当选择 GloryEX3D 时，将 product="GloryEX" 的公共部分也归入 GloryEX3D
        public_part_mapping = {
            'GloryEX': ['GloryEX', 'GloryEX3D'],  # GloryEX 的公共部分可以用于这两个产品
            'GloryEX3D': ['GloryEX3D', 'GloryEX'],  # GloryEX3D 的公共部分也可以用于这两个产品
        }
        
        # ✅ 【关键修复】对所有有 user_info_list 的数据都进行格式化
        formatted_list = []
        for user_info in user_info_list:
            product = user_info.get('Product', '')
            start_timestamp = user_info.get('Startdate', 0)
            end_timestamp = user_info.get('Expirydate', 0)
            
            # 转换时间戳为日期字符串
            from datetime import datetime, date
            start_date_str = ''
            end_date_str = ''
            remaining_days = 0
            
            if start_timestamp and isinstance(start_timestamp, (int, float)):
                try:
                    start_date_str = datetime.fromtimestamp(start_timestamp / 1000).strftime('%Y-%m-%d')
                except:
                    pass
            
            if end_timestamp and isinstance(end_timestamp, (int, float)):
                try:
                    end_date_str = datetime.fromtimestamp(end_timestamp / 1000).strftime('%Y-%m-%d')
                    
                    # ✅ 计算该产品的剩余天数
                    expiry_date = datetime.fromtimestamp(end_timestamp / 1000).date()
                    today = date.today()
                    delta = expiry_date - today
                    remaining_days = max(0, delta.days)  # 确保不为负数
                except:
                    pass
            
            # ✅ 【关键修复】提取该产品的 features 信息
            # user_info 的结构：{'Product': 'GloryEX', 'Startdate': ts, 'Expirydate': ts, 'GloryEX': {'feat1': 10, ...}}
            product_features = user_info.get(product, {})
            
            # ✅ 【新增】智能处理公共部分：如果当前产品是 GloryEX3D，但 user_info 中的 product 是 GloryEX
            # 且这是公共部分的 feature，则将其视为当前产品的一部分
            display_product = product  # 默认使用原始 product
            if current_product and product != current_product:
                # 检查是否属于公共部分映射
                if product in public_part_mapping:
                    valid_products = public_part_mapping[product]
                    if current_product in valid_products:
                        # 这是公共部分，且当前产品可以使用它
                        # 尝试从 user_info 中获取当前产品的 features
                        if current_product in user_info:
                            display_product = current_product
                            product_features = user_info[current_product]
                        else:
                            # 如果当前产品在 user_info 中没有对应的 features，说明这个公共部分不属于当前产品
                            # 但仍保留在列表中，只是标记为其他产品
                            pass
            
            formatted_list.append({
                'product': display_product,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'remaining_days': remaining_days,  # ✅ 添加每个产品的剩余天数
                'keyword': user_info.get('Keyword', ''),
                'mac_address': user_info.get('MacAddress', ''),
                'hostname': user_info.get('Hostname', ''),
                'features': product_features  # ✅ 添加该产品的 features
            })
        
        return formatted_list
    
    class Meta:
        model = LicenseApplication
        read_only_fields = ["id"]
        fields = [
            'id', 'applicant', 'applicant_id', 'application_type', 'feature',
            'product', 'serial_number', 'keyword', 'customer_name', 'mac_address', 'hostname',
            'start_time', 'end_time', 'quantity',
            'json_data', 'status', 'fail_reason', 'retry_count', 'max_retry_count',
            'application_type_display', 'status_display', 'user_info_list',
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
    remaining_days = serializers.SerializerMethodField(read_only=True)
    user_info_list = serializers.SerializerMethodField(read_only=True)
    
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
    
    def get_remaining_days(self, obj):
        """动态计算剩余天数（基于当前日期）"""
        from datetime import date
        
        if not obj.end_time:
            return 0
        
        # 使用当前日期计算剩余天数
        now = date.today()
        delta = obj.end_time - now
        return max(0, delta.days)
    
    def get_user_info_list(self, obj):
        """
        提取并格式化 user_info_list 数据（从关联的申请记录中获取）
        ✅ 【修复】对所有有 user_info_list 的数据都进行格式化，不仅限于产品组
        ✅ 【新增】智能处理公共部分（GloryEX/GloryEX3D-公共部分）的产品归属
        
        【数据来源】直接从申请记录的 user_info_list 字段读取（已存储转换后的 UserInfo）
        """
        if not obj.application or not obj.application.user_info_list or not isinstance(obj.application.user_info_list, list):
            return []
        
        user_info_list = obj.application.user_info_list
        
        # ✅ 【关键修复】获取当前申请的主要产品类型
        current_product = obj.application.product or ''
        
        # ✅ 【新增】定义公共部分产品的映射关系
        # 当选择 GloryEX3D 时，将 product="GloryEX" 的公共部分也归入 GloryEX3D
        public_part_mapping = {
            'GloryEX': ['GloryEX', 'GloryEX3D'],  # GloryEX 的公共部分可以用于这两个产品
            'GloryEX3D': ['GloryEX3D', 'GloryEX'],  # GloryEX3D 的公共部分也可以用于这两个产品
        }
        
        # ✅ 调试日志：输出原始数据结构
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[制作记录序列化器] application.id={obj.application.id}")
        logger.info(f"[制作记录序列化器] user_info_list 原始数据: {user_info_list}")
        
        # ✅ 【关键修复】对所有有 user_info_list 的数据都进行格式化
        formatted_list = []
        for user_info in user_info_list:
            product = user_info.get('Product', '')
            start_timestamp = user_info.get('Startdate', 0)
            end_timestamp = user_info.get('Expirydate', 0)
            
            # 转换时间戳为日期字符串
            from datetime import datetime, date
            start_date_str = ''
            end_date_str = ''
            remaining_days = 0
            
            if start_timestamp and isinstance(start_timestamp, (int, float)):
                try:
                    start_date_str = datetime.fromtimestamp(start_timestamp / 1000).strftime('%Y-%m-%d')
                except:
                    pass
            
            if end_timestamp and isinstance(end_timestamp, (int, float)):
                try:
                    end_date_str = datetime.fromtimestamp(end_timestamp / 1000).strftime('%Y-%m-%d')
                    
                    # ✅ 计算该产品的剩余天数
                    expiry_date = datetime.fromtimestamp(end_timestamp / 1000).date()
                    today = date.today()
                    delta = expiry_date - today
                    remaining_days = max(0, delta.days)  # 确保不为负数
                except:
                    pass
            
            # ✅ 【关键修复】提取该产品的 features 信息
            # user_info 的结构：{'Product': 'GloryEX', 'Startdate': ts, 'Expirydate': ts, 'GloryEX': {'feat1': 10, ...}}
            product_features = user_info.get(product, {})
            
            # ✅ 【新增】智能处理公共部分：如果当前产品是 GloryEX3D，但 user_info 中的 product 是 GloryEX
            # 且这是公共部分的 feature，则将其视为当前产品的一部分
            display_product = product  # 默认使用原始 product
            if current_product and product != current_product:
                # 检查是否属于公共部分映射
                if product in public_part_mapping:
                    valid_products = public_part_mapping[product]
                    if current_product in valid_products:
                        # 这是公共部分，且当前产品可以使用它
                        # 尝试从 user_info 中获取当前产品的 features
                        if current_product in user_info:
                            display_product = current_product
                            product_features = user_info[current_product]
                        else:
                            # 如果当前产品在 user_info 中没有对应的 features，说明这个公共部分不属于当前产品
                            # 但仍保留在列表中，只是标记为其他产品
                            pass
            
            formatted_list.append({
                'product': display_product,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'remaining_days': remaining_days,  # ✅ 添加每个产品的剩余天数
                'keyword': user_info.get('Keyword', ''),
                'mac_address': user_info.get('MacAddress', ''),
                'hostname': user_info.get('Hostname', ''),
                'features': product_features  # ✅ 添加该产品的 features
            })
        
        logger.info(f"[制作记录序列化器] 格式化后数据: {formatted_list}")
        return formatted_list
    
    class Meta:
        model = LicenseRecord
        read_only_fields = ["id"]
        fields = [
            'id', 'application', 'license_id', 'license_type', 'file_name',
            'file_relative_path', 'directory', 'full_path', 'feature', 'vendor',
            'version', 'host_id', 'start_time', 'end_time', 'start_date_str', 'end_date_str',
            'remaining_days', 'quantity', 'status', 'extra_info',
            'license_type_display', 'status_display', 'applicant', 'customer_name', 'user_info_list',
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
