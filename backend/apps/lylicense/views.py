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

# 从Django settings中获取路径
BASE_DIR = settings.BASE_DIR
MEDIA_ROOT = settings.MEDIA_ROOT


def transform_json_with_mapping(raw_json, license_type, user_type='internal'):
    """
    使用字段映射表转换JSON数据
    
    Args:
        raw_json: 原始JSON数据（字典）
        license_type: License类型 ('flexnet' 或 'bitanswer')
        user_type: 用户类型 ('internal' 或 'external')
    
    Returns:
        dict: 转换后的新JSON数据
    """
    # 获取该类型的所有字段映射
    mappings = LicenseFieldMapping.objects.filter(
        license_type=license_type,
        user_type=user_type,
        is_deleted=False
    ).all()
    
    # 构建映射字典: {field: real_key}
    mapping_dict = {m.field: m.real_key for m in mappings}
    
    # 提取 FormList 中的数据
    form_list = raw_json.get('FormList', {})
    
    # 过滤空值并转换key
    transformed_data = {}
    
    for key, value in form_list.items():
        # 过滤空值：None、空字符串、空列表、空字典
        if value is None or value == '' or value == [] or value == {}:
            continue
        
        # 查找映射后的key
        real_key = mapping_dict.get(key, key)  # 如果没有映射，使用原key
        
        # 处理特殊数据类型
        if isinstance(value, list):
            # 数组类型，保留原值
            transformed_data[real_key] = value
        elif isinstance(value, (int, float)):
            # 数字类型
            transformed_data[real_key] = value
        elif isinstance(value, str):
            # 字符串类型
            transformed_data[real_key] = value
        else:
            # 其他类型转为字符串
            transformed_data[real_key] = str(value)
    
    # 添加元数据
    result = {
        'transformed_data': transformed_data,
        'usage': raw_json.get('Usage', ''),
        'license_type': raw_json.get('LicenseType', '').lower(),
        'original_keys_count': len(form_list),
        'filtered_keys_count': len(transformed_data),
        'mapping_used': len(mapping_dict)
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
        扫描指定目录中的TXT文件并创建License申请记录
        1. 从配置目录读取所有TXT文件
        2. 解析JSON数据
        3. 根据LicenseType判断类型
        4. 使用字段映射表转换key
        5. 过滤空值
        6. 创建申请记录
        """
        try:
            # 获取TXT文件目录（从配置或请求参数）
            txt_dir = request.data.get('txt_dir', None)
            if not txt_dir:
                # 默认目录：BASE_DIR/license_txt_files
                txt_dir = os.path.join(BASE_DIR, 'license_txt_files')
            
            # 检查目录是否存在
            if not os.path.exists(txt_dir):
                return ErrorResponse(msg=f'TXT文件目录不存在: {txt_dir}')
            
            # 获取用户类型（默认为internal）
            user_type = request.data.get('user_type', 'internal')
            
            # 扫描目录中的所有.txt文件
            txt_files = [f for f in os.listdir(txt_dir) if f.endswith('.txt')]
            
            if not txt_files:
                return SuccessResponse(data={'processed': 0}, msg='目录中没有找到TXT文件')
            
            results = []
            processed_count = 0
            error_count = 0
            
            for txt_file in txt_files:
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
                    
                    # 使用字段映射表转换JSON
                    transform_result = transform_json_with_mapping(raw_json, license_type, user_type)
                    transformed_data = transform_result['transformed_data']
                    
                    # 提取关键字段用于创建申请记录
                    applicant = ''
                    customer_name = ''
                    mac_address = ''
                    feature = ''
                    start_time = None
                    end_time = None
                    quantity = 1
                    
                    # 从转换后的数据中提取信息
                    for key, value in transformed_data.items():
                        # 申请人
                        if key in ['applicant', 'employeeField_me87gr4t']:
                            if isinstance(value, list) and len(value) > 0:
                                applicant = value[0]
                            elif isinstance(value, str):
                                applicant = value
                        
                        # 客户名称
                        elif key in ['customer_name', 'textField_me87gr4w']:
                            customer_name = str(value)
                        
                        # MAC地址
                        elif key in ['mac_address', 'host_id', 'textField_me87gr4o']:
                            mac_address = str(value)
                        
                        # Feature
                        elif key in ['feature', 'checkboxField_me87gr5e']:
                            if isinstance(value, list):
                                feature = ','.join(value)
                            else:
                                feature = str(value)
                        
                        # 开始时间
                        elif key in ['start_time', 'dateField_me87gr4v']:
                            if isinstance(value, (int, float)):
                                from datetime import datetime
                                start_time = datetime.fromtimestamp(value / 1000)
                        
                        # 结束时间
                        elif key in ['end_time', 'dateField_mdy73q6p']:
                            if isinstance(value, (int, float)):
                                from datetime import datetime
                                end_time = datetime.fromtimestamp(value / 1000)
                        
                        # 授权数量
                        elif key in ['quantity', 'numberField_mj2hbj5c_value']:
                            try:
                                quantity = int(value)
                            except:
                                quantity = 1
                    
                    # 创建申请记录
                    application = LicenseApplication.objects.create(
                        applicant=applicant or '未知申请人',
                        application_type=license_type,
                        feature=feature or '未指定',
                        customer_name=customer_name or '未指定客户',
                        mac_address=mac_address or '未指定',
                        start_time=start_time,
                        end_time=end_time,
                        quantity=quantity,
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
                    logger.error(f"处理文件 {txt_file} 失败: {str(e)}")
                    error_count += 1
                    results.append({
                        'file': txt_file,
                        'status': 'error',
                        'message': str(e)
                    })
            
            return SuccessResponse(data={
                'total_files': len(txt_files),
                'processed': processed_count,
                'errors': error_count,
                'results': results
            }, msg=f'扫描完成：成功处理 {processed_count} 个文件，{error_count} 个失败')
            
        except Exception as e:
            logger.error(f"扫描TXT文件失败: {str(e)}")
            return ErrorResponse(msg=f'扫描失败: {str(e)}')
    
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
            
            # 更新申请的JSON数据和状态
            instance.json_data = json_data
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
                
                file_name = f'{instance.id}_bit.lic'
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
    queryset = LicenseFieldMapping.objects.filter(is_deleted=False)
    serializer_class = LicenseFieldMappingSerializer
    create_serializer_class = LicenseFieldMappingCreateSerializer
    update_serializer_class = LicenseFieldMappingUpdateSerializer
    filterset_fields = ['license_type', 'user_type']
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
