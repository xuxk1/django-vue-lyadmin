import os
from datetime import timedelta
from application.settings import BASE_DIR
# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ================================================= #
# ************** mysql数据库 配置  ************** #
# ================================================= #
# 数据库地址
DATABASE_ENGINE = "django.db.backends.mysql"
# 数据库地址
DATABASE_HOST = "127.0.0.1"
# 数据库端口
DATABASE_PORT = 3306
# 数据库用户名
DATABASE_USER = "root"
# 数据库密码
DATABASE_PASSWORD = "root123456"
# 数据库名
DATABASE_NAME = "lyadmin_db"
#数据库编码
DATABASE_CHARSET = "utf8mb4"
# SSL开关
DATABASE_SSL = False
# 连接超时时间
DATABASE_CONNECT_TIMEOUT = 30
# 数据库读取超时时间
DATABASE_TIMEOUT_READ = 60
# 数据库写入超时时间
DATABASE_TIMEOUT_WRITE = 60
# 数据库长连接时间（默认为0，单位秒）即每次请求都重新连接,debug模式下该值应该写为0 ，mysql默认长连接超时时间为8小时
DATABASE_CONN_MAX_AGE = 0 #推荐120（2分钟），使用 None 则是无限的持久连接（不推荐）。

# ================================================= #
# ************** redis 配置  ************** #
# ================================================= #

REDIS_PASSWORD = ''
REDIS_HOST = '127.0.0.1'
REDIS_PORT = '6379'
REDIS_URL = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}'

# ================================================= #
# ************** 远程服务器登录 配置  ************** #
# ================================================= #

SSH_HOST = '172.11.130.25'
SSH_USER = 'sqa'
SSH_PASSWORD = 'Phlexing_2019'
SSH_KEY_FILE = '/users/G01/efficiency_portal/.ssh/id_rsa'
SSH_REMOTE_TEMPLATE_DIR = '/TestHub/sqa/Platform/license'
SSH_REMOTE_SCRIPT_PATH= '/users/G01/efficiency_portal/xxk/lmcrypt_new'

# ================================================= #
# ************** 邮件 配置  ************** #
# ================================================= #

# 远程服务器邮件（正式使用）
MAIL_SMTP_SERVER = "mail.xingphle.com"
MAIL_PORT = 25
MAIL_USER = "systemmail@xingphle.com"
MAIL_PASSWORD = "YueMing#560"
# QQ 邮箱（仅临时测试用，需要时注释上方配置并取消下方注释）
# MAIL_SMTP_SERVER = "smtp.qq.com"
# MAIL_PORT = 465
# MAIL_USER = "962199374@qq.com"
# MAIL_PASSWORD = "lpiixjpekitgbdhj"
# 是否使用 SSL 隐式加密连接：默认由程序根据 MAIL_PORT 自动判断（465 为 SSL）；
# 如需强制指定，可手动添加 MAIL_USE_SSL = True/False 覆盖默认行为
MAIL_TIMEOUT = 30  # SMTP 连接超时时间（秒）
MAIL_MAX_RETRIES = 3  # 连接/发送失败最大重试次数
MAIL_RETRY_DELAY = 5  # 重试间隔时间（秒）
MAIL_RECIPIENT = "xuxiaokui"
MAIL_CC = "xuxiaokui"
MAIL_INTERNAL_CC = "xuxiaokui"
# 审批流程通知邮件默认抄送人（账号，不含域名；置空字符串则不抄送）
MAIL_WORKFLOW_CC = "xuxiaokui"

# 审批流邮件通知测试模式：
# True 时，所有审批邮件统一发送到 MAIL_TEST_RECIPIENT（方便测试验证）
# False 时，按实际待审批人的邮箱发送（正式使用请设为 False）
MAIL_TEST_MODE = True
MAIL_TEST_RECIPIENT = "xuxiaokui@phlexing.com"

