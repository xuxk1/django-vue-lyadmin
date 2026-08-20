# -*- coding: utf-8 -*-

"""
LDAP认证工具模块
使用UPN格式直接绑定认证（username@domain）
"""

import logging
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException

from config import (
    LDAP_ENABLED,
    LDAP_SERVER,
    LDAP_PORT,
    LDAP_USE_SSL,
    LDAP_SEARCH_BASE,
    LDAP_USER_DN_TEMPLATE,
    LDAP_AUTO_CREATE_USER,
    LDAP_DEFAULT_ROLE_KEY,
    LDAP_BIND_USER,
    LDAP_BIND_PASSWORD,
)

logger = logging.getLogger(__name__)

# LDAP属性映射（本地用户字段 -> LDAP属性）
LDAP_ATTR_MAP = {
    'name': 'displayName',
    'email': 'mail',
    'mobile': 'telephoneNumber',
    'nickname': 'givenName',
}

# AD性别值 -> 本地性别值 (AD: 0/2=女/男, 本地: 0=女, 1=男)
AD_GENDER_MAP = {
    '2': 1,   # male -> 男
    '0': 0,   # female -> 女
    'M': 1,   # Male -> 男
    'F': 0,   # Female -> 女
}


class LDAPAuthenticator:
    """LDAP认证器"""

    def __init__(self):
        self.server = Server(
            LDAP_SERVER,
            port=LDAP_PORT,
            use_ssl=LDAP_USE_SSL,
            get_info=ALL,
            connect_timeout=5,
        )
        self.enabled = LDAP_ENABLED

    def authenticate(self, username, password):
        """
        LDAP认证入口（UPN直接绑定）
        :param username: 登录用户名
        :param password: 登录密码
        :return: (success: bool, user_attrs: dict or None)
        """
        if not self.enabled:
            return False, None

        if not username or not password:
            logger.warning("LDAP认证: 用户名或密码为空")
            return False, None

        try:
            user_dn = LDAP_USER_DN_TEMPLATE % {'user': username}
            logger.info(f"LDAP绑定认证, DN: {user_dn}")

            conn = Connection(self.server, user=user_dn, password=password, auto_bind=True)
            if conn.bound:
                user_attrs = self._fetch_user_attrs(conn, username, user_dn)
                conn.unbind()
                logger.info(f"LDAP认证成功: {username}")
                return True, user_attrs
            return False, None
        except LDAPException as e:
            logger.error(f"LDAP认证异常: {e}")
            return False, None
        except Exception as e:
            logger.error(f"LDAP认证未知错误: {e}")
            return False, None

    def _fetch_user_attrs(self, conn, username, user_dn):
        """从已绑定的连接中获取用户属性
        同时支持短用户名(sAMAccountName)和UPN(userPrincipalName)搜索
        """
        try:
            search_filter = f'(&(objectClass=user)(|(sAMAccountName={username})(userPrincipalName={user_dn})))'
            # 收集所有需要请求的LDAP属性
            ldap_attrs = set(LDAP_ATTR_MAP.values())
            ldap_attrs.update(['sAMAccountName', 'displayName', 'givenName', 'department', 'distinguishedName', 'userAccountControl'])
            conn.search(
                search_base=LDAP_SEARCH_BASE,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=list(ldap_attrs),
            )
            if conn.entries:
                entry = conn.entries[0]
                # 打印LDAP返回的原始属性（方便调试）
                try:
                    raw_attrs = {}
                    for attr_name in entry.entry_attributes:
                        try:
                            raw_attrs[attr_name] = str(entry[attr_name].value)
                        except Exception:
                            pass
                    logger.info(f"LDAP用户原始属性: {raw_attrs}")
                except Exception as e:
                    logger.debug(f"打印LDAP原始属性失败: {e}")
                user_attrs = self._entry_to_dict(entry)
                logger.info(f"LDAP属性映射结果: {user_attrs}")
                return user_attrs
        except Exception as e:
            logger.warning(f"LDAP获取用户属性失败: {e}")
        return {'username': user_dn}

    def _entry_to_dict(self, entry):
        """将LDAP entry转换为字典"""
        attrs = {}
        for local_field, ldap_attr in LDAP_ATTR_MAP.items():
            try:
                val = getattr(entry, ldap_attr, None)
                if val and val.value:
                    attrs[local_field] = str(val.value)
            except Exception:
                pass
        # 用户名
        try:
            if hasattr(entry, 'sAMAccountName') and entry.sAMAccountName.value:
                attrs['username'] = str(entry.sAMAccountName.value)
        except Exception:
            pass
        # 性别转换 (AD userAccountControl位标志 -> 本地: 0=女, 1=男)
        # AD标准: UF_NORMAL_ACCOUNT(0x200) + 性别位
        # 实际上AD不直接存储性别，这里从userAccountControl尝试解析
        try:
            uac_val = getattr(entry, 'userAccountControl', None)
            if uac_val and uac_val.value:
                uac = int(uac_val.value)
                # AD没有标准性别属性，这里暂时不映射
                pass
        except Exception:
            pass
        # 部门名称列表（优先department属性，为空则从DN解析所有OU）
        dept_names = []
        try:
            dept_val = getattr(entry, 'department', None)
            if dept_val and dept_val.value:
                dept_names.append(str(dept_val.value))
        except Exception:
            pass
        if not dept_names:
            try:
                dn = str(entry.entry_dn)
                # 从DN中解析所有OU作为候选部门名
                # 例: CN=徐小魁,OU=研发平台组,OU=研发效能部,OU=hzxingxin,DC=phlexing,DC=com
                ou_parts = [p.split('=', 1)[1] for p in dn.split(',') if p.strip().upper().startswith('OU=')]
                dept_names = ou_parts
                if dept_names:
                    logger.debug(f"从DN解析部门候选: {dept_names}")
            except Exception:
                pass
        if dept_names:
            attrs['department_names'] = dept_names
        return attrs


