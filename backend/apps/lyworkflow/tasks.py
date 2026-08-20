from celery import shared_task
import logging
import uuid
import config

logger = logging.getLogger(__name__)


def get_workflow_status_display(status):
    """获取流程状态显示文本"""
    status_map = {
        0: '草稿',
        1: '审批中',
        2: '已通过',
        3: '已驳回',
        4: '已撤回',
        5: '已取消',
        6: '已退回'
    }
    return status_map.get(status, '未知')


def get_workflow_approval_url(instance_id):
    """生成审批页面超链接（点击后跳转到审核页面并自动打开审批弹窗）

    直接使用 config.MAIL_WEB_HOST 作为邮件中的前端跳转地址，
    不回退到 DOMAIN_HOST（后端服务地址 8000 端口，无法打开前端页面）。
    """
    return f'{config.MAIL_WEB_HOST}/#/workflowList?approve_instance={instance_id}'


def get_workflow_view_url(instance_id):
    """生成流程详情页面超链接（点击后跳转到流程列表并自动打开详情弹窗）

    用于评论通知等"仅查看"场景，与审批链接（自动打开审批弹窗）区分：
    - 审批链接：approve_instance 参数 → 自动打开审批/确认弹窗；
    - 详情链接：view_instance 参数 → 自动打开流程详情弹窗（含评论内容与历史）。
    """
    return f'{config.MAIL_WEB_HOST}/#/workflowList?view_instance={instance_id}'


def _resolve_user_email(user):
    """获取用户邮箱，未配置邮箱时回退到 账号@公司域名

    支持测试模式：config.MAIL_TEST_MODE 为 True 时，
    所有审批邮件统一发送到 config.MAIL_TEST_RECIPIENT，方便测试验证。
    关闭测试模式后自动恢复为按实际待审批人发送。
    """
    # 测试模式：统一发送到测试邮箱
    if getattr(config, 'MAIL_TEST_MODE', False):
        test_recipient = getattr(config, 'MAIL_TEST_RECIPIENT', '')
        if test_recipient:
            return test_recipient

    email = getattr(user, 'email', None)
    if email:
        return email
    # 回退：项目内用户通过 LDAP 登录，邮箱为 username@phlexing.com
    if getattr(user, 'username', None):
        return f'{user.username}@phlexing.com'
    return None


def _get_workflow_default_cc(recipient_email):
    """获取审批流通知邮件默认抄送地址（从配置 config.MAIL_WORKFLOW_CC 读取）

    当收件人已包含抄送地址时（如测试模式统一发往同一邮箱）返回空串，避免重复抄送。
    """
    cc_name = getattr(config, 'MAIL_WORKFLOW_CC', '')
    if not cc_name:
        logger.info('未配置 MAIL_WORKFLOW_CC，不添加默认抄送')
        return ''
    cc_addr = cc_name if '@' in cc_name else f'{cc_name}@phlexing.com'
    if cc_addr in str(recipient_email or ''):
        logger.info(f'收件人已包含默认抄送地址，跳过重复抄送：收件人={recipient_email}，抄送={cc_addr}')
        return ''
    return cc_addr