# 审批邮件中前端跳转地址（用于"前往审批"按钮跳转，与后端服务地址 DOMAIN_HOST 分离）
MAIL_WEB_HOST = "http://127.0.0.1:8080"

# License邮件抄送规则配置
# 内部申请时，当ScopeApplication字段的值为以下值时，使用MAIL_INTERNAL_CC进行抄送
LICENSE_INTERNAL_CC_SCOPES = [
    '公司内部测试使用',
    '客户现场使用',
    '需要IT安装到公司服务器',
]

# ================================================= #
# ************** 服务器基本 配置  ************** #
# ================================================= #
DEBUG = True #是否调试模式
IS_DEMO = False #是否演示模式（演示模式只能查看无法保存、编辑、删除、新增）
IS_SINGLE_TOKEN = False #是否只允许单用户单一地点登录(只有一个人在线上)(默认多地点登录),只针对后台用户生效
ALLOW_FRONTEND = True#是否关闭前端API访问
FRONTEND_API_LIST = ['/api/app/','/api/xcx/','/api/h5/']#微服务前端接口前缀
DOMAIN_HOST = "http://127.0.0.1:8000"
EXEC_LOG_PATH =  os.path.join(BASE_DIR, 'logs','lybbnexec.log')
TEMP_EXEC_PATH =  os.path.join(BASE_DIR, 'logs')

# ================================================= #
# ************** 极光推送 配置  ************** #
# ================================================= #

JIGUANG_APPKEY = "141990xxxx"
JIGUANG_SECRET = "b26b91xxxxxxxxxxxxxxxx"

# ================================================= #
# ************** 快递100 配置  ************** #
# ================================================= #

KUAIDI100_KEY = "xxx" # 客户授权key
KUAIDI100_CUSTOMER = "xxx" #查询公司编号

# ================================================= #
# ************** 字节跳动（抖音）小程序 配置  ************** #
# ================================================= #
#小程序appid
TT_XCX_APPID = "xxxxxxxxxxxxx"
#小程序秘钥
TT_XCX_APPSECRET = "xxxxxxxxxxxxxxxxxx"

# ================================================= #
# ************** 微信小程序 配置  ************** #
# ================================================= #
#小程序appid
WX_XCX_APPID = "xxxxxxxxxxxxxxxxxx"
#小程序秘钥
WX_XCX_APPSECRET = "xxxxxxxxxxxxxxxxxxxxxx"

# ================================================= #
# ************** 微信开放平台（服务号） 配置  ************** #
# ================================================= #

#微信公众平台申请的appid
WX_GZPT_APPID = "XXXXXXXXXXXXXX"
#微信公众平台申请的appsecret
WX_GZPT_APPSECRET = "XXXXXXXXXXXXXXXXXXXXXXXX"

# ================================================= #
# ************** 微信公众号（服务号） 配置  ************** #
# ================================================= #
#微信官网测试公众号申请：http://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login
#微信公众号appid
WX_GZH_APPID = "xxxxxxxxxxxxxxxxx"
#微信公众号秘钥
WX_GZH_APPSECRET = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
#微信公众号--服务器配置：服务器域名
WX_GZH_DOMAIN = "http://django-vue-lyadmin.lybbn.cn/"
#微信公众号--服务器配置：TOKEN
WX_GZH_TOKEN = "django-vue-lyadmin"
# #微信公众号——证书路径
# # WX_GZH_KEYSPATH = os.path.join(BASE_DIR, 'keys')
# # WX_GZH_MCH_CERT= os.path.join(WX_GZH_KEYSPATH, r"apiclient_cert.pem"),
# # WX_GZH_MCH_KEY= os.path.join(WX_GZH_KEYSPATH, r"apiclient_key.pem"),

