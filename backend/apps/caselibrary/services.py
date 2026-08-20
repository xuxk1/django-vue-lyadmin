# -*- coding: utf-8 -*-

"""
GitLab 案例看板服务层（apps.caselibrary）

临时方案（越简单越好）：
1. 配置 GITLAB_CASE_BOARD_PAGE 指定本地 HTML 页面路径（Windows/Linux 均可）
2. 后端以固定账号（sqa）表单登录 GitLab 获取 session cookie
3. 读取接口直接返回本地 HTML 文件，并把页面内 GitLab 资源地址改写为
   代理地址，由后端携带 cookie 转发，页面即可免登录访问 GitLab 资源

【持久化规划】配置读取集中在 _load_gitlab_config / get_board_config 两个函数
（当前读取 config.py，为临时方案）；后续落库维护时仅需改这两个函数，
服务类与视图层无需改动。
"""

import logging
import mimetypes
import os
import re
import threading
import time

import requests

# 内网 GitLab 常为自签名证书，关闭 SSL 校验时抑制 urllib3 告警
try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
except Exception:
    pass

logger = logging.getLogger(__name__)


# ============================== 常量 ============================== #

# GitLab Web 界面导航路径特征（/-/blob 文件页、/-/tree 目录页、/-/commits 提交历史等）。
# 这类链接是"页面跳转"，应直接打开 GitLab 真实地址；而图片/JS/raw 等资源
# 仍须走代理（免登录加载），不在此列。
# 供 views.py 的代理接口复用（对导航路径返回 302 重定向到真实 GitLab）。
GITLAB_WEB_NAV_RE = re.compile(r'/-/(blob|tree|commits|blame|compare|pipelines)/', re.IGNORECASE)


# ============================== 共享登录态 ============================== #

# 进程级共享已登录 Session：浏览器并发加载页面资源时会产生大量并发请求，
# 若每个请求各自登录 GitLab，会触发并发登录限流/竞态（表现为"部分图片 200、
# 部分 502"）。所有 GitLabService 实例复用同一份登录态，只在 TTL 过期或
# 登录态失效时重新登录，且并发下只允许一个线程执行登录。
_shared_session = None
_shared_login_time = 0.0
_shared_lock = threading.RLock()


# ============================== 配置加载 ============================== #

def _load_gitlab_config():
    """
    加载 GitLab 连接配置（当前从 config.py 读取，临时方案）

    Returns:
        dict: {base_url, username, password, connect_timeout, read_timeout, cookie_ttl}
    """
    from config import (GITLAB_BASE_URL, GITLAB_USERNAME, GITLAB_PASSWORD,
                        GITLAB_CONNECT_TIMEOUT, GITLAB_READ_TIMEOUT,
                        GITLAB_COOKIE_TTL, GITLAB_LOGIN_MODE, GITLAB_DIRECT_LINK,
                        GITLAB_VERIFY_SSL, GITLAB_PROXY)
    return {
        'base_url': GITLAB_BASE_URL,
        'username': GITLAB_USERNAME,
        'password': GITLAB_PASSWORD,
        'connect_timeout': GITLAB_CONNECT_TIMEOUT,
        'read_timeout': GITLAB_READ_TIMEOUT,
        'cookie_ttl': GITLAB_COOKIE_TTL,
        'login_mode': GITLAB_LOGIN_MODE,
        'direct_link': GITLAB_DIRECT_LINK,
        'verify_ssl': GITLAB_VERIFY_SSL,
        'proxy': GITLAB_PROXY,
    }


def get_board_config():
    """
    加载案例看板页面配置（当前从 config.py 读取，临时方案）

    Returns:
        dict: {enabled, page, base_url}
    """
    from config import GITLAB_ENABLED, GITLAB_CASE_BOARD_PAGE
    return {
        'enabled': GITLAB_ENABLED,
        'page': GITLAB_CASE_BOARD_PAGE,
        'base_url': _load_gitlab_config()['base_url'],
    }


# ============================== 服务类 ============================== #