def ldap_authenticate(username, password):
    """
    LDAP认证便捷函数
    :param username: 登录用户名
    :param password: 登录密码
    :return: (success: bool, user_attrs: dict or None)
    """
    authenticator = LDAPAuthenticator()
    return authenticator.authenticate(username, password)


def get_or_create_ldap_user(username, user_attrs=None):
    """
    根据LDAP认证结果，在本地获取或创建用户
    :param username: 用户名
    :param user_attrs: LDAP返回的用户属性字典
    :return: (user, created) 用户对象和是否新建的标记
    """
    from mysystem.models import Users
    from django.contrib.auth.hashers import make_password
    import uuid

    user = Users.objects.filter(username=username).first()
    if user:
        # 用户已存在，LDAP认证成功则统一为普通用户
        need_save = False
        if user.identity != 2:
            user.identity = 2
            need_save = True
        if not user.is_active:
            user.is_active = True
            need_save = True
        if not user.is_staff:
            user.is_staff = True
            need_save = True
        # 更新LDAP属性（普通字段）
        if user_attrs:
            for local_field, value in user_attrs.items():
                if local_field in ('department_names',):
                    continue
                if hasattr(user, local_field) and value:
                    setattr(user, local_field, value)
                    need_save = True
            # 部门关联（依次匹配OU名称，找到第一个匹配的部门即停止）
            dept_names = user_attrs.get('department_names', [])
            if dept_names:
                from mysystem.models import Dept
                matched_dept = None
                for dn_name in dept_names:
                    matched_dept = Dept.objects.filter(name=dn_name, status=1).first()
                    if matched_dept:
                        break
                if matched_dept:
                    user.dept = matched_dept
                    need_save = True
                    logger.info("LDAP用户 {} 已关联部门: {} (匹配OU: {})".format(username, matched_dept.name, dn_name))
                else:
                    logger.warning("LDAP用户 {} 未在lyadmin_dept表中匹配到部门, 候选OU: {}".format(username, dept_names))
        if need_save:
            user.save()
            user.refresh_from_db()
            msg = "LDAP用户已同步更新: {}, name={}, email={}, mobile={}, nickname={}, gender={}, dept={}, identity={}".format(
                username, user.name, user.email, user.mobile, user.nickname, user.gender, user.dept_id, user.identity)
            logger.info(msg)
        # 确保用户有普通用户角色
        _assign_default_role(user)
        return user, False

    # 用户不存在，自动创建
    if not LDAP_AUTO_CREATE_USER:
        return None, False

    create_data = {
        'username': username,
        'password': make_password(str(uuid.uuid4())),  # 随机密码，LDAP用户不通过本地密码登录
        'name': username,
        'identity': 2,  # 前端用户（普通用户）
        'is_staff': True,
        'is_active': True,
    }
    # 应用LDAP属性映射
    simple_fields = ['name', 'email', 'mobile', 'nickname', 'gender']
    if user_attrs:
        for local_field, value in user_attrs.items():
            if value and local_field in simple_fields:
                create_data[local_field] = value

    user = Users.objects.create(**create_data)

    # 部门关联（依次匹配OU名称，找到第一个匹配的部门即停止）
    if user_attrs:
        dept_names = user_attrs.get('department_names', [])
        if dept_names:
            from mysystem.models import Dept
            matched_dept = None
            for dn_name in dept_names:
                matched_dept = Dept.objects.filter(name=dn_name, status=1).first()
                if matched_dept:
                    break
            if matched_dept:
                user.dept = matched_dept
                user.save(update_fields=['dept'])
                logger.info("LDAP用户 {} 已关联部门: {} (匹配OU: {})".format(username, matched_dept.name, dn_name))
            else:
                logger.warning("LDAP用户 {} 未在lyadmin_dept表中匹配到部门, 候选OU: {}".format(username, dept_names))

    # 分配默认角色
    _assign_default_role(user)
    msg = "LDAP用户自动创建成功: {}, name={}, email={}, mobile={}, nickname={}, gender={}, dept={}, identity={}".format(
        username, user.name, user.email, user.mobile, user.nickname, user.gender, user.dept_id, user.identity)
    logger.info(msg)
    return user, True


