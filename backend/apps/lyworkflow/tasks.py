from celery import shared_task
import logging
import config

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_workflow_notification(self, user_id, instance_id, notification_type):
    """
    发送流程通知（支持站内消息 + 邮件）
    :param self: Celery 任务实例
    :param user_id: 用户ID
    :param instance_id: 流程实例ID
    :param notification_type: 通知类型 (approve, cc, reject, return, etc.)
    """
    try:
        from apps.lyworkflow.models import WorkflowInstance, Users
        from apps.lymessages.models import MyMessage, MyMessageUser
        
        logger.info(f'开始处理通知任务：user_id={user_id}, instance_id={instance_id}, type={notification_type}')
        
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
        
        # 检查是否已经存在相同的消息（避免重复推送）
        # 使用更严格的去重条件：用户 + 流程实例ID + 通知类型
        existing_message_user = MyMessageUser.objects.filter(
            revuserid=user,
            messageid__msg_title=message_title,
            messageid__msg_content=message_content,
            is_delete=False
        ).first()
        
        if existing_message_user:
            logger.info(f'消息已存在，跳过重复推送：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
            return
        
        # 创建站内消息（使用 get_or_create 防止并发重复）
        try:
            message, created = MyMessage.objects.get_or_create(
                msg_title=message_title,
                msg_content=message_content,
                msg_chanel=1,  # 系统通知
                public=False,
                status=True,
                defaults={
                    'msg_title': message_title,
                    'msg_content': message_content,
                    'msg_chanel': 1,
                    'public': False,
                    'status': True
                }
            )
            
            # 创建用户消息关联（使用 get_or_create 防止并发重复）
            message_user, user_created = MyMessageUser.objects.get_or_create(
                messageid=message,
                revuserid=user,
                defaults={
                    'is_read': False,
                    'is_delete': False
                }
            )
            
            if not user_created:
                logger.info(f'用户消息关联已存在，跳过：用户{user.name}，流程{instance.instance_no}')
                return
                
        except Exception as db_error:
            # 如果发生唯一约束冲突，说明消息已存在
            logger.info(f'检测到唯一约束冲突，消息已存在：用户{user.name}，流程{instance.instance_no}')
            return
        
        logger.info(f'站内消息创建成功：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
        
        # 尝试发送邮件通知（如果配置了邮件服务）
        self._send_email_notification(user, instance, notification_type)
        
        logger.info(f'发送流程通知成功：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
    except Exception as e:
        logger.error(f'发送流程通知失败：{str(e)}')
        # 重试机制
        raise self.retry(exc=e)
    
    def _send_email_notification(self, user, instance, notification_type):
        """
        发送邮件通知
        
        Args:
            user: 用户对象
            instance: 流程实例对象
            notification_type: 通知类型
        """
        try:
            from utils.email import EmailManager
            
            # 获取用户邮箱（假设用户有 email 字段）
            if not hasattr(user, 'email') or not user.email:
                logger.warning(f'用户 {user.name} 没有配置邮箱，跳过邮件通知')
                return
            
            # 根据通知类型生成邮件内容
            subject = ''
            html_body = ''
            text_body = ''
            
            if notification_type == 'approve':
                subject = f'【待审批】{instance.title}'
                html_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .header {{ background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                        .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                        .button {{ display: inline-block; padding: 10px 20px; background-color: #2196f3; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h2>📋 流程审批通知</h2>
                        <p>您好，{user.name}！您有一个新的流程需要审批。</p>
                    </div>
                    <div class="info">
                        <p><strong>流程标题：</strong>{instance.title}</p>
                        <p><strong>流程编号：</strong>{instance.instance_no}</p>
                        <p><strong>申请人：</strong>{instance.applicant_name if hasattr(instance, 'applicant_name') else '未知'}</p>
                        <p><strong>申请时间：</strong>{instance.create_datetime.strftime('%Y-%m-%d %H:%M:%S') if instance.create_datetime else '未知'}</p>
                    </div>
                    <a href="{config.DOMAIN_HOST}/#/workflowManage/workflowList" class="button">前往审批</a>
                    <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
                </body>
                </html>
                """
                text_body = f"""
流程审批通知

您好，{user.name}！您有一个新的流程需要审批。

流程标题：{instance.title}
流程编号：{instance.instance_no}
申请人：{instance.applicant_name if hasattr(instance, 'applicant_name') else '未知'}
申请时间：{instance.create_datetime.strftime('%Y-%m-%d %H:%M:%S') if instance.create_datetime else '未知'}

请前往系统查看并审批：{config.DOMAIN_HOST}/#/workflowManage/workflowList

此邮件为系统自动发送，请勿直接回复。
                """
            elif notification_type == 'approved':
                subject = f'【已通过】{instance.title}'
                html_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .header {{ background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                        .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h2>✅ 流程审批通过</h2>
                        <p>您好，{user.name}！您的流程申请已通过审批。</p>
                    </div>
                    <div class="info">
                        <p><strong>流程标题：</strong>{instance.title}</p>
                        <p><strong>流程编号：</strong>{instance.instance_no}</p>
                    </div>
                    <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
                </body>
                </html>
                """
                text_body = f"""
流程审批通过

您好，{user.name}！您的流程申请已通过审批。

流程标题：{instance.title}
流程编号：{instance.instance_no}

此邮件为系统自动发送，请勿直接回复。
                """
            elif notification_type == 'reject':
                subject = f'【已驳回】{instance.title}'
                html_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .header {{ background-color: #ffebee; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                        .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h2>❌ 流程审批驳回</h2>
                        <p>您好，{user.name}！您的流程申请已被驳回。</p>
                    </div>
                    <div class="info">
                        <p><strong>流程标题：</strong>{instance.title}</p>
                        <p><strong>流程编号：</strong>{instance.instance_no}</p>
                    </div>
                    <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
                </body>
                </html>
                """
                text_body = f"""
流程审批驳回

您好，{user.name}！您的流程申请已被驳回。

流程标题：{instance.title}
流程编号：{instance.instance_no}

此邮件为系统自动发送，请勿直接回复。
                """
            else:
                subject = f'【流程通知】{instance.title}'
                html_body = f"""
                <html>
                <head>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .header {{ background-color: #fff3e0; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                        .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h2> 流程状态更新</h2>
                        <p>您好，{user.name}！您的流程状态已更新。</p>
                    </div>
                    <div class="info">
                        <p><strong>流程标题：</strong>{instance.title}</p>
                        <p><strong>流程编号：</strong>{instance.instance_no}</p>
                        <p><strong>当前状态：</strong>{self._get_status_display(instance.status)}</p>
                    </div>
                    <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
                </body>
                </html>
                """
                text_body = f"""
流程状态更新

您好，{user.name}！您的流程状态已更新。

流程标题：{instance.title}
流程编号：{instance.instance_no}
当前状态：{self._get_status_display(instance.status)}

此邮件为系统自动发送，请勿直接回复。
                """
            
            # 创建自定义邮件消息类
            class WorkflowNotificationEmail:
                def __init__(self, recipient, subject, html_body, text_body):
                    self.recipient = recipient
                    self.subject = subject
                    self.html_body = html_body
                    self.text_body = text_body
                
                def get_email_content(self):
                    return {
                        "recipient": self.recipient,
                        "subject": self.subject,
                        "Cc": '',
                        "body_html": self.html_body,
                        "body_text": self.text_body
                    }
            
            # 发送邮件
            email_manager = EmailManager()
            email_message = WorkflowNotificationEmail(
                user.email,
                subject,
                html_body,
                text_body
            )
            email_manager.send_email([email_message])
            
            logger.info(f'邮件通知发送成功：{user.email}，流程{instance.instance_no}')
            
        except Exception as e:
            # 邮件发送失败不影响站内消息，只记录日志
            logger.warning(f'邮件通知发送失败（可能是邮件服务未配置）：{str(e)}')
    
    def _get_status_display(self, status):
        """获取状态显示文本"""
        status_map = {
            0: '草稿',
            1: '待审批',
            2: '审批中',
            3: '已通过',
            4: '已驳回',
            5: '已退回'
        }
        return status_map.get(status, '未知')
