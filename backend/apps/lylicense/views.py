import os
import json
import logging
from datetime import datetime, timedelta, date
from utils.email import EmailManager
import threading

import paramiko
from django.utils import timezone
from django.conf import settings
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as http_status

import config
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


def _execute_remote_lmcrypt(template_file_path, product_name):
    """
    通过 SSH 远程执行 lmcrypt_new 脚本生成正式 license 文件
    
    Args:
        template_file_path: 本地预制作 license 模板文件路径
        product_name: 产品名称
    
    Returns:
        dict: 执行结果
            {
                'success': bool,
                'remote_license_path': str,  # 远程服务器上的正式 license 文件路径
                'error': str  # 错误信息（如果失败）
            }
    """
    remote_template_dir = ''
    remote_license_filename = ''
    try:
        # SSH 连接配置
        ssh_host = config.SSH_HOST
        ssh_user = config.SSH_USER
        ssh_password = config.SSH_PASSWORD  # 使用免密登录（密钥认证）
        ssh_key_file = config.SSH_KEY_FILE  # 如果有密钥文件可以指定，否则使用默认 ~/.ssh/id_rsa
        
        # 远程服务器上的路径
        remote_template_dir = config.SSH_REMOTE_TEMPLATE_DIR
        remote_script_path = config.SSH_REMOTE_SCRIPT_PATH
        
        logger.info(f"准备远程执行 lmcrypt_new 脚本: {template_file_path}")
        
        # 创建 SSH 客户端
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # 连接 SSH
        if ssh_key_file:
            ssh.connect(ssh_host, username=ssh_user, key_filename=ssh_key_file)
        else:
            ssh.connect(ssh_host, username=ssh_user)
        
        logger.info(f"SSH 连接成功: {ssh_host}")
        
        # 步骤 1: 通过 SFTP 上传预制作模板文件
        sftp = ssh.open_sftp()
        
        # 提取文件名
        template_filename = os.path.basename(template_file_path)
        remote_template_file = os.path.join(remote_template_dir, template_filename)
        
        logger.info(f"上传预制作模板文件: {template_file_path} -> {remote_template_file}")
        sftp.put(template_file_path, remote_template_file)
        logger.info("文件上传成功")
        
        # 步骤 2: 远程执行 lmcrypt_new 脚本
        # 注意：lmcrypt_new 脚本会在当前目录生成 license 文件，文件名与输入文件相同
        cmd = f"cd {remote_template_dir} && {remote_script_path} {template_filename}"
        logger.info(f"远程执行命令: {cmd}")
        
        # 执行命令
        stdin, stdout, stderr = ssh.exec_command(cmd)
        
        # 获取命令输出
        output = stdout.read().decode('utf-8')
        error_output = stderr.read().decode('utf-8')
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status == 0:
            logger.info(f"远程 lmcrypt_new 执行成功: {output}")
            
            # 步骤 3: 下载生成的正式 license 文件回本地
            # lmcrypt_new 脚本会就地修改文件，所以生成的文件名与模板文件名相同
            remote_license_path = remote_template_file  # 远程文件路径
            
            # 创建本地目录
            license_dir = os.path.join(MEDIA_ROOT, 'license', 'flexnet')
            if not os.path.exists(license_dir):
                os.makedirs(license_dir)
            
            local_license_path = os.path.join(license_dir, template_filename)
            
            logger.info(f"下载正式 license 文件: {remote_license_path} -> {local_license_path}")
            sftp.get(remote_license_path, local_license_path)
            logger.info(f"文件下载成功: {local_license_path}")
            
            # 关闭 SFTP 连接
            sftp.close()
            
            return {
                'success': True,
                'local_license_path': local_license_path,
                'remote_license_path': remote_license_path,
                'output': output
            }
        else:
            error_msg = f"远程命令执行失败，退出码: {exit_status}, 错误: {error_output}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    except paramiko.AuthenticationException:
        error_msg = "SSH 认证失败，请检查密钥配置"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }
    except paramiko.SSHException as e:
        error_msg = f"SSH 连接失败: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }
    except Exception as e:
        error_msg = f"远程执行失败: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }
    finally:
        # 关闭 SFTP 连接
        if 'sftp' in locals() and sftp:
            try:
                sftp.close()
            except:
                pass
        # 关闭 SSH 连接
        if 'ssh' in locals() and ssh:
            try:
                ssh.close()
            except:
                pass


def _get_feature_id_from_api(product_name, feature_name):
    """
    通过第三方 API 获取 feature 的 ID
    
    Args:
        product_name: 产品名称（如 GloryBolt、GloryLink）
        feature_name: feature 名称（如 v2spef、link）
    
    Returns:
        int or None: feature 的 ID，如果获取失败则返回 None
    """
    try:
        import requests
        from config import BITANSWER_API_BASE_URL,BITANSWER_BITKEY
        
        # 构建 API URL
        api_url = f'{BITANSWER_API_BASE_URL}/e3/api/products/{product_name}/features?limit=1000'
        logger.info(f"调用 API 获取 {product_name} 产品的 feature '{feature_name}' 的 ID: {api_url}")

        headers = {
                'Content-Type': 'application/json',
                'bitkey': BITANSWER_BITKEY  # 固定的 bitkey
            }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            logger.warning(f"API 调用失败，状态码: {response.status_code}, URL: {api_url}")
            return None
        
        result = response.json()
        
        # 检查响应状态
        if result.get('status') != 0:
            logger.warning(f"API 返回错误状态: {result.get('status')}, 产品: {product_name}")
            return None
        
        # 解析数据
        data = result.get('data', {})
        items = data.get('items', [])
        
        if not items:
            logger.warning(f"未找到产品 '{product_name}' 的任何 feature")
            return None
        
        # 【优化】直接遍历所有 feature，精确匹配 feature_name
        # API 返回该产品所有的 feature 列表，我们只需要找到匹配的即可
        for item in items:
            item_name = item.get('name', '')
            item_id = item.get('id')
            
            # 精确匹配 feature 名称
            if item_name == feature_name:
                logger.info(f"✅ 找到 feature '{feature_name}' 的 ID: {item_id}")
                return item_id  # 找到第一个匹配的立即返回
        
        # 【优化】如果没有精确匹配，尝试模糊匹配
        # 例如：feature_name='v2spef' 可能对应 'v2spef_2.0' 或 'v2spef_v3'
        for item in items:
            item_name = item.get('name', '')
            item_id = item.get('id')
            
            # 模糊匹配：feature_name 是 item_name 的一部分，或者反过来
            if feature_name in item_name or item_name in feature_name:
                logger.info(f"️ 使用模糊匹配找到 feature '{feature_name}' -> '{item_name}', ID: {item_id}")
                return item_id  # 找到第一个匹配的立即返回
        
        logger.warning(f"未在产品 '{product_name}' 的所有 feature 中找到 '{feature_name}'")
        return None
        
    except Exception as e:
        logger.error(f"调用 API 获取 feature ID 失败: {str(e)}, 产品: {product_name}, feature: {feature_name}")
        return None


def _upload_bitanswer_license_to_remote(local_file_path, remote_filename):
    """
    将 Bitanswer License 文件复制到远程挂载目录
    
    Args:
        local_file_path: 本地 .upd 文件路径
        remote_filename: 远程文件名（包含扩展名）
    
    Returns:
        dict: 复制结果
            {
                'success': bool,
                'remote_path': str,  # 远程服务器上的完整路径
                'error': str  # 错误信息（如果失败）
            }
    """
    try:
        import shutil
        from config import SSH_REMOTE_TEMPLATE_DIR
        
        logger.info(f"准备复制 Bitanswer License 文件到挂载目录: {local_file_path}")
        
        # 构建远程文件路径
        remote_dir = SSH_REMOTE_TEMPLATE_DIR
        remote_file_path = os.path.join(remote_dir, remote_filename)
        
        # 确保目标目录存在
        if not os.path.exists(remote_dir):
            logger.warning(f"远程目录不存在，尝试创建: {remote_dir}")
            os.makedirs(remote_dir, exist_ok=True)
        
        # 复制文件
        shutil.copy2(local_file_path, remote_file_path)
        logger.info(f"文件复制成功: {remote_file_path}")
        
        return {
            'success': True,
            'remote_path': remote_file_path,
            'message': f'Bitanswer License 文件已复制到: {remote_file_path}'
        }
        
    except Exception as e:
        error_msg = f"复制到远程目录失败: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }


def get_applicant_from_transformed_data(transformed_data, license_type, user_type, field_name='ApplicantID'):
    """
    从转换后的 JSON 数据中获取申请人账号
    
    实现逻辑：
    转换后的数据中，字段名已经使用 real_key（如 ApplicantID 或 Applicant）
    直接用指定的 field_name 作为 key 从转换后的数据中获取值
    
    Args:
        transformed_data: 转换后的 JSON 数据（字典）
        license_type: License类型 ('flexnet' 或 'bitanswer')
        user_type: 用户类型 ('internal' 或 'external')
        field_name: 字段名称，默认 'ApplicantID'（用于邮件），也可以传 'Applicant'（用于记录）
    
    Returns:
        str: 申请人账号，如果未找到则返回空字符串
    """
    try:
        # 直接从转换后的数据中获取指定字段的值
        applicant = transformed_data.get(field_name, '')
        
        if applicant:
            # 如果提取到的是列表，取第一个元素
            if isinstance(applicant, list) and len(applicant) > 0:
                applicant = applicant[0]
            logger.info(f"从转换后的数据中提取到申请人: {applicant} (key: {field_name})")
            return applicant
        else:
            logger.warning(f"转换后的数据中未找到 {field_name}，applicant={applicant}")
        
        return ''
    except Exception as e:
        logger.error(f"提取申请人账号失败: {str(e)}")
        return ''