def _assign_default_role(user):
    """给用户分配普通用户角色"""
    if not LDAP_DEFAULT_ROLE_KEY:
        return
    try:
        from mysystem.models import Role
        role = Role.objects.filter(key=LDAP_DEFAULT_ROLE_KEY, status=1).first()
        if not role:
            logger.warning(f"未找到默认角色: {LDAP_DEFAULT_ROLE_KEY}，请在后台角色管理中创建该角色")
            return
        # 清除旧角色关联，分配新角色（自动写入lyadmin_users_role表）
        user.role.clear()
        user.role.add(role)
        logger.info(f"LDAP用户 {user.username} 已设置为普通用户角色: {role.name}")
    except Exception as e:
        logger.error(f"分配角色失败: {e}")


# ================================================= #
# ************** LDAP 批量同步用户  ************** #
# ================================================= #

def _get_service_connection():
    """使用服务账号连接LDAP
    :return: Connection对象，失败返回None
    """
    if not LDAP_BIND_USER or not LDAP_BIND_PASSWORD:
        logger.error("LDAP批量同步: 未配置服务账号(LDAP_BIND_USER/LDAP_BIND_PASSWORD)")
        return None
    try:
        server = Server(
            LDAP_SERVER,
            port=LDAP_PORT,
            use_ssl=LDAP_USE_SSL,
            get_info=ALL,
            connect_timeout=10,
        )
        conn = Connection(server, user=LDAP_BIND_USER, password=LDAP_BIND_PASSWORD, auto_bind=True)
        logger.info(f"LDAP服务账号绑定成功: {LDAP_BIND_USER}")
        return conn
    except Exception as e:
        logger.error(f"LDAP服务账号绑定失败: {e}")
        return None