# ================================================= #
# ************** 阿里云发送短信 配置  ************** #
# ================================================= #
# ACCESS_KEY_ID/ACCESS_KEY_SECRET 根据实际申请的账号信息进行替换
ALIYUN_SMS_ACCESS_KEY_ID = "xxxxxxxxxxxxx"
ALIYUN_SMS_ACCESS_KEY_SECRET = "xxxxxxxxxxxxxxxxxxxxxxx"
ALIYUN_SMS_SIGN='xxx'#短信签名名称
ALIYUM_SMS_TEMPLATE='SMS_221xxxxx'#模板code

# ================================================= #
# ************** 腾讯云发送短信 配置  ************** #
# ================================================= #
# SECRETID/SECRETKEY 根据实际申请的账号信息进行替换
TENCENT_SMS_SECRETID = "xxxxxxxxxxxxxxxxxxxxxxxx"#CAM ID
TENCENT_SMS_SECRETKEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"#CAM密匙
TENCENT_SMS_APPID = "14003xxxxx"#SdkAppId
TENCENT_SMS_SIGN='lybbn测试名称'#短信签名名称
TENCENT_SMS_TEMPLATE_ID='65xxxx'#模板id

# ================================================= #
# ************** 微信支付 配置  ************** #
# ================================================= #
"""
发起企业付款时需携带的证书
登录微信商户平台(pay.weixin.qq.com)-->账户设置-->API安全-->证书下载
下载apiclient_cert.p12
python无法使用双向证书，使用openssl导出：(从微信下载的证书已经有pem，无需再使用openssl导出操作)
    openssl pkcs12 -clcerts -nokeys -in apiclient_cert.p12 -out apiclient_cert.pem
    openssl pkcs12 -nocerts -in apiclient_cert.p12 -out apiclient_key.pem
导出apiclient_key.pem时需输入PEM phrase, 此后每次发起请求均要输入，可使用openssl解除：
    openssl rsa -in apiclient_key.pem -out apiclient_key.pem.unsecure
"""

# 微信支付相关
WXPAY_APPID = 'wx023axxxxxx'#微信小程序支付（'微信分配的公众账号ID'\申请商户号的appid或商户号绑定的appid）
WXPAY_APPID_APP = 'wxc5155xxxxx'#'微信app支付（app支付为开放平台申请的appid）
WXPAY_MCHID = 'xxxxxxxxxxxx'#'商户号'
WXPAY_APIKEY = 'C1098Dxxxxxxxxx0978A8F4B291C1'#v3
WXPAY_SERIAL_NO = "7367035E134xxxxxxxxxFED20C5071E83341"#商户号证书序列号，登录商户平台【API安全】->【API证书】->【查看证书】，可查看商户API证书序列号

# 服务器存放证书路径（微信支付签发的）
WXPAY_CLIENT_CERT_PATH = os.path.join(BASE_DIR, 'key', 'apiclient_cert.pem')
WXPAY_CLIENT_KEY_PATH = os.path.join(BASE_DIR, 'key', 'apiclient_key.pem')

WXPAY_CERT_DIR = os.path.join(BASE_DIR, 'key')#微信支付证书缓存路径
WXPAY_CERT_DIR_RESPONSE = os.path.join(WXPAY_CERT_DIR, 'wechatpay_response_key')#微信支付证书缓存路径

# ================================================= #
# ************** 支付宝支付APP 配置  ************** #
# ================================================= #
"""
使用OpenSSL生成证书app_private_key.pem（私钥）、app_public_key.pem（公钥）
1. 生成私钥
genrsa -out app_private_key.pem 2048
2. 生成公钥
rsa -in app_private_key.pem -pubout -out app_public_key.pem

注意 1和2步骤也可以使用支付宝自己得签名工具（支付宝开放平台开发助手）生成签名来完成（签名工具秘钥长度选择-RSA2）

3.cat app_public_key.pem 查看公钥的内容

将-----BEGIN PUBLIC KEY-----和-----END PUBLIC KEY-----中间的内容保存在支付宝的用户配置中（沙箱或者正式）

https://openhome.alipay.com/platform/appDaily.htm?tab=info

4.配置好公钥后，支付宝会生成公钥，将公钥的内容复制保存到一个文本文件中(alipay_public_key.pem)，注意需要在文本的首尾添加标记位(-----BEGIN PUBLIC KEY-----和-----END PUBLIC KEY-----) 

5.将刚刚生成的私钥app_private_key.pem和支付宝公钥alipay_public_key.pem放到我们的项目目录中
"""

