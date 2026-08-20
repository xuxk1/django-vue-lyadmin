# mysystem/cron.py
"""
django-crontab 定时任务入口 - LDAP用户同步
"""
import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)


def ldap_sync_users_job():
    """
    LDAP用户同步定时任务
    每天执行，从LDAP批量同步用户信息到本地数据库，自动创建部门和子部门
    """
    logger.info('=' * 60)
    logger.info('开始执行 LDAP 用户同步定时任务')

    try:
        call_command('ldap_sync_users')
        logger.info('LDAP 用户同步定时任务执行完成')
    except Exception as e:
        logger.error(f'LDAP 用户同步定时任务执行失败: {e}', exc_info=True)
        raise

    logger.info('=' * 60)
