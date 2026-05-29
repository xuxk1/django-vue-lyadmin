import os
import json
import logging
from django.utils import timezone
from django.conf import settings
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as http_status
from utils.viewset import CustomModelViewSet
from utils.jsonResponse import SuccessResponse, ErrorResponse
from apps.lylicense.models import LicenseApplication, LicenseRecord, LicenseFieldMapping
from apps.lylicense.serializers import (
    LicenseApplicationSerializer, 
    LicenseApplicationCreateSerializer,
    LicenseRecordSerializer,
    LicenseFieldMappingSerializer,
    LicenseFieldMappingCreateSerializer,
    LicenseFieldMappingUpdateSerializer
)

logger = logging.getLogger(__name__)

# 全局变量：文件监听器实例
_file_watcher_observer = None

# 从Django settings中获取路径
BASE_DIR = settings.BASE_DIR
MEDIA_ROOT = settings.MEDIA_ROOT


def transform_json_with_mapping(raw_json, license_type, user_type='external'):
    """
    使用字段映射表转换JSON数据
    
    处理流程：
    1. 遍历原始 JSON FormList 中的所有字段
    2. 忽略 checkbox 和 association 开头的字段
    3. 过滤空值
    4. 对于每个有值的字段，去映射表中查找 field = 原始 key
    5. 获取对应的 real_key，用 real_key 作为新的 key 组装成新 JSON
    6. 特殊处理：如果字段是 numberField_xxx_value（含 _value 后缀）
       - 去掉 _value 得到 base_key（如 numberField_mdy73qey）
       - 用 base_key 去映射表查找
       - 如果 field_type 是 'feature'，则 real_key 就是 feature 名称
       - 将 _value 字段的值（授权数量）赋给这个 feature
       - 数量字段不添加到 transformed_data
    
    Args:
        raw_json: 原始JSON数据（字典）
            示例结构：{
                "FormList": {
                    "employeeField_me87gr4t": ["夏于皓"],
                    "numberField_mdy73qey": 21,
                    "numberField_mdy73qey_value": "21",
                    ...
                },
                "Usage": "sale",
                "LicenseType": "FLEXNET"
            }
        license_type: License类型 ('flexnet' 或 'bitanswer')
        user_type: 用户类型 ('internal' 或 'external')
    
    Returns:
        dict: 转换后的新JSON数据
            {
                'transformed_data': {...},  # 转换后的数据（使用 real_key）
                'usage': 'sale',
                'license_type': 'flexnet'
            }
    """
    # 获取该类型的所有字段映射
    mappings = LicenseFieldMapping.objects.filter(
        license_type=license_type,
        user_type=user_type,
        is_deleted=False
    ).all()
    
    # 构建映射字典: {原始field: {real_key, field_type, name, product}}
    field_mapping = {}
    for m in mappings:
        field_mapping[m.field] = {
            'real_key': m.real_key,
            'field_type': m.field_type,  # 'feature', 'customer_info', 'applicant_info', 'common'
            'name': m.name,
            'product': m.product or ''  # 新增：产品名称
        }
    
    # 提取并列字段
    form_list = raw_json.get('FormList', {})
    usage = raw_json.get('Usage', '')
    license_type = raw_json.get('LicenseType', '').lower()

    if usage:
        if usage == '内部':
            user_type = 'internal'
        elif usage == '外部':
            user_type = 'external'
    
    if not form_list:
        return {
            'transformed_data': {},
            'usage': user_type,
            'license_type': license_type
        }
    
    # 存储转换后的数据
    transformed_data = {}
    features = []  # Feature列表（真实的feature名称，来自 real_key）
    feature_values = {}  # Feature对应的数量值 {feature_name: quantity}
    
    # 新增：按 Product 分组 Feature
    product_features = {}  # {product_name: {feature_name: quantity}}
    product_set = set()  # 记录所有出现过的产品名称
    
    def is_empty_value(value):
        """判断值是否为空"""
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == '':
            return True
        if isinstance(value, list) and len(value) == 0:
            return True
        if isinstance(value, dict) and len(value) == 0:
            return True
        return False
    
    def should_ignore_key(key):
        """判断是否应该忽略该字段"""
        # 忽略 checkbox 开头的 key
        if key.startswith('checkbox'):
            return True
        # 忽略 association 开头的 key
        if key.startswith('association'):
            return True
        # 忽略 _id 结尾的 key
        # if key.endswith('_id'):
        #     return True
        # 忽略 _value 结尾的 key
        if key.endswith('_value'):
            return True
        return False
    
    def is_quantity_key(key):
        """判断是否为数量字段（含_value后缀）"""
        return key.endswith('_value')
    
    def transform_table_row(row_data):
        """
        转换表格中的一行数据
        
        Args:
            row_data: 表格行的字典数据
        
        Returns:
            dict: 转换后的行数据
        """
        transformed_row = {}
        
        if not isinstance(row_data, dict):
            return row_data
        
        # 提取 Product 字段（如果存在）
        current_product = None
        for key, value in row_data.items():
            if key in field_mapping:
                mapping_info = field_mapping[key]
                if mapping_info['real_key'] == 'Product' and value:
                    current_product = value
                    break
        
        for key, value in row_data.items():
            # 跳过应该忽略的字段
            if should_ignore_key(key):
                continue
            
            # 跳过空值
            if is_empty_value(value):
                continue
            
            # 检查是否在映射表中
            if key in field_mapping:
                mapping_info = field_mapping[key]
                real_key = mapping_info['real_key']
                field_type = mapping_info['field_type']
                product = mapping_info['product']
                
                # 如果是 Feature 类型（大小写不敏感）
                if field_type.lower() == 'feature':
                    feature_name = real_key
                    
                    # 使用映射表中的 product，如果没有则使用表格行中的 product
                    feature_product = product or current_product or 'Unknown'
                    
                    # 查找对应的数量字段
                    quantity_key = key + '_value'
                    quantity_value = row_data.get(quantity_key)
                    
                    quantity = 0
                    if quantity_value and not is_empty_value(quantity_value):
                        try:
                            quantity = int(quantity_value) if isinstance(quantity_value, str) else int(quantity_value)
                        except:
                            pass
                    
                    # 按产品分组 Feature
                    if feature_product not in product_features:
                        product_features[feature_product] = {}
                        product_set.add(feature_product)
                    
                    product_features[feature_product][feature_name] = quantity
                    
                    if feature_name not in features:
                        features.append(feature_name)
                    
                    transformed_row[real_key] = value
                else:
                    # 其他类型字段，使用 real_key
                    transformed_row[real_key] = value
            else:
                # 不在映射表中的字段，使用原 key（这是问题所在！）
                # 我们应该记录日志，帮助调试
                logger.warning(f"表格字段 {key} 不在映射表中，使用原始 key")
                transformed_row[key] = value
        
        return transformed_row
    
    # 第一步：处理所有非 _value 字段
    for key, value in form_list.items():
        # 跳过应该忽略的字段
        if should_ignore_key(key):
            continue
        
        # 跳过数量字段（第二步处理）
        if is_quantity_key(key):
            continue
        
        # 跳过空值
        if is_empty_value(value):
            continue
        
        # 检查是否在映射表中
        if key in field_mapping:
            mapping_info = field_mapping[key]
            real_key = mapping_info['real_key']
            field_type = mapping_info['field_type']
            
            # 如果是 Feature 类型（大小写不敏感）
            if field_type.lower() == 'feature':
                # 查找对应的数量字段（key + '_value'）
                quantity_key = key + '_value'
                quantity_value = form_list.get(quantity_key)
                
                # 提取 feature 名称（使用 real_key）
                feature_name = real_key
                
                # 获取 product（从映射表中）
                feature_product = mapping_info.get('product', '') or 'Unknown'
                
                quantity = 0
                if quantity_value and not is_empty_value(quantity_value):
                    try:
                        quantity = int(quantity_value) if isinstance(quantity_value, str) else int(quantity_value)
                    except:
                        pass
                
                # 按产品分组 Feature
                if feature_product not in product_features:
                    product_features[feature_product] = {}
                    product_set.add(feature_product)
                
                product_features[feature_product][feature_name] = quantity
                
                if feature_name not in features:
                    features.append(feature_name)
                
                # 保存到 transformed_data（使用 real_key 作为 key）
                transformed_data[real_key] = value
                
            else:
                # 其他类型（CustomerInfo, ApplicantInfo, Common）
                # 检查是否是表格字段（list 类型）
                if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                    # 这是一个表格字段，需要递归处理其中的每一项
                    
                    # real_key 就是表格的名称
                    table_real_key = real_key
                    
                    # 递归处理表格中的每一行
                    transformed_rows = []
                    for row_idx, row_data in enumerate(value):
                        if isinstance(row_data, dict):
                            transformed_row = transform_table_row(row_data)
                            transformed_rows.append(transformed_row)
                    
                    # 将转换后的表格数据添加到 transformed_data
                    if transformed_rows:
                        transformed_data[table_real_key] = transformed_rows
                else:
                    # 普通字段，直接保存，使用 real_key 作为 key
                    transformed_data[real_key] = value
        else:
            # 不在映射表中的字段，检查是否是表格字段（list 类型）
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                # 这是一个表格字段，需要递归处理其中的每一项
                print(f"\n检测到表格字段: {key}，包含 {len(value)} 条记录")
                
                # 先转换表格字段的 key
                table_real_key = key  # 默认使用原 key
                if key in field_mapping:
                    table_real_key = field_mapping[key]['real_key']
                
                # 递归处理表格中的每一行
                transformed_rows = []
                for row_idx, row_data in enumerate(value):
                    if isinstance(row_data, dict):
                        print(f"  处理第 {row_idx + 1} 行数据，原始 key: {list(row_data.keys())}")
                        transformed_row = transform_table_row(row_data)
                        transformed_rows.append(transformed_row)
                        print(f"  第 {row_idx + 1} 行转换后的数据: {json.dumps(transformed_row, ensure_ascii=False)}")
                
                # 将转换后的表格数据添加到 transformed_data
                if transformed_rows:
                    transformed_data[table_real_key] = transformed_rows
            else:
                # 普通字段，使用原 key
                transformed_data[key] = value
    
    # 第二步：处理 _value 字段（数量字段）
    for key, value in form_list.items():
        # 只处理 _value 字段
        if not is_quantity_key(key):
            continue
        
        # 跳过空值
        if is_empty_value(value):
            continue
        
        # 去掉 _value 后缀，查找对应的 feature
        base_key = key[:-6]  # 去掉 '_value'
        
        if base_key in field_mapping:
            mapping_info = field_mapping[base_key]
            if mapping_info['field_type'].lower() == 'feature':
                feature_name = mapping_info['real_key']
                feature_product = mapping_info.get('product', '') or 'Unknown'
                
                try:
                    quantity = int(value) if isinstance(value, str) else int(value)
                    
                    # 按产品分组 Feature
                    if feature_product not in product_features:
                        product_features[feature_product] = {}
                        product_set.add(feature_product)
                    
                    product_features[feature_product][feature_name] = quantity
                    
                    # 如果 features 列表中还没有这个 feature，添加它
                    if feature_name not in features:
                        features.append(feature_name)
                    
                    # 将非空的 _value 字段也添加到 transformed_data，使用 real_key
                    value_real_key = mapping_info['real_key'] + '_value'
                    transformed_data[value_real_key] = quantity
                except:
                    pass
        # 注意：只有非空的 _value 字段才会被添加到 transformed_data

    # 构建 feature_values：将 product_features 合并为一个字典
    # {"GloryEX": 21, "GloryEX-RC": 21, ...}
    for product, product_feats in product_features.items():
        for feat_name, feat_quantity in product_feats.items():
            feature_values[feat_name] = feat_quantity
    
    # 构建 UserInfo 结构
    user_info_list = []
    
    # 从 transformed_data 中提取 UserInfo 的基础信息（全局的，作为 fallback）
    mac_address = transformed_data.get('MacAddress', '')
    if mac_address:
        mac_address = mac_address.upper()
    hostname = transformed_data.get('Hostname', '')
    start_timestamp = transformed_data.get('Startdate', 0)
    end_timestamp = transformed_data.get('Expirydate', 0)
    product_name = transformed_data.get('Product', '')
    
    # 优先使用 product_features 构建 UserInfo（无论是否已有 UserInfo）
    if product_features and product_set:
        # 构建产品到基础信息的映射（从表格数据中提取）
        product_base_info = {}  # {product_name: {MacAddress, Hostname, Startdate, Expirydate}}
        
        # 从 transformed_data 中提取表格数据（如果有）
        for key, value in transformed_data.items():
            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                # 这是一个表格，遍历每一行提取产品信息
                for row in value:
                    if isinstance(row, dict):
                        product = row.get('Product')
                        if product and product in product_set:
                            if product not in product_base_info:
                                product_base_info[product] = {}
                            # 提取基础信息
                            if 'MacAddress' in row:
                                product_base_info[product]['MacAddress'] = row['MacAddress']
                            if 'Hostname' in row:
                                product_base_info[product]['Hostname'] = row['Hostname']
                            if 'Startdate' in row:
                                product_base_info[product]['Startdate'] = row['Startdate']
                            if 'Expirydate' in row:
                                product_base_info[product]['Expirydate'] = row['Expirydate']
        
        for product in product_set:
            # 使用产品对应的基础信息，如果没有则使用全局的
            base_info = product_base_info.get(product, {})
            user_info_entry = {
                # 'MacAddress': base_info.get('MacAddress', mac_address),
                'Hostname': base_info.get('Hostname', hostname),
                'Expirydate': base_info.get('Expirydate', end_timestamp),
                'Startdate': base_info.get('Startdate', start_timestamp),
                'Product': product,
            }
            
            # 将该产品对应的 features 添加到 UserInfo 中
            if product in product_features:
                user_info_entry[product] = product_features[product]
            
            user_info_list.append(user_info_entry)
    elif transformed_data.get('UserInfo'):  # 如果已经有 UserInfo 且没有 product_features，保留原样
        user_info_list = transformed_data.get('UserInfo', [])
    
    # 如果有 UserInfo，添加到 transformed_data
    if user_info_list:
        transformed_data['UserInfo'] = user_info_list
    
    # 返回结果
    result = {
        'transformed_data': transformed_data,
        'usage': usage,
        'license_type': license_type,
        'features': features,
        'feature_values': feature_values,
        'product_features': product_features,  # 新增：按产品分组的 Feature
        'product_set': list(product_set),  # 新增：所有产品名称列表
        'original_keys_count': len(form_list),
        'filtered_keys_count': len(transformed_data),
        'mapping_used': len(field_mapping),
        'success': True
    }
    
    return result