def append_common_userinfo(user_info_list):
    """
    自动生成公共产品 UserInfo

    当前规则：

        GloryEX
        GloryEX3D
              ↓
        GloryEXCommon
    """
    if not user_info_list:
        return user_info_list

    # 已存在Common就跳过
    exists = {u.get("Product") for u in user_info_list}

    for common_product, source_products in config.COMMON_PRODUCT.items():
        if common_product in exists:
            continue

        matched = []
        for ui in user_info_list:
            if ui.get("Product") in source_products:
                matched.append(ui)

        if not matched:
            continue

        if len(matched) == 1:
            common = matched[0].copy()
        else:
            common = matched[0].copy()
            common["Startdate"] = min(x["Startdate"] for x in matched)
            common["Expirydate"] = max(x["Expirydate"] for x in matched)

        common["Product"] = common_product
        user_info_list.append(common)
        logger.info(f"新增公共产品UserInfo：{common_product}")

    return user_info_list

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
    
    # 提取并列字段：FormList、Usage、LicenseType 必须是并列关系
    if 'FormList' not in raw_json:
        raise ValueError(f"JSON格式错误：缺少 'FormList' 字段")
    if 'Usage' not in raw_json:
        raise ValueError(f"JSON格式错误：缺少 'Usage' 字段")
    if 'LicenseType' not in raw_json:
        raise ValueError(f"JSON格式错误：缺少 'LicenseType' 字段")
    
    form_list = raw_json.get('FormList', {})
    usage = raw_json.get('Usage', '')
    license_type_from_json = raw_json.get('LicenseType', '').lower()

    if usage:
        if usage == '内部':
            user_type = 'internal'
        elif usage == '外部':
            user_type = 'external'
    
    if not form_list:
        return {
            'transformed_data': {},
            'features': [],
            'feature_values': {},
            'user_info_list': [],
            'mac_address': '',
            'hostname': '',
            'product_features': {},
            'product_set': [],
            'usage': user_type,
            'license_type': license_type_from_json,
            'original_keys_count': 0,
            'filtered_keys_count': 0,
            'mapping_used': len(field_mapping),
            'success': True
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
                    # 如果值是列表且字段名是 ApplicantID，提取第一个元素（避免 ["value"] 格式）
                    if isinstance(value, list) and len(value) > 0 and real_key == 'ApplicantID':
                        transformed_row[real_key] = value[0]
                    else:
                        transformed_row[real_key] = value
            else:
                # 不在映射表中，检查是否是表格字段的子字段（通常不需要映射）
                # 忽略 selectField 等表格相关字段的警告
                if not key.startswith(('selectField_', 'dateField_')):
                    logger.warning(f"字段 {key} 不在映射表中，使用原始 key")
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
                    # 如果值是列表且字段名是 ApplicantID，提取第一个元素（避免 ["value"] 格式）
                    if isinstance(value, list) and len(value) > 0 and real_key == 'ApplicantID':
                        transformed_data[real_key] = value[0]
                    else:
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
    

    mac_address = transformed_data.get('MacAddress', '')
    if mac_address:
        mac_address = mac_address.replace('-', '').replace(':', '')
    hostname = transformed_data.get('Hostname', '')

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
        
        # 找出所有非零的时间值（用于公共部分时间继承）
        all_start_dates = []
        all_end_dates = []
        for product, base_info in product_base_info.items():
            start_date = base_info.get('Startdate', 0)
            end_date = base_info.get('Expirydate', 0)
            if start_date and start_date > 0:
                all_start_dates.append(start_date)
            if end_date and end_date > 0:
                all_end_dates.append(end_date)
        
        # 取第一个有效的时间作为默认值（如果没有则为0）
        default_startdate = all_start_dates[0] if all_start_dates else 0
        default_expirydate = all_end_dates[0] if all_end_dates else 0
        
        # 为每个产品构建 UserInfo 条目
        for product in product_set:
            # 使用产品对应的基础信息，如果没有则使用全局的
            base_info = product_base_info.get(product, {})
            
            # 获取该产品的原始时间
            product_startdate = base_info.get('Startdate', 0)
            product_expirydate = base_info.get('Expirydate', 0)
            
            # 公共部分时间继承规则：如果时间为0，从其他产品中继承
            # 注意：只有当产品名称包含 "Common" 时才应用此规则
            if 'Common' in product or product == 'GloryEXCommon':
                # 公共产品，如果时间为0，从其他产品中继承
                if product_startdate == 0 and default_startdate > 0:
                    product_startdate = default_startdate
                if product_expirydate == 0 and default_expirydate > 0:
                    product_expirydate = default_expirydate
            
            user_info_entry = {
                # 'MacAddress': base_info.get('MacAddress', mac_address),
                # 'Hostname': base_info.get('Hostname', hostname),
                'Expirydate': product_expirydate,
                'Startdate': product_startdate,
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
        append_common_userinfo(user_info_list)
        transformed_data['UserInfo'] = user_info_list
    
    # 返回结果
    result = {
        'transformed_data': transformed_data,
        'usage': usage,
        'license_type': license_type_from_json,  # 使用从JSON中提取的license_type
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
    filterset_fields = ['applicant', 'application_type', 'customer_name', 'status', 'serial_number']
    search_fields = ['applicant', 'customer_name', 'mac_address', 'feature', 'serial_number']
    ordering_fields = ['create_datetime']
    ordering = '-create_datetime'
    # License模块不需要数据权限过滤
    extra_filter_backends = []
    
    def get_queryset(self):
        """重写查询集，支持产品名称筛选（包括 user_info_list 中的产品）"""
        queryset = super().get_queryset()
        # 兼容前端两种参数名：product 和 product_name
        product_name = self.request.query_params.get('product') or self.request.query_params.get('product_name')
        if product_name:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[产品查询-get_queryset] 搜索关键词: {product_name}")
            
            # 由于 MySQL 的 JSONField __contains 查询不可靠，我们不在数据库层面过滤
            # 而是返回所有记录，在 list() 方法中进行 Python 层面的精确过滤
            logger.info(f"[产品查询-get_queryset] 跳过数据库过滤，返回所有记录")
        return queryset
    
    def list(self, request, *args, **kwargs):
        """重写列表方法，对产品名称进行精确过滤"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # 如果有产品名称参数，进行精确过滤（兼容 product 和 product_name）
        product_name = self.request.query_params.get('product') or self.request.query_params.get('product_name')
        if product_name:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[产品查询] 搜索关键词: {product_name}")
            
            filtered_data = []
            for obj in queryset:
                # 检查是否应该包含该记录
                should_include = False
                
                # 1. 检查 product 字段
                if obj.product and product_name.lower() in obj.product.lower():
                    should_include = True
                    logger.info(f"[产品查询] 记录ID={obj.id}, product字段匹配: '{obj.product}'")
                
                # 2. 检查 user_info_list 中的产品名称（独立检查，不依赖 product 字段）
                if not should_include and obj.user_info_list and isinstance(obj.user_info_list, list):
                    for user_info in obj.user_info_list:
                        product_in_list = user_info.get('Product', '')
                        if product_name.lower() in product_in_list.lower():
                            should_include = True
                            logger.info(f"[产品查询] 记录ID={obj.id}, user_info_list匹配: '{product_in_list}'")
                            break
                    else:
                        logger.debug(f"[产品查询] 记录ID={obj.id}, user_info_list不匹配: {[u.get('Product', '') for u in obj.user_info_list]}")
                
                if not should_include:
                    logger.debug(f"[产品查询] 记录ID={obj.id} 未匹配, product='{obj.product}', has_user_info_list={bool(obj.user_info_list)}")
                
                if should_include:
                    filtered_data.append(obj)
            
            logger.info(f"[产品查询] 过滤后结果数量: {len(filtered_data)}, IDs: {[obj.id for obj in filtered_data]}")
            
            # 重新创建 QuerySet（用于分页）
            queryset = LicenseApplication.objects.filter(id__in=[obj.id for obj in filtered_data])
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return SuccessResponse(data=serializer.data)
    
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
        user_type = ''
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
                    product_features = transform_result.get('product_features', {})
                    user_info_list = transform_result.get('user_info_list', [])
                    mac_address = transform_result.get('mac_address', '')
                    hostname = transform_result.get('hostname', '')
                                    
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
                    
                    # 提取申请人ID（用于邮件发送）
                    applicant_id = get_applicant_from_transformed_data(
                        transformed_data=transformed_data,
                        license_type=license_type,
                        user_type=user_type,  # 使用从JSON解析的user_type，而不是硬编码'external'
                        field_name='ApplicantID'
                    )
                    
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
                    
                    # 从转换后的数据中提取 ScopeApplication 的值（如果存在）
                    scope_application = ''
                    if user_type == 'internal':
                        # 优先从 transformed_data 中获取（已经映射后的 real_key）
                        scope_application = transformed_data.get('ScopeApplication', '')
                    
                    # 创建申请记录
                    application = LicenseApplication.objects.create(
                        applicant=applicant or '未知申请人',
                        applicant_id=applicant_id if applicant_id else None,  # 保存申请人ID
                        application_type=license_type,
                        usage_type=user_type,  # 使用范围（内部/外部）
                        scope_application=scope_application if scope_application else None,  # 使用范围具体值
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
                'watch_dir': os.path.join(settings.JSON_FILE_PATH) if is_running else None
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
            watch_dir = os.path.join(settings.JSON_FILE_PATH)
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
                        logger.error(f"错误位置: 行 {getattr(e, 'lineno', 'N/A')}, 列 {getattr(e, 'colno', 'N/A')}")
                        logger.info(f"准备发送 JSON 解析失败邮件...")
                        
                        # 发送 JSON 解析失败邮件
                        try:
                            logger.info(f"[邮件发送] 步骤1: 开始发送邮件")
                            
                            from utils.email import EmailManager
                            logger.info(f"[邮件发送] 步骤2: 导入 EmailManager 成功")
                            
                            # JSON 解析失败时，直接发送给指定人员
                            owner_account = config.MAIL_RECIPIENT  # 固定接收人
                            logger.info(f"[邮件发送] 步骤3: 邮件接收人: {owner_account}")
                            
                            # 直接使用原始内容，因为 JSON 已经解析失败，无法再次解析
                            formatted_json = content
                            logger.info(f"[邮件发送] 步骤4: JSON 内容长度: {len(formatted_json)} 字符")
                            
                            email_manager = EmailManager()
                            logger.info(f"[邮件发送] 步骤5: EmailManager 实例创建成功")
                            
                            # 提取文件名（从完整路径中）
                            import os
                            file_name = os.path.basename(file_path)
                            email_manager.json_parsing_failed_send_email(owner_account, formatted_json, file_name)
                            logger.info(f"[邮件发送] 步骤6: 已发送 JSON 解析失败邮件给: {owner_account}，文件名: {file_name}")
                        except Exception as email_err:
                            logger.error(f"[邮件发送] 发送邮件失败: {str(email_err)}", exc_info=True)
                        
                        logger.info(f"JSON 解析失败处理完成，返回 False")
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
                    
                    if not result.get('success'):
                        logger.error(f"转换失败: {result.get('error')}")
                        return False
                    
                    transformed_data = result['transformed_data']
                    features = result.get('features', [])
                    product_features = result.get('product_features', {})
                    user_info_list = result.get('user_info_list', [])
                    mac_address = result.get('mac_address', '')
                    hostname = result.get('hostname', '')
                    
                    # 从 transformed_data 中提取全局的 mac_address 和 hostname（作为 fallback）
                    mac_address = transformed_data.get('MacAddress', '')
                    if mac_address:
                        mac_address = mac_address.upper()
                    hostname = transformed_data.get('Hostname', '')
                    
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
                            applicant = value
                    
                    # 检查序列号是否为空
                    if not serial_number:
                        logger.warning(f'序列号为空，跳过处理文件: {file_path}')
                        return False
                    
                    # 在创建申请记录之前，为每个产品生成独立的 FlexNet 预制作 license 模板文件
                    flexnet_template_files = {}  # {product: template_file_path}
                    if license_type == 'flexnet':
                        try:
                            # 特殊产品分组：GloryEX、GloryEX3D、GloryPolaris、GloryEXCommon 合并为一个模板文件
                            gloryex_group_products = ['GloryEX', 'GloryEX3D', 'GloryPolaris', 'GloryEXCommon']
                            
                            # 第一步：检测是否存在 GloryEX 组的产品
                            has_gloryex_group = False
                            gloryex_products_found = []
                            for product in product_features.keys():
                                if product in gloryex_group_products:
                                    has_gloryex_group = True
                                    gloryex_products_found.append(product)
                            
                            logger.info(f"FlexNet模板生成 - GloryEX 组产品检测结果: has_gloryex_group={has_gloryex_group}, 找到的产品={gloryex_products_found}")
                            
                            # 第二步：如果存在 GloryEX 组产品，先合并生成一个模板文件
                            if has_gloryex_group:
                                logger.info("开始合并生成 GloryEX 组的 FlexNet 预制作模板文件")
                                
                                # 合并 GloryEX 组的所有产品的 features
                                merged_gloryex_features = {}
                                for group_product in gloryex_group_products:
                                    if group_product in product_features:
                                        merged_gloryex_features.update(product_features[group_product])
                                        logger.info(f"合并产品 {group_product} 的 feature 到模板中")
                                
                                if merged_gloryex_features:
                                    # 获取第一个 GloryEX 组产品的 keyword（如果有的话）
                                    gloryex_keyword = None
                                    for ui in user_info_list:
                                        product = ui.get('Product')
                                        if product and product in gloryex_group_products:
                                            gloryex_keyword = ui.get('Keyword')
                                            break
                                    
                                    # 【关键修复】生成合并的模板文件时，传入完整的 product_features（包含所有产品）
                                    # 这样函数内部可以根据每个 feature 所属的产品获取对应的时间
                                    template_file_path = _generate_flexnet_template_file(
                                        serial_number=serial_number,
                                        mac_address=mac_address,
                                        hostname=hostname,
                                        product_name='GloryEX',  # 统一使用 GloryEX 作为产品名（用于文件名）
                                        product_features=product_features,  # 传入完整的 product_features（包含所有产品）
                                        user_info_list=user_info_list,
                                        file_hash=file_hash,
                                        keyword=gloryex_keyword,
                                        is_product_group=True,  # 标记为产品组合并
                                        group_products=gloryex_group_products  # 传递组内产品名称列表
                                    )
                                    if template_file_path:
                                        flexnet_template_files['GloryEX'] = template_file_path
                                        logger.info(f"GloryEX 组合并模板文件已生成: {template_file_path}")
                                        # 标记这三个产品为已处理
                                        for p in gloryex_group_products:
                                            if p in product_features:
                                                flexnet_template_files[p] = template_file_path  # 指向同一个文件
                            
                            # 第二步：处理其他非 GloryEX 组的产品
                            for product, product_feats in product_features.items():
                                if not product_feats:
                                    continue
                                
                                # 如果是 GloryEX 组产品且已经生成了合并模板，跳过
                                if product in gloryex_group_products and 'GloryEX' in flexnet_template_files:
                                    logger.info(f"产品 {product} 已包含在 GloryEX 组合并模板中，跳过单独生成")
                                    continue
                                
                                # 从 user_info 中获取 keyword（如果有的话）
                                product_keyword = None
                                for ui in user_info_list:
                                    if ui.get('Product') == product:
                                        product_keyword = ui.get('Keyword')
                                        break
                                
                                template_file_path = _generate_flexnet_template_file(
                                    serial_number=serial_number,
                                    mac_address=mac_address,
                                    hostname=hostname,
                                    product_name=product,
                                    product_features={product: product_feats},  # 只传入当前产品的 features
                                    user_info_list=user_info_list,
                                    file_hash=file_hash,
                                    keyword=product_keyword  # 传递 keyword
                                )
                                if template_file_path:
                                    flexnet_template_files[product] = template_file_path
                                    logger.info(f"产品 {product} 的 FlexNet 预制作模板文件已生成: {template_file_path}")
                            
                            if flexnet_template_files:
                                logger.info(f"共生成 {len(set(flexnet_template_files.values()))} 个独立的 FlexNet 预制作模板文件")
                        except Exception as e:
                            logger.error(f"生成 FlexNet 预制作模板文件失败: {str(e)}", exc_info=True)
                            # 不阻断流程，继续创建申请记录
                    
                    # 特殊产品分组：GloryEX、GloryEX3D、GloryPolaris、GloryEXCommon 合并为一个申请记录
                    gloryex_group_products = ['GloryEX', 'GloryEX3D', 'GloryPolaris', 'GloryEXCommon']
                    # GloryBolt、GloryGrid 合并为一个申请记录
                    glorybolt_group_products = ['GloryBolt', 'GloryGrid']
                    
                    # 按产品分组处理
                    processed_products = set()  # 已处理的产品集合
                    created_applications = []  # 记录创建的申请
                    
                    # 第一步：检测是否存在 GloryEX 组的产品
                    has_gloryex_group = False
                    gloryex_products_found = []
                    for user_info in user_info_list:
                        product = user_info.get('Product')
                        if product and product in gloryex_group_products:
                            has_gloryex_group = True
                            gloryex_products_found.append(product)
                            logger.info(f"检测到 GloryEX 组产品: {product}")
                    
                    logger.info(f"GloryEX 组产品检测结果: has_gloryex_group={has_gloryex_group}, 找到的产品={gloryex_products_found}")
                    logger.info(f"product_features 中的所有产品: {list(product_features.keys())}")
                    
                    # 第二步：如果存在 GloryEX 组产品，先合并处理
                    if has_gloryex_group:
                        logger.info("开始合并处理 GloryEX 组产品")
                        
                        # 合并处理GloryEX组的所有产品
                        gloryex_features = {}
                        gloryex_feature_list = []
                        min_start_time = None
                        max_end_time = None
                        
                        for group_product in gloryex_group_products:
                            logger.info(f"检查是否处理产品: {group_product}")
                            if group_product in product_features:
                                logger.info(f"合并产品 {group_product} 的 feature: {list(product_features[group_product].keys())}")
                                # 合并feature
                                gloryex_features.update(product_features[group_product])
                                # 合并feature列表
                                for feat in product_features[group_product].keys():
                                    if feat not in gloryex_feature_list:
                                        gloryex_feature_list.append(feat)
                            else:
                                logger.info(f"产品 {group_product} 不在 product_features 中，跳过")
                            
                            # 查找对应产品的UserInfo，获取时间
                            for ui in user_info_list:
                                if ui.get('Product') == group_product:
                                    start_timestamp = ui.get('Startdate')
                                    end_timestamp = ui.get('Expirydate')
                                    logger.info(f"产品 {group_product} 的时间: Start={start_timestamp}, End={end_timestamp}")
                                    
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
                            
                            # 标记为已处理
                            processed_products.add(group_product)
                        
                        logger.info(f"合并后的 feature 列表: {gloryex_feature_list}")
                        logger.info(f"合并后的 quantity: {gloryex_features}")
                        logger.info(f"时间范围: {min_start_time} ~ {max_end_time}")
                        
                        # 【关键修复】为 GloryEX 组过滤出专属的 user_info_list（包含 GloryEXCommon）
                        gloryex_user_info_list = [
                            ui for ui in user_info_list 
                            if ui.get('Product') in gloryex_group_products
                        ]
                        logger.info(f"GloryEX 组专属 user_info_list 长度: {len(gloryex_user_info_list)}")
                        logger.info(f"GloryEX 组产品列表: {[ui.get('Product') for ui in gloryex_user_info_list]}")
                        
                        # 处理MAC地址：在最外层已经处理过了，直接使用
                        # mac_address 变量在第378行已经提取并处理

                        # 提取申请人ID（用于邮件发送）
                        applicant_id = get_applicant_from_transformed_data(
                            transformed_data=transformed_data,
                            license_type=license_type,
                            user_type=user_type,  # 使用从JSON解析的user_type，而不是硬编码'external'
                            field_name='ApplicantID'
                        )

                        # 从转换后的数据中提取 ScopeApplication 的值（如果存在）
                        scope_application = ''
                        if user_type == 'internal':
                            # 优先从 transformed_data 中获取（已经映射后的 real_key）
                            scope_application = transformed_data.get('ScopeApplication', '')

                        # 检查该产品的申请记录是否已存在
                        if LicenseApplication.objects.filter(file_hash=file_hash, product='GloryEX').exists():
                            logger.info(f'GloryEX产品申请记录已存在（文件哈希: {file_hash}），跳过创建')
                        else:
                            logger.info(f"准备创建 GloryEX 组合并申请记录")
                            logger.info(f"  - applicant: {applicant or '未知申请人'}")
                            logger.info(f"  - applicant_id: {applicant_id}")
                            logger.info(f"  - license_type: {license_type}")
                            logger.info(f"  - features: {gloryex_feature_list}")
                            logger.info(f"  - quantity: {gloryex_features}")
                            logger.info(f"  - start_time: {min_start_time}")
                            logger.info(f"  - end_time: {max_end_time}")
                            logger.info(f"  - file_hash: {file_hash}")
                            
                            # 创建GloryEX组的申请记录，使用过滤后的 user_info_list
                            application = LicenseApplication.objects.create(
                                applicant=applicant or '未知申请人',
                                applicant_id=applicant_id if applicant_id else None,  # 保存申请人ID
                                application_type=license_type,
                                usage_type=user_type,  # 使用范围（内部/外部）
                                scope_application=scope_application if scope_application else None,  # 使用范围具体值
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
                                user_info_list=gloryex_user_info_list,  # 【关键】使用过滤后的纯净数据
                                status=3,
                                max_retry_count=3
                            )
                            created_applications.append(application.id)
                            logger.info(f"创建 GloryEX 组合并申请记录成功，ID: {application.id}")
                            
                            # 检查结束时间是否即将过期（小于30天）
                            from datetime import datetime, timedelta
                            if max_end_time:
                                days_until_expiry = (max_end_time - datetime.now()).days
                                if days_until_expiry < 30:
                                    logger.warning(f"GloryEX 组合并 License 将在 {days_until_expiry} 天后过期 ({max_end_time})，发送提醒邮件")
                                    try:
                                        from utils.email import EmailManager
                                        
                                        # 通过映射表从转换后的数据中获取申请人账号
                                        owner_account = get_applicant_from_transformed_data(
                                            transformed_data, license_type, user_type
                                        )
                                        
                                        if not owner_account:
                                            logger.warning("未获取到申请人账号，使用默认值")
                                            owner_account = config.MAIL_RECIPIENT
                                        
                                        # 发送即将过期提醒邮件
                                        email_manager = EmailManager()
                                        email_manager.license_expired_send_email(owner_account, application, max_end_time)
                                        logger.info(f"已发送 License 即将过期提醒邮件给: {owner_account}")
                                    except Exception as email_err:
                                        logger.error(f"发送过期提醒邮件失败: {str(email_err)}")
                            
                            # 如果是 FlexNet 类型，立即生成 license 文件
                            if license_type == 'flexnet':
                                try:
                                    # 获取对应的预制作模板文件路径（使用第一个产品的模板）
                                    template_file = None
                                    for group_product in gloryex_group_products:
                                        if group_product in flexnet_template_files:
                                            template_file = flexnet_template_files[group_product]
                                            break
                                    
                                    if template_file:
                                        # 将相对路径转换为绝对路径
                                        abs_template_file = os.path.join(MEDIA_ROOT, template_file)
                                        gen_result = self._generate_flexnet_license(
                                            instance=application,
                                            json_data=json_data,
                                            template_file_path=abs_template_file
                                        )
                                        if gen_result.get('success'):
                                            logger.info(f"GloryEX组 License 文件生成成功: {gen_result.get('file_relative_path')}")
                                        else:
                                            logger.error(f"GloryEX组 License 文件生成失败: {gen_result.get('error')}")
                                    else:
                                        logger.warning(f"未找到 GloryEX 组的预制作模板文件，跳过 License 生成")
                                except Exception as e:
                                    logger.error(f"生成 GloryEX组 License 文件异常: {str(e)}", exc_info=True)
                            
                            # 如果是 Bitanswer 类型，直接调用 API 生成 license 文件
                            elif license_type == 'bitanswer':
                                try:
                                    gen_result = self._generate_bitanswer_license(
                                        instance=application,
                                        json_data=json_data
                                    )
                                    if gen_result.get('success'):
                                        logger.info(f"GloryEX组 Bitanswer License 文件生成成功: {gen_result.get('file_relative_path')}")
                                    else:
                                        logger.error(f"GloryEX组 Bitanswer License 文件生成失败: {gen_result.get('error')}")
                                except Exception as e:
                                    logger.error(f"生成 GloryEX组 Bitanswer License 文件异常: {str(e)}", exc_info=True)
                    
                    # 第二步：检测是否存在 GloryBolt 组的产品
                    has_glorybolt_group = False
                    glorybolt_products_found = []
                    for user_info in user_info_list:
                        product = user_info.get('Product')
                        if product and product in glorybolt_group_products:
                            has_glorybolt_group = True
                            glorybolt_products_found.append(product)
                            logger.info(f"检测到 GloryBolt 组产品: {product}")
                    
                    logger.info(f"GloryBolt 组产品检测结果: has_glorybolt_group={has_glorybolt_group}, 找到的产品={glorybolt_products_found}")
                    
                    # 第三步：如果存在 GloryBolt 组产品，先合并处理
                    if has_glorybolt_group:
                        logger.info("开始合并处理 GloryBolt 组产品")
                        
                        # 合并处理GloryBolt组的所有产品
                        glorybolt_features = {}
                        glorybolt_feature_list = []
                        min_start_time = None
                        max_end_time = None
                        
                        for group_product in glorybolt_group_products:
                            logger.info(f"检查是否处理产品: {group_product}")
                            if group_product in product_features:
                                logger.info(f"合并产品 {group_product} 的 feature: {list(product_features[group_product].keys())}")
                                # 合并feature
                                glorybolt_features.update(product_features[group_product])
                                # 合并feature列表
                                for feat in product_features[group_product].keys():
                                    if feat not in glorybolt_feature_list:
                                        glorybolt_feature_list.append(feat)
                            else:
                                logger.info(f"产品 {group_product} 不在 product_features 中，跳过")
                            
                            # 查找对应产品的UserInfo，获取时间
                            for ui in user_info_list:
                                if ui.get('Product') == group_product:
                                    start_timestamp = ui.get('Startdate')
                                    end_timestamp = ui.get('Expirydate')
                                    logger.info(f"产品 {group_product} 的时间: Start={start_timestamp}, End={end_timestamp}")
                                    
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
                            
                            # 标记为已处理
                            processed_products.add(group_product)
                        
                        logger.info(f"合并后的 feature 列表: {glorybolt_feature_list}")
                        logger.info(f"合并后的 quantity: {glorybolt_features}")
                        logger.info(f"时间范围: {min_start_time} ~ {max_end_time}")
                        
                        # 【关键修复】为 GloryBolt 组过滤出专属的 user_info_list
                        glorybolt_user_info_list = [
                            ui for ui in user_info_list 
                            if ui.get('Product') in glorybolt_group_products
                        ]
                        logger.info(f"GloryBolt 组专属 user_info_list 长度: {len(glorybolt_user_info_list)}")
                        
                        # 提取申请人ID（用于邮件发送）
                        applicant_id = get_applicant_from_transformed_data(
                            transformed_data=transformed_data,
                            license_type=license_type,
                            user_type=user_type,
                            field_name='ApplicantID'
                        )

                        # 从转换后的数据中提取 ScopeApplication 的值（如果存在）
                        scope_application = ''
                        if user_type == 'internal':
                            # 优先从 transformed_data 中获取（已经映射后的 real_key）
                            scope_application = transformed_data.get('ScopeApplication', '')

                        # 检查该产品的申请记录是否已存在
                        if LicenseApplication.objects.filter(file_hash=file_hash, product='GloryBolt').exists():
                            logger.info(f'GloryBolt产品申请记录已存在（文件哈希: {file_hash}），跳过创建')
                        else:
                            logger.info(f"准备创建 GloryBolt 组合并申请记录")
                            logger.info(f"  - applicant: {applicant or '未知申请人'}")
                            logger.info(f"  - applicant_id: {applicant_id}")
                            logger.info(f"  - license_type: {license_type}")
                            logger.info(f"  - features: {glorybolt_feature_list}")
                            logger.info(f"  - quantity: {glorybolt_features}")
                            logger.info(f"  - start_time: {min_start_time}")
                            logger.info(f"  - end_time: {max_end_time}")
                            logger.info(f"  - file_hash: {file_hash}")
                            
                            # 创建GloryBolt组的申请记录，使用过滤后的 user_info_list
                            application = LicenseApplication.objects.create(
                                applicant=applicant or '未知申请人',
                                applicant_id=applicant_id if applicant_id else None,
                                application_type=license_type,
                                usage_type=user_type,  # 使用范围（内部/外部）
                                scope_application=scope_application if scope_application else None,  # 使用范围具体值
                                feature=glorybolt_feature_list if glorybolt_feature_list else [],
                                product='GloryBolt',  # 统一使用GloryBolt作为产品名
                                serial_number=serial_number or '',
                                file_hash=file_hash,
                                customer_name=customer_name or '未指定客户',
                                mac_address=mac_address,
                                hostname=hostname or '',
                                start_time=min_start_time,
                                end_time=max_end_time,
                                quantity=glorybolt_features if glorybolt_features else {},
                                json_data=json_data,
                                user_info_list=glorybolt_user_info_list,  # 【关键】使用过滤后的纯净数据
                                status=3,
                                max_retry_count=3
                            )
                            created_applications.append(application.id)
                            logger.info(f"创建 GloryBolt 组合并申请记录成功，ID: {application.id}")
                            
                            # 检查结束时间是否即将过期（小于30天）
                            from datetime import datetime, timedelta
                            if max_end_time:
                                days_until_expiry = (max_end_time - datetime.now()).days
                                if days_until_expiry < 30:
                                    logger.warning(f"GloryBolt 组合并 License 将在 {days_until_expiry} 天后过期 ({max_end_time})，发送提醒邮件")
                                    try:
                                        
                                        # 通过映射表从转换后的数据中获取申请人账号
                                        owner_account = get_applicant_from_transformed_data(
                                            transformed_data, license_type, user_type
                                        )
                                        
                                        if not owner_account:
                                            logger.warning("未获取到申请人账号，使用默认值")
                                            owner_account = config.MAIL_RECIPIENT
                                        
                                        # 发送即将过期提醒邮件
                                        email_manager = EmailManager()
                                        email_manager.license_expired_send_email(owner_account, application, max_end_time)
                                        logger.info(f"已发送 License 即将过期提醒邮件给: {owner_account}")
                                    except Exception as email_err:
                                        logger.error(f"发送过期提醒邮件失败: {str(email_err)}")
                            
                            # 如果是 FlexNet 类型，立即生成 license 文件
                            if license_type == 'flexnet':
                                try:
                                    # 获取对应的预制作模板文件路径（使用第一个产品的模板）
                                    template_file = None
                                    for group_product in glorybolt_group_products:
                                        if group_product in flexnet_template_files:
                                            template_file = flexnet_template_files[group_product]
                                            break
                                    
                                    if template_file:
                                        # 将相对路径转换为绝对路径
                                        abs_template_file = os.path.join(MEDIA_ROOT, template_file)
                                        gen_result = self._generate_flexnet_license(
                                            instance=application,
                                            json_data=json_data,
                                            template_file_path=abs_template_file
                                        )
                                        if gen_result.get('success'):
                                            logger.info(f"GloryBolt组 License 文件生成成功: {gen_result.get('file_relative_path')}")
                                        else:
                                            logger.error(f"GloryBolt组 License 文件生成失败: {gen_result.get('error')}")
                                    else:
                                        logger.warning(f"未找到 GloryBolt 组的预制作模板文件，跳过 License 生成")
                                except Exception as e:
                                    logger.error(f"生成 GloryBolt组 License 文件异常: {str(e)}", exc_info=True)
                            
                            # 如果是 Bitanswer 类型，直接调用 API 生成 license 文件
                            elif license_type == 'bitanswer':
                                try:
                                    gen_result = self._generate_bitanswer_license(
                                        instance=application,
                                        json_data=json_data
                                    )
                                    if gen_result.get('success'):
                                        logger.info(f"GloryBolt组 Bitanswer License 文件生成成功: {gen_result.get('file_relative_path')}")
                                    else:
                                        logger.error(f"GloryBolt组 Bitanswer License 文件生成失败: {gen_result.get('error')}")
                                except Exception as e:
                                    logger.error(f"生成 GloryBolt组 Bitanswer License 文件异常: {str(e)}", exc_info=True)
                    
                    # 第三步：处理其他非产品组的产品
                    for user_info in user_info_list:
                        product = user_info.get('Product')
                        if not product:
                            continue
                        
                        logger.info(f"检查产品: {product}")
                        
                        # 如果产品已经处理过，跳过
                        if product in processed_products:
                            logger.info(f"产品 {product} 已在产品组合并中处理过，跳过")
                            continue
                        
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
                        
                        # 【关键修复】为单个产品过滤出专属的 user_info_list（只包含当前产品）
                        single_product_user_info_list = [user_info]  # 单个产品只需要自己的数据
                        logger.info(f"产品 {product} 专属 user_info_list 长度: {len(single_product_user_info_list)}")
                        
                        # 处理MAC地址：在最外层已经处理过了，直接使用
                        # mac_address 变量在第378行已经提取并处理
                        
                        # 提取申请人ID（用于邮件发送）
                        applicant_id = get_applicant_from_transformed_data(
                            transformed_data=transformed_data,
                            license_type=license_type,
                            user_type=user_type,  # 使用从JSON解析的user_type，而不是硬编码'external'
                            field_name='ApplicantID'
                        )

                        # 从转换后的数据中提取 ScopeApplication 的值（如果存在）
                        scope_application = ''
                        if user_type == 'internal':
                            # 优先从 transformed_data 中获取（已经映射后的 real_key）
                            scope_application = transformed_data.get('ScopeApplication', '')
                        
                        # 检查该产品的申请记录是否已存在
                        if LicenseApplication.objects.filter(file_hash=file_hash, product=product).exists():
                            logger.info(f'产品{product}申请记录已存在（文件哈希: {file_hash}），跳过创建')
                        else:
                            logger.info(f"准备创建产品 {product} 的申请记录")
                            logger.info(f"  - features: {feat_list}")
                            logger.info(f"  - quantity: {product_feats}")
                            
                            application = LicenseApplication.objects.create(
                                applicant=applicant or '未知申请人',
                                applicant_id=applicant_id if applicant_id else None,  # 保存申请人ID
                                application_type=license_type,
                                usage_type=user_type,  # 使用范围（内部/外部）
                                scope_application=scope_application if scope_application else None,  # 使用范围具体值
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
                                user_info_list=single_product_user_info_list,  # 【关键】使用过滤后的纯净数据
                                status=3,
                                max_retry_count=3
                            )
                            created_applications.append(application.id)
                            processed_products.add(product)
                            logger.info(f"创建产品{product}申请记录成功，ID: {application.id}")
                            
                            # 检查结束时间是否即将过期（小于30天）
                            from datetime import datetime, timedelta
                            if end_time:
                                days_until_expiry = (end_time - datetime.now()).days
                                if days_until_expiry < 30:
                                    logger.warning(f"产品 {product} License 将在 {days_until_expiry} 天后过期 ({end_time})，发送提醒邮件")
                                    try:
                                        from utils.email import EmailManager
                                        
                                        # 通过映射表从转换后的数据中获取申请人账号
                                        owner_account = get_applicant_from_transformed_data(
                                            transformed_data, license_type, user_type
                                        )
                                        
                                        if not owner_account:
                                            logger.warning("未获取到申请人账号，使用默认值")
                                            owner_account = config.MAIL_RECIPIENT
                                        
                                        # 发送即将过期提醒邮件
                                        email_manager = EmailManager()
                                        email_manager.license_expired_send_email(owner_account, application, end_time)
                                        logger.info(f"已发送 License 即将过期提醒邮件给: {owner_account}")
                                    except Exception as email_err:
                                        logger.error(f"发送过期提醒邮件失败: {str(email_err)}")
                            
                            # 如果是 FlexNet 类型，立即生成 license 文件
                            if license_type == 'flexnet':
                                try:
                                    # 获取对应的预制作模板文件路径
                                    template_file = flexnet_template_files.get(product)
                                    
                                    if template_file:
                                        # 将相对路径转换为绝对路径
                                        abs_template_file = os.path.join(MEDIA_ROOT, template_file)
                                        gen_result = self._generate_flexnet_license(
                                            instance=application,
                                            json_data=json_data,
                                            template_file_path=abs_template_file
                                        )
                                        if gen_result.get('success'):
                                            logger.info(f"产品 {product} License 文件生成成功: {gen_result.get('file_relative_path')}")
                                        else:
                                            logger.error(f"产品 {product} License 文件生成失败: {gen_result.get('error')}")
                                    else:
                                        logger.warning(f"未找到产品 {product} 的预制作模板文件，跳过 License 生成")
                                except Exception as e:
                                    logger.error(f"生成产品 {product} License 文件异常: {str(e)}", exc_info=True)
                            
                            # 如果是 Bitanswer 类型，直接调用 API 生成 license 文件
                            elif license_type == 'bitanswer':
                                try:
                                    gen_result = self._generate_bitanswer_license(
                                        instance=application,
                                        json_data=json_data
                                    )
                                    if gen_result.get('success'):
                                        logger.info(f"产品 {product} Bitanswer License 文件生成成功: {gen_result.get('file_relative_path')}")
                                    else:
                                        logger.error(f"产品 {product} Bitanswer License 文件生成失败: {gen_result.get('error')}")
                                except Exception as e:
                                    logger.error(f"生成产品 {product} Bitanswer License 文件异常: {str(e)}", exc_info=True)
                    
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
            # 从固定目录读取JSON文件，如果不存在则使用数据库中的json_data
            json_file_path = os.path.join(BASE_DIR, 'license_data', f'{instance.id}.json')
            
            if os.path.exists(json_file_path):
                # 从文件读取JSON数据
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                logger.info(f"从文件读取JSON数据: {json_file_path}")
            elif instance.json_data:
                # 文件不存在，使用数据库中的json_data
                json_data = instance.json_data
                logger.info(f"JSON文件不存在，使用数据库中的json_data: 申请记录ID {instance.id}")
            else:
                return ErrorResponse(msg=f'JSON文件不存在且数据库中也没有json_data: {json_file_path}')
            
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
                # 重试时，需要重新生成预制作模板文件
                try:
                    from apps.lylicense.views import _generate_flexnet_template_file
                    
                    # 从 transformed_data 中提取必要信息
                    serial_number = transformed_data.get('SerialNumber', instance.serial_number)
                    mac_address = transformed_data.get('MacAddress', instance.mac_address)
                    hostname = transformed_data.get('Hostname', instance.hostname)
                    product_name = transformed_data.get('Product', instance.product)
                    
                    # 清理 MAC 地址
                    mac_clean = mac_address.replace(':', '').replace('-', '').upper() if mac_address else 'UNKNOWN'
                    
                    # 构建 product_features 和 user_info_list
                    product_features = {}
                    user_info_list = []
                    
                    # 从 feature 和 quantity 中重建数据
                    if instance.feature and isinstance(instance.feature, list):
                        product_features[product_name] = {}
                        for feat in instance.feature:
                            # 从 quantity 中获取数量
                            if isinstance(instance.quantity, dict):
                                product_features[product_name][feat] = instance.quantity.get(feat, 1)
                            else:
                                product_features[product_name][feat] = 1
                    
                    # 构建 user_info_list
                    if instance.start_time and instance.end_time:
                        from datetime import datetime
                        start_timestamp = int(instance.start_time.strftime('%s')) * 1000 if hasattr(instance.start_time, 'strftime') else int(instance.start_time.timestamp()) * 1000
                        end_timestamp = int(instance.end_time.strftime('%s')) * 1000 if hasattr(instance.end_time, 'strftime') else int(instance.end_time.timestamp()) * 1000
                        
                        user_info_list.append({
                            'Product': product_name,
                            'Startdate': start_timestamp,
                            'Expirydate': end_timestamp,
                            'Keyword': instance.keyword
                        })
                    
                    # 生成预制作模板文件
                    file_hash = instance.file_hash or 'retry'
                    template_file_path = _generate_flexnet_template_file(
                        serial_number=serial_number or 'UNKNOWN',
                        mac_address=mac_address or 'UNKNOWN',
                        hostname=hostname or 'UNKNOWN',
                        product_name=product_name or 'UNKNOWN',
                        product_features=product_features,
                        user_info_list=user_info_list,
                        file_hash=file_hash,
                        keyword=instance.keyword
                    )
                    
                    if template_file_path:
                        # 将相对路径转换为绝对路径
                        abs_template_file = os.path.join(MEDIA_ROOT, template_file_path)
                        logger.info(f"重试时重新生成预制作模板文件: {abs_template_file}")
                        
                        result = self._generate_flexnet_license(
                            instance=instance,
                            json_data=transformed_data,
                            template_file_path=abs_template_file
                        )
                    else:
                        logger.error("重新生成预制作模板文件失败")
                        result = {
                            'success': False,
                            'error': '重新生成预制作模板文件失败'
                        }
                except Exception as e:
                    logger.error(f"重试时生成预制作模板文件异常: {str(e)}", exc_info=True)
                    result = {
                        'success': False,
                        'error': f'重试时生成预制作模板文件异常: {str(e)}'
                    }
            elif instance.application_type == 'bitanswer':
                result = self._generate_bitanswer_license(instance, json_data)
            else:
                return ErrorResponse(msg='不支持的License类型')
            
            if result['success']:
                instance.status = 1  # 制作成功
                instance.fail_reason = ''
                instance.save()
                
                # 创建License记录
                license_id = result.get('license_id', f'LIC-{instance.id}')
                
                # 从 json_data 中获取时间信息，并转换为 date 类型
                from datetime import datetime as dt
                start_time = json_data.get('start_time') or instance.start_time
                end_time = json_data.get('end_time') or instance.end_time
                
                # 如果是 datetime 类型，转换为 date 类型
                if isinstance(start_time, dt):
                    start_time = start_time.date()
                if isinstance(end_time, dt):
                    end_time = end_time.date()
                
                # 检查是否已存在
                if LicenseRecord.objects.filter(license_id=license_id).exists():
                    logger.info(f"LicenseRecord 已存在: {license_id}，跳过创建")
                else:
                    license_record = LicenseRecord.objects.create(
                        application=instance,
                        license_id=license_id,
                        license_type=instance.application_type,
                        file_name=result.get('file_name', ''),
                        file_relative_path=result.get('file_relative_path', ''),
                        directory=result.get('directory', ''),
                        full_path=result.get('full_path', ''),
                        feature=json_data.get('feature', instance.feature),
                        vendor=result.get('vendor', ''),
                        version=result.get('version', ''),
                        host_id=json_data.get('mac_address', instance.mac_address),
                        start_time=start_time,
                        end_time=end_time,
                        quantity=json_data.get('quantity', instance.quantity),
                        status=1,  # 有效
                        extra_info=result.get('extra_info', {})
                    )
                    logger.info(f"License 记录已创建: {license_record.license_id}, quantity: {json.dumps(license_record.quantity, ensure_ascii=False)}")
                
                # 发送邮件通知申请人（制作成功）
                try:
                    from utils.email import EmailManager
                    from django.conf import settings
                    
                    # 优先使用数据库中保存的 applicant_id（真实账号）
                    email_applicant = instance.applicant_id
                    
                    # 如果数据库中没有，尝试从 json_data 中提取
                    if not email_applicant:
                        # 从 instance.json_data 中提取 user_type
                        usage_from_json = instance.json_data.get('Usage', '') if instance.json_data else ''
                        email_user_type = 'external'  # 默认值
                        if usage_from_json == '内部':
                            email_user_type = 'internal'
                        elif usage_from_json == '外部':
                            email_user_type = 'external'
                        
                        email_applicant = get_applicant_from_transformed_data(
                            transformed_data=json_data,
                            license_type=instance.application_type,
                            user_type=email_user_type,  # 使用从JSON解析的user_type
                            field_name='ApplicantID'
                        )
                    
                    # 如果还是没有，使用配置文件中的默认接收人（不能使用中文名称）
                    if not email_applicant:
                        from config import MAIL_RECIPIENT
                        email_applicant = MAIL_RECIPIENT
                        logger.warning(f"未找到申请人账号，使用默认接收人: {email_applicant}")
                    
                    if email_applicant and email_applicant != '未知申请人':
                        email_manager = EmailManager()
                        email_manager.license_generated_send_email(
                            owner=email_applicant,
                            application=instance,
                            license_file_name=result.get('file_name'),
                            remote_dir=config.SSH_REMOTE_TEMPLATE_DIR
                        )
                        logger.info(f"已发送 License 生成成功邮件给申请人: {email_applicant}")
                    else:
                        logger.warning(f"申请人信息为空，跳过邮件发送")
                except Exception as email_error:
                    logger.error(f"发送邮件失败: {str(email_error)}", exc_info=True)
                
                return SuccessResponse(data={
                    'application_id': instance.id,
                    'license_id': license_record.license_id,
                    'result': result
                }, msg='License制作成功')
            else:
                instance.status = 0  # 制作失败
                instance.fail_reason = result.get('error', '未知错误')
                # 注意：retry_count 已在 retry 方法中增加，这里不再重复增加
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
                # 注意：retry_count 已在 retry 方法中增加，这里不再重复增加
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
            
            # 在重试开始前，先增加重试次数
            instance.retry_count += 1
            instance.save()
            logger.info(f"开始重试 License 制作，申请记录ID: {instance.id}，当前重试次数: {instance.retry_count}/{instance.max_retry_count}")
            
            # 直接调用parse_and_generate逻辑
            return self.parse_and_generate(request, pk)
            
        except Exception as e:
            logger.error(f"重试失败: {str(e)}")
            if instance:
                instance.fail_reason = str(e)
                instance.save()
            return ErrorResponse(msg=f"重试失败: {str(e)}")
    
    def _generate_flexnet_license(self, instance, json_data, template_file_path=None):
        """
        生成FlexNet类型的License
        执行远程 lmcrypt_new 脚本生成正式 license 文件
        
        Args:
            instance: LicenseApplication 实例
            json_data: JSON 数据
            template_file_path: 预制作 license 模板文件路径（可选），如果提供则使用远程执行
        """
        try:
            # 构建license文件路径
            license_dir = os.path.join(MEDIA_ROOT, 'license', 'flexnet')
            if not os.path.exists(license_dir):
                os.makedirs(license_dir)
            
            file_name = f'{instance.id}_{instance.product}_flex.lic'
            license_file = os.path.join(license_dir, file_name)
            relative_path = os.path.join('license', 'flexnet', file_name)
            
            # 如果有预制作模板文件，使用远程执行 lmcrypt_new 脚本
            if template_file_path and os.path.exists(template_file_path):
                logger.info(f"使用远程 lmcrypt_new 脚本生成 FlexNet License，模板文件: {template_file_path}")
                
                # 远程执行 lmcrypt_new 脚本
                remote_result = _execute_remote_lmcrypt(template_file_path, instance.product)
                
                if remote_result['success']:
                    # 远程执行成功，记录信息
                    logger.info(f"远程生成 License 成功: {remote_result['remote_license_path']}")
                    
                    # 使用远程执行返回的实际文件名，而不是预定义的文件名
                    actual_file_name = os.path.basename(remote_result['local_license_path'])
                    actual_relative_path = os.path.join('license', 'flexnet', actual_file_name)
                    actual_full_path = remote_result['local_license_path']
                    
                    result = {
                        'success': True,
                        'file_name': actual_file_name,
                        'file_relative_path': actual_relative_path,
                        'directory': os.path.dirname(actual_full_path),
                        'full_path': actual_full_path,
                        'vendor': 'FlexNet',
                        'version': json_data.get('version', '1.0'),
                        'license_id': f'FN-{instance.id}',
                        'message': 'FlexNet License制作成功（远程执行）',
                        'template_used': template_file_path,
                        'remote_license_path': remote_result['remote_license_path'],
                        'remote_output': remote_result.get('output', '')
                    }
                else:
                    # 远程执行失败
                    logger.error(f"远程 lmcrypt_new 执行失败: {remote_result['error']}")
                    result = {
                        'success': False,
                        'error': f'远程 lmcrypt_new 执行失败: {remote_result["error"]}',
                        'template_used': template_file_path
                    }
            else:
                # 没有模板文件，返回错误
                logger.error("未提供预制作模板文件，无法生成 FlexNet License")
                result = {
                    'success': False,
                    'error': '未提供预制作模板文件'
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
        完整流程：
        1. 调用获取授权码接口（generate_sn）获取 sn
        2. 调用授权码绑定新用户接口（sn/customers）绑定 MAC 地址
        3. 调用制作license接口（sn/update_code）获取 code
        4. 将 code 写入 .upd 文件
        
        关键逻辑：将本地的feature名称转换为第三方平台的featureID
        """
        try:
            import requests
            from apps.lylicense.models import LicenseFieldMapping
            from config import BITANSWER_API_BASE_URL, BITANSWER_BITKEY
            
            # 从JSON数据中提取基础参数
            customer_name = json_data.get('customer_name', instance.customer_name)
            mac_address = json_data.get('mac_address', instance.mac_address)
            
            # 优先使用 application 实例中的时间字段
            start_time = instance.start_time
            end_time = instance.end_time
            
            # 如果 application 中没有，尝试从 json_data 中获取
            if not start_time:
                start_time = json_data.get('start_time')
            if not end_time:
                end_time = json_data.get('end_time')
            
            quantity = json_data.get('quantity', instance.quantity) or {}
            
            # 获取用户类型和License类型，用于查询映射表
            user_type = 'external'  # Bitanswer通常是外部用户
            license_type = 'bitanswer'
            
            # 获取产品名
            original_product = instance.product
            
            # 特殊处理：GloryEX 产品组统一使用 "GloryEX" 作为产品名
            gloryex_group_products = ['GloryEX', 'GloryEX3D', 'GloryPolaris', 'GloryEXCommon']
            glorybolt_group_products = ['GloryBolt', 'GloryGrid']
            is_glorybolt_group = False  # 标记是否为 GloryBolt 组
            
            if original_product in gloryex_group_products:
                product = 'GloryEX'  # 统一使用 GloryEX
                logger.info(f"产品属于 GloryEX 组，原始产品: {original_product} -> 统一使用: {product}")
            elif original_product in glorybolt_group_products:
                product = 'GloryBolt'  # 统一使用 GloryBolt
                is_glorybolt_group = True  # 标记为 GloryBolt 组
                logger.info(f"产品属于 GloryBolt 组，原始产品: {original_product} -> 统一使用: {product}（将合并处理 GloryBolt 和 GloryGrid 的 feature）")
            else:
                product = original_product
            
            # 构建features列表（包含featureID）
            features_list = []
            total_users_number = 0  # 总授权数量
            
            # 【关键修复】从 instance.user_info_list 中获取 user_info_list，用于获取每个产品的时间
            # instance 是 LicenseApplication 对象，其中保存了转换后的 user_info_list
            user_info_list = instance.user_info_list or []
            logger.info(f"Bitanswer: user_info_list 长度={len(user_info_list)}")
            if user_info_list:
                logger.info(f"Bitanswer: user_info_list 内容预览={json.dumps(user_info_list[:1], ensure_ascii=False)}")
            
            # 从 quantity 中获取 feature 及其数量
            if isinstance(quantity, dict):
                for feature_name, users_count in quantity.items():
                    # 【关键】对于 GloryBolt 组，统一使用 'GloryBolt' 作为产品名称
                    # api_product_name = product if is_glorybolt_group else feature_name
                                
                    # 处理嵌套结构：如果 users_count 是字典，需要进一步提取
                    if isinstance(users_count, dict):
                        # 嵌套结构：{feature_name: {sub_feature: count}}
                        # 这种情况下，遍历子字典
                        for sub_feature, sub_count in users_count.items():
                            if isinstance(sub_count, (int, float)):
                                actual_feature_name = f"{sub_feature}"
                                actual_users_count = int(sub_count)
                                total_users_number += actual_users_count
                                                            
                                # 【优化】通过 API 获取 featureId
                                # 对于 GloryBolt 组，使用统一的 'GloryBolt' 作为产品名称
                                feature_id = _get_feature_id_from_api(product, actual_feature_name)
                                                            
                                if feature_id:
                                    # 【关键修复】根据 feature 名称从 user_info_list 中查找其所属产品，获取对应的时间
                                    feature_end_date = end_time.strftime('%Y-%m-%d') if end_time else None
                                    
                                    if user_info_list:
                                        # 遍历 user_info_list，查找该 feature 属于哪个产品
                                        for ui in user_info_list:
                                            ui_product = ui.get('Product', '')
                                            
                                            # 检查该 feature 是否属于这个产品
                                            # user_info_list 的结构：{'Product': 'GloryEX', 'GloryEX': {'feat1': 10, ...}}
                                            product_features_dict = ui.get(ui_product, {})
                                            
                                            if actual_feature_name in product_features_dict:
                                                # 找到了！这个 feature 属于 ui_product
                                                ui_end_timestamp = ui.get('Expirydate', 0)
                                                if ui_end_timestamp and isinstance(ui_end_timestamp, (int, float)):
                                                    from datetime import datetime
                                                    ui_end_dt = datetime.fromtimestamp(ui_end_timestamp / 1000)
                                                    feature_end_date = ui_end_dt.strftime('%Y-%m-%d')
                                                    logger.info(f"Feature '{actual_feature_name}' 属于产品 '{ui_product}', 使用过期时间: {feature_end_date}")
                                                break
                                    
                                    features_list.append({
                                        'id': feature_id, 
                                        'users': actual_users_count,
                                        'endDate': feature_end_date
                                    })
                                    logger.info(f"Feature转换(嵌套): {actual_feature_name} -> FID={feature_id}, 授权数量={actual_users_count}, endDate={feature_end_date}")
                                else:
                                    logger.warning(f"未找到{product}产品的feature '{actual_feature_name}' 的ID，跳过该feature")
                    elif isinstance(users_count, (int, float)):
                        # 简单结构：{feature_name: count}
                        actual_users_count = int(users_count)
                        total_users_number += actual_users_count
                                                    
                        # 【优化】通过 API 获取 featureId
                        # 对于 GloryBolt 组，使用统一的 'GloryBolt' 作为产品名称
                        feature_id = _get_feature_id_from_api(original_product, feature_name)
                                                    
                        if feature_id:
                            # 【关键修复】根据 feature 名称从 user_info_list 中查找其所属产品，获取对应的时间
                            feature_end_date = end_time.strftime('%Y-%m-%d') if end_time else None
                            
                            if user_info_list:
                                # 遍历 user_info_list，查找该 feature 属于哪个产品
                                for ui in user_info_list:
                                    ui_product = ui.get('Product', '')
                                    
                                    # 检查该 feature 是否属于这个产品
                                    # user_info_list 的结构：{'Product': 'GloryEX', 'GloryEX': {'feat1': 10, ...}}
                                    product_features_dict = ui.get(ui_product, {})
                                    
                                    if feature_name in product_features_dict:
                                        # 找到了！这个 feature 属于 ui_product
                                        ui_end_timestamp = ui.get('Expirydate', 0)
                                        if ui_end_timestamp and isinstance(ui_end_timestamp, (int, float)):
                                            from datetime import datetime
                                            ui_end_dt = datetime.fromtimestamp(ui_end_timestamp / 1000)
                                            feature_end_date = ui_end_dt.strftime('%Y-%m-%d')
                                            logger.info(f"Feature '{feature_name}' 属于产品 '{ui_product}', 使用过期时间: {feature_end_date}")
                                        break
                            
                            features_list.append({
                                'id': feature_id,  
                                'users': actual_users_count,
                                'endDate': feature_end_date
                            })
                            logger.info(f"Feature转换: {feature_name} -> FID={feature_id}, 授权数量={actual_users_count}, endDate={feature_end_date}")
                        else:
                            logger.warning(f"未找到feature '{feature_name}' 的ID，跳过该feature")
            
            # 构建请求参数（按照第三方API要求的格式）
            # 【关键修复】对于产品组，startDate 和 endDate 使用最早开始时间和最晚结束时间
            # 但每个 feature 的 endDate 已经在上面单独设置了
            params = {
                'product': {
                    'productName': product  # 产品名
                },
                'template': {
                    'name': config.BITANSWER_TEMPLATE_NAME  # 模版名，可根据实际情况调整
                },
                'business': {
                    'name': config.BITANSWER_BUSINESS_NAME  # 业务名，可根据实际情况调整
                },
                'usersNumber': total_users_number,  # 总授权数量（所有feature的数量之和）
                'startDate': start_time.strftime('%Y-%m-%d') if start_time else None,
                'endDate': end_time.strftime('%Y-%m-%d') if end_time else None,
                'features': features_list  # Feature列表，包含id(FID)、users(授权数量)、endDate
            }
            
            # 设置通用 headers（三个接口都需要 bitkey）
            headers = {
                'Content-Type': 'application/json',
                'bitkey': BITANSWER_BITKEY  # 固定的 bitkey
            }
            
            logger.info(f"开始 Bitanswer License 生成流程")
            logger.info(f"步骤1: 调用获取授权码接口")
            logger.info(f"请求参数: {json.dumps(params, ensure_ascii=False, indent=2)}")
            
            # ==================== 步骤1: 获取授权码 ====================
            generate_sn_url = f'{BITANSWER_API_BASE_URL}/e3/api/sns/generate_sn?count=1'
            
            response1 = requests.post(
                generate_sn_url,
                json=params,
                headers=headers,
                timeout=30
            )
            
            if response1.status_code != 200:
                return {
                    'success': False,
                    'error': f'步骤1失败：获取授权码接口调用失败，状态码: {response1.status_code}',
                    'api_response': response1.text
                }
            
            result1 = response1.json()
            logger.info(f"步骤1响应: {json.dumps(result1, ensure_ascii=False, indent=2)}")
            
            # 检查响应状态
            if result1.get('status') != 0:
                return {
                    'success': False,
                    'error': f'步骤1失败：API返回错误状态 {result1.get("status")}',
                    'api_response': result1
                }
            
            # 提取 sn
            data = result1.get('data', {})
            items = data.get('items', [])
            if not items:
                return {
                    'success': False,
                    'error': '步骤1失败：API返回数据中没有 items',
                    'api_response': result1
                }
            
            sn = items[0].get('sn')
            if not sn:
                return {
                    'success': False,
                    'error': '步骤1失败：API返回数据中没有 sn',
                    'api_response': result1
                }
            
            logger.info(f"✅ 步骤1成功：获取到 sn = {sn}")
            
            # ==================== 步骤2: 授权码绑定新用户 ====================
            logger.info(f"步骤2: 调用授权码绑定新用户接口 (客户名称: {customer_name})")
            
            bind_customer_url = f'{BITANSWER_API_BASE_URL}/e3/api/sns/{sn}/customers'
            bind_params = [{
                'name': customer_name
            }]
            
            logger.info(f"请求参数: {json.dumps(bind_params, ensure_ascii=False, indent=2)}")
            
            response2 = requests.post(
                bind_customer_url,
                json=bind_params,
                headers=headers,
                timeout=30
            )
            
            if response2.status_code != 200:
                return {
                    'success': False,
                    'error': f'步骤2失败：授权码绑定接口调用失败，状态码: {response2.status_code}',
                    'api_response': response2.text
                }
            
            result2 = response2.json()
            logger.info(f"步骤2响应: {json.dumps(result2, ensure_ascii=False, indent=2)}")
            
            # 检查响应状态
            if result2.get('status') != 0:
                return {
                    'success': False,
                    'error': f'步骤2失败：API返回错误状态 {result2.get("status")}',
                    'api_response': result2
                }
            
            logger.info(f"✅ 步骤2成功：授权码已绑定 MAC 地址")
            
            # ==================== 步骤3: 制作license ====================
            logger.info(f"步骤3: 调用制作license接口 (MAC: {mac_address})")
            
            update_code_url = f'{BITANSWER_API_BASE_URL}/e3/api/sns/{sn}/update_code'
            update_params = {
                'mac': mac_address
            }
            
            logger.info(f"请求参数: {json.dumps(update_params, ensure_ascii=False, indent=2)}")
            
            response3 = requests.post(
                update_code_url,
                json=update_params,
                headers=headers,
                timeout=30
            )
            
            if response3.status_code != 200:
                return {
                    'success': False,
                    'error': f'步骤3失败：制作license接口调用失败，状态码: {response3.status_code}',
                    'api_response': response3.text
                }
            
            result3 = response3.json()
            logger.info(f"步骤3响应: {json.dumps(result3, ensure_ascii=False, indent=2)}")
            
            # 检查响应状态
            if result3.get('status') != 0:
                return {
                    'success': False,
                    'error': f'步骤3失败：API返回错误状态 {result3.get("status")}',
                    'api_response': result3
                }
            
            # 提取 code
            data3 = result3.get('data', {})
            items3 = data3.get('items', [])
            if not items3:
                return {
                    'success': False,
                    'error': '步骤3失败：API返回数据中没有 items',
                    'api_response': result3
                }
            
            code = items3[0].get('code')
            if not code:
                return {
                    'success': False,
                    'error': '步骤3失败：API返回数据中没有 code',
                    'api_response': result3
                }
            
            logger.info(f"✅ 步骤3成功：获取到 code（长度: {len(code)}）")
            
            # ==================== 步骤4: 将 code 写入 .upd 文件 ====================
            logger.info(f"步骤4: 将 code 写入 .upd 文件")
            
            # 构建license文件路径
            license_dir = os.path.join(MEDIA_ROOT, 'license', 'bitanswer')
            if not os.path.exists(license_dir):
                os.makedirs(license_dir)
            
            # 文件名格式：{序列号}_{产品名称}_{申请ID}.upd
            serial_number = instance.serial_number or 'unknown'
            file_name = f'{serial_number}_{product}_{instance.id}.upd'
            license_file = os.path.join(license_dir, file_name)
            relative_path = os.path.join('license', 'bitanswer', file_name)
            
            # 格式化 XML 内容（添加缩进和换行）
            try:
                import xml.dom.minidom
                from io import StringIO
                
                # 解析 XML
                dom = xml.dom.minidom.parseString(code)
                
                # 格式化输出（使用 pretty print）
                formatted_xml = dom.toprettyxml(indent='  ', encoding='UTF-8')
                
                # toprettyxml 返回的是 bytes，需要解码为字符串
                if isinstance(formatted_xml, bytes):
                    formatted_xml = formatted_xml.decode('utf-8')
                
                # 【优化】移除 XML 声明行（toprettyxml 会自动添加 <?xml version="1.0" encoding="UTF-8"?>）
                # 原始 code 中没有这个声明，所以需要移除以保持格式一致
                lines = formatted_xml.strip().split('\n')
                if lines and lines[0].startswith('<?xml'):
                    # 移除第一行（XML 声明）
                    formatted_xml = '\n'.join(lines[1:]).strip()
                else:
                    formatted_xml = formatted_xml.strip()
                
                logger.info(f"XML 格式化成功，原始长度: {len(code)}, 格式化后长度: {len(formatted_xml)}")
            except Exception as e:
                logger.warning(f"XML 格式化失败，使用原始内容: {str(e)}")
                formatted_xml = code
            
            # 保存格式化后的 code 到文件
            with open(license_file, 'w', encoding='utf-8') as f:
                f.write(formatted_xml)
            
            logger.info(f"✅ 步骤4成功：License文件已保存到 {license_file}")
            
            # ==================== 步骤5: 上传到远程服务器 ====================
            logger.info(f"步骤5: 上传 License 文件到远程服务器")
            
            try:
                upload_result = _upload_bitanswer_license_to_remote(license_file, file_name)
                
                if upload_result['success']:
                    logger.info(f"✅ 步骤5成功：{upload_result['message']}")
                    remote_path = upload_result['remote_path']
                else:
                    logger.warning(f"⚠️ 步骤5失败：{upload_result.get('error')}")
                    remote_path = None
            except Exception as e:
                logger.error(f"步骤5异常：{str(e)}")
                remote_path = None
            
            logger.info(f"🎉 Bitanswer License 生成流程全部完成！")
            
            result = {
                'success': True,
                'file_name': file_name,
                'file_relative_path': relative_path,
                'directory': license_dir,
                'full_path': license_file,
                'vendor': 'Bitanswer',
                'version': '3',  # 从 code 中的 <version>3</version> 提取
                'license_id': f'BA-{instance.id}',
                'sn': sn,
                'message': 'Bitanswer License制作成功',
                'remote_path': remote_path,  # 远程服务器上的文件路径
                'api_responses': {
                    'step1_generate_sn': result1,
                    'step2_bind_customer': result2,
                    'step3_update_code': result3
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Bitanswer License制作失败: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    @action(methods=['get'], detail=False)
    def dashboard_statistics(self, request):
        """
        Dashboard 统计分析接口
        返回：产品申请分布、Feature申请分布、客户申请分布
        """
        from django.db.models import Count, Q
        from collections import defaultdict

        # 1. 产品申请分布统计（按产品分组统计申请数量）
        product_stats = LicenseApplication.objects.values('product').distinct().annotate(
            count=Count('id')
        ).order_by('-count')

        # 2. Feature 申请分布统计（解析 feature JSON 字段和 quantity 字段）
        feature_stats_dict = defaultdict(int)
        total_feature_count = 0  # 所有 Feature 的总数（包括重复）
        applications = LicenseApplication.objects.filter(
            feature__isnull=False
        ).exclude(feature=[])

        for app in applications:
            # if app.feature:
            #     # feature 是 JSON 数组，如 ["Feature1", "Feature2"]
            #     if isinstance(app.feature, list):
            #         for feat in app.feature:
            #             if feat:
            #                 feature_stats_dict[feat] += 1
            #                 total_feature_count += 1
            #     elif isinstance(app.feature, str):
            #         # 如果是字符串，直接计数
            #         feature_stats_dict[app.feature] += 1
            #         total_feature_count += 1
            
            # 同时统计 quantity 字段中的 feature 数量
            if app.quantity and isinstance(app.quantity, dict):
                # 判断是否为 GloryEX 组产品
                is_gloryex_group = app.product == 'GloryEX'
                
                if is_gloryex_group:
                    # GloryEX 组产品：quantity 是嵌套结构 {'GloryEX': {...}, 'GloryEX3D': {...}}
                    for product_name, product_quantity in app.quantity.items():
                        if isinstance(product_quantity, dict):
                            for feat, qty in product_quantity.items():
                                if feat:
                                    feature_stats_dict[feat] += 1
                                    total_feature_count += 1
                else:
                    # 非 GloryEX 组产品：quantity 可能是扁平结构或嵌套结构
                    for feat, qty in app.quantity.items():
                        if feat:
                            feature_stats_dict[feat] += 1
                            total_feature_count += 1

        # 转换为列表并按数量排序
        feature_stats = [
            {'feature': feat, 'count': count}
            for feat, count in sorted(feature_stats_dict.items(), key=lambda x: x[1], reverse=True)
        ]

        # 3. 客户申请分布统计（按客户名称分组）
        customer_stats = LicenseApplication.objects.values('customer_name').distinct().annotate(
            count=Count('id')
        ).order_by('-count')

        # 4. 按 License 类型统计
        license_type_stats = LicenseApplication.objects.values('application_type').annotate(
            count=Count('id')
        )

        # 5. 按状态统计
        status_stats = LicenseApplication.objects.values('status').annotate(
            count=Count('id')
        )

        # 6. 总体统计
        total_applications = LicenseApplication.objects.values('applicant').distinct().count()

        return SuccessResponse(data={
            'product_stats': list(product_stats),
            'feature_stats': feature_stats,  # 返回所有 Feature 统计数据
            'customer_stats': list(customer_stats),  # 返回所有客户统计数据
            'license_type_stats': list(license_type_stats),
            'status_stats': list(status_stats),
            'total_applications': total_applications,
            'total_feature_count': total_feature_count,  # 所有 Feature 的总数（包括重复）
            'unique_feature_count': len(feature_stats)  # 去重后的 Feature 种类数
        })


class LicenseRecordViewSet(CustomModelViewSet):
    """
    License记录管理ViewSet
    展示制作完成后的License列表
    """
    queryset = LicenseRecord.objects.all()
    serializer_class = LicenseRecordSerializer
    filterset_fields = ['license_type', 'status', 'host_id']
    search_fields = ['license_id', 'feature', 'host_id', 'file_name']
    ordering_fields = ['create_datetime', 'end_time', 'remaining_days']
    ordering = '-create_datetime'
    # License模块不需要数据权限过滤
    extra_filter_backends = []
    
    def get_queryset(self):
        """重写查询集，支持客户名称筛选"""
        queryset = super().get_queryset()
        customer_name = self.request.query_params.get('customer_name')
        if customer_name:
            queryset = queryset.filter(application__customer_name__icontains=customer_name)
        return queryset
    
    def list(self, request, *args, **kwargs):
        """
        列表查询时自动更新已过期的License状态，并发送邮件提醒（30天、15天、7天各提醒一次）
        注意：主要的定时检查由 django-crontab 在每天凌晨2点执行
              这里的检查是作为补充，确保用户刷新列表时能获取最新状态
        
        重要优化：
        - 过期状态更新同步执行（快速操作）
        - 邮件发送异步执行（避免阻塞列表加载）
        - 异常完全隔离（邮件失败不影响列表展示）
        - 支持动态配置提醒天数（LICENSE_EXPIRATION_REMINDERS）
        """
        
        # 检查是否启用自动检查
        if not getattr(settings, 'LICENSE_AUTO_CHECK_ENABLED', True):
            return super().list(request, *args, **kwargs)
        
        now = date.today()  # 使用 date 而不是 datetime，因为 end_time 是 DateField
        logger.info(f"开始执行License自动检查和邮件提醒（list视图），当前日期: {now}")
        
        # 1. 【同步执行】自动更新已过期的License状态（快速操作，不阻塞）
        try:
            expired_records = LicenseRecord.objects.filter(
                end_time__lt=now,
                status=1  # 只更新当前状态为有效的
            )
            
            expired_count = expired_records.count()
            if expired_count > 0:
                # 在更新前先获取需要发送邮件的记录列表（排除已发送过的）
                expired_to_notify = []
                for record in expired_records:
                    extra_info = record.extra_info or {}
                    if not extra_info.get('expired_email_sent', False):
                        expired_to_notify.append(record)
                
                # 更新状态为已过期
                expired_records.update(status=2)
                logger.info(f"列表查询时自动更新了 {expired_count} 条已过期的 License 记录状态")
                
                # 【异步执行】发送过期提醒邮件（不阻塞列表加载）
                self._send_async_emails(expired_to_notify, 'expired')
        except Exception as e:
            logger.error(f"更新过期License状态失败: {str(e)}")
            # 即使更新失败，也不影响列表查询
        
        # 2. 【异步执行】检查即将过期的License，分别在30天、15天、7天发送提醒邮件
        try:
            email_manager = EmailManager()
            
            # 从配置中读取提醒规则（支持动态配置）
            reminder_ranges = getattr(settings, 'LICENSE_EXPIRATION_REMINDERS', None)
            if not reminder_ranges:
                logger.warning('LICENSE_EXPIRATION_REMINDERS 配置未找到，跳过即将过期提醒')
                return super().list(request, *args, **kwargs)
            
            logger.info(f"使用提醒规则: {len(reminder_ranges)} 个级别")
            
            # 按 application_id 分组收集需要提醒的记录
            # key: application_id, value: {'records': [], 'days': days, 'lower': lower, 'upper': upper}
            applications_to_notify = {}
            
            for reminder in reminder_ranges:
                days = reminder['days']
                lower = reminder['lower']
                upper = reminder['upper']
                
                # 计算对应的日期范围（直接使用 end_time 字段查询，更可靠）
                if lower == 0:
                    # 7天提醒：[0, 7] -> end_time 在 [now, now+7天]
                    end_date_lower = now + timedelta(days=lower)
                    end_date_upper = now + timedelta(days=upper)
                    expiring_records = LicenseRecord.objects.filter(
                        end_time__gte=end_date_lower,
                        end_time__lte=end_date_upper,
                        status=1  # 有效状态
                    )
                else:
                    # 30天和15天提醒：(lower, upper] -> end_time 在 (now+lower, now+upper]
                    end_date_lower = now + timedelta(days=lower)
                    end_date_upper = now + timedelta(days=upper)
                    expiring_records = LicenseRecord.objects.filter(
                        end_time__gt=end_date_lower,
                        end_time__lte=end_date_upper,
                        status=1  # 有效状态
                    )
                
                expiring_count = expiring_records.count()
                if expiring_count > 0:
                    logger.info(f"发现 {expiring_count} 条需要在{days}天提醒的 License 记录（剩余天数范围: {lower}-{upper}）")
                    for record in expiring_records:
                        app_id = record.application.id
                        if app_id not in applications_to_notify:
                            applications_to_notify[app_id] = {
                                'records': [],
                                'days': days,
                                'lower': lower,
                                'upper': upper
                            }
                        applications_to_notify[app_id]['records'].append({
                            'record': record,
                            'days': days,
                            'lower': lower,
                            'upper': upper
                        })
            
            # 【异步执行】按 application 分组发送邮件（不阻塞列表加载）
            if applications_to_notify:
                self._send_async_emails_by_application(applications_to_notify)
                
        except Exception as e:
            logger.error(f"检查即将过期License失败: {str(e)}")
            # 即使检查失败，也不影响列表查询
        
        # 调用父类的 list 方法（立即返回，不受邮件发送影响）
        return super().list(request, *args, **kwargs)
    
    def _send_async_emails(self, email_data_list, email_type):
        """
        异步发送邮件（不阻塞主线程）
        :param email_data_list: 邮件数据列表
        :param email_type: 'expired' 或 'expiring'
        """
        if not email_data_list:
            return
        
        try:
            # 创建后台线程异步发送邮件
            thread = threading.Thread(
                target=self._process_email_sending,
                args=(email_data_list, email_type),
                daemon=True  # 守护线程，主程序退出时自动终止
            )
            thread.start()
            logger.info(f"已启动异步邮件发送线程，类型={email_type}, 数量={len(email_data_list)}")
        except Exception as e:
            logger.error(f"启动异步邮件发送线程失败: {str(e)}")
    
    def _send_async_emails_by_application(self, applications_to_notify):
        """
        按 application 分组异步发送邮件（避免重复发送）
        :param applications_to_notify: {app_id: {'records': [...], 'days': days, ...}}
        """
        if not applications_to_notify:
            return
        
        try:
            # 创建后台线程异步发送邮件
            thread = threading.Thread(
                target=self._process_email_sending_by_application,
                args=(applications_to_notify,),
                daemon=True  # 守护线程，主程序退出时自动终止
            )
            thread.start()
            logger.info(f"已启动按application分组的异步邮件发送线程，申请数量={len(applications_to_notify)}")
        except Exception as e:
            logger.error(f"启动按application分组的异步邮件发送线程失败: {str(e)}")
    
    def _process_email_sending(self, email_data_list, email_type):
        """
        实际处理邮件发送的逻辑（在后台线程中执行）
        :param email_data_list: 邮件数据列表
        :param email_type: 'expired' 或 'expiring'
        """
        from utils.email import EmailManager
        from datetime import date
        
        now = date.today()
        email_manager = EmailManager()
        
        logger.info(f"开始异步发送邮件，类型={email_type}, 总数={len(email_data_list)}")
        
        success_count = 0
        fail_count = 0
        
        for item in email_data_list:
            try:
                if email_type == 'expired':
                    # 过期邮件
                    record = item
                    extra_info = record.extra_info or {}
                    
                    if extra_info.get('expired_email_sent', False):
                        logger.info(f"跳过已发送过期提醒邮件的记录: {record.application.serial_number}")
                        continue
                    
                    application = LicenseApplication.objects.get(id=record.application.id)
                    if not application.applicant_id:
                        logger.warning(f"跳过发送邮件，申请人ID为空: {record.application.serial_number}")
                        continue
                    
                    email_manager.license_expired_send_email(
                        owner=application.applicant_id,
                        application=application,
                        end_time=record.end_time
                    )
                    
                    extra_info['expired_email_sent'] = True
                    record.extra_info = extra_info
                    record.save(update_fields=['extra_info'])
                    logger.info(f"✓ 已发送过期提醒邮件: {record.application.serial_number}")
                    success_count += 1
                    
                elif email_type == 'expiring':
                    # 即将过期邮件
                    record = item['record']
                    days = item['days']
                    lower = item['lower']
                    upper = item['upper']
                    
                    application = LicenseApplication.objects.get(id=record.application.id)
                    if not application.applicant_id:
                        logger.warning(f"跳过发送邮件，申请人ID为空: {record.application.serial_number}")
                        continue
                    
                    user_info_list = application.user_info_list or []
                    
                    if len(user_info_list) > 0:
                        # 产品组场景
                        self._handle_product_group_reminder_async(
                            record, application, email_manager, days, now, lower, upper
                        )
                    else:
                        # 单产品场景
                        self._handle_single_product_reminder_async(
                            record, application, email_manager, days
                        )
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"✗ 发送邮件失败: {str(e)}")
                fail_count += 1
                continue
        
        logger.info(f"异步邮件发送完成，类型={email_type}, 成功={success_count}, 失败={fail_count}")
    
    def _process_email_sending_by_application(self, applications_to_notify):
        """
        按 application 分组处理邮件发送（避免重复发送）
        :param applications_to_notify: {app_id: {'records': [...], 'days': days, 'lower': lower, 'upper': upper}}
        """
        from utils.email import EmailManager
        from datetime import date
        
        now = date.today()
        email_manager = EmailManager()
        
        logger.info(f"开始按application分组发送邮件，申请数量={len(applications_to_notify)}")
        
        success_count = 0
        fail_count = 0
        
        for app_id, data in applications_to_notify.items():
            try:
                records = data['records']
                days = data['days']
                lower = data['lower']
                upper = data['upper']
                
                if not records:
                    continue
                
                # 获取第一个记录的 application（所有记录应该属于同一个 application）
                first_record = records[0]['record']
                application = LicenseApplication.objects.get(id=first_record.application.id)
                
                if not application.applicant_id:
                    logger.warning(f"跳过发送邮件，申请人ID为空: {first_record.application.serial_number}")
                    continue
                
                # 检查是否有 user_info_list（产品组场景）
                user_info_list = application.user_info_list or []
                
                if len(user_info_list) > 0:
                    # 产品组场景：收集所有需要提醒的产品
                    all_products_to_remind = []
                    
                    for record_data in records:
                        record = record_data['record']
                        extra_info = record.extra_info or {}
                        
                        # 遍历 user_info_list 中的所有产品
                        for idx, product_info in enumerate(user_info_list):
                            product_name = product_info.get('Product', '')
                            end_timestamp = product_info.get('Expirydate')
                            
                            if not product_name or not end_timestamp:
                                continue
                            
                            # 解析产品结束时间
                            try:
                                if isinstance(end_timestamp, (int, float)):
                                    product_end_time = datetime.fromtimestamp(end_timestamp / 1000).date()
                                elif isinstance(end_timestamp, str):
                                    product_end_time = datetime.strptime(end_timestamp, '%Y-%m-%d').date()
                                else:
                                    product_end_time = end_timestamp
                            except (ValueError, TypeError):
                                continue
                            
                            # 计算剩余天数
                            product_remaining_days = (product_end_time - now).days
                            
                            # 判断是否在提醒范围内
                            in_range = False
                            if lower == 0:
                                in_range = (lower <= product_remaining_days <= upper)
                            else:
                                in_range = (lower < product_remaining_days <= upper)
                            
                            if in_range:
                                # 检查是否已发送
                                email_key = f'expiring_{days}day_{idx}_{product_name}_email_sent'
                                already_sent = extra_info.get(email_key, False)
                                
                                if not already_sent:
                                    # 检查是否已经在本次循环中收集过
                                    if not any(p['name'] == product_name and p['index'] == idx for p in all_products_to_remind):
                                        all_products_to_remind.append({
                                            'index': idx,
                                            'name': product_name,
                                            'remaining_days': product_remaining_days,
                                            'email_key': email_key,
                                            'record': record
                                        })
                    
                    # 如果有产品需要提醒，发送一封邮件包含所有产品
                    if all_products_to_remind:
                        product_details = [{
                            'name': p['name'],
                            'remaining_days': p['remaining_days'],
                            'start_time': p['record'].start_time,
                            'end_time': p['record'].end_time
                        } for p in all_products_to_remind]
                        
                        # 发送提醒邮件
                        email_manager.license_expiring_soon_send_email(
                            owner=application.applicant_id,
                            application=application,
                            end_time=first_record.end_time,
                            remaining_days=days,
                            product_details=product_details
                        )
                        
                        # 标记每个产品已发送（在所有相关记录中标记）
                        for product in all_products_to_remind:
                            record = product['record']
                            extra_info = record.extra_info or {}
                            extra_info[product['email_key']] = True
                            record.extra_info = extra_info
                            record.save(update_fields=['extra_info'])
                        
                        product_names = ', '.join([p['name'] for p in all_products_to_remind])
                        logger.info(f"✓ 已发送{days}天提醒邮件（产品组）: {first_record.application.serial_number}, 产品: {product_names}")
                        success_count += 1
                    else:
                        logger.info(f"产品组中没有需要提醒的产品: {first_record.application.serial_number}")
                else:
                    # 单产品场景：为每条记录单独发送邮件
                    for record_data in records:
                        record = record_data['record']
                        extra_info = record.extra_info or {}
                        email_key = f'expiring_{days}day_email_sent'
                        
                        if extra_info.get(email_key, False):
                            logger.info(f"跳过已发送{days}天提醒邮件的记录: {record.application.serial_number}")
                            continue
                        
                        email_manager.license_expiring_soon_send_email(
                            owner=application.applicant_id,
                            application=application,
                            end_time=record.end_time,
                            remaining_days=record.remaining_days
                        )
                        
                        extra_info[email_key] = True
                        record.extra_info = extra_info
                        record.save(update_fields=['extra_info'])
                        logger.info(f"✓ 已发送{days}天提醒邮件: {record.application.serial_number}, 剩余{record.remaining_days}天")
                        success_count += 1
                        
            except Exception as e:
                logger.error(f"✗ 按application分组发送邮件失败: {str(e)}", exc_info=True)
                fail_count += 1
                continue
        
        logger.info(f"按application分组邮件发送完成，成功={success_count}, 失败={fail_count}")
    
    def _handle_single_product_reminder_async(self, record, application, email_manager, days):
        """
        处理单产品场景的邮件提醒（异步版本）
        :param record: LicenseRecord 实例
        :param application: LicenseApplication 实例
        :param email_manager: EmailManager 实例
        :param days: 剩余天数阈值（30/15/7）
        """
        extra_info = record.extra_info or {}
        email_key = f'expiring_{days}day_email_sent'
        
        if extra_info.get(email_key, False):
            logger.info(f"跳过已发送{days}天提醒邮件的记录: {record.application.serial_number}")
            return
        
        logger.info(f"准备发送{days}天提醒邮件: {record.application.serial_number}, end_time={record.end_time}, remaining_days={record.remaining_days}")
        
        # 发送即将过期提醒邮件
        email_manager.license_expiring_soon_send_email(
            owner=application.applicant_id,
            application=application,
            end_time=record.end_time,
            remaining_days=record.remaining_days
        )
        
        # 标记已发送
        extra_info[email_key] = True
        record.extra_info = extra_info
        record.save(update_fields=['extra_info'])
        logger.info(f"✓ 已发送{days}天提醒邮件: {record.application.serial_number}, 剩余{record.remaining_days}天")
    
    def _handle_product_group_reminder_async(self, record, application, email_manager, days, now, lower, upper):
        """
        处理产品组场景的邮件提醒（异步版本）
        检查每个产品的剩余天数，如果某个产品在提醒阈值范围内，则发送提醒
        :param record: LicenseRecord 实例
        :param application: LicenseApplication 实例
        :param email_manager: EmailManager 实例
        :param days: 剩余天数阈值（30/15/7）
        :param now: 当前日期
        :param lower: 下限
        :param upper: 上限
        """
        from datetime import timedelta
        
        user_info_list = application.user_info_list or []
        extra_info = record.extra_info or {}
        
        logger.info(f"处理产品组提醒: {record.application.serial_number}, 产品数量={len(user_info_list)}, 提醒天数={days}")
        
        # 收集需要提醒的产品信息
        products_to_remind = []
        
        for idx, product_info in enumerate(user_info_list):
            product_name = product_info.get('Product', '')  # ✅ 注意：字段名是 Product（大写P）
            end_timestamp = product_info.get('Expirydate')  # ✅ 注意：字段名是 Expirydate（时间戳）
            
            if not product_name:
                logger.info(f"产品 {idx} 没有 Product 名称，跳过")
                continue
            
            if not end_timestamp:
                logger.info(f"产品 {idx} ({product_name}) 没有 Expirydate，跳过")
                continue
            
            # 解析产品结束时间（从毫秒时间戳转换为 date 对象）
            try:
                if isinstance(end_timestamp, (int, float)):
                    # 毫秒时间戳 -> 秒 -> date 对象
                    product_end_time = datetime.fromtimestamp(end_timestamp / 1000).date()
                elif isinstance(end_timestamp, str):
                    # 如果是字符串格式，尝试解析
                    product_end_time = datetime.strptime(end_timestamp, '%Y-%m-%d').date()
                else:
                    product_end_time = end_timestamp
            except (ValueError, TypeError) as e:
                logger.warning(f"无法解析产品结束时间: {end_timestamp}, 错误: {str(e)}")
                continue
            
            # 计算产品剩余天数
            product_remaining_days = (product_end_time - now).days
            
            logger.info(f"产品 {idx} ({product_name}): end_time={product_end_time}, 剩余天数={product_remaining_days}, 检查范围({lower}-{upper})")
            
            # 判断该产品的剩余天数是否在提醒范围内
            in_range = False
            if lower == 0:
                # 7天提醒：[0, 7]
                in_range = (lower <= product_remaining_days <= upper)
            else:
                # 30天和15天提醒：(lower, upper]
                in_range = (lower < product_remaining_days <= upper)
            
            logger.info(f"产品 {idx} ({product_name}): 是否在范围内={in_range}")
            
            if in_range:
                # 检查是否已经为该产品和该天数发送过提醒
                email_key = f'expiring_{days}day_{idx}_{product_name}_email_sent'
                already_sent = extra_info.get(email_key, False)
                
                logger.info(f"产品 {idx} ({product_name}): 已发送标记={already_sent}")
                
                if not already_sent:
                    logger.info(f"产品 {product_name} 需要提醒: 剩余{product_remaining_days}天, 范围({lower}-{upper})")
                    products_to_remind.append({
                        'index': idx,
                        'name': product_name,
                        'remaining_days': product_remaining_days,
                        'email_key': email_key
                    })
        
        # 如果有产品需要提醒，发送邮件
        if products_to_remind:
            # 构建产品信息列表用于邮件内容
            product_details = []
            for product in products_to_remind:
                product_details.append({
                    'name': product['name'],
                    'remaining_days': product['remaining_days'],
                    'start_time': record.start_time,
                    'end_time': record.end_time
                })
            
            # 发送提醒邮件（传入产品信息列表）
            email_manager.license_expiring_soon_send_email(
                owner=application.applicant_id,
                application=application,
                end_time=record.end_time,
                remaining_days=days,  # 使用当前阈值
                product_details=product_details  # 新增参数：具体产品信息
            )
            
            # 标记每个产品已发送
            for product in products_to_remind:
                extra_info[product['email_key']] = True
            
            record.extra_info = extra_info
            record.save(update_fields=['extra_info'])
            
            product_names = ', '.join([p['name'] for p in products_to_remind])
            logger.info(f"✓ 已发送{days}天提醒邮件（产品组）: {record.application.serial_number}, 产品: {product_names}")
        else:
            logger.info(f"产品组中没有需要提醒的产品: {record.application.serial_number}")

    
    @action(methods=['get'], detail=False)
    def statistics(self, request):
        """
        获取License统计信息
        """
        from django.db.models import Count
        from datetime import datetime, timedelta, date
        
        # 使用本地时间
        now = date.today()  # 使用 date 而不是 datetime，因为 end_time 是 DateField
        
        # 自动更新已过期的License状态
        expired_count = LicenseRecord.objects.filter(
            end_time__lt=now,
            status=1  # 只更新当前状态为有效的
        ).update(status=2)  # 更新为已过期
        
        if expired_count > 0:
            logger.info(f"自动更新了 {expired_count} 条已过期的 License 记录状态")
        
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
        
        # 即将过期的License（status=1 有效状态，且 end_time 距离现在<=30天且>0天）
        expiring_soon = LicenseRecord.objects.filter(
            end_time__lte=expiring_threshold,
            end_time__gt=now,
            status=1  # 有效状态
        ).count()
        
        # 已过期的License（status=2 已过期状态）
        expired = LicenseRecord.objects.filter(
            status=2  # 已过期状态
        ).count()

        # 有效的（status=1 有效状态）
        efficient = LicenseRecord.objects.filter(
            status=1  # 有效状态
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


def _generate_flexnet_template_file(serial_number, mac_address, hostname, product_name, product_features, user_info_list, file_hash, keyword=None, is_product_group=False, group_products=None):
    """
    为单个产品生成 FlexNet 预制作 license 模板文件
    
    文件格式示例：
    SERVER ahpc0320 C81FBCEB0AE 55555
    VENDOR PHLEXING ../PHLEXING
    USE_SERVER
    INCREMENT GloryEX PHLEXING 2.0 28-feb-2025 4600 HOSTID=ANY \
      START=24-jan-2025 SIGN="01C8 B069 20FB 044D 0260 188E ECCB \
      5263 48AB 4A6D 3F4E 9B7D E6A7 3965 9E37 08E1 1044 D208 6E1D \
      60F4 07AA 03E4 A3D4 BC29 5411 EEBA B6F4 4972 506B 5A38"
    
    Args:
        serial_number: 序列号（用作文件名）
        mac_address: MAC地址
        hostname: 主机名
        product_name: 产品名称（用于文件名，对于产品组使用统一名称如 'GloryEX'）
        product_features: 产品feature字典 {product: {feature: quantity}} (包含所有产品)
        user_info_list: UserInfo列表
        file_hash: 文件哈希值
        keyword: 关键字，如果为空使用 INCREMENT，不为空使用 FEATURE
        is_product_group: 是否为产品组合并情况
        group_products: 产品组内的产品名称列表（如 ['GloryEX', 'GloryEX3D', 'GloryPolaris']）
    
    Returns:
        str: 生成的模板文件路径，如果失败返回 None
    """
    try:
        from django.conf import settings
        from datetime import datetime
        
        # 构建模板文件存储路径
        template_dir = os.path.join(MEDIA_ROOT, 'license', 'templates', 'flexnet')
        if not os.path.exists(template_dir):
            os.makedirs(template_dir)
        
        # 使用序列号+产品名称作为文件名（去除特殊字符）
        safe_serial = serial_number.replace('/', '_').replace('\\', '_').replace(':', '_')
        safe_product = product_name.replace('/', '_').replace('\\', '_').replace(' ', '_')
        file_name = f"{safe_serial}_{safe_product}_{file_hash[:8]}.lic"
        template_file = os.path.join(template_dir, file_name)
        relative_path = os.path.join('license', 'templates', 'flexnet', file_name)
        
        # 构建模板文件内容
        lines = []
        
        # 第1行：SERVER <hostname> <mac_address_without_colons> 55555
        # mac_address 需要去除冒号
        mac_clean = mac_address.replace(':', '').replace('-', '') if mac_address else 'UNKNOWN'
        server_line = f"SERVER {hostname or 'UNKNOWN'} {mac_clean} 55555"
        lines.append(server_line)
        
        # 第2行：VENDOR PHLEXING ../PHLEXING
        lines.append("VENDOR PHLEXING ../PHLEXING")
        
        # 第3行：USE_SERVER
        lines.append("USE_SERVER")
        
        # 【关键修复】直接从 user_info_list 中解析产品、features 和时间，一个循环搞定
        # user_info_list 结构：{'Product': 'GloryEX', 'Startdate': ts, 'Expirydate': ts, 'GloryEX': {'feat1': 10, ...}}
        
        # 判断是否为产品组（需要从多个产品中合并 features）
        gloryex_group_products = ['GloryEX', 'GloryEX3D', 'GloryPolaris', 'GloryEXCommon']
        glorybolt_group_products = ['GloryBolt', 'GloryGrid']
        
        is_product_group = False
        related_products = []
        if product_name == 'GloryEX':
            is_product_group = True
            related_products = gloryex_group_products
        elif product_name == 'GloryBolt':
            is_product_group = True
            related_products = glorybolt_group_products
        else:
            related_products = [product_name]
        
        logger.info(f"FlexNet模板 - 产品: {product_name}, 是否产品组: {is_product_group}, 相关产品: {related_products}")
        
        # 验证是否有相关产品的数据
        has_valid_data = False
        for ui in user_info_list:
            ui_product = ui.get('Product', '')
            if ui_product in related_products:
                has_valid_data = True
                break
        
        if not has_valid_data:
            logger.error(f"产品 {product_name} 在 user_info_list 中找不到对应数据，无法生成模板文件")
            return None
        
        # 一个循环搞定：遍历 user_info_list，为每个相关产品的每个 feature 生成一行
        for ui in user_info_list:
            ui_product = ui.get('Product', '')
            
            # 只处理相关产品的数据
            if ui_product not in related_products:
                continue
            
            # 获取该产品的 features 字典
            product_features_dict = ui.get(ui_product, {})
            if not product_features_dict:
                logger.warning(f"产品 {ui_product} 没有 features，跳过")
                continue
            
            # 获取该产品的开始和结束时间
            ui_start_timestamp = ui.get('Startdate')
            ui_end_timestamp = ui.get('Expirydate')
            
            if not ui_start_timestamp or not ui_end_timestamp:
                logger.warning(f"产品 {ui_product} 缺少时间信息，跳过")
                continue
            
            # 转换时间戳为日期字符串
            from datetime import datetime
            start_dt = datetime.fromtimestamp(ui_start_timestamp / 1000)
            end_dt = datetime.fromtimestamp(ui_end_timestamp / 1000)
            start_date_str = start_dt.strftime("%d-%b-%Y").lower()
            end_date_str = end_dt.strftime("%d-%b-%Y").lower()
            
            logger.info(f"FlexNet模板 - 产品 {ui_product}: {start_date_str} ~ {end_date_str}, features: {list(product_features_dict.keys())}")
            
            # 为该产品的每个 feature 生成一行
            for feature_name, quantity in product_features_dict.items():
                # 根据 keyword 是否为空决定使用 INCREMENT 还是 FEATURE
                if keyword:
                    # keyword 不为空，使用 FEATURE
                    feature_line = f"FEATURE {feature_name} PHLEXING 2.0 {end_date_str} {quantity} HOSTID=ANY {keyword} \\"
                else:
                    # keyword 为空，使用 INCREMENT
                    feature_line = f"INCREMENT {feature_name} PHLEXING 2.0 {end_date_str} {quantity} HOSTID=ANY \\"
                
                lines.append(feature_line)
                
                # START=<start_date> SIGN="<16进制签名占位符> \
                sign_placeholder = "01C8 B069 20FB 044D 0260 188E ECCB \\\n  5263 48AB 4A6D 3F4E 9B7D E6A7 3965 9E37 08E1 1044 D208 6E1D \\\n  60F4 07AA 03E4 A3D4 BC29 5411 EE8A B6F4 4972 505B 5A38"
                start_line = f'  START={start_date_str} SIGN="{sign_placeholder}"'
                lines.append(start_line)
                
                logger.info(f"FlexNet模板 - 生成 {ui_product} 的 Feature '{feature_name}', 数量={quantity}, 时间: {start_date_str} ~ {end_date_str}")
            
            # 添加反斜杠结束
            # lines.append("  \\")
        
        # 写入文件
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        
        logger.info(f"FlexNet 模板文件已保存: {template_file}")
        logger.info(f"模板文件内容预览 (产品: {product_name}):")
        for i, line in enumerate(lines[:10], 1):
            logger.info(f"  {i}: {line}")
        
        return relative_path
        
    except Exception as e:
        logger.error(f"生成 FlexNet 模板文件失败 (产品: {product_name}): {str(e)}", exc_info=True)
        return None
