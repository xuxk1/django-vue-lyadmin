"""
UPD文件扫描命令行工具
扫描指定目录下的所有.upd文件，解析并发送过期提醒邮件
"""
import os
import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


class UpdFileScanner:
    """UPD文件扫描器"""

    def __init__(self, scan_directory: str = None, days_threshold: int = None):
        self.scan_directory = scan_directory or getattr(settings, 'UPD_SCAN_DIRECTORY', None)
        if not self.scan_directory:
            raise ValueError("未配置 UPD_SCAN_DIRECTORY")

        if days_threshold is not None:
            self.days_threshold = days_threshold
        else:
            self.days_threshold = getattr(settings, 'LICENSE_EXPIRY_THRESHOLD_DAYS', 30)

        logger.info(f"UPD扫描器初始化: 目录={self.scan_directory}, 阈值={self.days_threshold}天")

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        """
        解析日期字符串，兼容多种格式
        支持的格式：
        - %Y-%m-%d %H:%M:%S
        - %Y-%m-%d
        - %Y/%m/%d
        - %Y-%m-%dT%H:%M:%S
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # 支持的日期格式列表
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%d-%b-%Y',  # 兼容LIC文件格式
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # 如果都解析失败，尝试提取日期部分
        try:
            # 尝试提取 YYYY-MM-DD 格式
            date_match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_str)
            if date_match:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3))
                return datetime(year, month, day)
        except Exception:
            pass

        logger.error(f"无法解析日期: {date_str}")
        return None

    def parse_upd_file(self, file_path: str) -> Dict:
        """
        解析.upd文件，提取所有字段

        Args:
            file_path: 文件路径

        Returns:
            包含文件信息和各字段的字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            result = {
                'file_path': file_path,
                'file_name': os.path.basename(file_path),
                'is_valid': True,
                'end_date': None,
                'end_date_str': None,
                'start_date': None,
                'start_date_str': None,
                'product_name': None,
                'product_pid': None,
                'user_number': None,
                'volume_number': None,
                'features': [],
                'mac_address': None,
                'serial_number': None,
                'control_type': None,
                'error': None
            }

            # 1. 提取 endDate（支持多种格式）
            end_date_match = re.search(r'<endDate>(.*?)</endDate>', content, re.DOTALL)
            if end_date_match:
                end_date_str = end_date_match.group(1).strip()
                result['end_date_str'] = end_date_str
                result['end_date'] = self._parse_datetime(end_date_str)
                if not result['end_date']:
                    result['is_valid'] = False
                    result['error'] = f'无法解析endDate: {end_date_str}'
                    return result
            else:
                # 兼容旧格式：可能直接是 endDate 标签在 description 中
                end_date_match = re.search(r'<endDate>([^<]+)</endDate>', content)
                if end_date_match:
                    end_date_str = end_date_match.group(1).strip()
                    result['end_date_str'] = end_date_str
                    result['end_date'] = self._parse_datetime(end_date_str)
                    if not result['end_date']:
                        result['is_valid'] = False
                        result['error'] = f'无法解析endDate: {end_date_str}'
                        return result
                else:
                    logger.warning(f"文件 {file_path} 中未找到 endDate 字段")
                    result['is_valid'] = False
                    result['error'] = '未找到endDate字段'
                    return result

            # 2. 提取 startDate
            start_date_match = re.search(r'<startDate>(.*?)</startDate>', content, re.DOTALL)
            if start_date_match:
                start_date_str = start_date_match.group(1).strip()
                result['start_date_str'] = start_date_str
                result['start_date'] = self._parse_datetime(start_date_str)

            # 3. 提取 product 标签
            product_match = re.search(r'<product\s+pid="([^"]*)"\s+name="([^"]*)"', content)
            if product_match:
                result['product_pid'] = product_match.group(1)
                result['product_name'] = product_match.group(2)

            # 4. 提取 userNumber
            user_number_match = re.search(r'<userNumber>(\d+)</userNumber>', content)
            if user_number_match:
                result['user_number'] = int(user_number_match.group(1))

            # 5. 提取 volumeNumber
            volume_number_match = re.search(r'<volumeNumber>(\d+)</volumeNumber>', content)
            if volume_number_match:
                result['volume_number'] = int(volume_number_match.group(1))

            # 6. 提取 serial number
            sn_match = re.search(r'<sn>([^<]+)</sn>', content)
            if sn_match:
                result['serial_number'] = sn_match.group(1).strip()

            # 7. 提取 controlType
            control_type_match = re.search(r'<controlType>([^<]+)</controlType>', content)
            if control_type_match:
                result['control_type'] = control_type_match.group(1).strip()

            # 8. 提取 features
            # 支持两种格式：<feature name="xxx" users="x"/> 或 <feature name="xxx" users="x" />
            feature_matches = re.finditer(r'<feature\s+name="([^"]*)"\s+users="([^"]*)"', content)
            for match in feature_matches:
                result['features'].append({
                    'name': match.group(1),
                    'users': int(match.group(2))
                })

            # 如果没有找到，尝试另一种格式
            if not result['features']:
                feature_matches = re.finditer(r'<feature\s+name="([^"]*)"(?:\s+users="([^"]*)")?\s*/>', content)
                for match in feature_matches:
                    users = match.group(2) if match.group(2) else '0'
                    result['features'].append({
                        'name': match.group(1),
                        'users': int(users)
                    })

            # 9. 提取 mac
            mac_match = re.search(r'<mac>([^<]+)</mac>', content)
            if mac_match:
                result['mac_address'] = mac_match.group(1).strip()

            return result

        except Exception as e:
            logger.error(f"解析文件 {file_path} 失败: {str(e)}")
            return {
                'file_path': file_path,
                'file_name': os.path.basename(file_path),
                'is_valid': False,
                'error': str(e)
            }

    def scan(self) -> List[Dict]:
        """扫描所有UPD文件，返回即将过期的文件列表（不包含已过期）"""
        if not os.path.exists(self.scan_directory):
            logger.error(f"扫描目录不存在: {self.scan_directory}")
            return []

        # 查找所有UPD文件
        upd_files = []
        for root, _, files in os.walk(self.scan_directory):
            for file in files:
                if file.lower().endswith('.upd'):
                    upd_files.append(os.path.join(root, file))

        if not upd_files:
            logger.warning(f"未找到任何UPD文件: {self.scan_directory}")
            return []

        logger.info(f"找到 {len(upd_files)} 个UPD文件")

        warning_files = []  # 即将过期的文件列表
        now = datetime.now()

        for file_path in upd_files:
            file_info = self.parse_upd_file(file_path)

            if not file_info.get('is_valid') or not file_info.get('end_date'):
                continue

            end_date = file_info['end_date']
            days_remaining = (end_date - now).days

            # 只保留即将过期的（0 < days_remaining <= threshold），已过期的跳过
            if 0 < days_remaining <= self.days_threshold:
                file_info['days_remaining'] = days_remaining

                # 格式化功能特性
                features_str = '; '.join([f"{f['name']}({f['users']})" for f in file_info.get('features', [])])
                file_info['features_str'] = features_str

                warning_files.append(file_info)

        # 按剩余天数排序
        warning_files.sort(key=lambda x: x['days_remaining'])

        logger.info(f"扫描完成: 即将到期文件 {len(warning_files)} 个")
        return warning_files


