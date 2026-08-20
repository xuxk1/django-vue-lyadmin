"""
License Record中剩余天数及状态同步定时任务
每天固定时间执行，同步更新remaining_days和status字段
"""
from django.core.management import call_command
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def update_remaining_days_job():
    """
    License Record中剩余天数及状态同步定时任务
    每天执行，同步更新License Record表中remaining_days和status字段
    """
    logger.info('=' * 60)
    logger.info('开始执行 License Record 剩余天数及状态同步定时任务')

    try:
        call_command('update_license_remaining_days')
        logger.info('License Record 剩余天数及状态同步定时任务执行完成')
    except Exception as e:
        logger.error(f'License Record 剩余天数及状态同步定时任务执行失败: {e}', exc_info=True)
        raise

    logger.info('=' * 60)