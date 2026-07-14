"""
License文件扫描定时任务
每天固定时间执行，扫描LIC文件并发送过期提醒
"""
from django.core.management import call_command
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def scan_license_file_expiration_job():
    """
    License 过期检查定时任务
    每天执行，检查即将过期的 License 文件并发送提醒邮件
    """
    logger.info('=' * 60)
    logger.info('开始执行 License 过期检查定时任务')

    try:
        # 调用你的管理命令
        call_command('license_file_scanner')
        logger.info('License 过期检查定时任务执行完成')
    except Exception as e:
        logger.error(f'License 过期检查定时任务执行失败: {e}', exc_info=True)
        raise

    logger.info('=' * 60)