def _parse_ou_from_dn(dn):
    """从DN中解析OU层级列表（从根到叶）
    例: CN=xxx,OU=研发平台组,OU=研发效能部,OU=hzxingxin,DC=phlexing,DC=com
    返回: ['hzxingxin', '研发效能部', '研发平台组']（从顶层到底层）
    """
    ou_parts = []
    for part in dn.split(','):
        part = part.strip()
        if part.upper().startswith('OU='):
            ou_parts.append(part.split('=', 1)[1])
    ou_parts.reverse()  # 反转为从根到叶的顺序
    return ou_parts


def _fetch_all_ldap_users(conn):
    """通过服务账号连接批量查询所有LDAP用户（支持分页）
    :param conn: LDAP Connection对象
    :return: 用户属性字典列表 [{username, name, email, ...}, ...]
    """
    ldap_attrs = list(set(LDAP_ATTR_MAP.values()))
    ldap_attrs.extend([
        'sAMAccountName', 'displayName', 'givenName',
        'department', 'distinguishedName', 'userAccountControl',
    ])
    ldap_attrs = list(set(ldap_attrs))

    all_users = []
    page_size = 500  # AD分页大小，不超过MaxPageSize(默认1000)
    cookie = True

    while cookie:
        conn.search(
            search_base=LDAP_SEARCH_BASE,
            search_filter='(&(objectClass=user)(sAMAccountName=*))',
            search_scope=SUBTREE,
            attributes=ldap_attrs,
            paged_size=page_size,
            paged_cookie=cookie if cookie is not True else None,
        )
        for entry in conn.entries:
            try:
                user_dict = _entry_to_dict_batch(entry)
                if user_dict and user_dict.get('username'):
                    all_users.append(user_dict)
            except Exception as e:
                logger.warning(f"解析LDAP entry失败: {e}")
                continue

        # 获取分页cookie
        cookie = conn.result.get('controls', {}).get('1.2.840.113556.1.4.319', {}).get('value', {}).get('cookie')
        if not cookie:
            break

    logger.info(f"LDAP批量查询完成，共获取 {len(all_users)} 个用户")
    return all_users


def _entry_to_dict_batch(entry):
    """将LDAP entry转换为字典（批量同步版本，包含DN解析）"""
    attrs = {}
    for local_field, ldap_attr in LDAP_ATTR_MAP.items():
        try:
            val = getattr(entry, ldap_attr, None)
            if val and val.value:
                attrs[local_field] = str(val.value)
        except Exception:
            pass
    # 用户名
    try:
        if hasattr(entry, 'sAMAccountName') and entry.sAMAccountName.value:
            attrs['username'] = str(entry.sAMAccountName.value)
    except Exception:
        pass
    # 从DN解析OU层级
    try:
        dn = str(entry.entry_dn)
        ou_parts = _parse_ou_from_dn(dn)
        if ou_parts:
            attrs['department_names'] = ou_parts
    except Exception:
        pass
    return attrs


def _ensure_departments(dept_names):
    """确保部门及子部门层级存在，不存在则自动创建
    :param dept_names: 部门名称列表，从顶层到底层，如 ['hzxingxin', '研发效能部', '研发平台组']
    :return: 最底层部门对象（即用户应关联的部门），如果dept_names为空返回None
    """
    from mysystem.models import Dept
    from django.db import models

    if not dept_names:
        return None

    parent_dept = None
    for idx, dept_name in enumerate(dept_names):
        if parent_dept:
            # 有父部门，在父部门下查找
            dept = Dept.objects.filter(name=dept_name, parent=parent_dept).first()
        else:
            # 顶层部门（parent为False/None均视为顶层）
            dept = Dept.objects.filter(name=dept_name).filter(
                models.Q(parent=None) | models.Q(parent=False)
            ).first()

        if not dept:
            # 部门不存在，自动创建
            create_kwargs = {
                'name': dept_name,
                'sort': idx + 1,
                'status': 1,
            }
            if parent_dept:
                create_kwargs['parent'] = parent_dept
            dept = Dept.objects.create(**create_kwargs)
            logger.info(f"LDAP同步自动创建部门: {dept_name} (父部门: {parent_dept.name if parent_dept else '无'})")

        parent_dept = dept

    return parent_dept  # 返回最底层部门


