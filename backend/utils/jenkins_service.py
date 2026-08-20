"""
Jenkins API 服务类
用于与 Jenkins 进行交互，获取项目列表和触发构建
"""
import logging
import time
import requests
from urllib.parse import quote
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class JenkinsService:
    """Jenkins API 服务"""

    def __init__(self, base_url=None, username=None, password=None, timeout=None, connect_timeout=None):
        """
        初始化 Jenkins 服务

        Args:
            base_url: Jenkins 服务器地址
            username: Jenkins 用户名
            password: Jenkins 密码
            timeout: 读取超时秒数（默认取 config.JENKINS_READ_TIMEOUT=60；大项目列表接口响应慢，30 秒易超时）
            connect_timeout: 连接超时秒数（默认取 config.JENKINS_CONNECT_TIMEOUT=10；服务不可达时快速失败，
                避免 connect/read 共用同一超时导致每次请求拖满 60s、频繁点击时请求堆积）
        """
        from config import (JENKINS_BASE_URL, JENKINS_USERNAME, JENKINS_PASSWORD,
                            JENKINS_CONNECT_TIMEOUT, JENKINS_READ_TIMEOUT)

        self.base_url = base_url or JENKINS_BASE_URL
        self.username = username or JENKINS_USERNAME
        self.password = password or JENKINS_PASSWORD
        self.timeout = timeout if timeout is not None else JENKINS_READ_TIMEOUT
        self.connect_timeout = connect_timeout if connect_timeout is not None else JENKINS_CONNECT_TIMEOUT
        # 重试计数器（同一实例内累计，避免连续请求各自独立重试导致无限放大）：
        # 连接超时最多重试 1 次；读取超时/连接错误最多重试 2 次（指数退避）
        self._retry_connect = True
        self._retry_other = 0
        self.auth = HTTPBasicAuth(self.username, self.password) if self.username and self.password else None

        # 统一使用 Session：crumb 请求与写操作共享 cookie。
        # Jenkins 开启 "Use session to bind crumb" 时，crumb 与 session 绑定，
        # 不共享 cookie 会导致 POST 即使带正确 crumb 也返回 403。
        self.session = requests.Session()
        if self.auth:
            self.session.auth = self.auth

        # 移除末尾斜杠
        if self.base_url and self.base_url.endswith('/'):
            self.base_url = self.base_url.rstrip('/')

    @classmethod
    def for_user(cls, user):
        """
        使用用户真实身份（登录时缓存的 SSO 凭证）访问 Jenkins，构建人显示真实用户

        用户登录时密码会缓存到 Redis（key: lybbn-ldap-passwd-{user.id}），
        此处取出并用于 Jenkins 认证；无缓存凭证时回退默认账号（config.py）并记录警告。

        Args:
            user: 当前登录用户（Django User 对象）

        Returns:
            JenkinsService 实例
        """
        from config import JENKINS_USE_SSO_USER
        if JENKINS_USE_SSO_USER:
            username, password = cls.get_user_sso_credentials(user)
            if username and password:
                logger.info(f"使用用户真实身份访问 Jenkins: {username}")
                return cls(username=username, password=password)
            logger.warning(f"用户 {getattr(user, 'username', 'None')} 无 SSO 缓存凭证，回退默认账号触发构建")
        return cls()

    @staticmethod
    def get_user_sso_credentials(user):
        """
        读取用户登录时缓存的 SSO 凭证（Redis），无缓存时返回 (None, None)

        Args:
            user: Django User 对象

        Returns:
            (username, password) 或 (None, None)
        """
        if not user or not getattr(user, 'id', None):
            return None, None
        try:
            from django_redis import get_redis_connection
            redis_conn = get_redis_connection("singletoken")
            cache_key = f"lybbn-ldap-passwd-{user.id}"
            password = redis_conn.get(cache_key)
            if password:
                # 滑动续期：每次成功读取凭证后按配置有效期重新计时，
                # 活跃用户（触发构建/扫描等持续使用）的缓存不会过期
                try:
                    from config import JENKINS_SSO_CREDENTIAL_TTL
                    redis_conn.expire(cache_key, JENKINS_SSO_CREDENTIAL_TTL)
                except Exception as e:
                    logger.warning(f"刷新 SSO 凭证缓存有效期失败: user_id={getattr(user, 'id', None)}, 错误: {str(e)}")
            return (user.username, password) if password else (None, None)
        except Exception as e:
            logger.warning(f"读取用户 SSO 凭证失败: user_id={getattr(user, 'id', None)}, 错误: {str(e)}")
            return None, None

    @staticmethod
    def _build_error_message(method, url, error):
        """
        将 Jenkins API 异常转换为对用户友好的错误消息（技术细节保留在日志中）

        401（认证失败）与 403（权限不足）属于用户可预期的权限问题：
        - 非 LDAP 账号的凭证不是 AD 密码，Jenkins 认证必然返回 401；
        - 账号存在但无对应 Job 的构建权限时返回 403。
        直接抛出原始 "401 Client Error: Unauthorized" 会让用户无法理解，
        统一转换为明确的业务提示（日志中仍保留完整错误详情便于排查）。

        Args:
            method: HTTP 方法
            url: 请求 URL
            error: requests 异常对象（含 response 可获取状态码）

        Returns:
            对用户友好的错误消息字符串
        """
        resp = getattr(error, 'response', None)
        status_code = getattr(resp, 'status_code', None) if resp is not None else None
        if status_code == 401:
            return ('Jenkins 认证失败（401）：当前账号非 LDAP 账号或无 Jenkins 访问权限，'
                    '请使用 LDAP 账号登录后重试')
        if status_code == 403:
            return ('Jenkins 拒绝操作（403）：当前账号无 Jenkins 构建/操作权限，'
                    '请联系管理员授权')
        return f"Jenkins API 请求失败: {str(error)}"

    def _request(self, method, url, **kwargs):
        """
        发送 HTTP 请求到 Jenkins

        Args:
            method: HTTP 方法 (GET, POST)
            url: 请求 URL
            **kwargs: 其他请求参数

        Returns:
            requests.Response 对象
        """
        # Jenkins 2.204+ 默认启用 CSRF 保护，写操作需携带 crumb
        if method.upper() in ('POST', 'PUT', 'PATCH', 'DELETE'):
            crumb = self._get_crumb()
            if crumb:
                headers = kwargs.get('headers') or {}
                headers['Jenkins-Crumb'] = crumb
                kwargs['headers'] = headers

        try:
            response = self.session.request(method, url, timeout=(self.connect_timeout, self.timeout), **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.ConnectTimeout as e:
            # 连接阶段超时（服务不可达/网络异常）：快速失败，仅重试 1 次（短退避），
            # 避免服务不可达时反复重试拖满超时、多请求叠加形成请求队列积压
            if self._retry_connect:
                self._retry_connect = False
                logger.warning(f"Jenkins 连接超时，{self.connect_timeout}s 后重试: {method} {url}")
                time.sleep(1)
                try:
                    response = self.session.request(method, url, timeout=(self.connect_timeout, self.timeout), **kwargs)
                    response.raise_for_status()
                    return response
                except requests.exceptions.RequestException as e2:
                    resp = getattr(e2, 'response', None)
                    detail = resp.text[:300] if resp is not None else ''
                    logger.error(f"Jenkins API 请求失败(连接超时重试): {method} {url}, 错误: {str(e2)} {detail}")
                    raise Exception(self._build_error_message(method, url, e2))
            resp = getattr(e, 'response', None)
            detail = resp.text[:300] if resp is not None else ''
            logger.error(f"Jenkins API 请求失败: {method} {url}, 错误: {str(e)} {detail}")
            raise Exception(self._build_error_message(method, url, e))
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            # 读取超时/连接错误等瞬时故障：最多重试 2 次，退避间隔指数递增（1s/2s），
            # 避免 Jenkins 抖动时立即重试加剧请求堆积（大列表接口响应慢，偶发超时重试可显著提升成功率）
            retry_count = getattr(self, '_retry_other', 0)
            if retry_count < 2:
                self._retry_other = retry_count + 1
                backoff = 2 ** retry_count
                logger.warning(f"Jenkins 请求瞬时失败，{backoff}s 后重试: {method} {url}, 错误: {str(e)}")
                time.sleep(backoff)
                try:
                    response = self.session.request(method, url, timeout=(self.connect_timeout, self.timeout), **kwargs)
                    response.raise_for_status()
                    return response
                except requests.exceptions.RequestException as e2:
                    resp = getattr(e2, 'response', None)
                    detail = resp.text[:300] if resp is not None else ''
                    logger.error(f"Jenkins API 请求失败(重试): {method} {url}, 错误: {str(e2)} {detail}")
                    raise Exception(self._build_error_message(method, url, e2))
            resp = getattr(e, 'response', None)
            detail = resp.text[:300] if resp is not None else ''
            logger.error(f"Jenkins API 请求失败: {method} {url}, 错误: {str(e)} {detail}")
            raise Exception(self._build_error_message(method, url, e))
        # 附带 Jenkins 返回的错误详情，便于定位 403 原因
        except requests.exceptions.RequestException as e:
            resp = getattr(e, 'response', None)
            detail = resp.text[:300] if resp is not None else ''
            logger.error(f"Jenkins API 请求失败: {method} {url}, 错误: {str(e)} {detail}")
            raise Exception(self._build_error_message(method, url, e))

    def _get_crumb(self):
        """
        获取 Jenkins CSRF crumb（Jenkins 2.204+ 默认启用，写操作必需）

        Returns:
            crumb 字符串；Jenkins 未启用 CSRF 或获取失败时返回 None
        """
        url = f"{self.base_url}/crumbIssuer/api/json"
        try:
            # 使用与写操作相同的 session，确保 cookie 一致（crumb 与 session 绑定场景）；
            # 超时同样拆分为连接/读取两段，服务不可达时快速失败不拖累写操作
            response = self.session.get(url, timeout=(self.connect_timeout, self.timeout))
            if response.status_code == 404:
                # Jenkins 未启用 CSRF 保护
                return None
            response.raise_for_status()
            return response.json().get('crumb')
        except Exception as e:
            logger.warning(f"获取 Jenkins crumb 失败: {str(e)}")
            return None

    def get_projects(self, keyword='Personal'):
        """
        获取 Jenkins 项目列表（支持关键词过滤）

        Args:
            keyword: 项目名称关键词过滤

        Returns:
            项目列表 [{'name': 'xxx', 'url': 'xxx', 'color': 'xxx', 'lastBuild': {...}}]
            lastBuild 为 None 表示该任务从未构建过
        """
        # 批量携带 lastBuild 信息，一次请求即可获取所有任务的最新构建状态
        url = f"{self.base_url}/api/json?tree=jobs[name,url,color,lastBuild[number,building,result,url]]"

        try:
            response = self._request('GET', url)
            data = response.json()
            jobs = data.get('jobs', [])

            # 按关键词过滤
            if keyword:
                jobs = [job for job in jobs if keyword in job.get('name', '')]

            return jobs
        except Exception as e:
            logger.error(f"获取 Jenkins 项目列表失败: {str(e)}")
            raise

    def get_job(self, job_name):
        """
        精确获取 Jenkins 项目信息（复用 get_projects 全量列表后按名称精确匹配）

        Args:
            job_name: 项目名称

        Returns:
            项目信息 dict（含 lastBuild）；项目不存在返回 None
        """
        jobs = self.get_projects(keyword='')
        for job in jobs:
            if job.get('name') == job_name:
                return job
        logger.warning(f"Jenkins 中未找到项目: {job_name}")
        return None

    def get_package_scan_job(self, job_name=None):
        """
        获取包安全扫描项目信息及其构建参数（仅关注 package_path 参数）

        复用 get_job（精确匹配项目）与 get_job_parameters（构建参数），
        新增扫描项目时无需重复实现列表/参数接口，仅需在 config 中配置项目名。

        Args:
            job_name: 扫描项目名称（默认取 config.PACKAGE_SECURITY_SCAN_JOB）

        Returns:
            {
                'job': 项目信息 dict,
                'parameters': 全部构建参数列表,
                'package_path_param': package_path 参数定义（未定义时为 None）,
            }
            项目不存在时返回 None
        """
        from config import PACKAGE_SECURITY_SCAN_JOB

        job_name = job_name or PACKAGE_SECURITY_SCAN_JOB
        job = self.get_job(job_name)
        if not job:
            return None

        parameters = self.get_job_parameters(job_name)
        package_path_param = None
        for param in parameters:
            if param.get('name') == 'package_path':
                package_path_param = param
                break

        return {
            'job': job,
            'parameters': parameters,
            'package_path_param': package_path_param,
        }

    def get_build_artifact_content(self, job_name, build_number, filename_keyword=None, relative_path=None):
        """
        下载指定构建的制品文件内容（文本，如扫描报告 html）

        复用制品列表接口与 _request 下载；构建编号必传，避免误取其他构建的制品。

        Args:
            job_name: 任务名称
            build_number: 构建编号（必传，精确锁定本次构建的制品）
            filename_keyword: 制品文件名关键字（fileName 包含即匹配；与 relative_path 二选一）
            relative_path: 制品精确相对路径（优先于 filename_keyword）

        Raises:
            ValueError: build_number 缺失时抛出，防止拼出无效 URL 或误取其他构建制品

        Returns:
            制品文本内容；无匹配制品或下载失败返回 None
        """
        if not build_number:
            raise ValueError('get_build_artifact_content 缺少 build_number，必须指定具体构建编号')

        # 1. 获取构建制品列表
        url = f"{self.base_url}/job/{job_name}/{build_number}/api/json"
        params = {"tree": "artifacts[relativePath,fileName,displayPath]"}
        try:
            response = self._request('GET', url, params=params)
            artifacts = response.json().get('artifacts', [])
        except Exception as e:
            logger.error(f"获取构建制品列表失败: {job_name} #{build_number}, 错误: {str(e)}")
            raise

        # 2. 精确相对路径优先；否则按文件名关键字模糊匹配（顶层文件优先，与 package_info 解析策略一致）
        if relative_path:
            candidates = [a for a in artifacts if a.get('relativePath') == relative_path]
        elif filename_keyword:
            candidates = [a for a in artifacts if filename_keyword in a.get('fileName', '')]
            candidates.sort(key=lambda a: '/' in a.get('relativePath', ''))
        else:
            candidates = []

        # 3. 依次下载候选制品，返回首个成功下载的内容
        for artifact in candidates:
            download_url = (
                f"{self.base_url}/job/{job_name}/{build_number}/artifact/"
                f"{quote(artifact['relativePath'], safe='/')}"
            )
            try:
                content_resp = self._request('GET', download_url)
                return content_resp.text
            except Exception as e:
                logger.warning(f"下载制品失败: {download_url}, 错误: {str(e)}")
                continue

        logger.warning(f"构建 {job_name} #{build_number} 无匹配制品（keyword={filename_keyword}, path={relative_path}）")
        return None

    def get_job_parameters(self, job_name):
        """
        获取 Jenkins 任务的参数定义

        Args:
            job_name: 任务名称

        Returns:
            参数列表 [{'name': 'xxx', 'type': 'xxx', 'default_value': 'xxx', 'choices': [...]}]
        """
        url = f"{self.base_url}/job/{job_name}/api/json?tree=property[parameterDefinitions[name,type,defaultParameterValue[value],choices]]"

        try:
            response = self._request('GET', url)
            data = response.json()
            properties = data.get('property', [])

            parameters = []
            for prop in properties:
                param_defs = prop.get('parameterDefinitions', [])
                for param in param_defs:
                    param_info = {
                        'name': param.get('name'),
                        'type': param.get('type', 'StringParameterDefinition'),
                        'description': param.get('description', ''),
                        'default_value': param.get('defaultParameterValue', {}).get('value', '')
                    }
                    # 处理 ChoiceParameterDefinition 类型的 choices
                    if param.get('type') == 'ChoiceParameterDefinition' and param.get('choices'):
                        param_info['choices'] = param['choices']
                    parameters.append(param_info)

            return parameters
        except Exception as e:
            logger.error(f"获取 Jenkins 任务参数失败: {job_name}, 错误: {str(e)}")
            raise

    def trigger_build(self, job_name, parameters=None):
        """
        触发 Jenkins 构建

        Args:
            job_name: 任务名称
            parameters: 构建参数字典 {'param1': 'value1', 'param2': 'value2'}

        Returns:
            构建结果 {'build_number': xxx, 'build_url': 'xxx'}
        """
        if parameters:
            # 有参数时使用 buildWithParameters（参数通过 form data 传递）
            url = f"{self.base_url}/job/{job_name}/buildWithParameters"
            try:
                response = self._request('POST', url, data=parameters)
            except Exception as e:
                logger.error(f"触发 Jenkins 构建失败: {job_name}, 错误: {str(e)}")
                raise
        else:
            # 无参数时使用 build
            url = f"{self.base_url}/job/{job_name}/build"
            try:
                response = self._request('POST', url)
            except Exception as e:
                logger.error(f"触发 Jenkins 构建失败: {job_name}, 错误: {str(e)}")
                raise

        # 从响应头中获取构建信息
        location = response.headers.get('Location', '')
        build_number = None
        queue_item_id = None
        if location:
            # Location 格式：
            #   A) http://jenkins/job/xxx/12/queue/item/xxx/  -> 构建编号 12
            #   B) http://jenkins/queue/item/1139480/          -> queue item ID（排队中）
            parts = location.rstrip('/').split('/')
            try:
                queue_index = parts.index('queue')
                # 构建编号位于 'queue' 路径段前一位（需在 host 段之后，避免误解析）
                if queue_index >= 3:
                    build_number = int(parts[queue_index - 1])
            except (ValueError, IndexError):
                pass
            try:
                item_index = parts.index('item')
                queue_item_id = int(parts[item_index + 1])
            except (ValueError, IndexError):
                pass

        # 排队中（只有 queue item ID）时，查询 queue item 获取真实构建编号
        if build_number is None and queue_item_id:
            try:
                status = self.get_queue_item_status(queue_item_id)
                build_number = status.get('number')
            except Exception as e:
                logger.warning(f"查询 queue item 构建编号失败: {queue_item_id}, 错误: {str(e)}")

        return {
            'build_number': build_number,
            'build_url': location,
            'queue_item_id': queue_item_id,
        }

    @staticmethod
    def parse_queue_item_id(build_url):
        """从构建 URL 中解析 queue item ID（无法解析时返回 None）"""
        if not build_url:
            return None
        parts = build_url.rstrip('/').split('/')
        try:
            item_index = parts.index('item')
            return int(parts[item_index + 1])
        except (ValueError, IndexError):
            return None

    def get_queue_item_status(self, queue_item_id):
        """
        获取队列项状态（构建触发后排队时，用于解析真实构建编号）

        Args:
            queue_item_id: 队列项 ID

        Returns:
            {'number': 构建编号或 None(仍在排队), 'building': 是否已开始构建, 'queued': 是否仍在排队}
        """
        url = f"{self.base_url}/queue/item/{queue_item_id}/api/json"
        try:
            response = self._request('GET', url)
            data = response.json()
            executable = data.get('executable') or {}
            return {
                'number': executable.get('number'),
                'building': bool(executable),
                'queued': not bool(executable),
            }
        except Exception as e:
            logger.error(f"获取 queue item 状态失败: {queue_item_id}, 错误: {str(e)}")
            raise

    def get_job_latest_build(self, job_name):
        """
        获取任务最新构建信息（job view）

        触发构建后 queue item 在构建开始执行时即被 Jenkins 移除（再访问返回 404），
        此时无法通过 queue item 解析构建编号，改读 job view 的 lastBuild 信息，
        与 get_build_status 读取的是同一视图体系。

        Args:
            job_name: 任务名称

        Returns:
            最新构建信息 {'number': xxx, 'building': bool, 'result': 'SUCCESS'/None, 'timestamp': xxx}
            或 None（任务从未构建过）
        """
        url = f"{self.base_url}/job/{job_name}/api/json"
        params = {"tree": "lastBuild[number,building,result,timestamp]"}
        try:
            response = self._request('GET', url, params=params)
            last_build = response.json().get('lastBuild') or {}
            if not last_build.get('number'):
                return None
            return {
                'number': last_build.get('number'),
                'building': last_build.get('building', False),
                'result': last_build.get('result'),
                'timestamp': last_build.get('timestamp', 0),
            }
        except Exception as e:
            logger.error(f"获取 Jenkins 任务最新构建失败: {job_name}, 错误: {str(e)}")
            raise

    def get_build_status(self, job_name, build_number):
        """
        获取构建状态

        Args:
            job_name: 任务名称
            build_number: 构建编号

        Returns:
            构建状态信息 {'result': 'SUCCESS', 'building': False, 'duration': xxx}
        """
        url = f"{self.base_url}/job/{job_name}/{build_number}/api/json?tree=result,building,duration,timestamp"

        try:
            response = self._request('GET', url)
            data = response.json()
            return {
                'result': data.get('result'),  # SUCCESS, FAILURE, UNSTABLE, None(构建中)
                'building': data.get('building', False),
                'duration': data.get('duration', 0),
                'timestamp': data.get('timestamp', 0)
            }
        except Exception as e:
            logger.error(f"获取构建状态失败: {job_name} #{build_number}, 错误: {str(e)}")
            raise

    def get_build_console(self, job_name, build_number, offset=0):
        """
        获取构建控制台输出（支持增量拉取）
        
        Args:
            job_name: 任务名称
            build_number: 构建编号
            offset: 字节偏移量（与 Jenkins consoleText start 参数语义一致），\u003e0 时仅返回该偏移之后的新增内容
        
        Returns:
            控制台输出文本
        """
        url = f"{self.base_url}/job/{job_name}/{build_number}/consoleText"
        params = {'start': offset} if offset else None

        try:
            response = self._request('GET', url, params=params)
            return response.text
        except Exception as e:
            logger.error(f"获取构建日志失败: {job_name} #{build_number}, 错误: {str(e)}")
            raise

    def get_build_console_tail(self, job_name, build_number, max_lines=50, max_bytes=10240):
        """
        获取构建控制台输出的尾部内容（最新日志），避免全量传输超大日志

        实现：先通过 progressiveText 接口获取日志总字节数（X-Text-Size 响应头），
        若总大小超过 max_bytes 则仅拉取尾部片段，最后截取最后 max_lines 行。

        Args:
            job_name: 任务名称
            build_number: 构建编号
            max_lines: 返回的最大行数
            max_bytes: 允许拉取的最大字节数（超出时只拉尾部片段）

        Returns:
            日志尾部文本（最多 max_lines 行）
        """
        base_url = f"{self.base_url}/job/{job_name}/{build_number}/logText/progressiveText"

        try:
            # 第一次请求：获取日志总字节数（X-Text-Size 响应头）
            response = self._request('GET', base_url, params={'start': 0})
            total_size = response.headers.get('X-Text-Size')
            try:
                total_size = int(total_size) if total_size else None
            except (TypeError, ValueError):
                total_size = None

            # 总大小已知且超过阈值时，仅拉取尾部片段；X-Text-Size 缺失时直接用第一次响应截尾
            if total_size is not None and total_size > max_bytes:
                response = self._request('GET', base_url, params={'start': max(0, total_size - max_bytes)})

            lines = response.text.split('\n')
            return '\n'.join(lines[-max_lines:])
        except Exception as e:
            logger.error(f"获取构建日志尾部失败: {job_name} #{build_number}, 错误: {str(e)}")
            raise

    def get_build_package_info(self, job_name, build_number):
        """
        获取指定构建的 package_info 制品并解析包路径

        构建脚本会把构建信息写入名为 xx_package_info 的文本制品，内容为逐行
        key=value 格式，例如：
            BUILD_USER=Amy.Xing
            Branch=personal/xurongyan/dump_visual
            Package=/TestHub/GloryEX/.../xxx.tar.gz
            Package_sha256=/TestHub/.../xxx.tar.gz.sha256SUM
            Package_xml=/TestHub/.../xxx.xml

        Args:
            job_name: 任务名称
            build_number: 构建编号（必传，精确锁定本次构建的制品，
                禁止省略或传 lastSuccessfulBuild，避免误取其他构建的制品）

        Raises:
            ValueError: build_number 缺失时抛出，防止拼出无效 URL 或误取其他构建制品

        Returns:
            {
                'package_path': '/TestHub/.../xxx.tar.gz',   # Package= 对应的路径
                'package_info': {BUILD_USER, Branch, Package, ...},  # 完整 key=value 解析
                'artifact': {relativePath, fileName, displayPath},
            }
            无 package_info 制品时返回 None
        """
        # 构建编号必须精确指定：缺失时直接报错，避免拼出 None URL 或误用其他构建的制品
        if not build_number:
            raise ValueError('get_build_package_info 缺少 build_number，必须指定具体构建编号')

        # 1. 获取构建制品列表
        url = f"{self.base_url}/job/{job_name}/{build_number}/api/json"
        params = {"tree": "artifacts[relativePath,fileName,displayPath]"}
        try:
            response = self._request('GET', url, params=params)
            artifacts = response.json().get('artifacts', [])
        except Exception as e:
            logger.error(f"获取构建制品列表失败: {job_name} #{build_number}, 错误: {str(e)}")
            raise

        # 2. 查找 package_info 制品（优先顶层文件制品，目录制品可能命中但内容非目标文件）
        package_artifacts = [
            a for a in artifacts if 'package_info' in a.get('fileName', '')
        ]
        if not package_artifacts:
            logger.warning(f"构建 {job_name} #{build_number} 无 package_info 制品")
            return None
        # 顶层文件制品优先（relativePath 不含 '/'），目录制品（可能含子文件）排后
        package_artifacts.sort(key=lambda a: '/' in a.get('relativePath', ''))

        # 3. 依次下载制品内容，解析出有效 key=value 即返回（兼容目录制品/文件名差异）
        for package_artifact in package_artifacts:
            download_url = (
                f"{self.base_url}/job/{job_name}/{build_number}/artifact/"
                f"{quote(package_artifact['relativePath'], safe='/')}"
            )
            try:
                content_resp = self._request('GET', download_url)
                content = content_resp.text
            except Exception as e:
                logger.warning(f"下载 package_info 制品失败: {download_url}, 错误: {str(e)}")
                continue

            # 4. 逐行解析 key=value（精确匹配 'Package='，避免误匹配 Package_sha256/Package_xml）
            package_info = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                package_info[key.strip()] = value.strip()

            if package_info:
                return {
                    'package_path': package_info.get('Package', ''),
                    'package_info': package_info,
                    'artifact': package_artifact,
                }

        logger.warning(f"构建 {job_name} #{build_number} 的 package_info 制品内容为空或格式异常")
        return None

    def find_downstream_build_number(self, upstream_job, upstream_build, downstream_job, max_builds=10):
        """
        查找下游项目中由指定上游构建触发的构建编号（通过构建 cause 的上游关联）

        Jenkins 构建脚本内部触发下游构建（如 PhyBolt_Personal_Compile 构建过程中触发
        package_security_scan）时，系统侧没有触发记录，需按上游构建的触发关系
        （cause 中 upstreamProject/upstreamBuild）定位下游构建编号，用于扫描信息关联落库。

        Args:
            upstream_job: 上游项目名（如 PhyBolt_Personal_Compile）
            upstream_build: 上游构建编号（如 79）
            downstream_job: 下游项目名（如 package_security_scan）
            max_builds: 最多检查最近几个下游构建（默认 10）

        Returns:
            匹配的下游构建编号；未找到返回 None
        """
        if not upstream_job or not upstream_build or not downstream_job:
            return None
        url = f"{self.base_url}/job/{downstream_job}/api/json"
        params = {"tree": "builds[number,actions[causes[upstreamProject,upstreamBuild]]]"}
        try:
            response = self._request('GET', url, params=params)
            for build in (response.json().get('builds') or [])[:max_builds]:
                for action in build.get('actions') or []:
                    for cause in action.get('causes') or []:
                        if (cause.get('upstreamProject') == upstream_job
                                and cause.get('upstreamBuild') == upstream_build):
                            return build.get('number')
        except Exception as e:
            logger.warning(f"查找下游触发构建失败: {downstream_job} <- {upstream_job}#{upstream_build}, 错误: {str(e)}")
        return None
