from django.apps import AppConfig
import logging
import json
import os
from django.conf import settings
import threading
import sys
from watchdog.observers.polling import PollingObserver
# 注意：不要在这里导入 views 和 models，会导致循环导入
# 需要在函数内部延迟导入

logger = logging.getLogger(__name__)

# 模块级变量：防止重复启动
_file_watcher_started = False


class LylicenseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.lylicense'
    verbose_name = "License管理"
    
    def ready(self):
        """
        Django 应用启动时自动启动文件监听器
        """
        # 声明全局变量
        global _file_watcher_started
        
        # 避免在 Django 自动重载时重复执行
        if os.environ.get('RUN_MAIN') != 'true':
            logger.info("Django 重载进程，跳过监听器启动")
            return
        
        # 检查是否已经启动
        if _file_watcher_started:
            logger.info("文件监听器已启动，跳过重复启动")
            return
        
        try:
            # 只在主进程启动，避免多进程重复启动

            if 'runserver' in sys.argv or 'runserver_plus' in sys.argv:

                from apps.lylicense.file_watcher import LicenseFileHandler
                watch_dir = os.path.join(settings.JSON_FILE_PATH, 'json_file')
                
                # 确保目录存在
                if not os.path.exists(watch_dir):
                    os.makedirs(watch_dir, exist_ok=True)
                    logger.info(f"创建监听目录: {watch_dir}")
                
                # 定义文件处理回调函数
                def process_license_file(file_path):
                    """
                    处理 License 文件的回调函数
                    
                    Args:
                        file_path: 文件路径
                    
                    Returns:
                        bool: 是否处理成功
                    """
                    # 延迟导入，避免循环导入
                    import hashlib
                    from apps.lylicense.views import transform_json_with_mapping
                    from apps.lylicense.models import LicenseApplication
                    
                    try:
                        logger.info(f"开始处理文件: {file_path}")
                        
                        # 读取文件内容
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        try:
                            json_data = json.loads(content)
                            # 获取 LicenseType
                            license_type = json_data.get('LicenseType', '').lower()
                            usage = json_data.get('Usage', '')
                        except Exception as e:
                            logger.error(f"JSON 解析失败: {file_path}:{e}")
                            return False

                        user_type = ''
                        if usage:
                            if usage == '内部':
                                user_type = 'internal'
                            elif usage == '外部':
                                user_type = 'external'
                        
                        
                        # 计算文件内容的 MD5 哈希
                        file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
                        logger.info(f"文件哈希: {file_hash}")
                        
                        # 注意：不在文件级别检测，因为同一文件会创建多个产品的申请记录
                        # 而是在每个产品创建前检测该产品是否已存在

                        # 调用转换函数
                        result = transform_json_with_mapping(json_data, license_type=license_type, user_type=user_type)

                        if not result['success']:
                            logger.error(f"转换失败: {result.get('error')}")
                            return False

                        transformed_data = result['transformed_data']
                        features = result['features']
                        product_features = result['product_features']  # 直接使用product_features作为quantity
                        user_info_list = result['transformed_data'].get('UserInfo', [])  # 获取UserInfo列表
                        
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
                        
                        # 在最外层提取并处理MAC地址和Hostname
                        mac_address = transformed_data.get('MacAddress', '')
                        if mac_address:
                            mac_address = mac_address.upper()
                        hostname = transformed_data.get('Hostname', '')
                        
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
                                # mac_address 变量已经在上面提取并处理
                                
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
                                # mac_address 变量已经在上面提取并处理
                                
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
                logger.info(f"准备启动文件监听器，监听目录: {watch_dir}")
                
                # 检查是否已经存在全局监听器
                from apps.lylicense import views as views_module
                if hasattr(views_module, '_file_watcher_observer') and views_module._file_watcher_observer is not None:
                    if views_module._file_watcher_observer.is_alive():
                        logger.info("全局监听器已存在且运行中，跳过启动")
                        return
                
                event_handler = LicenseFileHandler(process_callback=process_license_file)
                observer = PollingObserver()
                observer.schedule(event_handler, watch_dir, recursive=False)
                
                # 启动观察者
                observer.start()
                logger.info(f"Observer 已启动，is_alive={observer.is_alive()}")
                
                # 保存到模块级变量
                views_module._file_watcher_observer = observer
                
                logger.info(f"文件监听器已自动启动，监听目录: {watch_dir}")
                
                # 标记为已启动
                _file_watcher_started = True
                
        except Exception as e:
            logger.error(f"自动启动文件监听器失败: {str(e)}", exc_info=True)