def ldap_sync_all_users():
    """LDAP批量同步所有用户到本地
    :return: dict 统计信息 {total, created, updated, skipped, dept_created}
    """
    from mysystem.models import Users, Dept
    from django.contrib.auth.hashers import make_password
    import uuid

    stats = {'total': 0, 'created': 0, 'updated': 0, 'skipped': 0, 'dept_created': 0}

    # 1. 使用服务账号连接LDAP
    conn = _get_service_connection()
    if not conn:
        return stats

    try:
        # 2. 批量查询所有用户
        all_users = _fetch_all_ldap_users(conn)
        stats['total'] = len(all_users)

        if not all_users:
            logger.warning("LDAP批量同步: 未查询到任何用户")
            return stats

        # 3. 预加载本地已有数据，减少数据库查询
        existing_users = {u['username']: u for u in Users.objects.values('id', 'username')}
        existing_depts = {}
        for dept in Dept.objects.filter(status=1).values('id', 'name', 'parent_id'):
            key = (dept['name'], dept['parent_id'])
            existing_depts[key] = dept

        # 4. 预加载默认角色
        default_role = None
        if LDAP_DEFAULT_ROLE_KEY:
            from mysystem.models import Role
            default_role = Role.objects.filter(key=LDAP_DEFAULT_ROLE_KEY, status=1).first()

        # 5. 逐个处理用户（使用事务批量操作）
        for user_data in all_users:
            username = user_data.get('username')
            if not username:
                stats['skipped'] += 1
                continue

            dept_names = user_data.get('department_names', [])

            # 5a. 确保部门层级存在
            target_dept = _ensure_departments(dept_names)

            if username in existing_users:
                # 用户已存在 - 仅更新部门和基本信息（不更新密码）
                user = Users.objects.get(id=existing_users[username]['id'])
                need_save = False

                # 更新部门
                if target_dept and user.dept_id != target_dept.id:
                    user.dept = target_dept
                    need_save = True

                # 更新基本属性
                for field in ['name', 'email', 'mobile', 'nickname']:
                    val = user_data.get(field)
                    if val and not getattr(user, field):
                        setattr(user, field, val)
                        need_save = True

                if need_save:
                    user.save()
                    stats['updated'] += 1
                else:
                    stats['skipped'] += 1
            else:
                # 新用户 - 批量创建
                create_data = {
                    'username': username,
                    'password': make_password(str(uuid.uuid4())),
                    'name': user_data.get('name', username),
                    'identity': 2,
                    'is_staff': True,
                    'is_active': True,
                    'dept': target_dept,
                }
                for field in ['email', 'mobile', 'nickname']:
                    val = user_data.get(field)
                    if val:
                        create_data[field] = val

                try:
                    new_user = Users.objects.create(**create_data)
                    # 分配默认角色
                    if default_role:
                        new_user.role.add(default_role)
                    stats['created'] += 1
                except Exception as e:
                    logger.error(f"LDAP同步创建用户失败 [{username}]: {e}")
                    stats['skipped'] += 1

        logger.info(
            f"LDAP批量同步完成: 总计={stats['total']}, "
            f"新建={stats['created']}, 更新={stats['updated']}, 跳过={stats['skipped']}"
        )
    finally:
        try:
            conn.unbind()
        except Exception:
            pass

    return stats
