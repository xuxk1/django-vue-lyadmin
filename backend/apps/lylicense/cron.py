# apps/LyLicense/cron.py
"""
django-crontab 定时任务入口
"""
import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)


def check_license_expiration_job():
    """
    License 过期检查定时任务
    每天执行，检查即将过期的 License 并发送提醒邮件
    """
    logger.info('=' * 60)
    logger.info('开始执行 License 过期检查定时任务')

    try:
        # 调用你的管理命令
        call_command('check_license_expiration', force=False)
        logger.info('License 过期检查定时任务执行完成')
    except Exception as e:
        logger.error(f'License 过期检查定时任务执行失败: {e}', exc_info=True)
        raise

    logger.info('=' * 60)