def _send_workflow_email_notification(user, instance, notification_type):
    """
    发送邮件通知

    Args:
        user: 用户对象
        instance: 流程实例对象
        notification_type: 通知类型
    """
    try:
        from utils.email import EmailManager

        # 获取收件邮箱：测试模式下统一发到测试邮箱，否则发给实际待审批人
        recipient_email = _resolve_user_email(user)
        if not recipient_email:
            logger.warning(f'用户 {getattr(user, "name", user.id)} 无法获取邮箱，跳过邮件通知')
            return
        if getattr(config, 'MAIL_TEST_MODE', False) and recipient_email == getattr(config, 'MAIL_TEST_RECIPIENT', ''):
            logger.info(f'[测试模式] 准备发送邮件通知：实际审批人={user.name}，邮件统一发往测试邮箱={recipient_email}，'
                        f'流程={instance.instance_no}，类型={notification_type}')
        else:
            logger.info(f'准备发送邮件通知：收件人={recipient_email}，流程={instance.instance_no}，类型={notification_type}')

        approval_url = get_workflow_approval_url(instance.id)
        applicant_name = instance.applicant.name if getattr(instance, 'applicant', None) else '未知'
        create_time_str = instance.create_datetime.strftime('%Y-%m-%d %H:%M:%S') if instance.create_datetime else '未知'

        # 每封邮件生成唯一邮件码：流程标题/编号固定不变，同一流程发给多人、
        # 或同一收件人短时间内收到多封同主题邮件（如退回重提）时主题仍会重复，
        # 邮件网关按"收件人+主题"去重会丢信；追加随机邮件码保证每封邮件主题全局唯一
        mail_code = uuid.uuid4().hex[:8]

        # 根据通知类型生成邮件内容
        subject = ''
        html_body = ''
        text_body = ''

        if notification_type == 'approve':
            # 主题携带审批人姓名与邮件码：多审批人/测试模式（同一收件人）下每封邮件主题唯一，
            # 避免相同主题邮件被邮件网关去重丢弃；流程编号各审批人相同，从主题中移除避免标题过长
            subject = f'【待审批】您有一个待审批的工作流 - {instance.title}（审批人：{user.name}，邮件码：{mail_code}）'
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
                    <h2>📋 待审批工作流通知</h2>
                    <p>您好，{user.name}！您有一个待审批的工作流，请及时处理。</p>
                </div>
                <div class="info">
                    <p><strong>流程标题：</strong>{instance.title}</p>
                    <p><strong>流程编号：</strong>{instance.instance_no}</p>
                    <p><strong>申请人：</strong>{applicant_name}</p>
                    <p><strong>申请时间：</strong>{create_time_str}</p>
                </div>
                <a href="{approval_url}" class="button">前往审批</a>
                <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
            </body>
            </html>
            """
            text_body = f"""
待审批工作流通知

您好，{user.name}！您有一个待审批的工作流，请及时处理。

流程标题：{instance.title}
流程编号：{instance.instance_no}
申请人：{applicant_name}
申请时间：{create_time_str}

请点击以下链接前往审批：{approval_url}

此邮件为系统自动发送，请勿直接回复。
            """
        elif notification_type == 'cc':
            subject = f'【流程抄送】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'
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
                    <h2>📨 流程抄送通知</h2>
                    <p>您好，{user.name}！您被抄送了一个流程。</p>
                </div>
                <div class="info">
                    <p><strong>流程标题：</strong>{instance.title}</p>
                    <p><strong>流程编号：</strong>{instance.instance_no}</p>
                    <p><strong>申请人：</strong>{applicant_name}</p>
                </div>
                <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
            </body>
            </html>
            """
            text_body = f"""
流程抄送通知

您好，{user.name}！您被抄送了一个流程。

流程标题：{instance.title}
流程编号：{instance.instance_no}
申请人：{applicant_name}

此邮件为系统自动发送，请勿直接回复。
            """
        elif notification_type == 'approved':
            subject = f'【已通过】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'
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
            subject = f'【已驳回】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'
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
        elif notification_type == 'return':
            subject = f'【已退回】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .header {{ background-color: #fff8e1; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                    .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h2>↩️ 流程审批退回</h2>
                    <p>您好，{user.name}！您的流程申请已被退回，请修改后重新提交。</p>
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
流程审批退回

您好，{user.name}！您的流程申请已被退回，请修改后重新提交。

流程标题：{instance.title}
流程编号：{instance.instance_no}

此邮件为系统自动发送，请勿直接回复。
            """
        elif notification_type == 'confirm':
            subject = f'【流程确认】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .header {{ background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                    .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h2>📋 流程确认通知</h2>
                    <p>您好，{user.name}！以下流程已被申请人确认。</p>
                </div>
                <div class="info">
                    <p><strong>流程标题：</strong>{instance.title}</p>
                    <p><strong>流程编号：</strong>{instance.instance_no}</p>
                    <p><strong>申请人：</strong>{applicant_name}</p>
                </div>
                <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
            </body>
            </html>
            """
            text_body = f"""
流程确认通知

您好，{user.name}！以下流程已被申请人确认。

流程标题：{instance.title}
流程编号：{instance.instance_no}
申请人：{applicant_name}

此邮件为系统自动发送，请勿直接回复。
            """
        else:
            subject = f'【流程通知】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'
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
                    <p><strong>当前状态：</strong>{get_workflow_status_display(instance.status)}</p>
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
当前状态：{get_workflow_status_display(instance.status)}