ALIPAY_APPID = 'xxxxxxxxxxxxxxxxxx'

# 服务器存放证书路径（支付宝支付签发的）
ALIPAY_PRIVATE_KEY_PATH = os.path.join(BASE_DIR, 'key', 'app_private_key.pem')
ALIPAY_PUBLIC_KEY_PATH = os.path.join(BASE_DIR, 'key', 'alipay_public_key.pem')

# ================================================= #
# ************** Bitanswer License 配置  ************** #
# ================================================= #

BITANSWER_API_BASE_URL = 'http://eee.phlexing.com'  # Bitanswer API基础地址
BITANSWER_BITKEY = 'your-bitkey-here'  # Bitanswer API的bitkey，固定值
BITANSWER_TEMPLATE_NAME = 'test_api'
BITANSWER_BUSINESS_NAME = 'test_linux'

# ================================================= #
# ************** 公共产品 配置  ************** #
# ================================================= #

COMMON_PRODUCT = {
    "GloryEXCommon": [
        "GloryEX",
        "GloryEX3D"
    ]
}

# ================================================= #
# ************** LDAP 配置  ************** #
# ================================================= #

LDAP_ENABLED = True  # 是否启用LDAP登录
LDAP_SERVER = '172.16.20.5'
LDAP_PORT = 389
LDAP_USE_SSL = False
LDAP_USER_DN_TEMPLATE = '%(user)s@phlexing.com'  # 用户DN模板（UPN格式）
LDAP_SEARCH_BASE = 'OU=hzxingxin,DC=phlexing,DC=com'  # 搜索基础DN（获取用户属性用）
LDAP_AUTO_CREATE_USER = True  # LDAP登录时自动创建本地用户
LDAP_DEFAULT_ROLE_KEY = 'public'  # LDAP用户默认角色key（对应Role表的key字段）

# LDAP服务账号配置（用于批量同步用户，需要有搜索权限的账号）
LDAP_BIND_USER = ''  # 服务账号DN或UPN，例如: 'CN=admin,OU=Users,DC=phlexing,DC=com' 或 'admin@phlexing.com'
LDAP_BIND_PASSWORD = ''  # 服务账号密码

# LDAP同步默认凭据（用于定时任务，不传参时使用此账号）
LDAP_SYNC_USERNAME = 'xuxiaokui'  # 默认同步账号（UPN格式，不含@phlexing.com）
LDAP_SYNC_PASSWORD = 'Xu12345678!'  # 默认同步密码

# ================================================= #
# ************** anythingllm PostgreSQL 数据库配置 ************** #
# ================================================= #
# 用于将LDAP用户同步到anythingllm的public.users表
ANYTHINGLLM_DB_HOST = '172.11.130.90'
ANYTHINGLLM_DB_PORT = 5432
ANYTHINGLLM_DB_NAME = 'anythingllm'
ANYTHINGLLM_DB_USER = 'anythingllm'
ANYTHINGLLM_DB_PASSWORD = 'anythingllm_pg_pass'  # 请根据实际密码修改

# ================================================= #
# ************** Phlexing / AnythingLLM 知识库配置 ************** #
# ================================================= #

PHLEXING_ENABLED = True  # 是否启用知识库（Phlexing/AnythingLLM）
PHLEXING_BASE_URL = 'http://aihub:3002'  # 知识库访问地址
PHLEXING_LOGIN_API = 'http://aihub:3002/api/request-token'  # 知识库登录API地址
PHLEXING_SSO_ENABLED = True  # 是否启用SSO单点登录（自动登录知识库）

