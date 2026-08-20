# -*- coding: utf-8 -*-
"""
LDAP诊断脚本 - 帮助发现AD目录结构
用法: python manage.py ldap_diagnose <用户名> <密码>
"""
from django.core.management.base import BaseCommand
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException


class Command(BaseCommand):
    help = 'LDAP诊断工具 - 发现AD目录结构和正确的用户DN'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='LDAP用户名')
        parser.add_argument('password', type=str, help='LDAP密码')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        from config import LDAP_SERVER, LDAP_PORT, LDAP_USE_SSL, LDAP_SEARCH_BASE

        server = Server(LDAP_SERVER, port=LDAP_PORT, use_ssl=LDAP_USE_SSL, get_info=ALL, connect_timeout=10)
        self.stdout.write(f"连接LDAP服务器: {LDAP_SERVER}:{LDAP_PORT} (SSL={LDAP_USE_SSL})")

        # ========== 测试1: 匿名绑定 ==========
        self.stdout.write(self.style.NOTICE("\n===== 测试1: 匿名绑定 ====="))
        try:
            conn = Connection(server, user=None, password=None, auto_bind=True)
            self.stdout.write(self.style.SUCCESS("✓ 匿名绑定成功"))

            # 尝试搜索
            self.stdout.write(f"\n在 {LDAP_SEARCH_BASE} 下搜索用户 {username}...")
            conn.search(
                search_base=LDAP_SEARCH_BASE,
                search_filter=f'(|(sAMAccountName={username})(userPrincipalName={username}))',
                search_scope=SUBTREE,
                attributes=['sAMAccountName', 'displayName', 'mail', 'distinguishedName', 'telephoneNumber'],
            )
            if conn.entries:
                for entry in conn.entries:
                    self.stdout.write(self.style.SUCCESS(f"\n找到用户:"))
                    self.stdout.write(f"  DN: {entry.entry_dn}")
                    for attr in entry.entry_attributes_as_dict:
                        self.stdout.write(f"  {attr}: {entry.entry_attributes_as_dict[attr]}")
            else:
                self.stdout.write(self.style.WARNING("  匿名搜索未找到用户"))

                # 尝试列出搜索基础下的所有OU
                self.stdout.write(f"\n列出 {LDAP_SEARCH_BASE} 下的子条目...")
                conn.search(
                    search_base=LDAP_SEARCH_BASE,
                    search_filter='(objectClass=*)',
                    search_scope=SUBTREE,
                    attributes=['distinguishedName', 'objectClass'],
                    size_limit=20,
                )
                if conn.entries:
                    self.stdout.write(f"找到 {len(conn.entries)} 个条目:")
                    for entry in conn.entries:
                        self.stdout.write(f"  DN: {entry.entry_dn}")
                        self.stdout.write(f"  objectClass: {entry.entry_attributes_as_dict.get('objectClass', [])}")
                else:
                    self.stdout.write(self.style.ERROR("✗ 匿名搜索无任何结果（AD可能禁止匿名访问）"))

            conn.unbind()
        except LDAPException as e:
            self.stdout.write(self.style.ERROR(f"✗ 匿名绑定失败: {e}"))

        # ========== 测试2: 尝试不同DN格式绑定 ==========
        self.stdout.write(self.style.NOTICE("\n===== 测试2: 尝试不同DN格式绑定 ====="))

        # 从配置获取domain
        dc_parts = [p.strip() for p in LDAP_SEARCH_BASE.split(',') if p.strip().startswith('DC=')]
        dc_values = [p.replace('DC=', '') for p in dc_parts]
        domain = '.'.join(dc_values)
        self.stdout.write(f"推断域名: {domain}")

        # 尝试从根DSE获取默认命名上下文
        try:
            root_conn = Connection(server, user=None, password=None, auto_bind=True)
            root_conn.search('', '(objectClass=*)', attributes=['defaultNamingContext', 'rootDomainNamingContext'])
            if root_conn.entries:
                for attr in ['defaultNamingContext', 'rootDomainNamingContext']:
                    val = root_conn.entries[0].entry_attributes_as_dict.get(attr)
                    if val:
                        self.stdout.write(f"\nAD根信息 - {attr}: {val[0]}")
                        # 用这个DN作为搜索基础再试一次
                        self.stdout.write(f"\n用 {val[0]} 作为搜索基础重新搜索...")
                        root_conn.search(
                            search_base=val[0],
                            search_filter=f'(|(sAMAccountName={username})(userPrincipalName={username}))',
                            search_scope=SUBTREE,
                            attributes=['sAMAccountName', 'displayName', 'mail', 'distinguishedName', 'telephoneNumber'],
                        )
                        if root_conn.entries:
                            for entry in root_conn.entries:
                                self.stdout.write(self.style.SUCCESS(f"\n找到用户:"))
                                self.stdout.write(f"  DN: {entry.entry_dn}")
                                for a in entry.entry_attributes_as_dict:
                                    self.stdout.write(f"  {a}: {entry.entry_attributes_as_dict[a]}")
                        else:
                            self.stdout.write(self.style.WARNING("✗ 仍未找到用户"))
                root_conn.unbind()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"根DSE查询失败: {e}"))

        # 尝试多种DN格式
        dn_formats = [
            f'CN={username},OU=Users,DC={",".join("DC=" + d for d in dc_values)}',
            f'CN={username},DC={",".join("DC=" + d for d in dc_values)}',
            f'{username}@{domain}',  # UPN格式
        ]

        for dn in dn_formats:
            self.stdout.write(f"\n尝试绑定 DN: {dn}")
            try:
                conn = Connection(server, user=dn, password=password, auto_bind=True)
                if conn.bound:
                    self.stdout.write(self.style.SUCCESS(f"✓ 绑定成功! 正确的DN是: {dn}"))
                    # 获取用户信息
                    conn.search(
                        search_base=dn,
                        search_filter='(objectClass=*)',
                        search_scope=SUBTREE,
                        attributes=['sAMAccountName', 'displayName', 'mail', 'distinguishedName', 'telephoneNumber', 'memberOf'],
                    )
                    if conn.entries:
                        entry = conn.entries[0]
                        self.stdout.write(self.style.SUCCESS(f"\n用户信息:"))
                        for attr in entry.entry_attributes_as_dict:
                            val = entry.entry_attributes_as_dict[attr]
                            if attr == 'memberOf':
                                self.stdout.write(f"  {attr}: (共{len(val)}个组)")
                                for g in val[:5]:
                                    self.stdout.write(f"    - {g}")
                                if len(val) > 5:
                                    self.stdout.write(f"    ... 还有{len(val)-5}个")
                            else:
                                self.stdout.write(f"  {attr}: {val}")
                    conn.unbind()
                    self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
                    self.stdout.write(self.style.SUCCESS(f"建议配置:"))
                    self.stdout.write(self.style.SUCCESS(f"  LDAP_AUTH_METHOD = 'direct'"))
                    self.stdout.write(self.style.SUCCESS(f"  LDAP_USER_DN_TEMPLATE = '{dn.replace(username, '%(user)s')}'"))
                    # 提取OU部分
                    if 'OU=' in dn:
                        search_base_suggestion = dn[dn.index('OU='):]
                    else:
                        search_base_suggestion = ','.join(dc_parts)
                    self.stdout.write(self.style.SUCCESS(f"  LDAP_SEARCH_BASE = '{search_base_suggestion}'"))
                    self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
                    return
                else:
                    self.stdout.write(self.style.ERROR(f"✗ 绑定失败"))
            except LDAPException as e:
                self.stdout.write(self.style.ERROR(f"✗ 绑定异常: {e}"))

        self.stdout.write(self.style.ERROR("\n所有DN格式都失败了。请检查:"))
        self.stdout.write("  1. 用户名和密码是否正确")
        self.stdout.write("  2. LDAP服务器地址和端口是否正确")
        self.stdout.write("  3. 联系AD管理员获取正确的用户DN格式")
