"""
License过期检查和邮件提醒定时任务
每天固定时间执行，自动检查并发送即将过期的License提醒邮件
"""
from django.core.management.base import BaseCommand
from datetime import datetime, timedelta, date
from django.utils import timezone
from apps.lylicense.models import LicenseRecord, LicenseApplication
from utils.email import EmailManager
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# 产品组定义（与 views.py 和 apps.py 保持一致）
GLORYEX_GROUP_PRODUCTS = ['GloryEX', 'GloryEX3D', 'GloryPolaris', 'GloryEXCommon']
GLORYBOLT_GROUP_PRODUCTS = ['GloryBolt', 'GloryGrid']


def get_product_group(product_name):
    """
    判断产品属于哪个产品组
    
    Args:
        product_name: 产品名称
        
    Returns:
        str: 产品组名称 ('gloryex', 'glorybolt') 或 None（不属于任何产品组）
    """
    if product_name in GLORYEX_GROUP_PRODUCTS:
        return 'gloryex'
    elif product_name in GLORYBOLT_GROUP_PRODUCTS:
        return 'glorybolt'
    else:
        return None


def check_has_product_group(products_list):
    """
    检查产品列表中是否有属于同一产品组的产品
    
    Args:
        products_list: 产品名称列表
        
    Returns:
        tuple: (has_group, group_name, group_products)
            - has_group: 是否有产品组
            - group_name: 产品组名称（如果有）
            - group_products: 属于该产品组的产品列表
    """
    # 统计每个产品组的产品数量
    group_counts = {'gloryex': [], 'glorybolt': []}
    
    for product_name in products_list:
        group = get_product_group(product_name)
        if group:
            group_counts[group].append(product_name)
    
    # 【关键修复】检查是否有产品组（至少1个产品属于同一组即可，因为 GloryEXCommon 也需要归属到产品组）
    for group_name, products in group_counts.items():
        if len(products) >= 1:  # 从 >= 2 改为 >= 1
            return True, group_name, products
    
    return False, None, []


