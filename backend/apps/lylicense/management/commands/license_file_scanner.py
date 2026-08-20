"""
License文件扫描命令行工具
扫描指定目录下的所有.lic文件，解析并发送过期提醒邮件
"""
import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


class LicenseFileScanner:
    """License文件扫描器"""

    def __init__(self, scan_directory: str = None, days_threshold: int = None):
        self.scan_directory = scan_directory or getattr(settings, 'LICENSE_SCAN_DIRECTORY', None)
        if not self.scan_directory:
            raise ValueError("未配置 LICENSE_SCAN_DIRECTORY")

        # 优先使用传入参数，否则从配置读取
        if days_threshold is not None:
            self.days_threshold = days_threshold
        else:
            self.days_threshold = getattr(settings, 'LICENSE_EXPIRY_THRESHOLD_DAYS', 30)

        logger.info(f"License扫描器初始化: 目录={self.scan_directory}, 阈值={self.days_threshold}天")

    def parse_license_file(self, file_path: str) -> List[Dict]:
        """解析单个LIC文件，提取所有授权行"""
        licenses = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                line = lines[i].strip()

                if line.startswith('INCREMENT') or line.startswith('FEATURE'):
                    lic_info = self._parse_license_line(lines, i)
                    if lic_info.get('is_valid'):
                        lic_info['file_path'] = file_path
                        lic_info['file_name'] = os.path.basename(file_path)
                        licenses.append(lic_info)

                    # 跳过续行
                    while i < len(lines) and lines[i].rstrip('\n\r').endswith('\\'):
                        i += 1

                i += 1

        except Exception as e:
            logger.error(f"读取文件 {file_path} 失败: {str(e)}")

        return licenses

    def _parse_license_line(self, lines: List[str], start_idx: int) -> Dict:
        """解析单行授权"""
        line_type = 'INCREMENT' if lines[start_idx].strip().startswith('INCREMENT') else 'FEATURE'

        # 合并续行
        content = lines[start_idx].rstrip('\\\n\r').strip()
        idx = start_idx
        while idx < len(lines) and lines[idx].rstrip('\n\r').endswith('\\'):
            idx += 1
            if idx < len(lines):
                content += ' ' + lines[idx].strip()

        # 正则匹配
        if line_type == 'FEATURE':
            pattern = r'^FEATURE\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*?)(?:\s+(?:SIGN=|$))'
        else:
            pattern = r'^INCREMENT\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*?)(?:\s+SIGN=|$)'

        match = re.match(pattern, content, re.DOTALL)

        if match:
            rest_params = match.group(6)
            return {
                'feature': match.group(1),
                'vendor': match.group(2),
                'version': match.group(3),
                'expiration_date': match.group(4),
                'license_count': match.group(5),
                'hostid': re.search(r'HOSTID=([^\s]+)', rest_params).group(1) if re.search(r'HOSTID=([^\s]+)', rest_params) else None,
                'start_date': re.search(r'START=\s*(\S+)', rest_params).group(1) if re.search(r'START=\s*(\S+)', rest_params) else None,
                'issuer': re.search(r'ISSUER="([^"]*)"', rest_params).group(1) if re.search(r'ISSUER="([^"]*)"', rest_params) else None,
                'line_type': line_type,
                'is_valid': True
            }

        return {'is_valid': False}

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串"""
        month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

        if not date_str:
            return None

        try:
            parts = date_str.lower().split('-')
            if len(parts) == 3:
                return datetime(int(parts[2]), month_map.get(parts[1], 1), int(parts[0]))
            return datetime.strptime(date_str, '%d-%b-%Y')
        except Exception:
            return None

    def scan(self) -> List[Dict]:
        """扫描所有LIC文件，返回即将过期的文件列表（不包含已过期）"""
        if not os.path.exists(self.scan_directory):
            logger.error(f"扫描目录不存在: {self.scan_directory}")
            return []

        # 查找所有LIC文件
        lic_files = []
        for root, _, files in os.walk(self.scan_directory):
            for file in files:
                if file.lower().endswith('.lic'):
                    lic_files.append(os.path.join(root, file))

        if not lic_files:
            logger.warning(f"未找到任何LIC文件: {self.scan_directory}")
            return []

        logger.info(f"找到 {len(lic_files)} 个LIC文件")

        warning_files = []   # 即将过期的文件列表
        now = datetime.now()

        for file_path in lic_files:
            licenses = self.parse_license_file(file_path)
            if not licenses:
                continue

            # 检查文件中是否有即将过期的授权（已过期的跳过）
            file_warning = []

            for lic in licenses:
                exp_date = self._parse_date(lic['expiration_date'])
                if exp_date:
                    days_remaining = (exp_date - now).days
                    # 只保留即将过期的（0 < days_remaining <= threshold），已过期的跳过
                    if 0 < days_remaining <= self.days_threshold:
                        file_warning.append({
                            'feature': lic.get('feature', 'N/A'),
                            'vendor': lic.get('vendor', 'N/A'),
                            'version': lic.get('version', 'N/A'),
                            'expiration_date': lic.get('expiration_date', 'N/A'),
                            'hostid': lic.get('hostid', 'N/A'),
                            'days_remaining': days_remaining
                        })

            # 如果有即将过期的授权，记录文件信息
            if file_warning:
                # 按剩余天数排序
                file_warning.sort(key=lambda x: x['days_remaining'])

                warning_files.append({
                    'file_path': file_path,
                    'file_name': os.path.basename(file_path),
                    'licenses': file_warning,
                    'count': len(file_warning),
                    # 取最小的剩余天数作为文件的整体剩余天数
                    'min_days': file_warning[0]['days_remaining'] if file_warning else 999
                })

        # 按最小剩余天数排序
        warning_files.sort(key=lambda x: x['min_days'])

        logger.info(f"扫描完成: 即将到期文件 {len(warning_files)} 个")
        return warning_files


class LicenseFileEmailSender:
    """License文件邮件发送器"""

    def __init__(self):
        from utils.email import EmailManager
        self.email_manager = EmailManager()

        # 收件人配置
        self.recipients = getattr(settings, 'LICENSE_EMAIL_RECIPIENTS', [])
        self.email_domain = getattr(settings, 'EMAIL_DOMAIN', '@phlexing.com')

        # 从配置文件读取抄送人，支持逗号分隔的多个邮箱
        self.cc = getattr(settings, 'LICENSE_DEFAULT_EXPIRED_CC', '')
        self.enabled = getattr(settings, 'LICENSE_AUTO_SEND_EMAIL', True)
        
        # 文档匹配收件人配置
        self.document_matching_recipients = getattr(settings, 'DOCUMENT_MATCHING_RECIPIENTS', {})

    def get_cc_list(self) -> List[str]:
        """获取抄送人列表"""
        if not self.cc:
            return []

        # 支持逗号、分号、空格分隔
        cc_list = re.split(r'[,;，；\s]+', self.cc)
        # 过滤空字符串
        cc_list = [c.strip() for c in cc_list if c.strip()]

        # 添加邮箱后缀（如果没有@符号）
        result = []
        for cc in cc_list:
            if '@' in cc:
                result.append(cc)
            else:
                result.append(cc + self.email_domain)

        return result

    def match_recipient_by_filename(self, file_name: str) -> Optional[str]:
        """
        根据文件名匹配收件人
        
        Args:
            file_name: 文件名（不含路径）
            
        Returns:
            匹配的收件人用户名，如果未匹配则返回None
        """
        if not self.document_matching_recipients:
            return None
        
        # 将文件名转为小写进行匹配
        file_name_lower = file_name.lower()
        
        # 遍历配置项，检查文件名是否包含关键字
        for recipient_username, keywords_str in self.document_matching_recipients.items():
            # 解析关键字列表（支持逗号分隔）
            keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
            
            # 检查文件名是否包含任意一个关键字
            for keyword in keywords:
                if keyword in file_name_lower:
                    logger.info(f"文件名 '{file_name}' 匹配关键字 '{keyword}'，收件人: {recipient_username}")
                    return recipient_username
        
        return None

    def get_recipients(self) -> List[str]:
        """获取收件人列表"""
        if not self.recipients:
            default = getattr(settings, 'LICENSE_DEFAULT_RECIPIENT', '')
            return [default + self.email_domain]

        result = []
        for r in self.recipients:
            if isinstance(r, dict):
                email = r.get('email', '')
                if email:
                    result.append(email)
            elif '@' in r:
                result.append(r)
            else:
                result.append(r + self.email_domain)
        return result

    def send_notifications(self, warning_files: List[Dict], dry_run: bool = False) -> Dict:
        """发送邮件通知"""
        result = {'sent': 0, 'failed': 0, 'errors': [], 'matched_files': 0, 'default_files': 0}

        if not self.enabled:
            logger.info("邮件发送已禁用")
            return result

        if not warning_files:
            logger.info("没有即将过期的文件需要提醒")
            return result

        # 按收件人分组
        recipient_groups = {}
        cc_list = self.get_cc_list()
        
        for file_info in warning_files:
            file_name = file_info['file_name']
            
            # 尝试根据文件名匹配收件人
            matched_recipient = self.match_recipient_by_filename(file_name)
            
            if matched_recipient:
                # 使用匹配的收件人
                result['matched_files'] += 1
                # 构建完整的邮箱地址
                if '@' in matched_recipient:
                    recipient_email = matched_recipient
                else:
                    recipient_email = matched_recipient + self.email_domain
                recipients_key = (recipient_email,)
            else:
                # 使用默认收件人
                result['default_files'] += 1
                default_recipients = self.get_recipients()
                recipients_key = tuple(sorted(default_recipients))
            
            # 将文件添加到对应收件人的组中
            if recipients_key not in recipient_groups:
                recipient_groups[recipients_key] = {
                    'recipients': list(recipients_key),
                    'files': []
                }
            recipient_groups[recipients_key]['files'].append(file_info)
        
        if cc_list:
            logger.info(f"抄送人: {', '.join(cc_list)}")
        
        logger.info(f"收件人分组统计: 匹配到特定收件人 {result['matched_files']} 个文件, 使用默认收件人 {result['default_files']} 个文件")
        logger.info(f"共 {len(recipient_groups)} 个不同的收件人组")

        # 向每个收件人组发送邮件
        for recipients_key, group_data in recipient_groups.items():
            recipients = group_data['recipients']
            files = group_data['files']
            
            for recipient in recipients:
                try:
                    if dry_run:
                        logger.info(f"[DRY RUN] 发送邮件给 {recipient} (包含 {len(files)} 个文件)")
                        result['sent'] += 1
                        continue

                    # 构建邮件内容
                    subject, html_body, text_body = self._build_email_content(files)

                    # 发送邮件
                    self._send_email(recipient, cc_list, subject, html_body, text_body)
                    result['sent'] += 1
                    logger.info(f"邮件发送成功: {recipient} (包含 {len(files)} 个文件)")

                except Exception as e:
                    result['failed'] += 1
                    result['errors'].append(f"{recipient}: {str(e)}")
                    logger.error(f"发送邮件给 {recipient} 失败: {str(e)}")

        return result

    def _build_email_content(self, warning_files: List[Dict]) -> Tuple[str, str, str]:
        """构建邮件内容"""
        # 统计信息
        total_files = len(warning_files)
        total_licenses = sum(f['count'] for f in warning_files)

        # 主题
        subject = f"License 到期提醒 - {total_files} 个文件, {total_licenses} 个授权即将到期"

        # HTML正文
        html_body = self._build_html(warning_files, total_files, total_licenses)

        # 纯文本正文
        text_body = self._build_text(warning_files, total_files, total_licenses)

        return subject, html_body, text_body

    def _build_html(self, warning_files: List[Dict], total_files: int, total_licenses: int) -> str:
        """构建HTML邮件内容（使用折叠展开）"""
        # 生成每个文件的折叠面板
        file_panels = ''
        for idx, f in enumerate(warning_files, 1):
            # 文件状态标识
            if f['min_days'] <= 7:
                status_icon = '🔴'
                status_color = '#f44336'
            elif f['min_days'] <= 15:
                status_icon = '🟡'
                status_color = '#ff9800'
            else:
                status_icon = '🟢'
                status_color = '#4caf50'

            # 生成该文件下的所有feature列表
            feature_rows = ''
            for lic in f['licenses']:
                feature_rows += f"""
                <tr>
                    <td style="padding: 4px 8px; border-bottom: 1px solid #eee;">{lic['feature']}</td>
                    <td style="padding: 4px 8px; border-bottom: 1px solid #eee;">{lic.get('version', 'N/A')}</td>
                    <td style="padding: 4px 8px; border-bottom: 1px solid #eee;">{lic['expiration_date']}</td>
                    <td style="padding: 4px 8px; border-bottom: 1px solid #eee; text-align: center;">{lic['days_remaining']}天</td>
                </tr>
                """

            # 使用 details/summary 实现折叠展开
            file_panels += f"""
            <details style="margin-bottom: 10px; border: 1px solid #ddd; border-radius: 5px; overflow: hidden;">
                <summary style="padding: 10px 15px; background-color: #f8f9fa; cursor: pointer; display: flex; align-items: center; justify-content: space-between; user-select: none;">
                    <span style="display: flex; align-items: center; gap: 10px;">
                        <span style="color: {status_color}; font-size: 18px;">{status_icon}</span>
                        <span style="font-weight: bold;">{f['file_name']}</span>
                        <span style="color: #666; font-size: 13px;">({f['count']} 个授权)</span>
                    </span>
                    <span style="color: #999; font-size: 13px;">
                        剩余 {f['min_days']} 天
                        <span style="margin-left: 10px;">▼</span>
                    </span>
                </summary>
                <div style="padding: 0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #e9ecef;">
                                <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #dee2e6;">Feature</th>
                                <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #dee2e6;">版本</th>
                                <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #dee2e6;">过期时间</th>
                                <th style="padding: 8px 12px; text-align: center; border-bottom: 2px solid #dee2e6;">剩余天数</th>
                            </tr>
                        </thead>
                        <tbody>
                            {feature_rows}
                        </tbody>
                    </table>
                </div>
            </details>
            """

        # 统计各紧急级别数量
        urgent_count = sum(1 for f in warning_files if f['min_days'] <= 7)
        warning_count = sum(1 for f in warning_files if 7 < f['min_days'] <= 15)
        info_count = sum(1 for f in warning_files if f['min_days'] > 15)

        # 构建完整HTML
        html = f"""
        <html>
        <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; }}
            .header {{ 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white; padding: 25px 30px; border-radius: 10px; margin-bottom: 25px;
            }}
            .header h2 {{ margin: 0 0 5px 0; font-size: 24px; }}
            .header p {{ margin: 0; opacity: 0.9; font-size: 14px; }}
            .stats {{ display: flex; gap: 15px; margin: 20px 0; flex-wrap: wrap; }}
            .stat-box {{ 
                background: #f5f5f5; padding: 15px 25px; border-radius: 8px; 
                border-left: 4px solid #667eea; flex: 1; min-width: 100px;
                text-align: center;
            }}
            .stat-box .number {{ font-size: 28px; font-weight: bold; color: #667eea; }}
            .stat-box .label {{ font-size: 13px; color: #888; }}
            .stat-box.urgent {{ border-left-color: #f44336; }}
            .stat-box.urgent .number {{ color: #f44336; }}
            .stat-box.warning {{ border-left-color: #ff9800; }}
            .stat-box.warning .number {{ color: #ff9800; }}
            .stat-box.info {{ border-left-color: #4caf50; }}
            .stat-box.info .number {{ color: #4caf50; }}
            .section-title {{ 
                font-size: 18px; font-weight: bold; margin: 25px 0 15px 0;
                padding-bottom: 10px; border-bottom: 2px solid #e9ecef;
            }}
            .section-title .badge {{
                background: #667eea; color: white; padding: 2px 10px; 
                border-radius: 12px; font-size: 13px; margin-left: 10px;
            }}
            details summary::-webkit-details-marker {{ display: none; }}
            details summary {{ list-style: none; }}
            details[open] summary span:last-child span {{
                transform: rotate(180deg);
                display: inline-block;
            }}
            .footer {{ 
                margin-top: 30px; padding-top: 15px; 
                border-top: 1px solid #e9ecef; color: #999; font-size: 12px;
                text-align: center;
            }}
        </style>
        </head>
        <body>
            <div class="header">
                <h2>📋 License 到期提醒</h2>
                <p>共 {total_files} 个文件，{total_licenses} 个授权即将到期</p>
            </div>
            
            <div class="stats">
                <div class="stat-box urgent">
                    <div class="number">{urgent_count}</div>
                    <div class="label">🔴 紧急 (≤7天)</div>
                </div>
                <div class="stat-box warning">
                    <div class="number">{warning_count}</div>
                    <div class="label">🟡 警告 (8-15天)</div>
                </div>
                <div class="stat-box info">
                    <div class="number">{info_count}</div>
                    <div class="label">🟢 提醒 (>15天)</div>
                </div>
            </div>
            
            <div class="section-title">
                📁 即将过期的 License 文件
                <span class="badge">{total_files} 个文件</span>
            </div>
            
            {file_panels}
            
            <div class="footer">
                <p>此邮件为系统自动发送，请勿直接回复。</p>
                <p>发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        </body>
        </html>
        """

        return html

    def _build_text(self, warning_files: List[Dict], total_files: int, total_licenses: int) -> str:
        """构建纯文本邮件内容"""
        lines = [
            "=" * 60,
            "License 到期提醒",
            "=" * 60,
            f"共 {total_files} 个文件，{total_licenses} 个授权即将到期",
            "",
            "-" * 60,
        ]

        # 按紧急程度分组
        urgent = [f for f in warning_files if f['min_days'] <= 7]
        warning = [f for f in warning_files if 7 < f['min_days'] <= 15]
        info = [f for f in warning_files if f['min_days'] > 15]

        if urgent:
            lines.append("【🔴 紧急 - 7天内到期】")
            lines.append("")
            for f in urgent:
                lines.append(f"  📁 {f['file_name']} (剩余 {f['min_days']} 天, {f['count']} 个授权)")
                for lic in f['licenses']:
                    lines.append(f"     - {lic['feature']} (版本: {lic.get('version', 'N/A')}, 过期: {lic['expiration_date']}, 剩余: {lic['days_remaining']}天)")
                lines.append("")

        if warning:
            lines.append("【🟡 警告 - 15天内到期】")
            lines.append("")
            for f in warning:
                lines.append(f"  📁 {f['file_name']} (剩余 {f['min_days']} 天, {f['count']} 个授权)")
                for lic in f['licenses']:
                    lines.append(f"     - {lic['feature']} (版本: {lic.get('version', 'N/A')}, 过期: {lic['expiration_date']}, 剩余: {lic['days_remaining']}天)")
                lines.append("")

        if info:
            lines.append("【🟢 提醒 - 即将到期】")
            lines.append("")
            for f in info:
                lines.append(f"  📁 {f['file_name']} (剩余 {f['min_days']} 天, {f['count']} 个授权)")
                lines.append("")

        lines.append("-" * 60)
        lines.append(f"发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("此邮件为系统自动发送，请勿直接回复。")

        return "\n".join(lines)

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串"""
        month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

        if not date_str:
            return None

        try:
            parts = date_str.lower().split('-')
            if len(parts) == 3:
                return datetime(int(parts[2]), month_map.get(parts[1], 1), int(parts[0]))
            return datetime.strptime(date_str, '%d-%b-%Y')
        except Exception:
            return None

    def _send_email(self, recipient: str, cc_list: List[str], subject: str, html_body: str, text_body: str):
        """发送邮件"""
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.utils import formatdate

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = getattr(settings, 'MAIL_USER', '')
        msg['To'] = recipient
        msg['Date'] = formatdate()

        # 添加抄送
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        self.email_manager.send_raw_email(msg)


class Command(BaseCommand):
    help = '扫描LIC文件并发送过期提醒邮件'

    def add_arguments(self, parser):
        parser.add_argument('--scan-dir', type=str, help='扫描目录，覆盖settings配置')
        parser.add_argument('--days', type=int, help='过期阈值天数，默认使用settings配置')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，只打印不发送邮件')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('License文件扫描和提醒任务'))
        self.stdout.write(self.style.SUCCESS(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        try:
            scan_dir = options.get('scan_dir') or getattr(settings, 'LICENSE_SCAN_DIRECTORY', None)
            if not scan_dir:
                self.stdout.write(self.style.ERROR('未配置 LICENSE_SCAN_DIRECTORY'))
                return

            # 获取阈值：命令行参数 > 配置文件 > 默认30天
            days = options.get('days')
            if days is None:
                days = getattr(settings, 'LICENSE_EXPIRY_THRESHOLD_DAYS', 30)

            dry_run = options.get('dry_run', False)

            self.stdout.write(f'扫描目录: {scan_dir}')
            self.stdout.write(f'阈值天数: {days}天')
            if options.get('days'):
                self.stdout.write(f'  (来源: 命令行参数)')
            else:
                self.stdout.write(f'  (来源: 配置文件)')
            self.stdout.write(f'试运行模式: {"是" if dry_run else "否"}')
            self.stdout.write('-' * 60)

            # 1. 扫描LIC文件 - 传入阈值参数
            self.stdout.write('\n[步骤1] 扫描LIC文件...')
            scanner = LicenseFileScanner(scan_dir, days_threshold=days)
            warning_files = scanner.scan()

            total_files = len(warning_files)
            total_licenses = sum(f['count'] for f in warning_files)

            self.stdout.write(f'找到 {total_files} 个即将过期的文件')
            self.stdout.write(f'  ⚠️ 即将到期: {total_licenses} 个授权')

            if total_files == 0:
                self.stdout.write(self.style.WARNING('没有即将过期的文件需要提醒'))
                return

            # 2. 发送邮件
            self.stdout.write('\n[步骤2] 发送邮件提醒...')
            sender = LicenseFileEmailSender()
            result = sender.send_notifications(warning_files, dry_run=dry_run)

            self.stdout.write(f'发送完成:')
            self.stdout.write(f'  成功: {result["sent"]} 封')
            if result['failed'] > 0:
                self.stdout.write(self.style.WARNING(f'  失败: {result["failed"]} 封'))
                for err in result['errors']:
                    self.stdout.write(f'    {err}')

            if dry_run:
                self.stdout.write(self.style.WARNING('  (试运行模式，未实际发送邮件)'))

            self.stdout.write(self.style.SUCCESS('=' * 60))
            self.stdout.write(self.style.SUCCESS('任务执行完成！'))

        except Exception as e:
            logger.error(f'License扫描任务执行失败: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'任务执行失败: {str(e)}'))
            raise