import json
import logging
import os
import smtplib
import time
from abc import abstractmethod, ABC
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

import config

logger = logging.getLogger(__name__)


class EmailMessage(ABC):
    def __init__(self, recipient, Cc):
        self.recipient = recipient
        self.Cc = Cc
        self.subject = self._generate_subject()
        self.body_html = self._generate_body_html()
        self.body_text = self._generate_body_text()

    @abstractmethod
    def _generate_subject(self):
        pass

    @abstractmethod
    def _generate_body_html(self):
        pass

    @abstractmethod
    def _generate_body_text(self):
        pass

    def get_email_content(self):  # 1 个用法 (1 个动态) & sqa
        return {
            "recipient": self.recipient,
            "subject": self.subject,
            "Cc": self.Cc,
            "body_html": self.body_html,
            "body_text": self.body_text
        }

    @abstractmethod  # & sqa
    def set_Cc_email(self):
        pass

    @abstractmethod  # & sqa
    def set_RC_email(self):
        pass

class JSONParsingFailedMessage(EmailMessage):
    def __init__(self, owner, json_data, file_name=''):
        self.owner = owner
        self.json_data = json_data
        self.file_name = file_name
        super().__init__(self.owner, '')
        self.set_RC_email()
        self.set_Cc_email()

    def set_Cc_email(self):
        cc_names = ['xuxiaokui']  # recipient
        cc_addr = []
        for name in cc_names:
            cc_addr.append(name + '@phlexing.com')
        self.Cc = ''.join(cc_addr)
        return

    def set_RC_email(self):
        # 从 owner 获取用户账号，添加邮箱后缀
        if self.owner:
            self.recipient = self.owner + '@phlexing.com'
        else:
            self.recipient = 'xuxiaokui@phlexing.com'
        return

    def _generate_subject(self):
        if self.file_name:
            return f"JSON 数据解析失败 - {self.file_name}"
        return "JSON 数据解析失败，请确认数据格式是否正确!"

    def _generate_body_html(self):
        # JSON 已经解析失败，直接显示原始内容
        # 不再尝试解析，避免再次抛出异常
        html = f"""
        <html>
        <head>
        <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .header {{
            background-color: #ffcccc;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .warning {{
            color: red;
            font-weight: bold;
        }}
        .json-data {{
            background-color: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 12px;
            overflow-x: auto;
            max-height: 500px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .file-info {{
            background-color: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 10px 15px;
            margin-bottom: 15px;
            border-radius: 3px;
        }}
        </style>
        </head>
        <body>
        <div class="header">
            <h2 class="warning">⚠️ JSON 数据解析失败</h2>
            <p>请检查以下数据格式是否正确：</p>
        </div>
        
        {f'<div class="file-info"><strong>文件名：</strong>{self.file_name}</div>' if self.file_name else ''}
        
        <h3>原始数据</h3>
        <pre class="json-data">{self.json_data}</pre>
        
        <p style="color: #666; margin-top: 20px; font-size: 12px;">
            发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </p>
        </body>
        </html>
        """
        
        return html

    def _generate_body_text(self):
        # JSON 已经解析失败，直接返回原始内容
        file_info = f"文件名: {self.file_name}\n" if self.file_name else ""
        return f"""
JSON 数据解析失败

{file_info}
原始数据:
{self.json_data}

发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """


