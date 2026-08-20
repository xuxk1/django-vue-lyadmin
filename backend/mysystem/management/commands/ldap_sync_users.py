# -*- coding: utf-8 -*-
"""
LDAP批量同步用户管理命令
用法:
  python manage.py ldap_sync_users              # 使用服务账号同步
  python manage.py ldap_sync_users -u xxx -p xxx  # 使用指定账号同步
  python manage.py ldap_sync_users --dry-run    # 仅预览，不实际创建
"""
import uuid
import logging
import bcrypt
from datetime import datetime

import psycopg2
from django.core.management.base import BaseCommand
from django.db import models
from django.contrib.auth.hashers import make_password
from ldap3 import Server, Connection, ALL, SUBTREE

from config import (
    LDAP_ENABLED,
    LDAP_SERVER,
    LDAP_PORT,
    LDAP_USE_SSL,
    LDAP_SEARCH_BASE,
    LDAP_USER_DN_TEMPLATE,
    LDAP_BIND_USER,
    LDAP_BIND_PASSWORD,
    LDAP_DEFAULT_ROLE_KEY,
    LDAP_SYNC_USERNAME,
    LDAP_SYNC_PASSWORD,
    ANYTHINGLLM_DB_HOST,
    ANYTHINGLLM_DB_PORT,
    ANYTHINGLLM_DB_NAME,
    ANYTHINGLLM_DB_USER,
    ANYTHINGLLM_DB_PASSWORD,
)
from mysystem.models import Users, Dept, Role

logger = logging.getLogger(__name__)

# ========== 过滤配置 ==========
EXCLUDED_OU_NAMES = {
    'disabled', 'temp', 'mail_accounts',
    'computers', 'citrix',
}
EXCLUDED_OU_PREFIXES = ('computers_', 'citrix', 'pc_', 'linux_')


def should_exclude(ou_hierarchy):
    """判断OU层级是否应被排除（非人员账号）"""
    for ou_name in ou_hierarchy:
        lower_name = ou_name.lower()
        if lower_name in EXCLUDED_OU_NAMES:
            return True
        for prefix in EXCLUDED_OU_PREFIXES:
            if lower_name.startswith(prefix):
                return True
    return False


def parse_ou_from_dn(dn):
    """从DN中解析OU层级（从根到叶）"""
    ou_parts = []
    for part in dn.split(','):
        part = part.strip()
        if part.upper().startswith('OU='):
            ou_parts.append(part.split('=', 1)[1])
    ou_parts.reverse()
    return ou_parts


def extract_user_info(entry):
    """从LDAP entry提取用户信息"""
    info = {'dn': str(entry.entry_dn)}
    key_attrs = {
        'sAMAccountName': 'username',
        'displayName': 'name',
        'givenName': 'nickname',
        'mail': 'email',
        'telephoneNumber': 'mobile',
    }
    for ldap_attr, local_key in key_attrs.items():
        try:
            val = getattr(entry, ldap_attr, None)
            if val and val.value is not None:
                info[local_key] = str(val.value)
        except Exception:
            pass
    info['ou_hierarchy'] = parse_ou_from_dn(info['dn'])
    return info


