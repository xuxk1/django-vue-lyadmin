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
                            
                            # 发送 JSON 解析失败邮件
                            try:
                                import config
                                from utils.email import EmailManager
                                
                                logger.info(f"准备发送 JSON 解析失败邮件...")
                                
                                # JSON 解析失败时，直接发送给指定人员
                                owner_account = config.MAIL_RECIPIENT
                                logger.info(f"邮件接收人: {owner_account}")
                                
                                # 直接使用原始内容
                                formatted_json = content
                                logger.info(f"JSON 内容长度: {len(formatted_json)} 字符")
                                
                                email_manager = EmailManager()
                                # 提取文件名（从完整路径中）
                                file_name = os.path.basename(file_path)
                                email_manager.json_parsing_failed_send_email(owner_account, formatted_json, file_name)
                                logger.info(f"已发送 JSON 解析失败邮件给: {owner_account}，文件名: {file_name}")
                            except Exception as email_err:
                                logger.error(f"发送邮件失败: {str(email_err)}", exc_info=True)
                            
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

                        # 在最外层提取并处理MAC地址和Hostname
                        mac_address = transformed_data.get('MacAddress', '')
                        if mac_address:
                            mac_address = mac_address.upper()
                        hostname = transformed_data.get('Hostname', '')

                        logger.info(
                            f"  MacAddress: {mac_address}, Hostname: {hostname}")
                        
                        # 打印转换后的数据，方便核对
                        logger.info(f"\n{'='*80}")
                        logger.info(f"转换后的 transformed_data:")
                        logger.info(json.dumps(transformed_data, ensure_ascii=False, indent=2))
                        logger.info(f"{'='*80}\n")
                        
                        logger.info(f"UserInfo 列表包含 {len(user_info_list)} 个产品:")
                        for idx, ui in enumerate(user_info_list, 1):
                            logger.info(f"  {idx}. Product: {ui.get('Product')}, Startdate: {ui.get('Startdate')}, Expirydate: {ui.get('Expirydate')}")
                        logger.info(f"\nproduct_features 结构:")
                        logger.info(json.dumps(product_features, ensure_ascii=False, indent=2))
                        logger.info(f"{'='*80}\n")
                        
                        # 提取公共数据
                        applicant = None
                        customer_name = None
                        serial_number = None
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
                        
                        # 在创建申请记录之前，为每个产品生成独立的 FlexNet 预制作 license 模板文件
                        flexnet_template_files = {}  # {product: template_file_path}
                        if license_type == 'flexnet':
                            try:
                                from apps.lylicense.views import _generate_flexnet_template_file
                                # 遍历每个产品，为其生成独立的 .lic 文件
                                for product, product_feats in product_features.items():
                                    if not product_feats:
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
                                    logger.info(f"共生成 {len(flexnet_template_files)} 个 FlexNet 预制作模板文件")
                            except Exception as e:
                                logger.error(f"生成 FlexNet 预制作模板文件失败: {str(e)}", exc_info=True)
                                # 不阻断流程，继续创建申请记录
                        
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
                                gloryex_features = {}  # 按产品分组的嵌套结构：{'GloryEX': {...}, 'GloryEX3D': {...}}
                                gloryex_feature_list = []
                                min_start_time = None
                                max_end_time = None
                                
                                for group_product in gloryex_group_products:
                                    if group_product in product_features:
                                        # 按产品分组保存 features（嵌套结构）
                                        gloryex_features[group_product] = product_features[group_product]
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
                                    # 从转换后的 JSON 数据中提取申请人账号（applicant_id）
                                    applicant_id = ''
                                    try:
                                        # 直接从最外层获取 ApplicantID
                                        for field_name in ['ApplicantID', 'applicant_id', 'applicantId', 'Applicant_ID', '申请人ID']:
                                            if field_name in transformed_data:
                                                applicant_id = transformed_data[field_name]
                                                logger.info(f"[DEBUG] 从 transformed_data 最外层提取到 {field_name}: {applicant_id}")
                                                break
                                    except Exception as e:
                                        logger.warning(f"提取申请人账号失败: {str(e)}")
                                    
                                    # 创建GloryEX组的申请记录
                                    application = LicenseApplication.objects.create(
                                        applicant=applicant or '未知申请人',
                                        applicant_id=applicant_id if applicant_id else None,  # 保存申请人ID
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
                                                from django.conf import settings
                                                abs_template_file = os.path.join(settings.MEDIA_ROOT, template_file)
                                                
                                                # 调用远程执行生成正式 license 文件
                                                from apps.lylicense.views import LicenseApplicationViewSet
                                                view_instance = LicenseApplicationViewSet()
                                                
                                                gen_result = view_instance._generate_flexnet_license(
                                                    instance=application,
                                                    json_data=json_data,
                                                    template_file_path=abs_template_file
                                                )
                                                
                                                if gen_result.get('success'):
                                                    logger.info(f"GloryEX组 License 文件生成成功: {gen_result.get('file_relative_path')}")
                                                    
                                                    # 1. 更新申请记录状态为制作成功
                                                    application.status = 1  # 制作成功
                                                    application.fail_reason = ''
                                                    application.save()
                                                    logger.info(f"GloryEX组 申请记录状态已更新为：制作成功")
                                                    
                                                    # 2. 为每个产品创建 License 制作记录（根据 quantity 中的产品）
                                                    try:
                                                        from apps.lylicense.models import LicenseRecord
                                                        from datetime import datetime, date
                                                        
                                                        # 从 json_data 中获取时间信息，并转换为 date 类型
                                                        start_time = json_data.get('start_time') or application.start_time
                                                        end_time = json_data.get('end_time') or application.end_time
                                                        
                                                        # 如果是 datetime 类型，转换为 date 类型
                                                        if isinstance(start_time, datetime):
                                                            start_time = start_time.date()
                                                        if isinstance(end_time, datetime):
                                                            end_time = end_time.date()
                                                        
                                                        # 获取 quantity（与申请记录保持一致）
                                                        quantity_data = application.quantity
                                                        
                                                        # 如果是 GloryEX 组，需要为每个产品创建记录
                                                        # quantity 格式: {'GloryEX': {'feature1': 10, 'feature2': 5}, 'GloryEX3D': {...}}
                                                        if isinstance(quantity_data, dict):
                                                            logger.info(f"GloryEX组 quantity_data: {json.dumps(quantity_data, ensure_ascii=False)}")
                                                            for product_name, prod_features in quantity_data.items():
                                                                logger.info(f"为产品 {product_name} 创建 LicenseRecord, prod_features: {json.dumps(prod_features, ensure_ascii=False) if isinstance(prod_features, dict) else prod_features}")
                                                                # 为每个产品创建一条 LicenseRecord，license_id 需要唯一
                                                                license_id = f"FN-{application.id}-{product_name}"
                                                                
                                                                # 检查是否已存在
                                                                if LicenseRecord.objects.filter(license_id=license_id).exists():
                                                                    logger.info(f"LicenseRecord 已存在: {license_id}，跳过创建")
                                                                    continue
                                                                
                                                                license_record = LicenseRecord.objects.create(
                                                                    application=application,
                                                                    license_id=license_id,
                                                                    license_type=application.application_type,
                                                                    file_name=gen_result.get('file_name', ''),
                                                                    file_relative_path=gen_result.get('file_relative_path', ''),
                                                                    directory=gen_result.get('directory', ''),
                                                                    full_path=gen_result.get('full_path', ''),
                                                                    feature=json_data.get('feature', application.feature),
                                                                    vendor=gen_result.get('vendor', ''),
                                                                    version=gen_result.get('version', '1.0'),
                                                                    host_id=json_data.get('mac_address', application.mac_address),
                                                                    start_time=start_time,
                                                                    end_time=end_time,
                                                                    quantity=prod_features if isinstance(prod_features, dict) else {},  # 存储单个产品的 feature 数量
                                                                    status=1,  # 有效
                                                                    extra_info={'product': product_name}
                                                                )
                                                                logger.info(f"GloryEX组-{product_name} License 记录已创建: {license_record.license_id}, quantity: {json.dumps(license_record.quantity, ensure_ascii=False)}")
                                                        else:
                                                            # 如果不是字典，创建一条记录
                                                            license_record = LicenseRecord.objects.create(
                                                                application=application,
                                                                license_id=gen_result.get('license_id', f'FN-{application.id}'),
                                                                license_type=application.application_type,
                                                                file_name=gen_result.get('file_name', ''),
                                                                file_relative_path=gen_result.get('file_relative_path', ''),
                                                                directory=gen_result.get('directory', ''),
                                                                full_path=gen_result.get('full_path', ''),
                                                                feature=json_data.get('feature', application.feature),
                                                                vendor=gen_result.get('vendor', ''),
                                                                version=gen_result.get('version', '1.0'),
                                                                host_id=json_data.get('mac_address', application.mac_address),
                                                                start_time=start_time,
                                                                end_time=end_time,
                                                                quantity=quantity_data if isinstance(quantity_data, dict) else {},
                                                                status=1,  # 有效
                                                                extra_info={}
                                                            )
                                                            logger.info(f"GloryEX组 License 记录已创建: {license_record.license_id}")
                                                    except Exception as record_error:
                                                        logger.error(f"创建 License 记录失败: {str(record_error)}", exc_info=True)
                                                    
                                                    # 3. 发送邮件通知申请人（制作成功）
                                                    try:
                                                        from utils.email import EmailManager
                                                        from apps.lylicense.views import get_applicant_from_transformed_data
                                                        
                                                        # 发送邮件时使用 ApplicantID（真实的账号）
                                                        email_applicant = get_applicant_from_transformed_data(
                                                            transformed_data=transformed_data,
                                                            license_type=application.application_type,
                                                            user_type='external',
                                                            field_name='ApplicantID'  # 邮件使用 ApplicantID
                                                        )
                                                        
                                                        # 如果没找到真实账号，使用申请记录中的 applicant
                                                        email_applicant = email_applicant if email_applicant else application.applicant
                                                        
                                                        if email_applicant and email_applicant != '未知申请人':
                                                            email_manager = EmailManager()
                                                            email_manager.license_generated_send_email(
                                                                owner=email_applicant,
                                                                application=application,
                                                                license_file_name=gen_result.get('file_name'),
                                                                remote_dir='/TestHub/sqa/Platform/license'
                                                            )
                                                            logger.info(f"已发送 License 生成成功邮件给申请人: {email_applicant}")
                                                        else:
                                                            logger.warning(f"申请人信息为空，跳过邮件发送")
                                                    except Exception as email_error:
                                                        logger.error(f"发送邮件失败: {str(email_error)}", exc_info=True)
                                                else:
                                                    logger.error(f"GloryEX组 License 文件生成失败: {gen_result.get('error')}")
                                                    
                                                    # 1. 更新申请记录状态为制作失败
                                                    application.status = 0  # 制作失败
                                                    application.fail_reason = gen_result.get('error', '未知错误')
                                                    application.save()
                                                    logger.info(f"GloryEX组 申请记录状态已更新为：制作失败")
                                                    
                                                    # 2. 发送邮件通知申请人（制作失败）
                                                    try:
                                                        from utils.email import EmailManager
                                                        from apps.lylicense.views import get_applicant_from_transformed_data
                                                        
                                                        # 发送邮件时使用 ApplicantID（真实的账号）
                                                        email_applicant = get_applicant_from_transformed_data(
                                                            transformed_data=transformed_data,
                                                            license_type=application.application_type,
                                                            user_type='external',
                                                            field_name='ApplicantID'  # 邮件使用 ApplicantID
                                                        )
                                                        
                                                        # 如果没找到真实账号，使用申请记录中的 applicant
                                                        email_applicant = email_applicant if email_applicant else application.applicant
                                                        
                                                        if email_applicant and email_applicant != '未知申请人':
                                                            email_manager = EmailManager()
                                                            email_manager.license_failed_send_email(
                                                                owner=email_applicant,
                                                                application=application,
                                                                error_message=gen_result.get('error', '未知错误')
                                                            )
                                                            logger.info(f"已发送 License 生成失败邮件给申请人: {email_applicant}")
                                                        else:
                                                            logger.warning(f"申请人信息为空，跳过邮件发送")
                                                    except Exception as email_error:
                                                        logger.error(f"发送邮件失败: {str(email_error)}", exc_info=True)
                                            else:
                                                logger.warning("未找到GloryEX组的预制作模板文件，跳过 License 生成")
                                        except Exception as e:
                                            logger.error(f"生成GloryEX组 License 文件异常: {str(e)}", exc_info=True)
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
                                    # 从转换后的 JSON 数据中提取申请人账号（applicant_id）
                                    applicant_id = ''
                                    try:
                                        # 直接从最外层获取 ApplicantID
                                        for field_name in ['ApplicantID', 'applicant_id', 'applicantId', 'Applicant_ID', '申请人ID']:
                                            if field_name in transformed_data:
                                                applicant_id = transformed_data[field_name]
                                                logger.info(f"[DEBUG] 从 transformed_data 最外层提取到 {field_name}: {applicant_id}")
                                                break
                                    except Exception as e:
                                        logger.warning(f"提取申请人账号失败: {str(e)}")
                                    
                                    application = LicenseApplication.objects.create(
                                        applicant=applicant or '未知申请人',
                                        applicant_id=applicant_id if applicant_id else None,  # 保存申请人ID
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
                                    
                                    # 如果是 FlexNet 类型，立即生成 license 文件
                                    if license_type == 'flexnet':
                                        try:
                                            # 获取对应的预制作模板文件路径
                                            template_file = flexnet_template_files.get(product)
                                            
                                            if template_file:
                                                # 将相对路径转换为绝对路径
                                                from django.conf import settings
                                                abs_template_file = os.path.join(settings.MEDIA_ROOT, template_file)
                                                
                                                # 调用远程执行生成正式 license 文件
                                                from apps.lylicense.views import LicenseApplicationViewSet
                                                view_instance = LicenseApplicationViewSet()
                                                
                                                gen_result = view_instance._generate_flexnet_license(
                                                    instance=application,
                                                    json_data=json_data,
                                                    template_file_path=abs_template_file
                                                )
                                                
                                                if gen_result.get('success'):
                                                    logger.info(f"产品 {product} License 文件生成成功: {gen_result.get('file_relative_path')}")
                                                    
                                                    # 1. 更新申请记录状态为制作成功
                                                    application.status = 1  # 制作成功
                                                    application.fail_reason = ''
                                                    application.save()
                                                    logger.info(f"产品 {product} 申请记录状态已更新为：制作成功")
                                                    
                                                    # 2. 创建 License 制作记录（与申请记录的 quantity 保持一致）
                                                    try:
                                                        from apps.lylicense.models import LicenseRecord
                                                        from datetime import datetime, date
                                                        
                                                        # 从 json_data 中获取时间信息，并转换为 date 类型
                                                        start_time = json_data.get('start_time') or application.start_time
                                                        end_time = json_data.get('end_time') or application.end_time
                                                        
                                                        # 如果是 datetime 类型，转换为 date 类型
                                                        if isinstance(start_time, datetime):
                                                            start_time = start_time.date()
                                                        if isinstance(end_time, datetime):
                                                            end_time = end_time.date()
                                                        
                                                        # 使用申请记录的 quantity（与申请记录保持一致）
                                                        license_id = gen_result.get('license_id', f'FN-{application.id}')
                                                        
                                                        # 检查是否已存在
                                                        if LicenseRecord.objects.filter(license_id=license_id).exists():
                                                            logger.info(f"LicenseRecord 已存在: {license_id}，跳过创建")
                                                        else:
                                                            license_record = LicenseRecord.objects.create(
                                                                application=application,
                                                                license_id=license_id,
                                                                license_type=application.application_type,
                                                                file_name=gen_result.get('file_name', ''),
                                                                file_relative_path=gen_result.get('file_relative_path', ''),
                                                                directory=gen_result.get('directory', ''),
                                                                full_path=gen_result.get('full_path', ''),
                                                                feature=json_data.get('feature', application.feature),
                                                                vendor=gen_result.get('vendor', ''),
                                                                version=gen_result.get('version', '1.0'),
                                                                host_id=json_data.get('mac_address', application.mac_address),
                                                                start_time=start_time,
                                                                end_time=end_time,
                                                                quantity=application.quantity,  # 使用申请记录的 quantity，保持一致
                                                                status=1,  # 有效
                                                                extra_info={}
                                                            )
                                                            logger.info(f"产品 {product} License 记录已创建: {license_record.license_id}, quantity: {json.dumps(license_record.quantity, ensure_ascii=False)}")
                                                    except Exception as record_error:
                                                        logger.error(f"创建 License 记录失败: {str(record_error)}", exc_info=True)
                                                    
                                                    # 3. 发送邮件通知申请人（制作成功）
                                                    try:
                                                        from utils.email import EmailManager
                                                        from apps.lylicense.views import get_applicant_from_transformed_data
                                                        
                                                        # 发送邮件时使用 ApplicantID（真实的账号）
                                                        email_applicant = get_applicant_from_transformed_data(
                                                            transformed_data=transformed_data,
                                                            license_type=application.application_type,
                                                            user_type='external',
                                                            field_name='ApplicantID'  # 邮件使用 ApplicantID
                                                        )
                                                        
                                                        # 如果没找到真实账号，使用申请记录中的 applicant
                                                        email_applicant = email_applicant if email_applicant else application.applicant
                                                        
                                                        if email_applicant and email_applicant != '未知申请人':
                                                            email_manager = EmailManager()
                                                            email_manager.license_generated_send_email(
                                                                owner=email_applicant,
                                                                application=application,
                                                                license_file_name=gen_result.get('file_name'),
                                                                remote_dir='/TestHub/sqa/Platform/license'
                                                            )
                                                            logger.info(f"已发送 License 生成成功邮件给申请人: {email_applicant}")
                                                        else:
                                                            logger.warning(f"申请人信息为空，跳过邮件发送")
                                                    except Exception as email_error:
                                                        logger.error(f"发送邮件失败: {str(email_error)}", exc_info=True)
                                                else:
                                                    logger.error(f"产品 {product} License 文件生成失败: {gen_result.get('error')}")
                                                    
                                                    # 1. 更新申请记录状态为制作失败
                                                    application.status = 0  # 制作失败
                                                    application.fail_reason = gen_result.get('error', '未知错误')
                                                    application.save()
                                                    logger.info(f"产品 {product} 申请记录状态已更新为：制作失败")
                                                    
                                                    # 2. 发送邮件通知申请人（制作失败）
                                                    try:
                                                        from utils.email import EmailManager
                                                        from apps.lylicense.views import get_applicant_from_transformed_data
                                                        
                                                        # 发送邮件时使用 ApplicantID（真实的账号）
                                                        email_applicant = get_applicant_from_transformed_data(
                                                            transformed_data=transformed_data,
                                                            license_type=application.application_type,
                                                            user_type='external',
                                                            field_name='ApplicantID'  # 邮件使用 ApplicantID
                                                        )
                                                        
                                                        # 如果没找到真实账号，使用申请记录中的 applicant
                                                        email_applicant = email_applicant if email_applicant else application.applicant
                                                        
                                                        if email_applicant and email_applicant != '未知申请人':
                                                            email_manager = EmailManager()
                                                            email_manager.license_failed_send_email(
                                                                owner=email_applicant,
                                                                application=application,
                                                                error_message=gen_result.get('error', '未知错误')
                                                            )
                                                            logger.info(f"已发送 License 生成失败邮件给申请人: {email_applicant}")
                                                        else:
                                                            logger.warning(f"申请人信息为空，跳过邮件发送")
                                                    except Exception as email_error:
                                                        logger.error(f"发送邮件失败: {str(email_error)}", exc_info=True)
                                            else:
                                                logger.warning(f"未找到产品 {product} 的预制作模板文件，跳过 License 生成")
                                        except Exception as e:
                                            logger.error(f"生成产品 {product} License 文件异常: {str(e)}", exc_info=True)
                        
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