class EmailManager:
    def __init__(self):
        self.smtp_server = config.MAIL_SMTP_SERVER
        self.port = config.MAIL_PORT
        self.sender_email = config.MAIL_USER
        self.sender_password = config.MAIL_PASSWORD
        self.server = None
        self.max_retries = 3
        self.retry_delay = 5 # seconds

    def connect(self) -> None:
        """Establish SMTP connection with retry mechanism"""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                self.server = smtplib.SMTP(self.smtp_server, self.port)
                # Note: Removed starttls() since you're using port 25
                self.server.login(self.sender_email, self.sender_password)
                logging.info("Successfully connected to SMTP server")
                return
            except Exception as e:
                retry_count += 1
                if retry_count == self.max_retries:
                    raise Exception(f"Failed to connect after {self.max_retries} attempts: {str(e)}")
                logging.warning(f"Connection attempt {retry_count} failed, retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)

    def send_email(self, email_messages):
        """Send emails with proper connection handling and retries"""
        if not self.server:
            self.connect()

        for message in email_messages:
            content = message.get_email_content()
            mime_message = MIMEMultipart("alternative")
            mime_message["From"] = self.sender_email
            mime_message["Date"] = datetime.now().strftime("%d %b %Y %H:%M:%S")
            mime_message["To"] = content["recipient"]

            if content.get('Cc'):
                mime_message["Cc"] = content['Cc']

            mime_message["Subject"] = content['subject']

            body_part = "No message"
            if content.get('body_html'):
                body_part = MIMEText(content['body_html'], 'html')
            elif content.get('body_text'):
                body_part = MIMEText(content['body_text'], 'plain')
            else:
                body_part = MIMEText(body_part, 'plain')

            mime_message.attach(body_part)

            # 【新增】如果存在附件，则附加文件
            if content.get('attachment'):
                attachment_info = content['attachment']
                attachment_path = attachment_info.get('path')
                attachment_filename = attachment_info.get('filename', os.path.basename(attachment_path))
                
                if attachment_path and os.path.exists(attachment_path):
                    try:
                        with open(attachment_path, 'rb') as f:
                            attachment = MIMEBase('application', 'octet-stream')
                            attachment.set_payload(f.read())
                        encoders.encode_base64(attachment)
                        attachment.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{attachment_filename}"'
                        )
                        mime_message.attach(attachment)
                        logging.info(f"已附加 License 文件: {attachment_filename}")
                    except Exception as e:
                        logging.error(f"附加文件失败: {str(e)}, 文件路径: {attachment_path}")

            retry_count = 0
            while retry_count < self.max_retries:
                try:
                    self.server.send_message(mime_message)
                    logging.info(f"Email sent successfully to {content['recipient']}")
                    break
                except smtplib.SMTPServerDisconnected:
                    logging.warning("Server disconnected. Attempting to reconnect...")
                    self.connect()
                    retry_count += 1
                except Exception as e:
                    retry_count += 1
                    if retry_count == self.max_retries:
                        logging.error(f"Failed to send Email for {content['recipient']}, error is {str(e)}")
                        logging.info(mime_message)
                        break
                    logging.warning(f"Send attempt {retry_count} failed, retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)

    def __del__(self):
        """Cleanup SMTP connection"""
        if self.server:
            try:
                self.server.quit()
            except:
                pass

    def json_parsing_failed_send_email(self, owner, data, file_name=''):
        messages = []
        message = JSONParsingFailedMessage(owner, data, file_name)
        messages.append(message)
        self.send_email(messages)

    def license_expired_send_email(self, owner, application, end_time):
        """
        发送 License 结束时间过期提醒邮件
        
        Args:
            owner: 申请人账号
            application: LicenseApplication 实例
            end_time: License 结束时间
        """
        messages = []
        message = LicenseExpiredMessage(owner, application, end_time)
        messages.append(message)
        self.send_email(messages)

    def license_expiring_soon_send_email(self, owner, application, end_time, remaining_days, product_details=None):
        """
        发送 License 即将过期提醒邮件
        
        Args:
            owner: 申请人账号
            application: LicenseApplication 实例
            end_time: License 结束时间
            remaining_days: 剩余天数
            product_details: 产品详细信息列表（可选），用于产品组场景
        """
        messages = []
        message = LicenseExpiringSoonMessage(owner, application, end_time, remaining_days, product_details)
        messages.append(message)
        self.send_email(messages)

    def license_generated_send_email(self, owner, application, license_file_name, remote_dir=config.SSH_REMOTE_TEMPLATE_DIR, local_license_path=None):
        """
        发送 License 制作成功通知邮件
        
        Args:
            owner: 申请人账号
            application: LicenseApplication 实例
            license_file_name: License 文件名
            remote_dir: 远程存放目录
            local_license_path: 本地 License 文件路径（用于附件）
        """
        messages = []
        message = LicenseGeneratedMessage(owner, application, license_file_name, remote_dir, local_license_path)
        messages.append(message)
        self.send_email(messages)

    def license_failed_send_email(self, owner, application, error_message):
        """
        发送 License 制作失败通知邮件
        
        Args:
            owner: 申请人账号
            application: LicenseApplication 实例
            error_message: 失败原因
        """
        messages = []
        message = LicenseFailedMessage(owner, application, error_message)
        messages.append(message)
        self.send_email(messages)


class LicenseExpiredMessage(EmailMessage):
    def __init__(self, owner, application, end_time):
        self.owner = owner
        self.application = application
        self.end_time = end_time
        super().__init__(self.owner, '')
        self.set_RC_email()
        self.set_Cc_email()

    def set_Cc_email(self):
        cc_names = [config.MAIL_CC]  # recipient
        cc_addr = []
        for name in cc_names:
            cc_addr.append(name + '@phlexing.com')
        self.Cc = ', '.join(cc_addr)  # 使用逗号分隔多个邮箱
        return

    def set_RC_email(self):
        # owner 是单个申请人账号字符串（如 'ltjiadong'）
        recip_names = [self.owner] if isinstance(self.owner, str) else self.owner
        recip_addr = []
        for name in recip_names:
            recip_addr.append(name + '@phlexing.com')
        self.recipient = ', '.join(recip_addr)  # 使用逗号分隔多个邮箱
        return

    def _generate_subject(self):
        return f"License 结束时间过期提醒 - {self.application.product}"

    def _generate_body_html(self):
        html = f"""
        <html>
        <head>
        <style>
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        .expired-row {{
            background-color: #ffcccc;
        }}
        </style>
        </head>
        <body>
        <h2>License 结束时间过期提醒</h2>
        <table>
            <tr>
                <th>产品名称</th>
                <th>申请人</th>
                <th>客户名称</th>
                <th>序列号</th>
                <th>结束时间</th>
                <th>状态</th>
            </tr>
            <tbody>
                <tr class="expired-row">
                    <td>{self.application.product}</td>
                    <td>{self.application.applicant}</td>
                    <td>{self.application.customer_name}</td>
                    <td>{self.application.serial_number}</td>
                    <td>{self.end_time.strftime('%Y-%m-%d')}</td>
                    <td>已过期</td>
                </tr>
            </tbody>
        </table>
        <p style="color: red; margin-top: 20px;">请注意：该 License 已经结束，请及时处理！</p>
        </body>
        </html>
        """
        return html

    def _generate_body_text(self):
        return f"""
            License 结束时间过期提醒
            
            产品名称: {self.application.product}
            申请人: {self.application.applicant}
            客户名称: {self.application.customer_name}
            序列号: {self.application.serial_number}
            结束时间: {self.end_time.strftime('%Y-%m-%d')}
            状态: 已过期
            
            请注意：该 License 已经结束，请及时处理！
        """


class LicenseExpiringSoonMessage(EmailMessage):
    """License 即将过期提醒邮件"""
    
    def __init__(self, owner, application, end_time, remaining_days, product_details=None):
        self.owner = owner
        self.application = application
        self.end_time = end_time
        self.remaining_days = remaining_days
        self.product_details = product_details or []  # 产品详细信息列表（可选）
        super().__init__(self.owner, '')
        self.set_RC_email()
        self.set_Cc_email()

    def set_Cc_email(self):
        cc_names = [config.MAIL_CC]  # recipient
        cc_addr = []
        for name in cc_names:
            cc_addr.append(name + '@phlexing.com')
        self.Cc = ', '.join(cc_addr)  # 使用逗号分隔多个邮箱
        return

    def set_RC_email(self):
        # owner 是单个申请人账号字符串（如 'ltjiadong'）
        recip_names = [self.owner] if isinstance(self.owner, str) else self.owner
        recip_addr = []
        for name in recip_names:
            recip_addr.append(name + '@phlexing.com')
        self.recipient = ', '.join(recip_addr)  # 使用逗号分隔多个邮箱
        return

    def _generate_subject(self):
        return f"License 即将过期提醒 - {self.application.customer_name} - {self.application.product}"

    def _generate_body_html(self):
        # 如果有产品详细信息（产品组场景），生成产品列表
        if self.product_details and len(self.product_details) > 0:
            # 产品组场景：显示每个产品的剩余天数
            product_rows = ''
            for idx, product in enumerate(self.product_details):
                product_name = product.get('name', '')
                product_remaining_days = product.get('remaining_days', 0)
                
                # 根据剩余天数设置不同的样式
                if product_remaining_days <= 7:
                    row_style = 'background-color: #f8d7da;'
                elif product_remaining_days <= 15:
                    row_style = 'background-color: #fff3cd;'
                else:
                    row_style = 'background-color: #d4edda;'
                
                product_rows += f"""
                <tr style="{row_style}">
                    <td>{product_name}</td>
                    <td>{self.application.applicant}</td>
                    <td>{self.application.customer_name}</td>
                    <td>{self.application.serial_number}</td>
                    <td>-</td>
                    <td><strong>{product_remaining_days}天</strong></td>
                </tr>
                """
            
            html = f"""
            <html>
            <head>
            <style>
            table {{
                border-collapse: collapse;
                width: 100%;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
            }}
            </style>
            </head>
            <body>
            <h2>License 即将过期提醒（产品组）</h2>
            <p>以下产品的 License 将在 {product_remaining_days} 天后过期：</p>
            <table>
                <tr>
                    <th>产品名称</th>
                    <th>申请人</th>
                    <th>客户名称</th>
                    <th>序列号</th>
                    <th>结束时间</th>
                    <th>剩余天数</th>
                </tr>
                <tbody>
                    {product_rows}
                </tbody>
            </table>
            <p style="color: orange; margin-top: 20px;">请注意：请及时续费或重新申请这些产品，如已申请，请忽略该邮件！</p>
            </body>
            </html>
            """
        else:
            # 单产品场景：原有逻辑
            html = f"""
            <html>
            <head>
            <style>
            table {{
                border-collapse: collapse;
                width: 100%;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            th {{
                background-color: #f2f2f2;
            }}
            .warning-row {{
                background-color: #fff3cd;
            }}
            </style>
            </head>
            <body>
            <h2>License 即将过期提醒</h2>
            <table>
                <tr>
                    <th>产品名称</th>
                    <th>申请人</th>
                    <th>客户名称</th>
                    <th>序列号</th>
                    <th>结束时间</th>
                    <th>剩余天数</th>
                </tr>
                <tbody>
                    <tr class="warning-row">
                        <td>{self.application.product}</td>
                        <td>{self.application.applicant}</td>
                        <td>{self.application.customer_name}</td>
                        <td>{self.application.serial_number}</td>
                        <td>{self.end_time.strftime('%Y-%m-%d')}</td>
                        <td>{self.remaining_days}天</td>
                    </tr>
                </tbody>
            </table>
            <p style="color: orange; margin-top: 20px;">请注意：该 License 将在 {self.remaining_days} 天后过期，请及时续费或重新申请，如已申请，请忽略该邮件！</p>
            </body>
            </html>
            """
        return html

    def _generate_body_text(self):
        return f"""
            License 即将过期提醒
            
            产品名称: {self.application.product}
            申请人: {self.application.applicant}
            客户名称: {self.application.customer_name}
            序列号: {self.application.serial_number}
            结束时间: {self.end_time.strftime('%Y-%m-%d')}
            剩余天数: {self.remaining_days}天
            
            请注意：该 License 将在 {self.remaining_days} 天后过期，请及时续费或重新申请，如已申请，请忽略该邮件！
        """


class LicenseGeneratedMessage(EmailMessage):
    """License 制作成功通知邮件"""
    
    def __init__(self, owner, application, license_file_name, remote_dir=config.SSH_REMOTE_TEMPLATE_DIR, local_license_path=None):
        self.owner = owner
        self.application = application
        self.license_file_name = license_file_name
        self.remote_dir = remote_dir
        self.local_license_path = local_license_path  # 本地 License 文件路径（用于附件）
        super().__init__(self.owner, '')
        self.set_RC_email()
        self.set_Cc_email()

    def set_Cc_email(self):
        cc_names = [config.MAIL_CC]  # recipient
        cc_addr = []
        for name in cc_names:
            cc_addr.append(name + '@phlexing.com')
        self.Cc = ', '.join(cc_addr)  # 使用逗号分隔多个邮箱
        return

    def set_RC_email(self):
        # owner 是单个申请人账号字符串（如 'ltjiadong'）
        recip_names = [self.owner] if isinstance(self.owner, str) else self.owner
        recip_addr = []
        for name in recip_names:
            recip_addr.append(name + '@phlexing.com')
        self.recipient = ', '.join(recip_addr)  # 使用逗号分隔多个邮箱
        return

    def get_email_content(self):
        """重写以支持附件"""
        content = super().get_email_content()
        # 添加附件信息（如果存在本地文件路径）
        if self.local_license_path and os.path.exists(self.local_license_path):
            content['attachment'] = {
                'path': self.local_license_path,
                'filename': self.license_file_name
            }
        return content

    def _generate_subject(self):
        return f"License 制作成功通知 - {self.application.customer_name} - {self.application.product}"

    def _generate_body_html(self):
        # 构建文件路径
        file_path = f"{self.remote_dir}/{self.license_file_name}"

        # 判断是否有 user_info_list（产品组情况）
        has_user_info_list = hasattr(self.application, 'user_info_list') and self.application.user_info_list
        
        # 调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[邮件生成] application.id={self.application.id}")
        logger.info(f"[邮件生成] has_user_info_list={has_user_info_list}")
        if has_user_info_list:
            logger.info(f"[邮件生成] user_info_list={self.application.user_info_list}")
        else:
            logger.warning(f"[邮件生成] user_info_list 为空或不存在")
        
        if has_user_info_list:
            # 产品组：直接从 user_info_list 中获取每个产品的完整信息
            products_html = ''
            for idx, item in enumerate(self.application.user_info_list, 1):
                product_name = item.get('Product', '')
                start_timestamp = item.get('Startdate', 0)
                end_timestamp = item.get('Expirydate', 0)
                
                # 转换时间戳为日期字符串
                from datetime import datetime
                start_date_str = 'N/A'
                end_date_str = 'N/A'
                
                if start_timestamp and isinstance(start_timestamp, (int, float)):
                    try:
                        start_date_str = datetime.fromtimestamp(start_timestamp / 1000).strftime('%Y-%m-%d')
                    except:
                        pass
                
                if end_timestamp and isinstance(end_timestamp, (int, float)):
                    try:
                        end_date_str = datetime.fromtimestamp(end_timestamp / 1000).strftime('%Y-%m-%d')
                    except:
                        pass
                
                # 获取该产品的授权数量（从 user_info_list 中直接获取）
                quantity_items = ''
                # 使用产品名称作为 key 获取授权数量
                if product_name in item:
                    prod_features = item[product_name]
                    if isinstance(prod_features, dict):
                        for feat, qty in prod_features.items():
                            quantity_str = str(qty) if qty else ''
                            quantity_items += f"<li style='margin-left: 20px;'>{feat} (授权数量: {quantity_str})</li>"
                
                products_html += f"""
                <div class="info-section" style="margin-bottom: 15px;">
                    <h3>📦 产品 {idx}: {product_name}</h3>
                    <div class="info-grid">
                        <div class="info-label">生效时间：</div>
                        <div class="info-value">{start_date_str}</div>
                        
                        <div class="info-label">过期时间：</div>
                        <div class="info-value">{end_date_str}</div>
                    </div>
                    {f'<ul class="feature-list" style="margin-top: 10px;">{quantity_items}</ul>' if quantity_items else '<p style="color: #666; margin-top: 10px;">无授权特性</p>'}
                </div>
                """
        else:
            # 单个产品：使用原有的逻辑
            products_html = f"""
            <div class="info-section">
                <h3>📦 产品信息</h3>
                <div class="info-grid">
                    <div class="info-label">产品名称：</div>
                    <div class="info-value">{self.application.product}</div>
                    
                    <div class="info-label">生效时间：</div>
                    <div class="info-value">{self.application.start_time.strftime('%Y-%m-%d') if self.application.start_time else 'N/A'}</div>
                    
                    <div class="info-label">过期时间：</div>
                    <div class="info-value">{self.application.end_time.strftime('%Y-%m-%d') if self.application.end_time else 'N/A'}</div>
                </div>
            </div>
            """

        html = f"""
        <html>
        <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #e8f5e9;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                border-left: 4px solid #4caf50;
            }}
            .header h2 {{
                color: #2e7d32;
                margin: 0 0 10px 0;
            }}
            .success-icon {{
                font-size: 48px;
                margin-bottom: 10px;
            }}
            .info-section {{
                background-color: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 15px;
            }}
            .info-section h3 {{
                color: #1976d2;
                margin-top: 0;
                margin-bottom: 10px;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: 120px 1fr;
                gap: 8px;
                align-items: baseline;
            }}
            .info-label {{
                font-weight: bold;
                color: #666;
            }}
            .info-value {{
                color: #333;
            }}
            .file-path {{
                background-color: #e3f2fd;
                padding: 12px;
                border-radius: 5px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                word-break: break-all;
                border-left: 3px solid #2196f3;
                margin: 10px 0;
            }}
            .feature-list {{
                margin: 10px 0;
                padding-left: 20px;
            }}
            .feature-list li {{
                margin-bottom: 5px;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 15px;
                border-top: 1px solid #ddd;
                color: #666;
                font-size: 12px;
            }}
        </style>
        </head>
        <body>
            <div class="header">
                <div class="success-icon">✓</div>
                <h2>License 文件制作成功</h2>
                <p>您的 License 文件已成功生成，请及时下载并使用。</p>
            </div>
            
            <div class="info-section">
                <h3>📋 基本信息</h3>
                <div class="info-grid">
                    <div class="info-label">客户名称：</div>
                    <div class="info-value">{self.application.customer_name}</div>
                    
                    <div class="info-label">序列号：</div>
                    <div class="info-value">{self.application.serial_number}</div>
                </div>
            </div>
            
            {products_html}
            
            <div class="info-section">
                <h3>📂 文件存放位置</h3>
                <p style="margin-bottom: 5px;">License 文件已存放在以下目录：</p>
                <div class="file-path">{file_path}</div>
                <p style="color: #666; font-size: 13px; margin-top: 10px;">
                    💡 提示：该文件路径方便追溯附件的原始文件 <strong>{self.license_file_name}</strong> 的真实存放位置,邮件接收者请忽略!
                </p>
            </div>
            
            <div class="info-section">
                <h3>📝 申请信息</h3>
                <div class="info-grid">
                    <div class="info-label">申请人：</div>
                    <div class="info-value">{self.application.applicant}</div>
                    
                    <div class="info-label">申请类型：</div>
                    <div class="info-value">{self.get_application_type_display()}</div>
                    
                    <div class="info-label">MAC 地址：</div>
                    <div class="info-value">{self.application.mac_address}</div>
                    
                    <div class="info-label">主机名：</div>
                    <div class="info-value">{self.application.hostname}</div>
                </div>
            </div>
            
            <div class="footer">
                <p>此邮件为系统自动发送，请勿直接回复。</p>
                <p>发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>如有问题，请联系系统管理员。</p>
            </div>
        </body>
        </html>
        """
        return html

    def _generate_body_text(self):
        # 构建文件路径
        file_path = f"{self.remote_dir}/{self.license_file_name}"
        
        # 判断是否有 user_info_list（产品组情况）
        has_user_info_list = hasattr(self.application, 'user_info_list') and self.application.user_info_list
        
        if has_user_info_list:
            # 产品组：直接从 user_info_list 中获取每个产品的完整信息
            products_text = ''
            for idx, item in enumerate(self.application.user_info_list, 1):
                product_name = item.get('Product', '')
                start_timestamp = item.get('Startdate', 0)
                end_timestamp = item.get('Expirydate', 0)
                
                # 转换时间戳为日期字符串
                from datetime import datetime
                start_date_str = 'N/A'
                end_date_str = 'N/A'
                
                if start_timestamp and isinstance(start_timestamp, (int, float)):
                    try:
                        start_date_str = datetime.fromtimestamp(start_timestamp / 1000).strftime('%Y-%m-%d')
                    except:
                        pass
                
                if end_timestamp and isinstance(end_timestamp, (int, float)):
                    try:
                        end_date_str = datetime.fromtimestamp(end_timestamp / 1000).strftime('%Y-%m-%d')
                    except:
                        pass
                
                # 获取该产品的授权数量（从 user_info_list 中直接获取）
                quantity_items = ''
                # 使用产品名称作为 key 获取授权数量
                if product_name in item:
                    prod_features = item[product_name]
                    if isinstance(prod_features, dict):
                        for feat, qty in prod_features.items():
                            quantity_str = str(qty) if qty else ''
                            quantity_items += f"    - {feat} (授权数量: {quantity_str})\n"
                
                products_text += f"""
                【产品 {idx}: {product_name}】
                生效时间: {start_date_str}
                过期时间: {end_date_str}
                {quantity_items}"""
        else:
            # 单个产品：使用原有的逻辑
            start_time_str = self.application.start_time.strftime('%Y-%m-%d') if self.application.start_time else 'N/A'
            end_time_str = self.application.end_time.strftime('%Y-%m-%d') if self.application.end_time else 'N/A'
            
            # 构建特性列表
            feature_list = ''
            if self.application.feature and isinstance(self.application.feature, list):
                for feat in self.application.feature:
                    quantity = ''
                    if self.application.quantity and isinstance(self.application.quantity, dict):
                        # 先尝试直接从 quantity 中查找（扁平结构）
                        quantity = self.application.quantity.get(feat, '')
                        # 如果没找到，尝试在嵌套结构中查找（产品组的情况）
                        if not quantity:
                            for product_key, product_quantity in self.application.quantity.items():
                                if isinstance(product_quantity, dict):
                                    quantity = product_quantity.get(feat, '')
                                    if quantity:
                                        break
                        quantity = str(quantity) if quantity else ''
                    feature_list += f"  - {feat} (授权数量: {quantity})\n"
            
            products_text = f"""
  【产品信息】
  产品名称: {self.application.product}
  生效时间: {start_time_str}
  过期时间: {end_time_str}
{feature_list}"""
        
        text = f"""
                License 文件制作成功
                
                【基本信息】
                客户名称: {self.application.customer_name}
                序列号: {self.application.serial_number}
                {products_text}
                
                【文件存放位置】
                License 文件已存放在以下目录：
                {file_path}
                
                提示：该文件路径方便追溯附件的原始文件 {self.license_file_name} 的真实存放位置，邮件接收者请忽略!
                
                【申请信息】
                申请人: {self.application.applicant}
                申请类型: {self.get_application_type_display()}
                MAC 地址: {self.application.mac_address}
                主机名: {self.application.hostname}
                
                此邮件为系统自动发送，请勿直接回复。
                发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                如有问题，请联系系统管理员。
            """
        return text

    def get_application_type_display(self):
        """获取申请类型的显示名称"""
        type_map = {
            'flexnet': 'FlexNet',
            'bitanswer': 'BitAnswer',
        }
        return type_map.get(self.application.application_type, self.application.application_type)


class LicenseFailedMessage(EmailMessage):
    """License 制作失败通知邮件"""
    
    def __init__(self, owner, application, error_message):
        self.owner = owner
        self.application = application
        self.error_message = error_message
        super().__init__(self.owner, '')
        self.set_RC_email()
        self.set_Cc_email()

    def set_Cc_email(self):
        cc_names = [config.MAIL_CC]  # recipient
        cc_addr = []
        for name in cc_names:
            cc_addr.append(name + '@phlexing.com')
        self.Cc = ', '.join(cc_addr)  # 使用逗号分隔多个邮箱
        return

    def set_RC_email(self):
        # owner 是单个申请人账号字符串（如 'ltjiadong'）
        recip_names = [self.owner] if isinstance(self.owner, str) else self.owner
        recip_addr = []
        for name in recip_names:
            recip_addr.append(name + '@phlexing.com')
        self.recipient = ', '.join(recip_addr)  # 使用逗号分隔多个邮箱
        return

    def _generate_subject(self):
        return f"License 制作失败通知 - {self.application.customer_name} - {self.application.product}"

    def _generate_body_html(self):
        # 获取时间信息
        start_time_str = self.application.start_time.strftime('%Y-%m-%d') if self.application.start_time else 'N/A'
        end_time_str = self.application.end_time.strftime('%Y-%m-%d') if self.application.end_time else 'N/A'
        
        html = f"""
        <html>
        <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }}
            .header {{
                background-color: #ffebee;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                border-left: 4px solid #f44336;
            }}
            .header h2 {{
                color: #c62828;
                margin: 0 0 10px 0;
            }}
            .error-icon {{
                font-size: 48px;
                margin-bottom: 10px;
            }}
            .info-section {{
                background-color: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 15px;
            }}
            .info-section h3 {{
                color: #1976d2;
                margin-top: 0;
                margin-bottom: 10px;
            }}
            .info-grid {{
                display: grid;
                grid-template-columns: 120px 1fr;
                gap: 8px;
                align-items: baseline;
            }}
            .info-label {{
                font-weight: bold;
                color: #666;
            }}
            .info-value {{
                color: #333;
            }}
            .error-message {{
                background-color: #fff3e0;
                padding: 15px;
                border-radius: 5px;
                border-left: 3px solid #ff9800;
                margin: 10px 0;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                color: #e65100;
            }}
            .footer {{
                margin-top: 30px;
                padding-top: 15px;
                border-top: 1px solid #ddd;
                color: #666;
                font-size: 12px;
            }}
        </style>
        </head>
        <body>
            <div class="header">
                <div class="error-icon">✗</div>
                <h2>License 文件制作失败</h2>
                <p>很抱歉，您的 License 文件制作未能成功完成。</p>
            </div>
            
            <div class="info-section">
                <h3>📦 申请信息</h3>
                <div class="info-grid">
                    <div class="info-label">产品名称：</div>
                    <div class="info-value">{self.application.product}</div>
                    
                    <div class="info-label">客户名称：</div>
                    <div class="info-value">{self.application.customer_name}</div>
                    
                    <div class="info-label">序列号：</div>
                    <div class="info-value">{self.application.serial_number}</div>
                    
                    <div class="info-label">生效时间：</div>
                    <div class="info-value">{start_time_str}</div>
                    
                    <div class="info-label">过期时间：</div>
                    <div class="info-value">{end_time_str}</div>
                </div>
            </div>
            
            <div class="info-section">
                <h3>⚠️ 失败原因</h3>
                <div class="error-message">{self.error_message}</div>
            </div>
            
            <div class="info-section">
                <h3>📝 建议</h3>
                <ul>
                    <li>请检查申请信息是否完整、准确</li>
                    <li>如问题持续存在，请联系系统管理员</li>
                    <li>您可以尝试重新提交申请</li>
                </ul>
            </div>
            
            <div class="footer">
                <p>此邮件为系统自动发送，请勿直接回复。</p>
                <p>发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>如有问题，请联系系统管理员。</p>
            </div>
        </body>
        </html>
        """
        return html

    def _generate_body_text(self):
        # 获取时间信息
        start_time_str = self.application.start_time.strftime('%Y-%m-%d') if self.application.start_time else 'N/A'
        end_time_str = self.application.end_time.strftime('%Y-%m-%d') if self.application.end_time else 'N/A'
        
        text = f"""
        License 文件制作失败
        
        【申请信息】
        产品名称：{self.application.product}
        客户名称：{self.application.customer_name}
        序列号：{self.application.serial_number}
        生效时间：{start_time_str}
        过期时间：{end_time_str}
        
        【失败原因】
        {self.error_message}
        
        【建议】
        - 请检查申请信息是否完整、准确
        - 如问题持续存在，请联系系统管理员
        - 您可以尝试重新提交申请
        
        此邮件为系统自动发送，请勿直接回复。
        发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        如有问题，请联系系统管理员。
        """
        return text