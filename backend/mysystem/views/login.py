# -*- coding: utf-8 -*-

"""
@Remark:管理后台登录视图
"""
import base64
import logging
from datetime import datetime, timedelta
from captcha.views import CaptchaStore, captcha_image
from django.utils.translation import gettext_lazy as _
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from mysystem.models import Users
from utils.jsonResponse import SuccessResponse, ErrorResponse
from utils.validator import CustomValidationError
from utils.request_util import save_login_log
from django_redis import get_redis_connection
from django.conf import settings
from config import IS_SINGLE_TOKEN, LDAP_ENABLED

logger = logging.getLogger(__name__)

class CaptchaView(APIView):
    """
    获取图片验证码
    """
    authentication_classes = []

    @swagger_auto_schema(
        responses={
            '200': openapi.Response('获取成功')
        },
        security=[],
        operation_id='captcha-get',
        operation_description='验证码获取',
    )
    def get(self, request):
        hashkey = CaptchaStore.generate_key()
        id = CaptchaStore.objects.filter(hashkey=hashkey).first().id
        imgage = captcha_image(request, hashkey)
        # 将图片转换为base64
        image_base = base64.b64encode(imgage.content)
        json_data = {"key": id, "image_base": "data:image/png;base64," + image_base.decode('utf-8')}
        return SuccessResponse(data=json_data)