# AnythingLLM API Key（在 AnythingLLM 管理后台 → 通用设置 → 安全 中获取）
ANYTHINGLLM_API_KEY = 'your-api-key-here'  # 请替换为实际的 API Key

# ================================================= #
# ************** Jenkins 配置 ************** #
# ================================================= #

JENKINS_BASE_URL = 'http://jenkins.phlexing.com:8080'  # Jenkins 服务器地址
JENKINS_USERNAME = 'sqa'  # Jenkins 用户名
JENKINS_PASSWORD = 'Phlexing_2026#@!'  # Jenkins 密码（账号密码登录方式）
JENKINS_PROJECT_KEYWORD = 'Personal'  # Jenkins 项目关键词过滤
JENKINS_USE_SSO_USER = True  # 触发构建时使用当前登录用户的真实身份（SSO缓存凭证）访问 Jenkins，构建人显示真实用户；无缓存凭证时回退 JENKINS_USERNAME
# SSO 凭证缓存有效期：用户登录时密码缓存到 Redis（key: lybbn-ldap-passwd-{user.id}），供 Jenkins 等第三方
# 系统以真实用户身份代理认证。每次读取使用时滑动续期（按此有效期重新计时），活跃用户缓存不会过期；
# 长期未使用超过有效期则缓存失效，触发构建时回退默认账号（sqa）
JENKINS_SSO_CREDENTIAL_TTL = timedelta(days=7)
JENKINS_CONNECT_TIMEOUT = 10  # Jenkins 连接超时（秒）：服务不可达时快速失败，避免每次请求拖满超时导致请求堆积
JENKINS_READ_TIMEOUT = 60  # Jenkins 读取超时（秒）：大列表接口响应慢，读取阶段需宽松超时
JENKINS_SYNC_COOLDOWN = 30  # 打包管理同步按钮冷却时间（秒）：限制同步频率，防止频繁点击并发请求打满 Jenkins
JENKINS_SYNC_LOCK_TIMEOUT = 600  # 同步任务互斥锁自动过期时间（秒）：异常退出时锁能自动释放

# ================================================= #
# ************** 软件包发包流程 配置  ************** #
# ================================================= #
# 打包管理自动发包链路依赖的流程类型名（构建成功后自动创建并发起该流程）
DELIVERY_WORKFLOW_TYPE_NAME = '软件包(D包)发包流程'
# 自动回填字段映射配置：{发包表单字段 key: 回填来源标识}，构建成功后系统自动回填，用户无需填写。
# 回填来源标识（等号右侧的值）的含义如下（与 views.py 的 AUTO_FILL_VALUE_PROVIDERS 注册表一一对应）：
#   package_path           回填内容 = 制品完整路径（Jenkins 构建产物完整路径）
#   package_version_name   回填内容 = 制品文件名（路径最后一段，含文件后缀）
# 新增回填字段：照抄一行，左侧改为流程表单中实际的字段 key，右侧从上方两个回填来源标识中选择，
# 并在流程配置界面开启该字段的"自动回填"开关即可；
# 新增回填内容类型（如制品 MD5）：在下方定义一个可读的新标识，并在 views.py 的 AUTO_FILL_VALUE_PROVIDERS 注册取值逻辑
DELIVERY_AUTO_FILL_FIELDS = {
    'software_path': 'package_path',  # 软件包存放路径 → 回填制品完整路径
    'software_version_name': 'package_version_name',  # 软件包版本名称 → 回填制品文件名
}