class LicenseApplicationViewSet(CustomModelViewSet):
    """
    License申请管理ViewSet
    """
    queryset = LicenseApplication.objects.all()
    serializer_class = LicenseApplicationSerializer
    create_serializer_class = LicenseApplicationCreateSerializer
    filterset_fields = ['applicant', 'application_type', 'customer_name', 'status']
    search_fields = ['applicant', 'customer_name', 'mac_address', 'feature']
    ordering_fields = ['create_datetime']
    ordering = '-create_datetime'
    # License模块不需要数据权限过滤
    extra_filter_backends = []
    
    @action(methods=['post'], detail=False)
    def scan_txt_files(self, request):
        """
        扫描固定目录中的TXT文件并创建License申请记录
        1. 从固定目录读取所有TXT文件
        2. 解析JSON数据
        3. 根据LicenseType判断类型
        4. 使用字段映射表转换key
        5. 过滤空值
        6. 创建申请记录
        """
        try:
            # 固定目录：BASE_DIR/license_txt_files
            txt_dir = os.path.join(BASE_DIR, 'license_txt_files')
            
            # 检查目录是否存在
            if not os.path.exists(txt_dir):
                return ErrorResponse(msg=f'TXT文件目录不存在: {txt_dir}')
            
            # 扫描目录中的所有.json文件
            txt_files = [f for f in os.listdir(txt_dir) if f.endswith('.json')]
            
            # 获取文件数量
            file_count = len(txt_files)
            logger.info(f'扫描到 {file_count} 个TXT文件，将逐个处理')
            
            if not txt_files:
                return SuccessResponse(data={'processed': 0}, msg='目录中没有找到TXT文件')
            
            results = []
            processed_count = 0
            error_count = 0
            
            # 逐个处理每个TXT文件
            for idx, txt_file in enumerate(txt_files, 1):
                logger.info(f'正在处理第 {idx}/{file_count} 个文件: {txt_file}')
                try:
                    file_path = os.path.join(txt_dir, txt_file)
                    
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    
                    # 解析JSON
                    try:
                        raw_json = json.loads(file_content)
                    except json.JSONDecodeError as e:
                        logger.error(f"文件 {txt_file} JSON解析失败: {str(e)}")
                        results.append({
                            'file': txt_file,
                            'status': 'error',
                            'message': f'JSON解析失败: {str(e)}'
                        })
                        error_count += 1
                        continue
                    
                    # 获取License类型
                    license_type_raw = raw_json.get('LicenseType', '').upper()
                    usage = raw_json.get('Usage', '').lower()
                    if usage == '内部':
                        user_type = 'internal'
                    elif usage == '外部':
                        user_type = 'external'
                    if license_type_raw == 'FLEXNET':
                        license_type = 'flexnet'
                    elif license_type_raw == 'BITANSWER':
                        license_type = 'bitanswer'
                    else:
                        logger.warning(f"文件 {txt_file} 不支持的License类型: {license_type_raw}")
                        results.append({
                            'file': txt_file,
                            'status': 'error',
                            'message': f'不支持的License类型: {license_type_raw}'
                        })
                        error_count += 1
                        continue
                    
                    # 使用字段映射表转换JSON（根据数据库中的实际数据，使用 external）
                    transform_result = transform_json_with_mapping(raw_json, license_type, user_type)
                    transformed_data = transform_result['transformed_data']
                    features = transform_result.get('features', [])
                    feature_values = transform_result.get('feature_values', {})
                                    
                    # 从数据库动态获取字段映射关系
                    mappings = LicenseFieldMapping.objects.filter(
                        license_type=license_type,
                        user_type=user_type,
                        is_deleted=False
                    ).all()
                                    
                    # 构建 real_key 到 field 的映射
                    real_key_to_field = {m.real_key: m.field for m in mappings}
                    
                    # 定义关键字段的 real_key
                    # 根据数据库表中的 real_key 定义
                    KEY_FIELD_MAPPING = {
                        'Applicant': 'applicant',           # 申请人
                        'CustomerName': 'customer_name',    # 客户名称
                        'MacAddress': 'mac_address',        # MAC地址
                        'Hostname': 'hostname',             # 主机名
                        'Product': 'product',               # 产品名/Product
                        'Startdate': 'start_time',          # 开始时间
                        'Expirydate': 'end_time',           # 结束时间
                        'SerialNumber': 'serial_number',    # 流水号
                    }
                                    
                    # 从转换后的数据中提取信息
                    applicant = ''
                    customer_name = ''
                    mac_address = ''
                    hostname = ''  # 主机名
                    product = ''  # 产品名
                    serial_number = ''  # 流水号
                    start_time = None
                    end_time = None
                    
                    # 直接使用 transform_result 中的 features
                    if features:
                        product = ','.join(features)
                    
                    # 从转换后的数据中提取其他关键字段
                    for real_key, value in transformed_data.items():
                        if real_key in KEY_FIELD_MAPPING:
                            field_type = KEY_FIELD_MAPPING[real_key]
                            
                            # 处理列表类型的值
                            if isinstance(value, list):
                                if field_type == 'applicant':
                                    applicant = value[0] if len(value) > 0 and isinstance(value[0], str) else str(value[0]) if len(value) > 0 else ''
                                elif field_type == 'customer_name':
                                    customer_name = str(value[0]) if len(value) > 0 else ''
                                elif field_type == 'mac_address':
                                    mac_address = str(value[0]) if len(value) > 0 else ''
                            # 处理字符串/数字类型的值
                            else:
                                if field_type == 'applicant':
                                    applicant = str(value) if value else ''
                                elif field_type == 'customer_name':
                                    customer_name = str(value) if value else ''
                                elif field_type == 'mac_address':
                                    mac_address = str(value) if value else ''
                                elif field_type == 'hostname':
                                    hostname = str(value) if value else ''
                                elif field_type == 'serial_number':
                                    serial_number = str(value) if value else ''
                                elif field_type == 'start_time':
                                    if isinstance(value, (int, float)):
                                        from datetime import datetime
                                        start_time = datetime.fromtimestamp(value / 1000)
                                elif field_type == 'end_time':
                                    if isinstance(value, (int, float)):
                                        from datetime import datetime
                                        end_time = datetime.fromtimestamp(value / 1000)
                    
                    # 处理嵌套的表格数据，查找时间字段
                    for key, value in transformed_data.items():
                        if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                            # 这是表格数据
                            for row in value:
                                if isinstance(row, dict):
                                    # 查找表格中的时间字段
                                    for table_key, table_value in row.items():
                                        if table_key in KEY_FIELD_MAPPING:
                                            field_type = KEY_FIELD_MAPPING[table_key]
                                            if field_type == 'start_time' and isinstance(table_value, (int, float)):
                                                if start_time is None:
                                                    from datetime import datetime
                                                    start_time = datetime.fromtimestamp(table_value / 1000)
                                            elif field_type == 'end_time' and isinstance(table_value, (int, float)):
                                                if end_time is None:
                                                    from datetime import datetime
                                                    end_time = datetime.fromtimestamp(table_value / 1000)
                    
                    # 处理MAC地址：去掉":"符号
                    if mac_address:
                        mac_address = mac_address.replace(':', '')
                    
                    # 检查序列号是否已存在（防止重复申请）
                    if serial_number:
                        existing_application = LicenseApplication.objects.filter(
                            serial_number=serial_number
                        ).first()
                        
                        if existing_application:
                            logger.warning(f'序列号 {serial_number} 已存在，跳过处理文件: {txt_file}')
                            results.append({
                                'file': txt_file,
                                'status': 'skipped',
                                'reason': f'序列号 {serial_number} 已存在，申请记录ID: {existing_application.id}',
                                'application_id': existing_application.id
                            })
                            error_count += 1
                            continue  # 跳过此文件，继续处理下一个
                    
                    # 创建申请记录
                    application = LicenseApplication.objects.create(
                        applicant=applicant or '未知申请人',
                        application_type=license_type,
                        feature=features if features else [],  # Feature 列表
                        product=product or '',  # 产品名称
                        serial_number=serial_number or '',  # 序列号
                        customer_name=customer_name or '未指定客户',
                        mac_address=mac_address or '未指定',
                        hostname=hostname or '',  # 主机名
                        start_time=start_time,
                        end_time=end_time,
                        quantity=feature_values if feature_values else {},  # Feature 数量字典，如 {"GloryEX": 10, "GloryEX_Basic": 5}
                        json_data=raw_json,  # 保存原始JSON
                        status=3,  # 待制作
                        max_retry_count=3
                    )
                    
                    # 保存转换后的JSON到文件
                    json_dir = os.path.join(BASE_DIR, 'license_data')
                    if not os.path.exists(json_dir):
                        os.makedirs(json_dir)
                    
                    json_file_path = os.path.join(json_dir, f'{application.id}.json')
                    with open(json_file_path, 'w', encoding='utf-8') as f:
                        json.dump(transformed_data, f, ensure_ascii=False, indent=2)
                    
                    # 移动或标记已处理的TXT文件（可选）
                    # 这里可以选择移动到processed目录或删除
                    
                    processed_count += 1
                    logger.info(f'成功处理第 {idx} 个文件: {txt_file}，申请记录ID: {application.id}')
                    results.append({
                        'file': txt_file,
                        'status': 'success',
                        'application_id': application.id,
                        'license_type': license_type,
                        'applicant': applicant,
                        'transform_info': {
                            'original_keys': transform_result['original_keys_count'],
                            'filtered_keys': transform_result['filtered_keys_count']
                        }
                    })
                    
                except Exception as e:
                    logger.error(f'处理第 {idx} 个文件 {txt_file} 失败: {str(e)}')
                    error_count += 1
                    results.append({
                        'file': txt_file,
                        'status': 'error',
                        'message': str(e)
                    })
            
            logger.info(f'扫描完成：共 {file_count} 个文件，成功 {processed_count} 个，失败 {error_count} 个')
            return SuccessResponse(data={
                'total_files': file_count,
                'processed': processed_count,
                'errors': error_count,
                'results': results
            }, msg=f'扫描完成：共 {file_count} 个文件，成功处理 {processed_count} 个，{error_count} 个失败')
            
        except Exception as e:
            logger.error(f"扫描TXT文件失败: {str(e)}")
            return ErrorResponse(msg=f'扫描失败: {str(e)}')
    
    @action(methods=['post'], detail=False)
    def stop_file_watcher(self, request):
        """
        停止文件监听器
        """
        global _file_watcher_observer
        
        try:
            if '_file_watcher_observer' not in globals() or _file_watcher_observer is None:
                return ErrorResponse(msg='文件监听器未运行')
            
            # 停止监听器
            _file_watcher_observer.stop()
            _file_watcher_observer.join(timeout=5)
            _file_watcher_observer = None
            
            logger.info("文件监听器已停止")
            return SuccessResponse(msg='文件监听器已停止')
            
        except Exception as e:
            logger.error(f"停止文件监听器失败: {str(e)}")
            return ErrorResponse(msg=f'停止失败: {str(e)}')
    
    @action(methods=['post'], detail=False)
    def get_watcher_status(self, request):
        """
        获取监听器状态
        """
        global _file_watcher_observer
        
        try:
            is_running = '_file_watcher_observer' in globals() and _file_watcher_observer is not None and _file_watcher_observer.is_alive()
            
            return SuccessResponse(data={
                'is_running': is_running,
                'watch_dir': os.path.join(settings.JSON_FILE_PATH, 'json_file') if is_running else None
            })
            
        except Exception as e:
            logger.error(f"获取监听器状态失败: {str(e)}")
            return ErrorResponse(msg=f'获取状态失败: {str(e)}')
    
    @action(methods=['post'], detail=False)
    def start_file_watcher(self, request):
        """
        启动文件监听器（后台线程）
        监听指定目录，自动处理新创建的 JSON/TXT 文件
        """
        try:
            import threading
            from apps.lylicense.file_watcher import LicenseFileHandler
            from watchdog.observers.polling import PollingObserver
            
            # 监听目录
            watch_dir = os.path.join(settings.JSON_FILE_PATH, 'json_file')
            logger.info(f"准备启动文件监听器，监听目录: {watch_dir}")
            
            # 确保目录存在
            if not os.path.exists(watch_dir):
                os.makedirs(watch_dir, exist_ok=True)
                logger.info(f"创建监听目录: {watch_dir}")
            
            # 使用全局变量存储监听器状态
            global _file_watcher_observer
            
            # 检查是否已经在运行
            if '_file_watcher_observer' in globals() and _file_watcher_observer is not None and _file_watcher_observer.is_alive():
                logger.warning("文件监听器已在运行中")
                return ErrorResponse(msg='文件监听器已在运行中')
            
            # 定义文件处理回调函数
            def process_license_file(file_path):
                """
                处理 License 文件的回调函数
                
                Args:
                    file_path: 文件路径
                
                Returns:
                    bool: 是否处理成功
                """
                try:
                    logger.info(f"开始处理文件: {file_path}")
                    
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 计算文件内容的 MD5 哈希
                    import hashlib
                    file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                    logger.info(f"文件哈希: {file_hash}")
                    
                    # 注意：不在文件级别检测，因为同一文件会创建多个产品的申请记录
                    # 而是在每个产品创建前检测该产品是否已存在
                    
                    # 尝试解析 JSON
                    try:
                        json_data = json.loads(content)
                        # 获取 LicenseType
                        license_type = json_data.get('LicenseType', '').lower()
                        usage = json_data.get('Usage', '')
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON 解析失败: {file_path}")
                        logger.error(f"JSON 错误详情: {str(e)}")
                        logger.error(f"错误位置: 行 {e.lineno}, 列 {e.colno}")
                        return False
                    except Exception as e:
                        logger.error(f"读取文件失败: {file_path}")
                        logger.error(f"错误详情: {str(e)}", exc_info=True)
                        return False
                    user_type = ''
                    if usage:
                        logger.info(f"开始转换 License and Usage")
                        if usage == '内部':
                            user_type = 'internal'
                        elif usage == '外部':
                            user_type = 'external'
                    # 调用转换函数
                    result = transform_json_with_mapping(json_data, license_type=license_type, user_type=user_type)
                    
                    if not result['success']:
                        logger.error(f"转换失败: {result.get('error')}")
                        return False
                    
                    transformed_data = result['transformed_data']  # 修复：使用正确的键名
                    features = result['features']
                    product_features = result['product_features']  # 直接使用product_features作为quantity
                    user_info_list = result['transformed_data'].get('UserInfo', [])  # 获取UserInfo列表
                    
                    # 从 transformed_data 中提取全局的 mac_address 和 hostname（作为 fallback）
                    mac_address = transformed_data.get('MacAddress', '')
                    if mac_address:
                        mac_address = mac_address.upper()
                    hostname = transformed_data.get('Hostname', '')
                    
                    # 打印转换后的数据，方便核对
                    logger.info(f"\n{'='*80}")
                    logger.info(f"转换后的 transformed_data:")
                    logger.info(json.dumps(transformed_data, ensure_ascii=False, indent=2))
                    logger.info(f"{'='*80}\n")
                    
                    logger.info(f"UserInfo 列表包含 {len(user_info_list)} 个产品:")
                    for idx, ui in enumerate(user_info_list, 1):
                        logger.info(f"  {idx}. Product: {ui.get('Product')}, MacAddress: {ui.get('MacAddress')}, Hostname: {ui.get('Hostname')}")
                        logger.info(f"     Startdate: {ui.get('Startdate')}, Expirydate: {ui.get('Expirydate')}")
                    logger.info(f"\nproduct_features 结构:")
                    logger.info(json.dumps(product_features, ensure_ascii=False, indent=2))
                    logger.info(f"{'='*80}\n")
                    
                    # 提取公共数据
                    applicant = None
                    customer_name = None
                    serial_number = None
                    
                    # 从转换后的数据中提取公共字段
                    for key, value in transformed_data.items():
                        if key == 'SerialNumber':
                            serial_number = value
                        elif key == 'CustomerName':
                            customer_name = value
                        elif key == 'Applicant':
                            applicant = value[0]
                    
                    # 检查序列号是否为空
                    if not serial_number:
                        logger.warning(f'序列号为空，跳过处理文件: {file_path}')
                        return False
                    
                    # 特殊产品分组：GloryEX、GloryEX3D、GloryPolaris 合并为一个申请记录
                    gloryex_group_products = ['GloryEX', 'GloryEX3D', 'GloryPolaris']
                    
                    # 按产品分组处理
                    processed_products = set()  # 已处理的产品集合
                    created_applications = []  # 记录创建的申请
                    
                    for user_info in user_info_list:
                        product = user_info.get('Product')
                        if not product:
                            continue
                        
                        # 如果产品已经处理过，跳过
                        if product in processed_products:
                            continue
                        
                        # 判断是否属于GloryEX组
                        if product in gloryex_group_products:
                            # 合并处理GloryEX组的所有产品
                            gloryex_features = {}
                            gloryex_feature_list = []
                            min_start_time = None
                            max_end_time = None
                            
                            for group_product in gloryex_group_products:
                                if group_product in product_features:
                                    # 合并feature
                                    gloryex_features.update(product_features[group_product])
                                    # 合并feature列表
                                    for feat in product_features[group_product].keys():
                                        if feat not in gloryex_feature_list:
                                            gloryex_feature_list.append(feat)
                                
                                # 查找对应产品的UserInfo，获取时间
                                for ui in user_info_list:
                                    if ui.get('Product') == group_product:
                                        start_timestamp = ui.get('Startdate')
                                        end_timestamp = ui.get('Expirydate')
                                        
                                        if start_timestamp and isinstance(start_timestamp, (int, float)):
                                            from datetime import datetime
                                            start_time = datetime.fromtimestamp(start_timestamp / 1000)
                                            if min_start_time is None or start_time < min_start_time:
                                                min_start_time = start_time
                                        
                                        if end_timestamp and isinstance(end_timestamp, (int, float)):
                                            from datetime import datetime
                                            end_time = datetime.fromtimestamp(end_timestamp / 1000)
                                            if max_end_time is None or end_time > max_end_time:
                                                max_end_time = end_time
                                        break
                                
                                processed_products.add(group_product)
                            
                            # 处理MAC地址：在最外层已经处理过了，直接使用
                            # mac_address 变量在第378行已经提取并处理

                            # 检查该产品的申请记录是否已存在
                            if LicenseApplication.objects.filter(file_hash=file_hash, product='GloryEX').exists():
                                logger.info(f'GloryEX产品申请记录已存在（文件哈希: {file_hash}），跳过创建')
                            else:
                                # 创建GloryEX组的申请记录
                                application = LicenseApplication.objects.create(
                                    applicant=applicant or '未知申请人',
                                    application_type=license_type,
                                    feature=gloryex_feature_list if gloryex_feature_list else [],
                                    product='GloryEX',  # 统一使用GloryEX作为产品名
                                    serial_number=serial_number or '',
                                    file_hash=file_hash,
                                    customer_name=customer_name or '未指定客户',
                                    mac_address=mac_address,
                                    hostname=hostname or '',
                                    start_time=min_start_time,
                                    end_time=max_end_time,
                                    quantity=gloryex_features if gloryex_features else {},
                                    json_data=json_data,
                                    status=3,
                                    max_retry_count=3
                                )
                                created_applications.append(application.id)
                                logger.info(f"创建GloryEX组申请记录成功，ID: {application.id}，包含产品: {', '.join([p for p in gloryex_group_products if p in product_features])}")
                        else:
                            # 其他产品单独创建申请记录
                            product_feats = product_features.get(product, {})
                            feat_list = list(product_feats.keys())
                            
                            # 获取该产品的开始和结束时间
                            start_timestamp = user_info.get('Startdate')
                            end_timestamp = user_info.get('Expirydate')
                            
                            start_time = None
                            end_time = None
                            if start_timestamp and isinstance(start_timestamp, (int, float)):
                                from datetime import datetime
                                start_time = datetime.fromtimestamp(start_timestamp / 1000)
                            if end_timestamp and isinstance(end_timestamp, (int, float)):
                                from datetime import datetime
                                end_time = datetime.fromtimestamp(end_timestamp / 1000)
                            
                            # 处理MAC地址：在最外层已经处理过了，直接使用
                            # mac_address 变量在第378行已经提取并处理
                            
                            # 检查该产品的申请记录是否已存在
                            if LicenseApplication.objects.filter(file_hash=file_hash, product=product).exists():
                                logger.info(f'产品{product}申请记录已存在（文件哈希: {file_hash}），跳过创建')
                            else:
                                application = LicenseApplication.objects.create(
                                    applicant=applicant or '未知申请人',
                                    application_type=license_type,
                                    feature=feat_list if feat_list else [],
                                    product=product,
                                    serial_number=serial_number or '',
                                    file_hash=file_hash,
                                    customer_name=customer_name or '未指定客户',
                                    mac_address=mac_address,
                                    hostname=hostname or '',
                                    start_time=start_time,
                                    end_time=end_time,
                                    quantity=product_feats if product_feats else {},
                                    json_data=json_data,
                                    status=3,
                                    max_retry_count=3
                                )
                                created_applications.append(application.id)
                                processed_products.add(product)
                                logger.info(f"创建产品{product}申请记录成功，ID: {application.id}")
                    
                    if created_applications:
                        logger.info(f"共创建 {len(created_applications)} 条申请记录，IDs: {created_applications}")
                        return True
                    else:
                        logger.warning(f'未找到任何产品信息，跳过处理文件: {file_path}')
                        return False
                    
                except Exception as e:
                    logger.error(f"处理文件失败 {file_path}: {str(e)}", exc_info=True)
                    return False
            
            # 使用 PollingObserver（Windows 上更稳定）
            logger.info(f"创建事件处理器和观察者...")
            event_handler = LicenseFileHandler(process_callback=process_license_file)
            observer = PollingObserver()
            observer.schedule(event_handler, watch_dir, recursive=False)
            
            # 启动观察者
            observer.start()
            logger.info(f"Observer 已启动，is_alive={observer.is_alive()}")
            
            # 保存到全局变量
            _file_watcher_observer = observer
            
            logger.info(f"文件监听器已启动，监听目录: {watch_dir}")
            
            return SuccessResponse(msg=f'文件监听器已启动，监听目录: {watch_dir}')
            
        except Exception as e:
            logger.error(f"启动文件监听器失败: {str(e)}")
            return ErrorResponse(msg=f'启动失败: {str(e)}')
    
    @action(methods=['post'], detail=True)
    def parse_and_generate(self, request, pk=None):
        """
        解析JSON文件并生成License
        1. 从固定目录读取JSON文件
        2. 解析JSON数据并写入数据库
        3. 根据类型生成License
        """
        instance = None
        try:
            instance = self.get_object()
            
            if instance.status not in [0, 3]:  # 待制作或制作失败
                return ErrorResponse(msg='当前状态不允许制作License')
            
            # 检查是否超过最大重试次数
            if instance.retry_count >= instance.max_retry_count:
                return ErrorResponse(msg=f'已达到最大重试次数({instance.max_retry_count})，无法继续重试')
            
            # 从固定目录读取JSON文件
            json_file_path = os.path.join(BASE_DIR, 'license_data', f'{instance.id}.json')
            
            if not os.path.exists(json_file_path):
                return ErrorResponse(msg=f'JSON文件不存在: {json_file_path}')
            
            # 解析JSON数据
            with open(json_file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # 从JSON中提取元数据作为转换条件
            license_type_from_json = json_data.get('LicenseType', '').lower()
            usage_from_json = json_data.get('Usage', '')
            
            # 转换Usage为数据库值
            user_type_mapping = {
                '内部': 'internal',
                '外部': 'external',
                'internal': 'internal',
                'external': 'external',
            }
            
            # 如果Usage为空或不在映射中，使用申请记录中的用户类型（如果有）
            if usage_from_json and usage_from_json in user_type_mapping:
                user_type_from_json = user_type_mapping[usage_from_json]
                logger.info(f"从JSON提取Usage: '{usage_from_json}' -> '{user_type_from_json}'")
            else:
                # Usage为空或未知时，根据申请记录的application_type推断默认值
                # 这里可以根据业务需求调整默认策略
                user_type_from_json = '未匹配到真实值'
                logger.warning(f"JSON中Usage字段缺失或未知: '{usage_from_json}'，使用默认值: '{user_type_from_json}'")
            
            # 如果LicenseType为空，使用申请记录中的类型
            if not license_type_from_json:
                license_type_from_json = instance.application_type
                logger.warning(f"JSON中LicenseType字段缺失，使用申请记录中的类型: '{license_type_from_json}'")
            
            logger.info(f"最终使用的转换条件 - LicenseType: {license_type_from_json}, UserType: {user_type_from_json}")
            
            # 使用字段映射表转换JSON数据（使用从JSON中提取的license_type和user_type）
            transform_result = transform_json_with_mapping(
                json_data, 
                license_type_from_json if license_type_from_json else instance.application_type,
                user_type_from_json
            )
            transformed_data = transform_result['transformed_data']
            
            # 如果申请记录中有keyword字段，将其添加到转换后的数据中
            if instance.keyword:
                # 查找keyword对应的real_key（使用从JSON中提取的license_type和user_type）
                keyword_mapping = LicenseFieldMapping.objects.filter(
                    license_type=license_type_from_json if license_type_from_json else instance.application_type,
                    user_type=user_type_from_json,
                    field__icontains='selectfield',
                    real_key__iexact='keyword',
                    is_deleted=False
                ).first()
                
                if keyword_mapping:
                    # 使用映射表中的real_key作为key
                    transformed_data[keyword_mapping.real_key] = instance.keyword
                    logger.info(f"添加keyword字段: {keyword_mapping.real_key} = {instance.keyword}")
                else:
                    # 如果没有找到映射，直接使用'Keyword'作为key
                    transformed_data['Keyword'] = instance.keyword
                    logger.info(f"未找到keyword映射，使用默认key: Keyword = {instance.keyword}")
            
            # 更新申请的JSON数据和状态（使用转换后的数据）
            instance.json_data = transformed_data
            instance.status = 2  # 制作中
            instance.save()
            
            # 根据application_type调用不同的生成逻辑
            if instance.application_type == 'flexnet':
                result = self._generate_flexnet_license(instance, json_data)
            elif instance.application_type == 'bitanswer':
                result = self._generate_bitanswer_license(instance, json_data)
            else:
                return ErrorResponse(msg='不支持的License类型')
            
            if result['success']:
                instance.status = 1  # 制作成功
                instance.fail_reason = ''
                instance.save()
                
                # 创建License记录
                license_record = LicenseRecord.objects.create(
                    application=instance,
                    license_id=result.get('license_id', f'LIC-{instance.id}'),
                    license_type=instance.application_type,
                    file_name=result.get('file_name', ''),
                    file_relative_path=result.get('file_relative_path', ''),
                    directory=result.get('directory', ''),
                    full_path=result.get('full_path', ''),
                    feature=json_data.get('feature', instance.feature),
                    vendor=result.get('vendor', ''),
                    version=result.get('version', ''),
                    host_id=json_data.get('mac_address', instance.mac_address),
                    start_time=json_data.get('start_time') or instance.start_time,
                    end_time=json_data.get('end_time') or instance.end_time,
                    quantity=json_data.get('quantity', instance.quantity),
                    extra_info=result.get('extra_info', {})
                )
                
                return SuccessResponse(data={
                    'application_id': instance.id,
                    'license_id': license_record.license_id,
                    'result': result
                }, msg='License制作成功')
            else:
                instance.status = 0  # 制作失败
                instance.fail_reason = result.get('error', '未知错误')
                instance.retry_count += 1  # 增加重试次数
                instance.save()
                
                # 判断是否可以自动重试
                can_retry = instance.retry_count < instance.max_retry_count
                
                return ErrorResponse(
                    msg='License制作失败', 
                    data={
                        **result,
                        'retry_count': instance.retry_count,
                        'max_retry_count': instance.max_retry_count,
                        'can_retry': can_retry
                    }
                )
            
        except Exception as e:
            logger.error(f"解析和生成License失败: {str(e)}")
            if instance:
                instance.status = 0
                instance.fail_reason = str(e)
                instance.retry_count += 1
                instance.save()
            return ErrorResponse(msg=f"操作失败: {str(e)}")
    
    @action(methods=['post'], detail=True)
    def retry(self, request, pk=None):
        """
        重试制作License（直接重新执行制作流程）
        """
        instance = None
        try:
            instance = self.get_object()
            
            if instance.status != 0:  # 只有制作失败才能重试
                return ErrorResponse(msg='只有制作失败的申请才能重试')
            
            # 检查是否超过最大重试次数
            if instance.retry_count >= instance.max_retry_count:
                return ErrorResponse(msg=f'已达到最大重试次数({instance.max_retry_count})，无法继续重试')
            
            # 直接调用parse_and_generate逻辑
            return self.parse_and_generate(request, pk)
            
        except Exception as e:
            logger.error(f"重试失败: {str(e)}")
            if instance:
                instance.fail_reason = str(e)
                instance.save()
            return ErrorResponse(msg=f"重试失败: {str(e)}")
    
    def _generate_flexnet_license(self, instance, json_data):
        """
        生成FlexNet类型的License
        执行flexnet命令生成license文件
        """
        try:
            # 构建license文件路径
            license_dir = os.path.join(MEDIA_ROOT, 'license', 'flexnet')
            if not os.path.exists(license_dir):
                os.makedirs(license_dir)
            
            file_name = f'{instance.id}_flex.lic'
            license_file = os.path.join(license_dir, file_name)
            relative_path = os.path.join('license', 'flexnet', file_name)
            
            # 执行flexnet命令
            cmd = f'flexnet {license_file}'
            logger.info(f"执行FlexNet命令: {cmd}")
            
            # 执行命令，无返回表示成功
            exit_code = os.system(cmd)
            
            if exit_code == 0:
                # 命令执行成功
                result = {
                    'success': True,
                    'file_name': file_name,
                    'file_relative_path': relative_path,
                    'directory': os.path.join(MEDIA_ROOT, 'license', 'flexnet'),
                    'full_path': license_file,
                    'vendor': 'FlexNet',
                    'version': json_data.get('version', '1.0'),
                    'license_id': f'FN-{instance.id}',
                    'message': 'FlexNet License制作成功',
                    'exit_code': exit_code
                }
            else:
                result = {
                    'success': False,
                    'error': f'FlexNet命令执行失败，退出码: {exit_code}',
                    'exit_code': exit_code
                }
            
            return result
        except Exception as e:
            logger.error(f"FlexNet License制作失败: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_bitanswer_license(self, instance, json_data):
        """
        生成Bitanswer类型的License
        解析JSON数据，拼装参数，调用Bitanswer API
        """
        try:
            import requests
            
            # 从JSON数据中提取参数
            params = {
                'customer_name': json_data.get('customer_name', instance.customer_name),
                'mac_address': json_data.get('mac_address', instance.mac_address),
                'feature': json_data.get('feature', instance.feature),
                'start_time': json_data.get('start_time'),
                'end_time': json_data.get('end_time'),
                'quantity': json_data.get('quantity', instance.quantity),
            }
            
            # 如果JSON数据中有Keyword字段，添加到参数中
            if 'Keyword' in json_data:
                params['keyword'] = json_data['Keyword']
                logger.info(f"添加Keyword参数: {params['keyword']}")
            
            # Bitanswer API配置
            bitanswer_api_url = 'http://bitanswer-server/api/generate-license'  # 替换为实际API地址
            bitanswer_api_key = 'your-api-key'  # 替换为实际的API Key
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {bitanswer_api_key}'
            }
            
            logger.info(f"调用Bitanswer API: {bitanswer_api_url}")
            logger.info(f"请求参数: {params}")
            
            # 调用Bitanswer API
            response = requests.post(
                bitanswer_api_url,
                json=params,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result_data = response.json()
                
                # 构建license文件路径
                license_dir = os.path.join(MEDIA_ROOT, 'license', 'bitanswer')
                if not os.path.exists(license_dir):
                    os.makedirs(license_dir)
                
                file_name = f'{instance.id}_bit.upd'
                license_file = os.path.join(license_dir, file_name)
                relative_path = os.path.join('license', 'bitanswer', file_name)
                
                # 保存API返回的license内容
                license_content = result_data.get('license_content', '')
                with open(license_file, 'w', encoding='utf-8') as f:
                    f.write(license_content)
                
                result = {
                    'success': True,
                    'file_name': file_name,
                    'file_relative_path': relative_path,
                    'directory': os.path.join(MEDIA_ROOT, 'license', 'bitanswer'),
                    'full_path': license_file,
                    'vendor': 'Bitanswer',
                    'version': result_data.get('version', '1.0'),
                    'license_id': result_data.get('license_id', f'BA-{instance.id}'),
                    'message': 'Bitanswer License制作成功',
                    'api_response': result_data
                }
            else:
                result = {
                    'success': False,
                    'error': f'Bitanswer API调用失败，状态码: {response.status_code}',
                    'api_response': response.text
                }
            
            return result
        except Exception as e:
            logger.error(f"Bitanswer License制作失败: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


class LicenseRecordViewSet(CustomModelViewSet):
    """
    License记录管理ViewSet
    展示制作完成后的License列表
    """
    queryset = LicenseRecord.objects.all()
    serializer_class = LicenseRecordSerializer
    filterset_fields = ['license_type', 'status', 'host_id', 'vendor']
    search_fields = ['license_id', 'feature', 'vendor', 'host_id', 'file_name']
    ordering_fields = ['create_datetime', 'end_time', 'remaining_days']
    ordering = '-create_datetime'
    # License模块不需要数据权限过滤
    extra_filter_backends = []
    
    @action(methods=['get'], detail=False)
    def statistics(self, request):
        """
        获取License统计信息
        """
        from django.db.models import Count
        from datetime import datetime, timedelta
        
        # 使用本地时间
        now = datetime.now()
        
        # 按类型统计
        type_stats = LicenseRecord.objects.values('license_type').annotate(
            count=Count('id')
        )
        
        # 按状态统计
        status_stats = LicenseRecord.objects.values('status').annotate(
            count=Count('id')
        )
        
        # 计算动态时间阈值
        expiring_threshold = now + timedelta(days=30)
        
        # 即将过期的License（end_time距离现在<=30天且>0天）
        expiring_soon = LicenseRecord.objects.filter(
            end_time__lte=expiring_threshold,
            end_time__gt=now,
            status=1  # 有效状态
        ).count()
        
        # 已过期的License（end_time < 现在）
        expired = LicenseRecord.objects.filter(
            end_time__lt=now
        ).count()

        # 有效的（end_time > 现在）
        efficient = LicenseRecord.objects.filter(
            end_time__gt=now
        ).count()
        
        return SuccessResponse(data={
            'type_stats': list(type_stats),
            'status_stats': list(status_stats),
            'expiring_soon': expiring_soon,
            'expired': expired,
            'efficient': efficient,
            'total': LicenseRecord.objects.count()
        })


class LicenseFieldMappingViewSet(CustomModelViewSet):
    """
    License字段映射管理ViewSet
    """
    queryset = LicenseFieldMapping.objects.filter()
    serializer_class = LicenseFieldMappingSerializer
    create_serializer_class = LicenseFieldMappingCreateSerializer
    update_serializer_class = LicenseFieldMappingUpdateSerializer
    filterset_fields = ['license_type', 'user_type', 'field', 'name', 'real_key']
    search_fields = ['field', 'name', 'real_key']
    ordering_fields = ['create_datetime']
    ordering = '-create_datetime'
    extra_filter_backends = []
    
    def list(self, request, *args, **kwargs):
        """调试：打印列表接口返回数据"""
        try:
            response = super().list(request, *args, **kwargs)
            print(f"\n{'='*60}")
            print(f"[LicenseFieldMappingViewSet.list]")
            print(f"Response data type: {type(response.data)}")
            print(f"Response keys: {list(response.data.keys()) if isinstance(response.data, dict) else 'N/A'}")
            if isinstance(response.data, dict) and 'data' in response.data:
                data = response.data['data']
                if isinstance(data, list):
                    print(f"Data is list, count: {len(data)}")
                    if data:
                        print(f"First item type: {type(data[0])}")
                elif isinstance(data, dict):
                    print(f"Data is dict, keys: {list(data.keys())}")
                else:
                    print(f"Data type: {type(data)}, value: {data}")
            print(f"{'='*60}\n")
            return response
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"[LicenseFieldMappingViewSet.list ERROR]")
            print(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            print(f"{'='*60}\n")
            raise