class LoginSerializer(TokenObtainPairSerializer):
    """
    登录的序列化器:
    重写djangorestframework-simplejwt的序列化器
    """
    captcha = serializers.CharField(max_length=6)

    class Meta:
        model = Users
        fields = "__all__"
        read_only_fields = ["id"]

    default_error_messages = {
        'no_active_account': _('该账号已被禁用,请联系管理员')
    }

    #开启验证码验证
    def validate_captcha(self, captcha):
        self.image_code = CaptchaStore.objects.filter(id=self.initial_data['captchaKey']).first()
        five_minute_ago = datetime.now() - timedelta(hours=0, minutes=5, seconds=0)
        if self.image_code and five_minute_ago > self.image_code.expiration:
            self.image_code and self.image_code.delete()
            raise CustomValidationError('验证码过期')
        else:
            if self.image_code and (self.image_code.response == captcha or self.image_code.challenge == captcha):
                self.image_code and self.image_code.delete()
            else:
                self.image_code and self.image_code.delete()
                raise CustomValidationError("图片验证码错误")

    def validate(self, attrs):
        username = attrs['username']
        password = attrs['password']
        user = Users.objects.filter(username=username).first()

        # ========== 第一步: 尝试本地数据库认证 ==========
        local_auth_success = False
        if user and user.check_password(password):
            local_auth_success = True

        # ========== 第二步: 本地认证失败时，尝试LDAP认证 ==========
        if not local_auth_success and LDAP_ENABLED:
            logger.info(f"本地认证失败，尝试LDAP认证: {username}")
            from utils.ldap_auth import ldap_authenticate, get_or_create_ldap_user
            ldap_success, ldap_attrs = ldap_authenticate(username, password)
            logger.info(f'ldap_success: {ldap_success}')
            logger.info(f'ldap_attrs: {ldap_attrs}')
            if ldap_success:
                logger.info(f"LDAP认证成功: {username}")
                # 获取或创建本地用户
                user, created = get_or_create_ldap_user(username, ldap_attrs)
                if created:
                    logger.info(f"LDAP用户自动创建成功: {username}")
                if user:
                    # LDAP登录成功，同步密码到本地数据库
                    from django.contrib.auth.hashers import make_password
                    user.password = make_password(password)
                    user.save(update_fields=['password'])
                    logger.info(f"LDAP用户 {username} 已同步到本地")
                    # LDAP认证通过，跳过本地密码校验
                    return self._login_success(user, attrs, is_ldap=True)
                else:
                    return {
                        "code": 4000,
                        "msg": "LDAP认证通过，但无法创建本地用户账户",
                        "data": None
                    }
            else:
                logger.info(f"LDAP认证也失败: {username}")

        # ========== 第三步: 本地认证成功的后续处理 ==========
        if local_auth_success:
            return self._login_success(user, attrs)

        # 两种方式都失败
        return {
            "code": 4000,
            "msg": "账号/密码不正确",
            "data": None
        }

    def _cache_ldap_password(self, user, password):
        """缓存用户密码到Redis，用于Phlexing/Jenkins等第三方系统的SSO代理登录
        （Jenkins触发构建时以真实用户身份认证，构建人显示真实用户而非sqa）

        仅缓存 LDAP（AD）账号的有效凭证：本地账号（非LDAP）的密码不是 AD 密码，
        用于 Jenkins HTTP Basic Auth 认证必然返回 401；不缓存则触发构建时回退
        默认账号（config.JENKINS_USERNAME，本身是有效 AD 账号），构建功能不受影响。"""
        try:
            from config import (PHLEXING_SSO_ENABLED, JENKINS_USE_SSO_USER, JENKINS_SSO_CREDENTIAL_TTL,
                                LDAP_ENABLED)
            if not (PHLEXING_SSO_ENABLED or JENKINS_USE_SSO_USER):
                return
            if not password:
                return
            # 通过 LDAP 绑定认证校验密码是否为有效 AD 凭证：LDAP 账号校验通过后缓存，
            # 本地账号认证失败不缓存（避免无效凭证触发 Jenkins 401）；LDAP 未启用时保持原缓存行为
            if LDAP_ENABLED:
                from utils.ldap_auth import ldap_authenticate
                ldap_ok, _ = ldap_authenticate(user.username, password)
                if not ldap_ok:
                    logger.info(f"用户 {user.username} 非 LDAP 账号（AD 认证失败），跳过 Jenkins SSO 凭证缓存，触发构建时回退默认账号")
                    return
            redis_conn = get_redis_connection("singletoken")
            k = f"lybbn-ldap-passwd-{user.id}"
            # 缓存密码，有效期按配置（默认 7 天），每次读取使用时滑动续期，活跃用户缓存不会过期
            redis_conn.set(k, password, JENKINS_SSO_CREDENTIAL_TTL)
            logger.info(f"用户密码已缓存到Redis: user_id={user.id}, ttl={JENKINS_SSO_CREDENTIAL_TTL}")
        except Exception as e:
            logger.warning(f"缓存用户密码失败: {e}")

    def _sync_to_anythingllm(self, username, password):
        """将用户同步到AnythingLLM数据库，使用真实密码（bcrypt哈希）
        这样SSO代理登录时密码能匹配上
        """
        try:
            from config import PHLEXING_SSO_ENABLED, ANYTHINGLLM_DB_HOST, ANYTHINGLLM_DB_PORT, ANYTHINGLLM_DB_NAME, ANYTHINGLLM_DB_USER, ANYTHINGLLM_DB_PASSWORD
            if not PHLEXING_SSO_ENABLED:
                return
            import bcrypt as bcrypt_lib
            import psycopg2

            hashed_pw = bcrypt_lib.hashpw(password.encode('utf-8'), bcrypt_lib.gensalt()).decode('utf-8')

            conn = psycopg2.connect(
                host=ANYTHINGLLM_DB_HOST,
                port=ANYTHINGLLM_DB_PORT,
                dbname=ANYTHINGLLM_DB_NAME,
                user=ANYTHINGLLM_DB_USER,
                password=ANYTHINGLLM_DB_PASSWORD,
            )
            cursor = conn.cursor()
            # 检查用户是否已存在
            cursor.execute('SELECT id FROM public.users WHERE username = %s', (username,))
            existing = cursor.fetchone()
            if existing:
                cursor.execute('UPDATE public.users SET password = %s WHERE username = %s', (hashed_pw, username))
                logger.info(f"AnythingLLM用户密码已更新: {username}")
            else:
                cursor.execute(
                    "INSERT INTO public.users (username, password, role) VALUES (%s, %s, 'default')",
                    (username, hashed_pw)
                )
                logger.info(f"AnythingLLM用户已创建: {username}")
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.warning(f"同步用户到AnythingLLM失败: {e}")
    
    def _init_user_workspace(self, user):
        """初始化用户工作空间（登录时自动创建工作目录）"""
        try:
            from config import PHLEXING_ENABLED
            if not PHLEXING_ENABLED:
                return
            from mysystem.views.knowledge_base import init_user_workspace
            result = init_user_workspace(user)
            if result.get('success'):
                logger.info(f"用户 {user.username} 工作空间初始化成功: {result.get('workspace_name')}")
            else:
                logger.warning(f"用户 {user.username} 工作空间初始化失败")
        except Exception as e:
            logger.warning(f"初始化用户工作空间失败: {e}")
    
    def _login_success(self, user, attrs, is_ldap=False):
        """登录成功后的统一处理逻辑"""
        # 校验用户权限
        if not user.is_staff:
            return {
                "code": 4000,
                "msg": "您没有权限登录后台",
                "data": None
            }
        if not user.is_active:
            return {
                "code": 4000,
                "msg": "该账号已被禁用,请联系管理员",
                "data": None
            }
    
        # 生成JWT token
        self.user = user
        if is_ldap:
            # LDAP用户密码是随机UUID，不能走super().validate()（内部会调用authenticate失败）
            # 直接生成token
            data = {}
        else:
            data = super().validate(attrs)
        refresh = self.get_token(self.user)
    
        data['name'] = self.user.name
        data['userId'] = self.user.id
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        request = self.context.get('request')
        request.user = self.user
        # 记录登录成功日志
        save_login_log(request=request)
        # 缓存用户的jwt token
        if IS_SINGLE_TOKEN:
            redis_conn = get_redis_connection("singletoken")
            k = "lybbn-single-token{}".format(user.id)
            TOKEN_EXPIRE_CONFIG = getattr(settings, 'SIMPLE_JWT', None)
            if TOKEN_EXPIRE_CONFIG:
                TOKEN_EXPIRE = TOKEN_EXPIRE_CONFIG['ACCESS_TOKEN_LIFETIME']
                redis_conn.set(k, data['access'], TOKEN_EXPIRE)
        # 缓存用户密码到Redis（用于Phlexing/Jenkins等系统的SSO代理登录，构建时以真实用户身份认证Jenkins）
        self._cache_ldap_password(user, attrs.get('password', ''))
        # 每次登录成功都同步用户到AnythingLLM数据库（使用真实密码，确保SSO代理登录能成功）
        # self._sync_to_anythingllm(user.username, attrs.get('password', ''))
        # 登录时初始化用户工作空间（确保用户进入知识库后能看到自己的工作目录）
        # self._init_user_workspace(user)
        return {
            "code": 2000,
            "msg": "请求成功",
            "data": data
        }


class LoginView(TokenObtainPairView):
    """
    登录接口
    """
    serializer_class = LoginSerializer
    permission_classes = []