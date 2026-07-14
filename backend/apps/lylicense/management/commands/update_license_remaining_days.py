"""
更新License记录的剩余天数字段
用于定期同步 remaining_days 字段，确保数据准确性
"""
from django.core.management.base import BaseCommand
from datetime import date
from django.utils import timezone
from apps.lylicense.models import LicenseRecord
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '更新所有有效License记录的剩余天数字段'

    def handle(self, *args, **options):
        """执行更新任务"""
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'开始更新 License 剩余天数'))
        self.stdout.write(self.style.SUCCESS(f'执行时间: {date.today().strftime("%Y-%m-%d")}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        try:
            # 更新状态为有效(1)和即将到期(3)的记录
            # status=2(已过期)和status=0(已撤销)不需要更新
            valid_records = LicenseRecord.objects.filter(status__in=[1, 3])
            total_count = valid_records.count()
            
            self.stdout.write(f'\n发现 {total_count} 条有效 License 记录')
            
            if total_count == 0:
                self.stdout.write(self.style.WARNING('没有需要更新的记录'))
                return
            
            updated_count = 0
            skipped_count = 0
            now = date.today()
            
            for record in valid_records:
                # 计算新的剩余天数
                if record.end_time:
                    delta = record.end_time - now
                    new_remaining_days = max(0, delta.days)
                    
                    # 只有当值发生变化时才更新
                    if record.remaining_days != new_remaining_days:
                        old_value = record.remaining_days
                        record.remaining_days = new_remaining_days
                        # 使用 update 方法直接更新数据库，同时更新 update_datetime
                        # 注意：update() 不会触发 auto_now，需要手动指定
                        LicenseRecord.objects.filter(id=record.id).update(
                            remaining_days=new_remaining_days,
                            update_datetime=timezone.now()
                        )
                        updated_count += 1
                        self.stdout.write(f'✓ 记录 {record.application.serial_number}: {old_value}天 → {new_remaining_days}天')
                    else:
                        skipped_count += 1
            
            self.stdout.write(self.style.SUCCESS('=' * 60))
            if updated_count > 0:
                self.stdout.write(self.style.SUCCESS(f'✅ 更新完成！'))
                self.stdout.write(self.style.SUCCESS(f'- 总记录数: {total_count}'))
                self.stdout.write(self.style.SUCCESS(f'- 实际更新: {updated_count} 条'))
                self.stdout.write(self.style.SUCCESS(f'- 数据未变化: {skipped_count} 条'))
            else:
                self.stdout.write(self.style.WARNING('⚠️  无需更新'))
                self.stdout.write(self.style.WARNING(f'- 总记录数: {total_count}'))
                self.stdout.write(self.style.WARNING(f'- 数据未变化: {skipped_count} 条'))
            self.stdout.write(self.style.SUCCESS('=' * 60))
            
            logger.info(f'License剩余天数更新完成: 总数={total_count}, 更新={updated_count}, 未变化={skipped_count}')
            
        except Exception as e:
            logger.error(f'License剩余天数更新失败: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'任务执行失败: {str(e)}'))
            raise