class UpdFileEmailSender:
    """UPD文件邮件发送器"""

    def __init__(self):
        from utils.email import EmailManager
        self.email_manager = EmailManager()

        self.recipients = getattr(settings, 'LICENSE_EMAIL_RECIPIENTS', [])
        self.email_domain = getattr(settings, 'EMAIL_DOMAIN', '@phlexing.com')
        self.cc = getattr(settings, 'LICENSE_DEFAULT_EXPIRED_CC', '')
        self.enabled = getattr(settings, 'LICENSE_AUTO_CHECK_ENABLED', True)
        
        # 文档匹配收件人配置
        self.document_matching_recipients = getattr(settings, 'DOCUMENT_MATCHING_RECIPIENTS', {})

    def get_cc_list(self) -> List[str]:
        """获取抄送人列表"""
        if not self.cc:
            return []

        cc_list = re.split(r'[,;，；\s]+', self.cc)
        cc_list = [c.strip() for c in cc_list if c.strip()]

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
            default = getattr(settings, 'LICENSE_DEFAULT_RECIPIENT', 'admin')
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

                    subject, html_body, text_body = self._build_email_content(files)
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
        total_files = len(warning_files)
        total_features = sum(len(f.get('features', [])) for f in warning_files)

        subject = f"BitAnswer License 到期提醒 - {total_files} 个文件, {total_features} 个授权即将到期"

        html_body = self._build_html(warning_files, total_files, total_features)
        text_body = self._build_text(warning_files, total_files, total_features)

        return subject, html_body, text_body

    def _build_html(self, warning_files: List[Dict], total_files: int, total_features: int) -> str:
        """构建HTML邮件内容"""
        file_panels = ''
        for idx, f in enumerate(warning_files, 1):
            days = f['days_remaining']
            if days <= 7:
                status_icon = '🔴'
                status_color = '#f44336'
            elif days <= 15:
                status_icon = '🟡'
                status_color = '#ff9800'
            else:
                status_icon = '🟢'
                status_color = '#4caf50'

            feature_rows = ''
            for feature in f.get('features', []):
                feature_rows += f"""
                <tr>
                    <td style="padding: 4px 8px; border-bottom: 1px solid #eee;">{feature['name']}</td>
                    <td style="padding: 4px 8px; border-bottom: 1px solid #eee; text-align: center;">{feature['users']}</td>
                </tr>
                """

            if not feature_rows:
                feature_rows = """
                <tr>
                    <td colspan="2" style="padding: 8px; text-align: center; color: #999;">无功能特性</td>
                </tr>
                """

            # 构建产品信息显示
            product_info = f.get('product_name', 'N/A')
            if f.get('product_pid'):
                product_info += f" ({f['product_pid']})"

            file_panels += f"""
            <details style="margin-bottom: 10px; border: 1px solid #ddd; border-radius: 5px; overflow: hidden;">
                <summary style="padding: 10px 15px; background-color: #f8f9fa; cursor: pointer; display: flex; align-items: center; justify-content: space-between; user-select: none;">
                    <span style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <span style="color: {status_color}; font-size: 18px;">{status_icon}</span>
                        <span style="font-weight: bold;">{f['file_name']}</span>
                        <span style="color: #666; font-size: 13px;">产品: {product_info}</span>
                        <span style="color: #666; font-size: 13px;">用户: {f.get('user_number', f.get('volume_number', 'N/A'))}</span>
                        <span style="color: #666; font-size: 13px;">序列号: {f.get('serial_number', 'N/A')}</span>
                    </span>
                    <span style="color: #999; font-size: 13px;">
                        剩余 {f['days_remaining']} 天
                        <span style="margin-left: 10px;">▼</span>
                    </span>
                </summary>
                <div style="padding: 0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background-color: #e9ecef;">
                                <th style="padding: 8px 12px; text-align: left; border-bottom: 2px solid #dee2e6;">Feature</th>
                                <th style="padding: 8px 12px; text-align: center; border-bottom: 2px solid #dee2e6;">用户数</th>
                            </tr>
                        </thead>
                        <tbody>
                            {feature_rows}
                        </tbody>
                    </table>
                    <div style="padding: 8px 12px; background-color: #f8f9fa; border-top: 1px solid #eee; font-size: 12px; color: #666;">
                        📅 到期时间: {f['end_date_str']} | 剩余: {f['days_remaining']} 天
                        {f' | 控制类型: {f["control_type"]}' if f.get('control_type') else ''}
                        {f' | MAC: {f["mac_address"]}' if f.get('mac_address') else ''}
                    </div>
                </div>
            </details>
            """

        urgent_count = sum(1 for f in warning_files if f['days_remaining'] <= 7)
        warning_count = sum(1 for f in warning_files if 7 < f['days_remaining'] <= 15)
        info_count = sum(1 for f in warning_files if f['days_remaining'] > 15)

        html = f"""
        <html>
        <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; }}
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
                <h2>📋 BitAnswer License 到期提醒</h2>
                <p>共 {total_files} 个文件，{total_features} 个授权即将到期</p>
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
                📁 即将过期的 BitAnswer 授权文件
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

    def _build_text(self, warning_files: List[Dict], total_files: int, total_features: int) -> str:
        """构建纯文本邮件内容"""
        lines = [
            "=" * 60,
            "BitAnswer License 到期提醒",
            "=" * 60,
            f"共 {total_files} 个文件，{total_features} 个授权即将到期",
            "",
            "-" * 60,
        ]

        urgent = [f for f in warning_files if f['days_remaining'] <= 7]
        warning = [f for f in warning_files if 7 < f['days_remaining'] <= 15]
        info = [f for f in warning_files if f['days_remaining'] > 15]

        if urgent:
            lines.append("【🔴 紧急 - 7天内到期】")
            lines.append("")
            for f in urgent:
                lines.append(f"  📁 {f['file_name']}")
                lines.append(f"     产品: {f.get('product_name', 'N/A')}")
                lines.append(f"     用户数: {f.get('user_number', f.get('volume_number', 'N/A'))}")
                lines.append(f"     序列号: {f.get('serial_number', 'N/A')}")
                lines.append(f"     到期: {f['end_date_str']}")
                lines.append(f"     剩余: {f['days_remaining']} 天")
                if f.get('features'):
                    lines.append(f"     功能特性: {', '.join([feat['name'] for feat in f['features']])}")
                lines.append("")

        if warning:
            lines.append("【🟡 警告 - 15天内到期】")
            lines.append("")
            for f in warning:
                lines.append(f"  📁 {f['file_name']}")
                lines.append(f"     产品: {f.get('product_name', 'N/A')}")
                lines.append(f"     用户数: {f.get('user_number', f.get('volume_number', 'N/A'))}")
                lines.append(f"     序列号: {f.get('serial_number', 'N/A')}")
                lines.append(f"     到期: {f['end_date_str']}")
                lines.append(f"     剩余: {f['days_remaining']} 天")
                if f.get('features'):
                    lines.append(f"     功能特性: {', '.join([feat['name'] for feat in f['features']])}")
                lines.append("")

        if info:
            lines.append("【🟢 提醒 - 即将到期】")
            lines.append("")
            for f in info:
                lines.append(f"  📁 {f['file_name']}")
                lines.append(f"     产品: {f.get('product_name', 'N/A')}")
                lines.append(f"     到期: {f['end_date_str']}")
                lines.append(f"     剩余: {f['days_remaining']} 天")
                lines.append("")

        lines.append("-" * 60)
        lines.append(f"发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("此邮件为系统自动发送，请勿直接回复。")

        return "\n".join(lines)

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

        if cc_list:
            msg['Cc'] = ', '.join(cc_list)

        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        self.email_manager.send_raw_email(msg)


class Command(BaseCommand):
    help = '扫描UPD文件并发送过期提醒邮件'

    def add_arguments(self, parser):
        parser.add_argument('--scan-dir', type=str, help='扫描目录，覆盖settings配置')
        parser.add_argument('--days', type=int, help='过期阈值天数，默认使用settings配置')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，只打印不发送邮件')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('BitAnswer UPD文件扫描和提醒任务'))
        self.stdout.write(self.style.SUCCESS(f'执行时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        try:
            scan_dir = options.get('scan_dir') or getattr(settings, 'UPD_SCAN_DIRECTORY', None)
            if not scan_dir:
                self.stdout.write(self.style.ERROR('未配置 UPD_SCAN_DIRECTORY'))
                return

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

            self.stdout.write('\n[步骤1] 扫描UPD文件...')
            scanner = UpdFileScanner(scan_dir, days_threshold=days)
            warning_files = scanner.scan()

            total_files = len(warning_files)
            total_features = sum(len(f.get('features', [])) for f in warning_files)

            self.stdout.write(f'找到 {total_files} 个即将过期的文件')
            self.stdout.write(f'  ⚠️ 即将到期: {total_features} 个授权')

            if total_files == 0:
                self.stdout.write(self.style.WARNING('没有即将过期的文件需要提醒'))
                return

            self.stdout.write('\n[步骤2] 发送邮件提醒...')
            sender = UpdFileEmailSender()
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
            logger.error(f'UPD扫描任务执行失败: {str(e)}', exc_info=True)
            self.stdout.write(self.style.ERROR(f'任务执行失败: {str(e)}'))
            raise