# ================================================= #
# ************** 包安全扫描 配置  ************** #
# ================================================= #
# 包安全扫描 Jenkins 项目名（jenkins_service.get_package_scan_job 按此精确匹配）
PACKAGE_SECURITY_SCAN_JOB = 'package_security_scan'
# ================================================= #
# ************** GitLab 案例看板 配置  ************** #
# ================================================= #
# 案例看板（临时方案，越简单越好）：
# 只需指定一个本地 HTML 页面路径，后端直接读取该文件返回给前端菜单嵌入；
# 同时用 GITLAB_USERNAME/GITLAB_PASSWORD 登录 GitLab 获取登录 cookie，
# 页面内引用的 GitLab 资源（图片/API/文件）地址会被自动改写，
# 由后端携带 cookie 转发，页面即可免登录访问 GitLab（casehub 等）资源。
# Windows/Linux 部署均只需把 GITLAB_CASE_BOARD_PAGE 指向实际文件即可。
GITLAB_ENABLED = True  # 是否启用 GitLab 案例看板
GITLAB_BASE_URL = 'https://gitlab.phlexing.com'  # GitLab 服务地址（443 HTTPS）
GITLAB_USERNAME = 'sqa'  # 登录 GitLab 的账号（需有目标仓库/资源访问权限）
GITLAB_PASSWORD = 'Phlexing_2026#@!'  # GitLab 账号密码
GITLAB_COOKIE_TTL = 1800  # 登录 cookie 缓存有效期（秒），过期后自动重新登录
GITLAB_CONNECT_TIMEOUT = 10  # GitLab 连接超时（秒）
GITLAB_READ_TIMEOUT = 60  # GitLab 读取超时（秒）
GITLAB_LOGIN_MODE = 'auto'  # GitLab 登录方式: auto=自动检测 LDAP/SSO 表单; form=标准表单; ldap=强制走 LDAP/SSO 端点
GITLAB_DIRECT_LINK = True  # 页面内 GitLab Web 导航链接（/-/blob、/-/tree 等）是否还原为真实地址直接跳转 GitLab（True=点击直接打开 GitLab；False=仍走代理）
GITLAB_VERIFY_SSL = False  # 是否校验证书（内网自签名证书请保持 False）
GITLAB_PROXY = ''  # GitLab 访问代理（如浏览器需走代理才能访问 GitLab，填 http://proxy-host:port）
# 案例看板 HTML 页面本地文件路径（直接读取，无需任何代理配置）：
# Windows 示例: r'C:\Users\xxx\Downloads\index.html'
# Linux 示例:   '/opt/caseboard/index.html'
# 页面引用的同目录资源（js/css/图片）可用相对路径，同样直接读取；
# 页面内 GitLab 资源请写完整域名 https://gitlab.phlexing.com/... ，后端会自动改写转发
GITLAB_CASE_BOARD_PAGE = r'C:\Users\xuxiaokui\Downloads\index.html'

