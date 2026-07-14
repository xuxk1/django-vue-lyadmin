"""
License文件扫描定时任务
每天固定时间执行，扫描LIC文件并发送过期提醒
"""
from django.core.management import call_command
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def update_remaining_days_job():
    """
    License Record中剩余天数更新定时任务
    每天执行，更新License Record表中remaining_days字段
    """
    logger.info('=' * 60)
    logger.info('开始执行 License Record表中remaining_days字段更新定时任务')

    try:
        # 调用你的管理命令
        call_command('update_license_remaining_days')
        logger.info('License Record表中remaining_days字段更新定时任务执行完成')
    except Exception as e:
        logger.error(f'License Record表中remaining_days字段更新定时任务执行失败: {e}', exc_info=True)
        raise

    logger.info('=' * 60)