class GitLabService:
    """GitLab 登录与资源访问服务"""

    def __init__(self, base_url=None, username=None, password=None,
                 connect_timeout=None, read_timeout=None, cookie_ttl=None,
                 login_mode=None, verify_ssl=None, proxy=None, direct_link=None):
        cfg = _load_gitlab_config()
        self.base_url = (base_url or cfg['base_url']).rstrip('/')
        self.username = username or cfg['username']
        self.password = password or cfg['password']
        self.connect_timeout = connect_timeout if connect_timeout is not None else cfg['connect_timeout']
        self.read_timeout = read_timeout if read_timeout is not None else cfg['read_timeout']
        self.cookie_ttl = cookie_ttl if cookie_ttl is not None else cfg['cookie_ttl']
        self.login_mode = login_mode or cfg['login_mode']
        self.direct_link = cfg['direct_link'] if direct_link is None else direct_link
        self.verify_ssl = cfg['verify_ssl'] if verify_ssl is None else verify_ssl
        self.proxy = cfg['proxy'] if proxy is None else proxy

        # 登录态为进程级共享（见模块级 _shared_* 变量），实例本身不缓存登录态

    # ============================== 登录 ============================== #

    def _login(self):
        """
        以表单方式登录 GitLab，获取带 _gitlab_session cookie 的 Session

        GitLab 表单登录流程：
        1. GET /users/sign_in 获取页面内嵌的 authenticity_token（CSRF 令牌）
        2. POST /users/sign_in 提交 user[login] / user[password]
        3. 成功后 session 持有 _gitlab_session cookie
        """
        sess = requests.Session()
        sess.verify = self.verify_ssl
        if self.proxy:
            sess.proxies = {'http': self.proxy, 'https': self.proxy}
        success = False
        try:
            # 1. 获取登录页与 CSRF 令牌
            resp = sess.get(f'{self.base_url}/users/sign_in', timeout=(self.connect_timeout, self.read_timeout))
            resp.raise_for_status()
            html = resp.text

            # 2. 检测 SSO/LDAP 登录表单（GitLab 集成 LDAP/SSO 后，登录页会出现
            #    action 指向 /users/auth/<provider>/callback 的 OmniAuth 表单，
            #    LDAP 用户必须走该端点，标准 /users/sign_in 仅接受本地库用户）
            sso_action, sso_token = self._find_sso_form(html)
            mode = self.login_mode
            if mode == 'auto' and sso_action:
                mode = 'sso'

            if mode == 'sso':
                resp = self._login_via_sso(sess, sso_action, sso_token)
            else:
                resp = self._login_via_form(sess, html)

            # 3. 校验登录结果：须持有 _gitlab_session 且不再停留在登录页
            if '_gitlab_session' not in sess.cookies.get_dict():
                raise Exception('登录成功但未获取到 _gitlab_session cookie（可能账号密码错误）')
            if resp.url.rstrip('/').endswith('/users/sign_in'):
                # GitLab 登录被拒时页面会带 flash alert（如 Invalid login or password / Your account is blocked），
                # 解析出来拼进错误信息，便于区分是凭据错误还是账号被禁用
                alert = self._extract_alert(resp.text)
                raise Exception('登录失败：仍停留在登录页（账号或密码错误，或账号被禁用）' + (f'。GitLab 提示: {alert}' if alert else ''))

            success = True
            logger.info(f"GitLab 登录成功: {self.username} @ {self.base_url} (mode={mode}, pid={os.getpid()})")
            return sess
        except requests.exceptions.ConnectionError:
            raise Exception(f'无法连接 GitLab 服务器: {self.base_url}，请检查网络')
        except requests.exceptions.Timeout:
            raise Exception(f'GitLab 服务器响应超时: {self.base_url}')
        except requests.exceptions.HTTPError as e:
            raise Exception(f'GitLab 登录请求失败 (HTTP {e.response.status_code if e.response else "?"})')
        finally:
            if not success:
                sess.close()

    def _find_sso_form(self, html):
        """
        从登录页中查找 OmniAuth SSO/LDAP 登录表单

        GitLab 集成 LDAP/SAML/CAS 后，登录页会出现 action 指向
        /users/auth/<provider>/callback 的表单；LDAP 用户只能通过该端点认证。

        Returns:
            (action, authenticity_token)：找到返回表单提交地址与表单内 CSRF 令牌，
            未找到返回 (None, None)
        """
        providers = []
        for m in re.finditer(r'<form\b[^>]*>([\s\S]*?)</form>', html, flags=re.IGNORECASE):
            block = m.group(0)
            action_m = re.search(r'action=["\']([^"\']*users/auth/([a-zA-Z0-9_]+)/callback[^"\']*)["\']', block)
            if not action_m:
                continue
            token_m = re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', block)
            providers.append((action_m.group(2), action_m.group(1),
                              token_m.group(1) if token_m else ''))
        if not providers:
            return None, None
        # 优先 LDAP provider（ldapmain / ldapsecondary 等）；否则取第一个 SSO 端点
        for provider, action, token in providers:
            if 'ldap' in provider.lower():
                return action, token
        return providers[0][1], providers[0][2]

    def _login_via_sso(self, sess, sso_action, sso_token):
        """
        通过 OmniAuth SSO/LDAP 端点登录（GitLab: POST /users/auth/<provider>/callback）

        LDAP provider 表单字段为 username/password（OmniAuth LDAP 约定），
        与标准表单的 user[login]/user[password] 不同。
        """
        if not sso_action:
            raise Exception('登录方式为 SSO 但登录页未找到 users/auth/<provider>/callback 表单，'
                            '请确认 GitLab 已启用 LDAP/SSO 集成，或调整 GITLAB_LOGIN_MODE 配置')
        logger.info(f"GitLab SSO 登录端点: {sso_action}")
        resp = sess.post(
            f'{self.base_url}{sso_action}',
            data={
                'authenticity_token': sso_token,
                'username': self.username,
                'password': self.password,
            },
            allow_redirects=True,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        resp.raise_for_status()
        return resp

    def _login_via_form(self, sess, html):
        """通过标准登录表单提交（本地库用户）"""
        match = re.search(r'name="authenticity_token"[^>]*value="([^"]+)"', html)
        auth_token = match.group(1) if match else ''
        if not auth_token:
            raise Exception('登录页未找到 authenticity_token，可能登录方式已变更或页面无法访问')
        resp = sess.post(
            f'{self.base_url}/users/sign_in',
            data={
                'authenticity_token': auth_token,
                'user[login]': self.username,
                'user[password]': self.password,
                'user[remember_me]': '1',
            },
            allow_redirects=True,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        resp.raise_for_status()
        return resp

    def _extract_alert(self, html):
        """提取 GitLab 登录页 flash alert 文本（登录被拒的具体原因）"""
        patterns = [
            r'<div[^>]*class="[^"]*(?:alert|flash)[^"]*"[^>]*>([\s\S]*?)</div>',
            r'data-testid="[^"]*alert[^"]*"[^>]*>([\s\S]*?)</',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                text = re.sub(r'<[^>]+>', ' ', m.group(1))
                text = re.sub(r'\s+', ' ', text).strip()
                if text:
                    return text[:200]
        return ''

    def _login_with_retry(self):
        """
        登录失败时短暂退避后重试一次

        GitLab/LDAP 认证存在间歇性失败（LDAP 连接抖动、限流等），
        直接失败会导致整批并发请求 502。退避重试可吸收这类抖动，
        让首波并发请求一次全部成功，避免依赖浏览器/页面的二次请求。
        """
        try:
            return self._login()
        except Exception as first_exc:
            logger.warning(f"GitLab 首次登录失败，1s 后重试: {first_exc}")
            time.sleep(1.0)
            return self._login()

    def get_session(self):
        """
        获取已登录的 Session（进程级共享，线程安全），cookie 过期时自动重新登录

        Returns:
            requests.Session（已登录）
        """
        global _shared_session, _shared_login_time
        with _shared_lock:
            if _shared_session and (time.time() - _shared_login_time) < self.cookie_ttl:
                return _shared_session
            sess = self._login_with_retry()
            _shared_session = sess
            _shared_login_time = time.time()
            return sess

    def _force_relogin(self):
        """
        强制重新登录（登录态失效时调用）

        并发下多个请求可能同时发现失效，只允许第一个线程重新登录，
        其余线程复用其刷新后的 Session，避免重复登录触发 GitLab 限流。
        """
        global _shared_session, _shared_login_time
        with _shared_lock:
            if _shared_session and (time.time() - _shared_login_time) < self.cookie_ttl:
                return _shared_session
            if _shared_session:
                try:
                    _shared_session.close()
                except Exception:
                    pass
                _shared_session = None
            sess = self._login_with_retry()
            _shared_session = sess
            _shared_login_time = time.time()
            return sess

    # ============================== GitLab 资源请求 ============================== #

    def _is_session_expired(self, response):
        """判断响应是否表明登录态失效（401/403 或跳转回登录页）"""
        return response.status_code in (401, 403) or \
            response.url.rstrip('/').endswith('/users/sign_in')

    def fetch(self, path, rewrite_domain=True):
        """
        携带 sqa 登录 cookie 请求 GitLab 资源（登录态失效自动重新登录并重试一次）

        Args:
            path: GitLab 相对路径（以 / 开头），如 /api/v4/projects/casehub/...
            rewrite_domain: 文本类内容是否将 GitLab 域名改写为代理地址
                （默认 True；二进制内容自动跳过改写）

        Returns:
            (status_code, content_type, content_bytes)
        """
        if not path.startswith('/'):
            path = '/' + path
        url = f'{self.base_url}{path}'

        try:
            response = self.get_session().get(
                url, timeout=(self.connect_timeout, self.read_timeout))
            # 登录态失效：重新登录后重试一次
            if self._is_session_expired(response):
                logger.warning(f"GitLab 登录态失效，重新登录后重试: GET {url}")
                self._force_relogin()
                response = self.get_session().get(
                    url, timeout=(self.connect_timeout, self.read_timeout))
        except requests.exceptions.ConnectionError:
            raise Exception(f'无法连接 GitLab 服务器: {self.base_url}')
        except requests.exceptions.Timeout:
            raise Exception(f'GitLab 请求超时: {path}')

        content_type = response.headers.get('Content-Type', '') or 'application/octet-stream'
        content = response.content
        base_type = content_type.split(';')[0].strip().lower()

        # 文本类内容改写 GitLab 域名 → 代理地址，使页面内资源请求自动走后端代理
        if rewrite_domain and (
            base_type.startswith('text/') or
            base_type in ('application/json', 'application/javascript', 'application/xml',
                          'application/x-javascript', 'application/wasm', 'image/svg+xml')
        ):
            content = self._rewrite_domain(content.decode('utf-8', errors='replace')).encode('utf-8')

        return response.status_code, content_type, content

    # ============================== 本地文件读取 ============================== #

    def fetch_local(self, path):
        """
        直接读取本地文件（页面本身或其同目录资源），
        文本类内容同样改写 GitLab 域名为代理地址

        Args:
            path: 本地文件绝对路径

        Returns:
            (status_code, content_type, content_bytes)
        """
        if not os.path.isfile(path):
            raise Exception(f'文件不存在: {path}')
        with open(path, 'rb') as f:
            content = f.read()
        content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        base_type = content_type.split(';')[0].strip().lower()
        if (
            base_type.startswith('text/') or
            base_type in ('application/json', 'application/javascript', 'application/xml',
                          'application/x-javascript', 'application/wasm', 'image/svg+xml')
        ):
            content = self._rewrite_domain(content.decode('utf-8', errors='replace')).encode('utf-8')
        return 200, content_type, content

    def _rewrite_domain(self, text):
        """
        将文本内容中的 GitLab 域名改写为代理地址

        兼容三种书写形式（防止替换后产生异常 URL）：
        - http://host/path    → /api/caseboard/proxy/?path=/path
        - https://host/path   → /api/caseboard/proxy/?path=/path
        - //host/path（协议相对）→ /api/caseboard/proxy/?path=/path
        """
        proxy_prefix = self.get_proxy_prefix()
        host = self.base_url.split('://', 1)[-1]
        # 完整 URL：http(s)://host/path（协议与域名整体替换，避免残留 https:// 前缀）
        text = re.sub(
            r'https?://%s(?=/|$)' % re.escape(host),
            proxy_prefix, text, flags=re.IGNORECASE)
        # 协议相对地址：//host/path
        text = text.replace('//' + host, proxy_prefix)
        # 导航链接还原为真实 GitLab 地址（开启直接跳转时）
        if self.direct_link:
            text = self._restore_nav_links(text)
        return text

    def _restore_nav_links(self, text):
        """
        将 <a href> 中已被改写的 GitLab Web 导航链接还原为真实地址

        页面内"GitLab 案例目录"这类链接（/-/blob、/-/tree 等）是页面跳转入口，
        点击后应直接打开 GitLab 对应页面；而图片/raw/JS 等资源链接保持代理
        （iframe 内免登录加载）。仅还原 <a href>，不影响其他资源引用。
        """
        proxy_prefix = self.get_proxy_prefix()

        def _restore(m):
            href = m.group(1)
            if href.startswith(proxy_prefix):
                path = href[len(proxy_prefix):]
                if GITLAB_WEB_NAV_RE.search(path):
                    return f'href="{self.base_url}{path}"'
            return m.group(0)

        return re.sub(r'href="([^"]*)"', _restore, text, flags=re.IGNORECASE)

    # ============================== 工具 ============================== #

    @staticmethod
    def get_proxy_prefix():
        """代理接口前缀（页面内 GitLab 地址被改写为该前缀）"""
        return '/api/caseboard/proxy/?path='