# ================================================= #
# ************** 包安全扫描 配置  ************** #
# ================================================= #
# 软件包共享路径：发包/提交审批流时拼接"共享路径 + 软件包名称"判断软件包是否已就位
PACKAGE_SCAN_SHARED_PATH = '/TestHub/PhyBolt/Package/Personal'
# 软件包备份路径：扫描前将软件包复制到此路径，目录按"产品名/当天年月日"创建、文件按"时间戳_包名"重命名
PACKAGE_SCAN_BACKUP_PATH = '/TestHub/PhyBolt/Package/Backup'
# 审批表单中"软件包名称"字段 key（用户手动创建审批流时填写的软件包文件名，用于拼接共享路径）
PACKAGE_SCAN_PACKAGE_NAME_FIELD = 'software_version_name'
# 审批表单中"产品名"字段 key（多选，用于确定备份目录：先按产品名创建目录、再创建当天日期目录）
PACKAGE_SCAN_PRODUCT_NAME_FIELD = 'product_name'
# 产品名 → 备份目录名映射：GloryEX 系列（GloryEX/GloryEX3D/GloryPolaris）任选其一或多选时统一归入 GloryEX
# 目录，其余产品未配置映射时一对一（目录名即产品名）
PACKAGE_SCAN_PRODUCT_DIR_MAP = {
    'GloryEX': 'GloryEX',
    'GloryEX3D': 'GloryEX',
    'GloryPolaris': 'GloryEX',
}
# 审批流程 form_data 中固定存储的包扫描字段 key（无需在流程表单中配置，也不受"自动回填"开关控制，
# 扫描完成后直接按此四个 key 回填，前端审批详情按固定 label 展示）
PACKAGE_SCAN_STATUS_FIELD = 'package_scan_status'  # 字段1：包扫描状态（如 PASS/FAIL）
PACKAGE_SCAN_REPORT_FIELD = 'package_scan_report'  # 字段2：扫描报告详情（html 内容）
PACKAGE_SCAN_PATH_FIELD = 'package_scan_path'  # 字段3：扫描软件包路径（触发扫描时为传给 Jenkins 的包路径入参；发包直接回填时即软件包存放路径）
PACKAGE_SCAN_BUILD_NUMBER_FIELD = 'package_scan_build_number'  # 字段4：扫描 Jenkins 构建编号（发包回填/异步扫描完成时写入）
# 包扫描字段数据来源映射：{form_data 固定字段 key: Jenkins 侧字段名}
#   package_scan_status ← 读取构建 package_info 制品的 ScanStatus 值（包扫描状态）
#   package_scan_report ← 读取构建 package_info 制品的 ScanReport 值（扫描报告 html 内容）
#   package_scan_path   ← 触发扫描时传给 Jenkins 扫描项目 package_path 入参的值（备份路径重命名后的绝对路径）
PACKAGE_SCAN_AUTO_FILL_FIELDS = {
    PACKAGE_SCAN_STATUS_FIELD: 'ScanStatus',
    PACKAGE_SCAN_REPORT_FIELD: 'ScanReport',
    PACKAGE_SCAN_PATH_FIELD: 'package_path',
}
# 包扫描失败重试：不区分构建成功/失败（构建失败必然读不到结果，构建成功时结果也可能尚未生成/缺失），
# 统一以"能否读到 ScanStatus/ScanReport"为判据——构建结束后读取结果，读不到即以原软件包路径重新触发
# 扫描构建、异步等待新构建结束后重新读取，最多重试 PACKAGE_SCAN_FAIL_MAX_RETRIES 次；触发构建接口
# 异常时按 PACKAGE_SCAN_FAIL_RETRY_DELAY 间隔再次尝试。重试耗尽仍失败时，扫描状态回填
# PACKAGE_SCAN_ERROR_STATUS（ERROR）、扫描报告回填 PACKAGE_SCAN_DEFAULT_REPORT
# 缺省报告，提示用户报告获取异常，不阻塞审批流程（ERROR 不影响"包扫描状态为PASS"跳过逻辑），
# 后续再排查扫描失败原因
PACKAGE_SCAN_FAIL_MAX_RETRIES = 3
PACKAGE_SCAN_FAIL_RETRY_DELAY = 60
# 扫描结果获取异常时的状态值（区别于 PASS/FAIL 真实结果，仅表示结果读取失败）
PACKAGE_SCAN_ERROR_STATUS = 'ERROR'
# 扫描结果获取异常时的缺省默认报告（html 内容，提示用户报告获取异常；以 <html> 开头，前端按 html 内容直接展示）
PACKAGE_SCAN_DEFAULT_REPORT = (
    '<html><body style="font-family:Microsoft YaHei,Arial,sans-serif;color:#333;padding:16px;line-height:1.8;">'
    '<h3 style="color:#e6a23c;margin:0 0 12px;">包扫描报告获取异常</h3>'
    '<p style="margin:4px 0;">系统多次尝试读取包安全扫描结果均失败（扫描状态或报告为空，未能获取完整结果），'
    '当前审批流程不受影响，可继续正常审批。</p>'
    '<p style="margin:4px 0;">已记录异常日志，后续将排查包扫描失败原因，'
    '如扫描结果有疑问可联系CI组处理。</p>'
    '</body></html>'
)