此邮件为系统自动发送，请勿直接回复。
            """

        # 计算默认抄送地址（从配置读取）
        cc_addr = _get_workflow_default_cc(recipient_email)

        # 创建自定义邮件消息类
        class WorkflowNotificationEmail:
            def __init__(self, recipient, subject, html_body, text_body, cc=''):
                self.recipient = recipient
                self.subject = subject
                self.html_body = html_body
                self.text_body = text_body
                self.cc = cc

            def get_email_content(self):
                return {
                    "recipient": self.recipient,
                    "subject": self.subject,
                    "Cc": self.cc,
                    "body_html": self.html_body,
                    "body_text": self.text_body
                }

        # 发送邮件
        email_manager = EmailManager()
        email_message = WorkflowNotificationEmail(
            recipient_email,
            subject,
            html_body,
            text_body,
            cc=cc_addr
        )
        logger.info(f'准备调用邮件服务发送：收件人={recipient_email}，抄送={cc_addr or "无"}，'
                    f'主题={subject}，流程={instance.instance_no}，类型={notification_type}')
        email_manager.send_email([email_message])

        logger.info(f'邮件通知发送成功：收件人={recipient_email}，抄送={cc_addr or "无"}，'
                    f'流程{instance.instance_no}，类型{notification_type}')

    except Exception as e:
        # 邮件发送失败不影响站内消息，只记录日志（记录完整堆栈便于排查）
        logger.warning(f'邮件通知发送失败（可能是邮件服务未配置）：收件人={getattr(user, "name", getattr(user, "id", "未知"))}，'
                       f'流程={getattr(instance, "instance_no", "未知")}，类型={notification_type}，错误：{str(e)}',
                       exc_info=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_workflow_notification(self, user_id, instance_id, notification_type, notify_email=True, notify_message=True):
    """
    发送流程通知（支持站内消息 + 邮件，按节点配置开关控制）
    :param self: Celery 任务实例
    :param user_id: 用户ID
    :param instance_id: 流程实例ID
    :param notification_type: 通知类型 (approve, cc, reject, return, confirm, approved 等)
    :param notify_email: 是否发送邮件通知（节点配置）
    :param notify_message: 是否发送站内信通知（节点配置）
    """
    try:
        from apps.lyworkflow.models import WorkflowInstance
        from mysystem.models import Users
        from apps.lymessages.models import MyMessage, MyMessageUser

        logger.info(f'开始处理通知任务：user_id={user_id}, instance_id={instance_id}, type={notification_type}, '
                    f'notify_email={notify_email}, notify_message={notify_message}')

        try:
            user = Users.objects.get(id=user_id)
        except Users.DoesNotExist:
            # 用户不存在属于无效数据，重试也不会成功，直接结束任务
            logger.error(f'通知任务终止：用户不存在 user_id={user_id}，不再重试')
            return

        try:
            instance = WorkflowInstance.objects.get(id=instance_id)
        except WorkflowInstance.DoesNotExist:
            # 流程实例不存在（可能已被删除），重试也不会成功，直接结束任务
            logger.error(f'通知任务终止：流程实例不存在 instance_id={instance_id}，不再重试')
            return

        # 站内信通知（返回该通知此前是否已存在：重复投递/重复入队的通知任务据此跳过重复邮件）
        inapp_existed = False
        if notify_message:
            inapp_existed = _send_workflow_inapp_message(user, instance, notification_type)
        else:
            logger.info(f'节点未开启站内信通知，跳过站内消息：用户{user.name}，流程{instance.instance_no}')

        # 邮件通知
        if notify_email:
            if inapp_existed:
                # 站内信已存在说明该通知任务此前已执行过（扫描任务重复投递/重复驱动导致的重复入队），
                # 邮件发送无去重机制，直接跳过可避免审批人收到重复邮件
                logger.info(f'该通知此前已发送（站内信已存在），跳过重复邮件：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
            else:
                _send_workflow_email_notification(user, instance, notification_type)
        else:
            logger.info(f'节点未开启邮件通知，跳过邮件发送：用户{user.name}，流程{instance.instance_no}')

        logger.info(f'发送流程通知完成：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
    except Exception as e:
        logger.error(f'发送流程通知失败：{str(e)}')
        # 重试机制
        raise self.retry(exc=e)


def _send_workflow_inapp_message(user, instance, notification_type):
    """创建站内消息通知（带去重逻辑）

    Returns:
        bool: 该通知此前是否已存在（True=已存在，本任务为重复执行；False=本次新建）
    """
    from apps.lymessages.models import MyMessage, MyMessageUser

    # 根据通知类型生成消息内容
    message_title = ''
    message_content = ''

    if notification_type == 'approve':
        message_title = f'待审批工作流通知 - {instance.title}'
        message_content = f'您有一个待审批的工作流：{instance.title}，流程编号：{instance.instance_no}，请及时处理'
    elif notification_type == 'cc':
        message_title = f'流程抄送通知 - {instance.title}'
        message_content = f'您被抄送了一个流程：{instance.title}，流程编号：{instance.instance_no}'
    elif notification_type == 'reject':
        message_title = f'流程驳回通知 - {instance.title}'
        message_content = f'您的流程申请已被驳回：{instance.title}，流程编号：{instance.instance_no}'
    elif notification_type == 'return':
        message_title = f'流程退回通知 - {instance.title}'
        message_content = f'您的流程申请已被退回：{instance.title}，流程编号：{instance.instance_no}'
    elif notification_type == 'confirm':
        message_title = f'流程确认通知 - {instance.title}'
        message_content = f'流程已被申请人确认：{instance.title}，流程编号：{instance.instance_no}'
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
        return True

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
            return True

    except Exception as db_error:
        # 如果发生唯一约束冲突，说明消息已存在
        logger.info(f'检测到唯一约束冲突，消息已存在：用户{user.name}，流程{instance.instance_no}，错误：{str(db_error)}')
        return True

    logger.info(f'站内消息创建成功：用户{user.name}，流程{instance.instance_no}，类型{notification_type}')
    return False


def _send_workflow_comment_email(user, instance, commenter_name, comment_content, step_name=''):
    """发送流程评论通知邮件

    Args:
        user: 收件用户（当前待审批节点的审批人）
        instance: 流程实例对象
        commenter_name: 评论人姓名
        comment_content: 评论内容
        step_name: 当前待审批节点名称（可能为空）
    """
    try:
        from utils.email import EmailManager

        # 获取收件邮箱：测试模式下统一发到测试邮箱，否则发给实际审批人
        recipient_email = _resolve_user_email(user)
        if not recipient_email:
            logger.warning(f'用户 {getattr(user, "name", user.id)} 无法获取邮箱，跳过评论邮件通知')
            return
        if getattr(config, 'MAIL_TEST_MODE', False) and recipient_email == getattr(config, 'MAIL_TEST_RECIPIENT', ''):
            logger.info(f'[测试模式] 准备发送评论邮件：实际审批人={user.name}，邮件统一发往测试邮箱={recipient_email}，'
                        f'流程={instance.instance_no}')
        else:
            logger.info(f'准备发送评论邮件：收件人={recipient_email}，流程={instance.instance_no}')

        view_url = get_workflow_view_url(instance.id)
        applicant_name = instance.applicant.name if getattr(instance, 'applicant', None) else '未知'

        # 每封邮件生成唯一邮件码，避免相同主题被邮件网关去重丢弃
        mail_code = uuid.uuid4().hex[:8]
        subject = f'【流程评论】{instance.title}（流程编号：{instance.instance_no}，邮件码：{mail_code}）'

        step_desc = f'（节点：{step_name}）' if step_name else ''
        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .header {{ background-color: #e8f5e9; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .info {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                .comment {{ background-color: #fff8e1; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                .button {{ display: inline-block; padding: 10px 20px; background-color: #2196f3; color: white; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>💬 流程评论通知</h2>
                <p>您好，{user.name}！{commenter_name} 在流程中发表了评论{step_desc}，请及时查看。</p>
            </div>
            <div class="info">
                <p><strong>流程标题：</strong>{instance.title}</p>
                <p><strong>流程编号：</strong>{instance.instance_no}</p>
                <p><strong>申请人：</strong>{applicant_name}</p>
            </div>
            <div class="comment">
                <p><strong>评论人：</strong>{commenter_name}</p>
                <p><strong>评论内容：</strong>{comment_content}</p>
            </div>
            <a href="{view_url}" class="button">查看流程</a>
            <p style="color: #666; margin-top: 20px; font-size: 12px;">此邮件为系统自动发送，请勿直接回复。</p>
        </body>
        </html>
        """
        text_body = f"""
流程评论通知

您好，{user.name}！{commenter_name} 在流程中发表了评论{step_desc}，请及时查看。

流程标题：{instance.title}
流程编号：{instance.instance_no}
申请人：{applicant_name}

评论人：{commenter_name}
评论内容：{comment_content}

请点击以下链接查看流程：{view_url}

此邮件为系统自动发送，请勿直接回复。
        """

        # 计算默认抄送地址（从配置读取）
        cc_addr = _get_workflow_default_cc(recipient_email)

        # 创建自定义邮件消息类（与审批通知邮件一致的发送协议）
        class WorkflowCommentEmail:
            def __init__(self, recipient, subject, html_body, text_body, cc=''):
                self.recipient = recipient
                self.subject = subject
                self.html_body = html_body
                self.text_body = text_body
                self.cc = cc

            def get_email_content(self):
                return {
                    "recipient": self.recipient,
                    "subject": self.subject,
                    "Cc": self.cc,
                    "body_html": self.html_body,
                    "body_text": self.text_body
                }

        email_manager = EmailManager()
        email_message = WorkflowCommentEmail(
            recipient_email,
            subject,
            html_body,
            text_body,
            cc=cc_addr
        )
        logger.info(f'准备调用邮件服务发送评论通知：收件人={recipient_email}，抄送={cc_addr or "无"}，'
                    f'主题={subject}，流程={instance.instance_no}')
        email_manager.send_email([email_message])

        logger.info(f'评论邮件通知发送成功：收件人={recipient_email}，流程={instance.instance_no}')

    except Exception as e:
        # 邮件发送失败不影响评论本身，只记录日志
        logger.warning(f'评论邮件通知发送失败：收件人={getattr(user, "name", getattr(user, "id", "未知"))}，'
                       f'流程={getattr(instance, "instance_no", "未知")}，错误：{str(e)}',
                       exc_info=True)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_workflow_comment_notification(self, user_id, instance_id, commenter_name, comment_content, step_name=''):
    """发送流程评论通知邮件

    :param self: Celery 任务实例
    :param user_id: 收件用户ID（当前待审批节点的审批人或流程发起人）
    :param instance_id: 流程实例ID
    :param commenter_name: 评论人姓名
    :param comment_content: 评论内容
    :param step_name: 当前待审批节点名称
    """
    try:
        from apps.lyworkflow.models import WorkflowInstance
        from mysystem.models import Users

        try:
            user = Users.objects.get(id=user_id)
        except Users.DoesNotExist:
            # 用户不存在属于无效数据，重试也不会成功，直接结束任务
            logger.error(f'评论通知任务终止：用户不存在 user_id={user_id}，不再重试')
            return

        try:
            instance = WorkflowInstance.objects.get(id=instance_id)
        except WorkflowInstance.DoesNotExist:
            # 流程实例不存在（可能已被删除），重试也不会成功，直接结束任务
            logger.error(f'评论通知任务终止：流程实例不存在 instance_id={instance_id}，不再重试')
            return

        _send_workflow_comment_email(user, instance, commenter_name, comment_content, step_name)
        logger.info(f'评论通知邮件发送完成：用户{user.name}，流程{instance.instance_no}')
    except Exception as e:
        logger.error(f'发送评论通知邮件失败：{str(e)}')
        # 重试机制
        raise self.retry(exc=e)