class Command(BaseCommand):
    help = '检查License过期状态并发送邮件提醒（30天、15天、7天各提醒一次）'

    def add_arguments(self, parser):
        """添加命令行参数"""
        parser.add_argument(
            '--force',
            action='store_true',
            dest='force',
            help='强制重新发送所有提醒邮件（忽略已发送标记）',
        )

    def handle(self, *args, **options):
        """执行定时任务"""
        force_send = options.get('force', False)
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'开始执行 License 过期检查任务'))
        self.stdout.write(self.style.SUCCESS(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'))
        self.stdout.write(self.style.SUCCESS(f'强制发送模式: {"是" if force_send else "否"}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        try:
            now = date.today()
            
            # 0. 【关键】先更新所有记录的 remaining_days 字段，确保数据准确
            self._update_remaining_days(now)
            
            # 1. 自动更新已过期的License状态
            expired_count = self._update_expired_records(now, force_send)
            
            # 2. 检查即将过期的License并发送提醒
            expiring_count = self._send_expiring_reminders(now, force_send)
            
            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS(f'任务执行完成！'))
            self.stdout.write(self.style.SUCCESS(f'- 更新剩余天数: 已完成'))
            self.stdout.write(self.style.SUCCESS(f'- 更新过期记录: {expired_count} 条'))
            self.stdout.write(self.style.SUCCESS(f'- 发送即将过期提醒: {expiring_count} 条'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
        except Exception as e:
            logger.error(f'License过期检查任务执行失败: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'任务执行失败: {str(e)}'))
            raise

    def _update_remaining_days(self, now):
        """
        更新所有有效License记录的剩余天数字段，并同步更新状态
        确保 remaining_days 和 status 字段与实际日期同步
        
        状态同步规则：
          - remaining_days == 0  → status=2 (已过期)
          - 0 < remaining_days <= 阈值  → status=3 (即将到期)
          - remaining_days > 阈值  → status=1 (有效)
          - status=0 (已撤销) 不做修改
        
        Args:
            now: 当前日期
        """
        self.stdout.write('\n[步骤0] 更新剩余天数及状态字段...')
        
        # 从配置中读取即将到期阈值天数，默认30天
        threshold_days = getattr(settings, 'LICENSE_EXPIRY_THRESHOLD_DAYS', 30)
        
        try:
            # 更新状态为有效(1)、已过期(2)和即将到期(3)的记录
            # status=0(已撤销)不做任何修改
            valid_records = LicenseRecord.objects.filter(status__in=[1, 2, 3])
            total_count = valid_records.count()
            
            if total_count == 0:
                self.stdout.write('没有需要更新的记录')
                return
            
            updated_days_count = 0
            updated_status_count = 0
            skipped_count = 0
            status_names = {1: '有效', 2: '已过期', 3: '即将到期'}
            
            for record in valid_records:
                if not record.end_time:
                    skipped_count += 1
                    continue
                
                # 计算新的剩余天数
                delta = record.end_time - now
                new_remaining_days = max(0, delta.days)
                
                # 根据剩余天数计算应有的状态
                if new_remaining_days == 0:
                    new_status = 2  # 已过期
                elif new_remaining_days <= threshold_days:
                    new_status = 3  # 即将到期
                else:
                    new_status = 1  # 有效
                
                # 判断是否需要更新
                days_changed = record.remaining_days != new_remaining_days
                status_changed = record.status != new_status
                
                if days_changed or status_changed:
                    update_fields = {
                        'remaining_days': new_remaining_days,
                        'status': new_status,
                        'update_datetime': timezone.now(),
                    }
                    LicenseRecord.objects.filter(id=record.id).update(**update_fields)
                    
                    changes = []
                    if days_changed:
                        changes.append(f'天数: {record.remaining_days}→{new_remaining_days}')
                        updated_days_count += 1
                    if status_changed:
                        changes.append(f'状态: {status_names.get(record.status, record.status)}→{status_names.get(new_status, new_status)}')
                        updated_status_count += 1
                    
                    self.stdout.write(f'✓ {record.application.serial_number}: {" | ".join(changes)}')
                else:
                    skipped_count += 1
            
            if updated_days_count > 0 or updated_status_count > 0:
                self.stdout.write(self.style.SUCCESS(
                    f'✓ 已更新: 天数变更 {updated_days_count} 条, '
                    f'状态变更 {updated_status_count} 条, '
                    f'未变化 {skipped_count} 条（共 {total_count} 条）'
                ))
                logger.info(
                    f'License剩余天数及状态更新完成: '
                    f'总数={total_count}, 天数变更={updated_days_count}, '
                    f'状态变更={updated_status_count}, 未变化={skipped_count}'
                )
            else:
                self.stdout.write(self.style.WARNING(f'⚠ 无需更新剩余天数及状态（{skipped_count} 条数据未变化）'))
                logger.info(f'License剩余天数及状态无需更新: 总数={total_count}, 未变化={skipped_count}')
            
        except Exception as e:
            logger.error(f'更新剩余天数及状态失败: {str(e)}', exc_info=True)
            # 不抛出异常，继续执行后续任务
            self.stdout.write(self.style.WARNING(f'⚠ 更新剩余天数及状态失败，但将继续执行: {str(e)}'))

    def _update_expired_records(self, now, force_send=False):
        """
        更新已过期的License状态并发送邮件
        
        Args:
            now: 当前日期
            force_send: 是否强制重新发送
            
        Returns:
            更新的记录数量
        """
        self.stdout.write('\n[步骤1] 检查已过期的License...')
        
        expired_records = LicenseRecord.objects.filter(
            end_time__lt=now,
            status__in=[1, 3]  # 有效状态和即将到期状态都可能已过期
        )
        
        expired_count = expired_records.count()
        self.stdout.write(f'发现 {expired_count} 条已过期的 License 记录')
        
        if expired_count > 0:
            # 在更新前先获取需要发送邮件的记录列表
            expired_to_notify = []
            for record in expired_records:
                extra_info = record.extra_info or {}
                if force_send or not extra_info.get('expired_email_sent', False):
                    expired_to_notify.append(record)
            
            # 更新状态为已过期
            expired_records.update(status=2)
            logger.info(f'自动更新了 {expired_count} 条已过期的 License 记录状态')
            
            # 发送过期提醒邮件
            email_manager = EmailManager()
            sent_count = 0
            for record in expired_to_notify:
                try:
                    application = LicenseApplication.objects.get(id=record.application.id)
                    if not application.applicant_id:
                        logger.warning(f'跳过发送邮件，申请人ID为空: {record.application.serial_number}')
                        continue
                    
                    email_manager.license_expired_send_email(
                        owner=application.applicant_id,
                        application=application,
                        end_time=record.end_time
                    )
                    
                    # 标记已发送
                    extra_info = record.extra_info or {}
                    extra_info['expired_email_sent'] = True
                    record.extra_info = extra_info
                    record.save(update_fields=['extra_info'])
                    
                    sent_count += 1
                    logger.info(f'已发送过期提醒邮件: {record.application.serial_number}')
                    
                except Exception as e:
                    logger.error(f'发送过期提醒邮件失败 {record.application.serial_number}: {str(e)}')
            
            self.stdout.write(f'✓ 已发送过期提醒邮件: {sent_count} 条')
        
        return expired_count

    def _send_expiring_reminders(self, now, force_send=False):
        """
        发送即将过期的License提醒邮件
        
        Args:
            now: 当前日期
            force_send: 是否强制重新发送
            
        Returns:
            发送提醒的记录数量
        """
        self.stdout.write('\n[步骤2] 检查即将过期的License...')
        
        email_manager = EmailManager()
        total_sent = 0
        
        # 从配置中读取提醒规则（支持动态配置）
        reminder_ranges = getattr(settings, 'LICENSE_EXPIRATION_REMINDERS', None)
        if not reminder_ranges:
            error_msg = 'LICENSE_EXPIRATION_REMINDERS 配置未找到，请在 settings.py 中配置'
            self.stdout.write(self.style.ERROR(error_msg))
            logger.error(error_msg)
            return 0
        
        self.stdout.write(f'使用提醒规则: {len(reminder_ranges)} 个级别')
        for reminder in reminder_ranges:
            self.stdout.write(f'  - {reminder["days"]}天提醒: 范围({reminder["lower"]}-{reminder["upper"]})')
        
        for reminder in reminder_ranges:
            days = reminder['days']
            lower = reminder['lower']
            upper = reminder['upper']
            
            # 计算对应的日期范围（直接使用 end_time 字段查询）
            if lower == 0:
                # 7天提醒：[0, 7] -> end_time 在 [now, now+7天]
                end_date_lower = now + timedelta(days=lower)
                end_date_upper = now + timedelta(days=upper)
                expiring_records = LicenseRecord.objects.filter(
                    end_time__gte=end_date_lower,
                    end_time__lte=end_date_upper,
                    status__in=[1, 3]  # 有效状态和即将到期状态
                )
            else:
                # 30天和15天提醒：(lower, upper] -> end_time 在 (now+lower, now+upper]
                end_date_lower = now + timedelta(days=lower)
                end_date_upper = now + timedelta(days=upper)
                expiring_records = LicenseRecord.objects.filter(
                    end_time__gt=end_date_lower,
                    end_time__lte=end_date_upper,
                    status__in=[1, 3]  # 有效状态和即将到期状态
                )
            
            expiring_count = expiring_records.count()
            self.stdout.write(f'  - {days}天提醒范围({lower}-{upper}): 发现 {expiring_count} 条记录')
            
            if expiring_count > 0:
                for record in expiring_records:
                    try:
                        application = LicenseApplication.objects.get(id=record.application.id)
                        if not application.applicant_id:
                            logger.warning(f'跳过发送邮件，申请人ID为空: {record.application.serial_number}')
                            continue
                        
                        # 检查是否有 user_info_list（多产品场景）
                        user_info_list = application.user_info_list or []
                        
                        # 调试日志：记录当前记录的 extra_info 状态
                        current_extra_info = record.extra_info or {}
                        logger.debug(f"处理记录 {record.application.serial_number}: status={record.status}, "
                                   f"end_time={record.end_time}, remaining_days={record.remaining_days}, "
                                   f"user_info_list长度={len(user_info_list)}, extra_info keys={list(current_extra_info.keys())}")
                        
                        if len(user_info_list) > 1:
                            # 多产品场景：需要判断是否所有产品剩余天数相同
                            sent = self._handle_multi_product_reminder(
                                record, application, email_manager, days, now, lower, upper, force_send
                            )
                        else:
                            # 单产品场景：没有 user_info_list 或只有一个产品
                            sent = self._handle_single_product_reminder(
                                record, application, email_manager, days, force_send
                            )
                        
                        if sent:
                            total_sent += 1
                            
                    except Exception as e:
                        logger.error(f'发送{days}天提醒邮件失败 {record.application.serial_number}: {str(e)}', exc_info=True)
        
        self.stdout.write(f'✓ 已发送即将过期提醒邮件: {total_sent} 条')
        return total_sent

    def _handle_single_product_reminder(self, record, application, email_manager, days, force_send=False):
        """
        处理单产品场景的邮件提醒
        
        Returns:
            bool: 是否成功发送
        """
        extra_info = record.extra_info or {}
        email_key = f'expiring_{days}day_email_sent'
        
        if not force_send and extra_info.get(email_key, False):
            return False
        
        try:
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
            
            logger.info(f'已发送{days}天提醒邮件: {record.application.serial_number}, 剩余{record.remaining_days}天')
            return True
            
        except Exception as e:
            logger.error(f'发送{days}天提醒邮件失败 {record.application.serial_number}: {str(e)}')
            return False

    def _handle_multi_product_reminder(self, record, application, email_manager, days, now, lower, upper, force_send=False):
        """
        处理多产品场景的邮件提醒
        
        逻辑：
        1. 首先判断是否有产品组（多个产品属于同一产品组）
           - 如果有产品组：将产品组内的产品合并发送一封邮件
           - 如果没有产品组：继续下面的逻辑
        2. 对于非产品组的产品：
           - 如果剩余天数相同：为每个产品分别发送独立邮件
           - 如果剩余天数不同：使用产品组模式，在一封邮件中列出所有即将过期的产品
        
        Returns:
            int: 成功发送的邮件数量
        """
        user_info_list = application.user_info_list or []
        extra_info = record.extra_info or {}
        
        # 收集需要提醒的产品信息
        products_to_remind = []
        
        # 【关键】获取 License 类型，只有 FlexNet 才有公共的 feature
        license_type = application.application_type  # 'flexnet' 或 'bitanswer'
        
        for idx, product_info in enumerate(user_info_list):
            product_name = product_info.get('Product', '')
            end_timestamp = product_info.get('Expirydate')
            
            if not product_name or not end_timestamp:
                continue
            
            # 【关键修复】对于 Bitanswer 类型，跳过 GloryEXCommon（它没有独立的过期时间）
            if license_type != 'flexnet' and ('Common' in product_name or product_name == 'GloryEXCommon'):
                logger.debug(f"  产品[{idx}] {product_name}: Bitanswer 类型无公共部分，跳过")
                continue
            
            # 解析产品结束时间（从毫秒时间戳转换为 date 对象）
            try:
                if isinstance(end_timestamp, (int, float)):
                    product_end_time = datetime.fromtimestamp(end_timestamp / 1000).date()
                elif isinstance(end_timestamp, str):
                    product_end_time = datetime.strptime(end_timestamp, '%Y-%m-%d').date()
                else:
                    product_end_time = end_timestamp
            except (ValueError, TypeError):
                continue
            
            # 计算产品剩余天数
            product_remaining_days = (product_end_time - now).days
            
            # 判断该产品的剩余天数是否在提醒范围内
            in_range = False
            if lower == 0:
                in_range = (lower <= product_remaining_days <= upper)
            else:
                in_range = (lower < product_remaining_days <= upper)
            
            if in_range:
                email_key = f'expiring_{days}day_{idx}_{product_name}_email_sent'
                already_sent = extra_info.get(email_key, False)
                
                # 调试日志：记录每个产品的去重状态
                logger.debug(f"  产品[{idx}] {product_name}: 剩余{product_remaining_days}天, "
                           f"in_range={in_range}, email_key={email_key}, already_sent={already_sent}")
                
                if force_send or not already_sent:
                    products_to_remind.append({
                        'index': idx,
                        'name': product_name,
                        'remaining_days': product_remaining_days,
                        'email_key': email_key,
                        'end_time': product_end_time
                    })
                else:
                    logger.debug(f"  产品[{idx}] {product_name} 已发送过{days}天提醒，跳过")
        
        # 如果没有产品需要提醒，返回0
        if not products_to_remind:
            logger.debug(f"记录 {record.application.serial_number} 的所有产品都已发送过{days}天提醒，跳过")
            return 0
        
        # 提取产品名称列表
        product_names = [p['name'] for p in products_to_remind]
        
        # 检查是否有产品组
        has_group, group_name, group_products = check_has_product_group(product_names)
        
        total_sent = 0
        
        if has_group:
            # 有产品组：将产品组内的产品合并发送一封邮件
            logger.info(f"检测到产品组 '{group_name}'，包含产品: {', '.join(group_products)}")
            
            # 分离产品组产品和非产品组产品
            group_product_items = [p for p in products_to_remind if p['name'] in group_products]
            standalone_product_items = [p for p in products_to_remind if p['name'] not in group_products]
            
            # 1. 处理产品组：合并发送一封邮件
            if group_product_items:
                try:
                    product_details = []
                    for product in group_product_items:
                        product_details.append({
                            'name': product['name'],
                            'remaining_days': product['remaining_days'],
                            'start_time': record.start_time,
                            'end_time': product['end_time']
                        })
                    
                    # 使用最早的过期时间作为邮件中的end_time
                    earliest_end_time = min([p['end_time'] for p in group_product_items])
                    
                    email_manager.license_expiring_soon_send_email(
                        owner=application.applicant_id,
                        application=application,
                        end_time=earliest_end_time,
                        remaining_days=days,
                        product_details=product_details
                    )
                    
                    # 标记产品组内所有产品已发送（无论成功与否，都标记避免重复）
                    for product in group_product_items:
                        extra_info[product['email_key']] = True
                    
                    total_sent += 1
                    
                    product_names_str = ', '.join([p['name'] for p in group_product_items])
                    logger.info(f'已发送{days}天提醒邮件（产品组合并）: {record.application.serial_number}, 产品组: {group_name}, 产品: {product_names_str}')
                    
                except Exception as e:
                    logger.error(f'发送{days}天提醒邮件失败（产品组合并） {record.application.serial_number}: {str(e)}')
            
            # 2. 处理非产品组产品：根据剩余天数决定发送方式
            if standalone_product_items:
                remaining_days_set = set([p['remaining_days'] for p in standalone_product_items])
                all_same_days = len(remaining_days_set) == 1
                
                if all_same_days:
                    # 所有非产品组产品剩余天数相同：分别发送独立邮件
                    logger.info(f"非产品组产品：{len(standalone_product_items)}个产品剩余天数相同({standalone_product_items[0]['remaining_days']}天)，分别发送邮件")
                    
                    for product in standalone_product_items:
                        try:
                            product_details = [{
                                'name': product['name'],
                                'remaining_days': product['remaining_days'],
                                'start_time': record.start_time,
                                'end_time': product['end_time']
                            }]
                            
                            email_manager.license_expiring_soon_send_email(
                                owner=application.applicant_id,
                                application=application,
                                end_time=product['end_time'],
                                remaining_days=product['remaining_days'],
                                product_details=product_details
                            )
                            
                            extra_info[product['email_key']] = True
                            total_sent += 1
                            
                            logger.info(f"已发送{days}天提醒邮件（非产品组-独立）: {record.application.serial_number}, 产品: {product['name']}, 剩余{product['remaining_days']}天")
                            
                        except Exception as e:
                            logger.error(f"发送{days}天提醒邮件失败（非产品组-独立） {record.application.serial_number} - {product['name']}: {str(e)}")
                            # 即使发送失败，也标记为已发送，避免重复尝试
                            extra_info[product['email_key']] = True
                else:
                    # 非产品组产品剩余天数不同：合并发送一封邮件
                    logger.info(f"非产品组产品：剩余天数不同，合并发送一封邮件")
                    
                    try:
                        product_details = []
                        for product in standalone_product_items:
                            product_details.append({
                                'name': product['name'],
                                'remaining_days': product['remaining_days'],
                                'start_time': record.start_time,
                                'end_time': product['end_time']
                            })
                        
                        earliest_end_time = min([p['end_time'] for p in standalone_product_items])
                        
                        email_manager.license_expiring_soon_send_email(
                            owner=application.applicant_id,
                            application=application,
                            end_time=earliest_end_time,
                            remaining_days=days,
                            product_details=product_details
                        )
                        
                        for product in standalone_product_items:
                            extra_info[product['email_key']] = True
                        
                        total_sent += 1
                        
                        product_names_str = ', '.join([p['name'] for p in standalone_product_items])
                        logger.info(f'已发送{days}天提醒邮件（非产品组-组合）: {record.application.serial_number}, 产品: {product_names_str}')
                        
                    except Exception as e:
                        logger.error(f'发送{days}天提醒邮件失败（非产品组-组合） {record.application.serial_number}: {str(e)}')
        else:
            # 没有产品组：按照原有逻辑处理
            remaining_days_set = set([p['remaining_days'] for p in products_to_remind])
            all_same_days = len(remaining_days_set) == 1
            
            if all_same_days:
                # 所有产品剩余天数相同：为每个产品分别发送独立邮件
                logger.info(f"多产品场景：{len(products_to_remind)}个产品剩余天数相同({products_to_remind[0]['remaining_days']}天)，分别发送邮件")
                
                for product in products_to_remind:
                    try:
                        product_details = [{
                            'name': product['name'],
                            'remaining_days': product['remaining_days'],
                            'start_time': record.start_time,
                            'end_time': product['end_time']
                        }]
                        
                        email_manager.license_expiring_soon_send_email(
                            owner=application.applicant_id,
                            application=application,
                            end_time=product['end_time'],
                            remaining_days=product['remaining_days'],
                            product_details=product_details
                        )
                        
                        extra_info[product['email_key']] = True
                        total_sent += 1
                        
                        logger.info(f"已发送{days}天提醒邮件（多产品-独立）: {record.application.serial_number}, 产品: {product['name']}, 剩余{product['remaining_days']}天")
                        
                    except Exception as e:
                        logger.error(f"发送{days}天提醒邮件失败（多产品-独立） {record.application.serial_number} - {product['name']}: {str(e)}")
                        # 即使发送失败，也标记为已发送，避免重复尝试
                        extra_info[product['email_key']] = True
            else:
                # 产品剩余天数不同：使用产品组模式，在一封邮件中列出所有即将过期的产品
                logger.info(f"多产品场景：产品剩余天数不同，使用产品组模式发送一封邮件")
                
                try:
                    product_details = []
                    for product in products_to_remind:
                        product_details.append({
                            'name': product['name'],
                            'remaining_days': product['remaining_days'],
                            'start_time': record.start_time,
                            'end_time': product['end_time']
                        })
                    
                    earliest_end_time = min([p['end_time'] for p in products_to_remind])
                    
                    email_manager.license_expiring_soon_send_email(
                        owner=application.applicant_id,
                        application=application,
                        end_time=earliest_end_time,
                        remaining_days=days,
                        product_details=product_details
                    )
                    
                    for product in products_to_remind:
                        extra_info[product['email_key']] = True
                    
                    record.extra_info = extra_info
                    record.save(update_fields=['extra_info'])
                    
                    product_names_str = ', '.join([p['name'] for p in products_to_remind])
                    logger.info(f'已发送{days}天提醒邮件（多产品-组合）: {record.application.serial_number}, 产品: {product_names_str}')
                    total_sent = 1
                    
                except Exception as e:
                    logger.error(f'发送{days}天提醒邮件失败（多产品-组合） {record.application.serial_number}: {str(e)}')
        
        # 保存extra_info
        if total_sent > 0:
            record.extra_info = extra_info
            record.save(update_fields=['extra_info'])
        
        return total_sent