class Command(BaseCommand):
    help = '从LDAP批量同步用户信息到本地数据库，自动创建部门和子部门'

    def add_arguments(self, parser):
        parser.add_argument('-u', '--username', help='LDAP登录用户名（UPN格式）')
        parser.add_argument('-p', '--password', help='LDAP登录密码')
        parser.add_argument('--dry-run', action='store_true', help='仅预览，不实际创建用户和部门')

    def handle(self, *args, **options):
        if not LDAP_ENABLED:
            self.stdout.write(self.style.WARNING('LDAP未启用（LDAP_ENABLED=False）'))
            return

        dry_run = options.get('dry_run', False)
        username = options.get('username')
        password = options.get('password')

        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS(f'LDAP用户同步任务 - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'))
        self.stdout.write(self.style.SUCCESS(f'模式: {"预览(dry-run)" if dry_run else "正式同步"}'))
        self.stdout.write(self.style.SUCCESS('=' * 60))

        # 确定绑定凭据
        bind_user, bind_password = self._get_bind_credentials(username, password)
        if not bind_user:
            return

        # 连接LDAP
        conn = self._connect_ldap(bind_user, bind_password)
        if not conn:
            return

        try:
            # 批量查询
            all_entries = self._fetch_all_users(conn)
            self.stdout.write(f'LDAP查询完成，共 {len(all_entries)} 条记录')

            # 过滤
            all_users, stats_filter = self._filter_users(all_entries)
            self.stdout.write(f'\n过滤结果: 总记录={len(all_entries)}, '
                            f'排除计算机={stats_filter["computer"]}, '
                            f'排除非人员OU={stats_filter["excluded_ou"]}, '
                            f'待同步={len(all_users)}')

            if not all_users:
                self.stdout.write(self.style.WARNING('没有需要同步的用户'))
                return

            if dry_run:
                self._print_preview(all_users)
                self.stdout.write(self.style.WARNING('\n[DRY-RUN] 仅预览，未实际创建'))
                return

            # 执行同步
            stats = self._sync_users(all_users)

            # 同步部门信息（负责人、电话、邮箱）
            dept_updated = self._sync_dept_info()

            # 同步用户名密码到 anythingllm PostgreSQL
            anythingllm_stats = self._sync_to_anythingllm(all_users)

            # 输出统计
            self.stdout.write(self.style.SUCCESS(f'\n=== 同步完成 ==='))
            self.stdout.write(self.style.SUCCESS(f'  新建用户: {stats["created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  更新用户: {stats["updated"]}'))
            self.stdout.write(self.style.SUCCESS(f'  跳过用户: {stats["skipped"]}'))
            self.stdout.write(self.style.SUCCESS(f'  新建部门: {stats["dept_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  更新部门信息: {dept_updated}'))
            self.stdout.write(self.style.SUCCESS(f'  错误数量: {stats["errors"]}'))
            self.stdout.write(self.style.SUCCESS(f'  anythingllm新增: {anythingllm_stats["inserted"]}'))
            self.stdout.write(self.style.SUCCESS(f'  anythingllm跳过: {anythingllm_stats["skipped"]}'))
            self.stdout.write(self.style.SUCCESS(f'  anythingllm错误: {anythingllm_stats["errors"]}'))

            logger.info(f'LDAP同步完成: 新建={stats["created"]}, 更新={stats["updated"]}, '
                       f'跳过={stats["skipped"]}, 新建部门={stats["dept_created"]}, 错误={stats["errors"]}')

        finally:
            conn.unbind()

    def _get_bind_credentials(self, username, password):
        """获取LDAP绑定凭据
        优先级: 命令行参数 > LDAP_BIND_USER服务账号 > config.py默认同步凭据
        """
        # 1. 优先使用服务账号（配置了LDAP_BIND_USER时）
        if LDAP_BIND_USER and LDAP_BIND_PASSWORD:
            self.stdout.write('使用服务账号绑定')
            return LDAP_BIND_USER, LDAP_BIND_PASSWORD
        # 2. 命令行参数覆盖默认值
        if username and password:
            bind_user = LDAP_USER_DN_TEMPLATE % {'user': username}
            self.stdout.write(f'使用指定账号绑定: {username}')
            return bind_user, password
        # 3. 使用config.py中的默认同步凭据
        if LDAP_SYNC_USERNAME and LDAP_SYNC_PASSWORD:
            bind_user = LDAP_USER_DN_TEMPLATE % {'user': LDAP_SYNC_USERNAME}
            self.stdout.write(f'使用默认同步账号绑定: {LDAP_SYNC_USERNAME}')
            return bind_user, LDAP_SYNC_PASSWORD
        # 4. 都没有配置
        self.stdout.write(self.style.ERROR(
            '错误: 请配置 LDAP_BIND_USER/LDAP_BIND_PASSWORD 或 LDAP_SYNC_USERNAME/LDAP_SYNC_PASSWORD，或通过 -u/-p 参数指定'))
        return None, None

    def _connect_ldap(self, bind_user, bind_password):
        """连接LDAP服务器"""
        try:
            server = Server(LDAP_SERVER, port=LDAP_PORT, use_ssl=LDAP_USE_SSL,
                          get_info=ALL, connect_timeout=10)
            conn = Connection(server, user=bind_user, password=bind_password, auto_bind=True)
            self.stdout.write(f'LDAP服务器: {LDAP_SERVER}:{LDAP_PORT} (SSL={LDAP_USE_SSL})')
            self.stdout.write(f'搜索基础: {LDAP_SEARCH_BASE}')
            self.stdout.write('绑定成功')
            return conn
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'LDAP绑定失败: {e}'))
            logger.error(f'LDAP绑定失败: {e}')
            return None

    def _fetch_all_users(self, conn):
        """分页查询所有LDAP用户"""
        search_filter = '(&(objectClass=user)(sAMAccountName=*))'
        all_entries = []
        page_num = 0
        cookie = True

        while cookie:
            page_num += 1
            conn.search(
                search_base=LDAP_SEARCH_BASE,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=['sAMAccountName', 'displayName', 'givenName', 'mail',
                           'telephoneNumber', 'distinguishedName'],
                paged_size=500,
                paged_cookie=cookie if cookie is not True else None,
            )
            page_count = len(conn.entries)
            self.stdout.write(f'  第 {page_num} 页: {page_count} 条记录')
            all_entries.extend(conn.entries)

            cookie = conn.result.get('controls', {}).get('1.2.840.113556.1.4.319', {}).get('value', {}).get('cookie')
            if not cookie:
                break

        return all_entries

    def _filter_users(self, all_entries):
        """过滤非人员账号"""
        all_users = []
        skipped_computer = 0
        skipped_excluded_ou = 0

        for entry in all_entries:
            try:
                info = extract_user_info(entry)
            except Exception:
                continue

            username = info.get('username', '')
            ou_hierarchy = info.get('ou_hierarchy', [])

            if username.endswith('$'):
                skipped_computer += 1
                continue

            if should_exclude(ou_hierarchy):
                skipped_excluded_ou += 1
                continue

            all_users.append(info)

        return all_users, {'computer': skipped_computer, 'excluded_ou': skipped_excluded_ou}

    def _print_preview(self, all_users):
        """打印用户预览列表"""
        self.stdout.write(f'\n{"序号":<5} {"用户名":<20} {"姓名":<15} {"邮箱":<30} {"部门OU层级"}')
        self.stdout.write('-' * 120)
        for idx, u in enumerate(all_users, 1):
            uname = u.get('username', '?')
            dname = u.get('name', u.get('nickname', '?'))
            email = u.get('email', '')
            ou_str = ' > '.join(u.get('ou_hierarchy', []))
            self.stdout.write(f'{idx:<5} {uname:<20} {dname:<15} {email:<30} {ou_str}')

    def _ensure_departments(self, dept_names):
        """确保部门层级存在，不存在则自动创建
        :return: (dept_obj, created_count)
        """
        if not dept_names:
            return None, 0

        parent_dept = None
        created_count = 0
        for idx, dept_name in enumerate(dept_names):
            if parent_dept:
                dept = Dept.objects.filter(name=dept_name, parent=parent_dept).first()
            else:
                dept = Dept.objects.filter(name=dept_name).filter(
                    models.Q(parent=None) | models.Q(parent=False)
                ).first()

            if not dept:
                create_kwargs = {
                    'name': dept_name,
                    'sort': idx + 1,
                    'status': 1,
                }
                if parent_dept:
                    create_kwargs['parent'] = parent_dept
                dept = Dept.objects.create(**create_kwargs)
                created_count += 1
                logger.info(f'LDAP同步自动创建部门: {dept_name} (父部门: {parent_dept.name if parent_dept else "无"})')

            parent_dept = dept

        return parent_dept, created_count

    def _sync_users(self, all_users):
        """执行用户同步"""
        # 预加载默认角色
        default_role = None
        if LDAP_DEFAULT_ROLE_KEY:
            default_role = Role.objects.filter(key=LDAP_DEFAULT_ROLE_KEY, status=1).first()
            if not default_role:
                self.stdout.write(self.style.WARNING(
                    f'警告: 未找到默认角色 key={LDAP_DEFAULT_ROLE_KEY}'))
            else:
                self.stdout.write(f'默认角色: {default_role.name} (key={default_role.key})')

        # 预加载本地已有用户（含大小写不敏感集合，避免大小写差异导致重复创建报错）
        existing_usernames = set(Users.objects.values_list('username', flat=True))
        existing_usernames_lower = {u.lower() for u in existing_usernames}
        self.stdout.write(f'本地已有用户数: {len(existing_usernames)}')

        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'dept_created': 0, 'errors': 0}

        self.stdout.write(f'\n开始同步...')
        for idx, user_data in enumerate(all_users, 1):
            username = user_data.get('username')
            if not username:
                stats['skipped'] += 1
                continue

            # 跳过系统内置管理员账号（admin/Admin，大小写不敏感），不参与同步
            if username.lower() == 'admin':
                self.stdout.write(f'  跳过系统管理员账号: {username}')
                stats['skipped'] += 1
                continue

            # 与库内已有账号仅大小写不同（如 LDAP 为 Admin、库内为 admin）时跳过，
            # 避免触发 username 唯一约束报错
            if username not in existing_usernames and username.lower() in existing_usernames_lower:
                self.stdout.write(f'  跳过大小写冲突账号: {username}（库内已有同名账号）')
                stats['skipped'] += 1
                continue

            ou_hierarchy = user_data.get('ou_hierarchy', [])

            # 确保部门层级存在
            target_dept, dept_created = self._ensure_departments(ou_hierarchy)
            stats['dept_created'] += dept_created

            if username in existing_usernames:
                # 用户已存在 - 更新部门和基本信息（不更新密码）
                try:
                    user = Users.objects.get(username=username)
                    need_save = False

                    if target_dept and user.dept_id != target_dept.id:
                        user.dept = target_dept
                        need_save = True

                    for field in ['name', 'email', 'mobile', 'nickname']:
                        val = user_data.get(field)
                        if val and not getattr(user, field, None):
                            setattr(user, field, val)
                            need_save = True

                    if need_save:
                        user.save()
                        stats['updated'] += 1
                    else:
                        stats['skipped'] += 1
                except Exception as e:
                    logger.error(f'更新用户失败 [{username}]: {e}')
                    stats['errors'] += 1
            else:
                # 新用户 - 创建
                try:
                    create_data = {
                        'username': username,
                        'password': make_password(str(uuid.uuid4())),
                        'name': user_data.get('name', username),
                        'identity': 2,
                        'is_staff': True,
                        'is_active': True,
                    }
                    if target_dept:
                        create_data['dept'] = target_dept
                    for field in ['email', 'mobile', 'nickname']:
                        val = user_data.get(field)
                        if val:
                            create_data[field] = val

                    new_user = Users.objects.create(**create_data)
                    if default_role:
                        new_user.role.add(default_role)
                    stats['created'] += 1
                    existing_usernames.add(username)
                    existing_usernames_lower.add(username.lower())
                except Exception as e:
                    logger.error(f'创建用户失败 [{username}]: {e}')
                    stats['errors'] += 1

            # 每50个用户输出一次进度
            if idx % 50 == 0:
                self.stdout.write(f'  进度: {idx}/{len(all_users)}')

        return stats

    def _sync_dept_info(self):
        """同步部门信息：仅填充空缺的负责人/电话/邮箱
        LDAP 未维护部门负责人等字段，owner/phone/email 由人工在部门管理界面维护。
        同步时仅当字段为空才自动填充候选值（取部门下第一个用户），
        非空字段（含手动维护的数据）一律跳过，避免被自动推断值覆盖。
        """
        updated_count = 0
        all_depts = Dept.objects.all()

        for dept in all_depts:
            # 三个字段均已有值（含手动维护），跳过
            if dept.owner and dept.phone and dept.email:
                continue

            # 查找该部门下第一个有 email 或 phone 的用户作为候选
            user = Users.objects.filter(dept=dept).exclude(
                models.Q(email='') | models.Q(email__isnull=True)
            ).order_by('create_datetime').first()

            if not user:
                # 没有有邮箱的用户，尝试找有手机的用户
                user = Users.objects.filter(dept=dept).exclude(
                    models.Q(mobile='') | models.Q(mobile__isnull=True)
                ).order_by('create_datetime').first()

            if not user:
                # 都没有，取第一个用户作为候选
                user = Users.objects.filter(dept=dept).order_by('create_datetime').first()

            if not user:
                continue

            need_save = False
            # 仅空值填充，非空（手动维护）不覆盖
            if not dept.owner:
                dept.owner = user.name or user.username
                need_save = True

            if not dept.phone and user.mobile:
                dept.phone = user.mobile
                need_save = True

            if not dept.email and user.email:
                dept.email = user.email
                need_save = True

            if need_save:
                dept.save()
                updated_count += 1

        if updated_count > 0:
            self.stdout.write(f'\n部门信息同步完成: 仅空值填充了 {updated_count} 个部门的负责人/电话/邮箱（手动维护的值不会被覆盖）')
        else:
            self.stdout.write('\n部门信息无需更新（已有值均未覆盖）')

        return updated_count

    def _sync_to_anythingllm(self, all_users):
        """将LDAP用户同步到 anythingllm PostgreSQL 的 public.users 表
        - 不存在的 username 新增记录（随机密码，用户首次登录时会被真实密码覆盖）
        - 已存在的 username 跳过，不覆盖密码（密码由登录时实时同步）
        """
        stats = {'inserted': 0, 'skipped': 0, 'errors': 0}

        try:
            conn = psycopg2.connect(
                host=ANYTHINGLLM_DB_HOST,
                port=ANYTHINGLLM_DB_PORT,
                dbname=ANYTHINGLLM_DB_NAME,
                user=ANYTHINGLLM_DB_USER,
                password=ANYTHINGLLM_DB_PASSWORD,
            )
            self.stdout.write(f'\n已连接 anythingllm PostgreSQL: {ANYTHINGLLM_DB_HOST}:{ANYTHINGLLM_DB_PORT}/{ANYTHINGLLM_DB_NAME}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'连接 anythingllm 数据库失败: {e}'))
            logger.error(f'连接 anythingllm 数据库失败: {e}')
            return stats

        try:
            cursor = conn.cursor()

            for user_data in all_users:
                username = user_data.get('username')
                if not username:
                    continue

                try:
                    # 检查用户是否已存在
                    cursor.execute(
                        'SELECT id FROM public.users WHERE username = %s',
                        (username,)
                    )
                    existing = cursor.fetchone()

                    if existing:
                        # 已存在 - 跳过，不覆盖密码（密码由登录时实时同步真实密码）
                        stats['skipped'] += 1
                    else:
                        # 不存在 - 新增（随机密码，用户首次登录时会被真实密码覆盖）
                        random_password = str(uuid.uuid4())
                        hashed_password = bcrypt.hashpw(
                            random_password.encode('utf-8'), bcrypt.gensalt()
                        ).decode('utf-8')
                        cursor.execute(
                            "INSERT INTO public.users (username, password, role) VALUES (%s, %s, 'default')",
                            (username, hashed_password)
                        )
                        stats['inserted'] += 1

                except Exception as e:
                    logger.error(f'同步用户到 anythingllm 失败 [{username}]: {e}')
                    stats['errors'] += 1

            conn.commit()
            self.stdout.write(f'anythingllm 同步完成: 新增={stats["inserted"]}, 跳过={stats["skipped"]}, 错误={stats["errors"]}')

        except Exception as e:
            conn.rollback()
            self.stdout.write(self.style.ERROR(f'anythingllm 同步事务失败: {e}'))
            logger.error(f'anythingllm 同步事务失败: {e}')
        finally:
            cursor.close()
            conn.close()

        return stats
