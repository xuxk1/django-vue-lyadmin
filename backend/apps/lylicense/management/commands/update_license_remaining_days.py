"""更新License记录的剩余天数字段和状态
用于定期同步 remaining_days 和 status 字段，确保数据准确性
状态同步规则：
  - remaining_days == 0  → status=2 (已过期)
  - 0 < remaining_days <= 阈值  → status=3 (即将到期)
  - remaining_days > 阈值  → status=1 (有效)
  - status=0 (已撤销) 不做修改
"""
from django.core.management.base import BaseCommand
from datetime import date
from django.conf import settings
from django.utils import timezone
from apps.lylicense.models import LicenseRecord
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '更新所有有效License记录的剩余天数字段，并同步更新状态'

    def handle(self, *args, **options):
        """执行更新任务"""
        # 从配置中读取即将到期阈值天数，默认30天
        threshold_days = getattr(settings, 'LICENSE_EXPIRY_THRESHOLD_DAYS', 30)
        
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'开始更新 License 剩余天数及状态'))
        self.stdout.write(self.style.SUCCESS(f'执行时间: {date.today().strftime("%Y-%m-%d")}'))
        self.stdout.write(self.style.SUCCESS(f'即将到期阈值: {threshold_days} 天'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        try:
            # 更新状态为有效(1)、已过期(2)和即将到期(3)的记录
            # status=0(已撤销)不做任何修改
            # 包含status=2是因为需要持续同步状态，防止状态与剩余天数不匹配
            valid_records = LicenseRecord.objects.filter(status__in=[1, 2, 3])
            total_count = valid_records.count()
            
            self.stdout.write(f'\n发现 {total_count} 条 License 记录（排除已撤销）')
            
            if total_count == 0:
                self.stdout.write(self.style.WARNING('没有需要更新的记录'))
                return
            
            updated_days_count = 0
            updated_status_count = 0
            skipped_count = 0
            now = date.today()
            
            # 状态名称映射，用于日志输出
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
                    old_days = record.remaining_days
                    old_status = record.status
                    
                    # 构建更新字段
                    update_fields = {
                        'remaining_days': new_remaining_days,
                        'status': new_status,
                        'update_datetime': timezone.now(),
                    }
                    LicenseRecord.objects.filter(id=record.id).update(**update_fields)
                    
                    # 输出详细变更日志
                    changes = []
                    if days_changed:
                        changes.append(f'天数: {old_days}→{new_remaining_days}')
                        updated_days_count += 1
                    if status_changed:
                        changes.append(f'状态: {status_names.get(old_status, old_status)}→{status_names.get(new_status, new_status)}')
                        updated_status_count += 1
                    
                    self.stdout.write(f'✓ 记录 {record.application.serial_number}: {" | ".join(changes)}')
                else:
                    skipped_count += 1
            
            # 输出统计汇总
            self.stdout.write(self.style.SUCCESS('=' * 60))
            if updated_days_count > 0 or updated_status_count > 0:
                self.stdout.write(self.style.SUCCESS(f'✅ 更新完成！'))
                self.stdout.write(self.style.SUCCESS(f'- 总记录数: {total_count}'))
                self.stdout.write(self.style.SUCCESS(f'- 剩余天数变更: {updated_days_count} 条'))
                self.stdout.write(self.style.SUCCESS(f'- 状态变更: {updated_status_count} 条'))
                self.stdout.write(self.style.SUCCESS(f'- 数据未变化: {skipped_count} 条'))
            else:
                self.stdout.write(self.style.WARNING('⚠️  无需更新'))
                self.stdout.write(self.style.WARNING(f'- 总记录数: {total_count}'))
                self.stdout.write(self.style.WARNING(f'- 数据未变化: {skipped_count} 条'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
            logger.info(
                f'License剩余天数及状态更新完成: '
                f'总数={total_count}, 天数变更={updated_days_count}, '
                f'状态变更={updated_status_count}, 未变化={skipped_count}'
            )
            
        except Exception as e:
            logger.error(f'License剩余天数及状态更新失败: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'任务执行失败: {str(e)}'))
            raise
