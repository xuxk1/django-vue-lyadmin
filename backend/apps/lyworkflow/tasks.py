from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_workflow_notification(user_id, instance_id, notification_type):
    """
    发送流程通知
    :param user_id: 用户ID
    :param instance_id: 流程实例ID
    :param notification_type: 通知类型 (approve, cc, reject, return, etc.)
    """
    try:
        from apps.lyworkflow.models import WorkflowInstance, Users
        from apps.lymessages.models import MyMessage, MyMessageUser
        
        user = Users.objects.get(id=user_id)
        instance = WorkflowInstance.objects.get(id=instance_id)
        
        # 根据通知类型生成消息内容
        message_title = ''
        message_content = ''
        
        if notification_type == 'approve':
            message_title = f'流程审批通知 - {instance.title}'
            message_content = f'您有一个流程需要审批：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'cc':
            message_title = f'流程抄送通知 - {instance.title}'
            message_content = f'您被抄送了一个流程：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'reject':
            message_title = f'流程驳回通知 - {instance.title}'
            message_content = f'您的流程申请已被驳回：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'return':
            message_title = f'流程退回通知 - {instance.title}'
            message_content = f'您的流程申请已被退回：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'approved':
            message_title = f'流程通过通知 - {instance.title}'
            message_content = f'您的流程申请已通过审批：{instance.title}，流程编号：{instance.instance_no}'
        else:
            message_title = f'流程通知 - {instance.title}'
            message_content = f'流程状态更新：{instance.title}'
        
        # 创建站内消息
        message = MyMessage.objects.create(
            msg_title=message_title,
            msg_content=message_content,
            msg_chanel=1,  # 系统通知
            public=False,
            status=True
        )
        
        # 创建用户消息关联
        MyMessageUser.objects.create(
            messageid=message,
            revuserid=user,
            is_read=False,
            is_delete=False
        )
        
        logger.info(f'发送流程通知成功：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
    except Exception as e:
        logger.error(f'发送流程通知失败：{str(e)}')
