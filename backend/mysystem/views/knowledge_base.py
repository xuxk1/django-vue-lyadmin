# -*- coding: utf-8 -*-

"""
@Remark: Phlexing知识库SSO单点登录视图
使用 AnythingLLM SimpleSSO 临时令牌机制实现免登录
支持自动创建工作空间并分配用户
"""

import logging
import json
import requests as http_requests
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from utils.jsonResponse import DetailResponse, ErrorResponse
from config import (
    PHLEXING_ENABLED,
    PHLEXING_BASE_URL,
    PHLEXING_SSO_ENABLED,
    ANYTHINGLLM_API_KEY
)

logger = logging.getLogger(__name__)


def _get_anythingllm_headers():
    """获取AnythingLLM API请求头"""
    return {
        'Authorization': f'Bearer {ANYTHINGLLM_API_KEY}',
        'Content-Type': 'application/json',
    }


def _get_user_department_name(user):
    """
    根据用户的dept_id查询部门名称
    返回部门名称，如果无部门则返回None
    """
    try:
        dept_id = user.dept_id
        if not dept_id:
            logger.info(f"用户 {user.username} 未关联部门(dept_id为空)")
            return None
        from mysystem.models import Dept
        dept = Dept.objects.filter(id=dept_id).first()
        if dept:
            logger.info(f"用户 {user.username} 的部门: {dept.name} (dept_id={dept_id})")
            return dept.name
        else:
            logger.warning(f"用户 {user.username} 的dept_id={dept_id} 对应的部门不存在")
            return None
    except Exception as e:
        logger.error(f"查询用户 {user.username} 部门信息失败: {e}")
        return None


def _list_all_workspaces():
    """获取所有工作空间列表"""
    try:
        resp = http_requests.get(
            f"{PHLEXING_BASE_URL}/api/v1/workspaces",
            headers=_get_anythingllm_headers(),
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        result = resp.json()
        workspaces = result.get('workspaces', [])
        return {w.get('name'): w for w in workspaces if w.get('name')}
    except Exception as e:
        logger.error(f"获取工作空间列表失败: {e}")
        return {}


def _ensure_workspace_exists(workspace_name):
    """确保工作空间存在，如果不存在则创建"""
    if not workspace_name:
        logger.warning("工作空间名称为空，使用默认名称")
        workspace_name = "默认工作空间"

    try:
        workspaces = _list_all_workspaces()
        if workspace_name in workspaces:
            logger.info(f"工作空间已存在: {workspace_name}")
            return workspaces[workspace_name]

        logger.info(f"创建工作空间: {workspace_name}")
        resp = http_requests.post(
            f"{PHLEXING_BASE_URL}/api/v1/workspace/new",
            headers=_get_anythingllm_headers(),
            json={"name": workspace_name},
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        result = resp.json()
        workspace = result.get('workspace', result)
        logger.info(f"工作空间创建成功: {workspace_name}")
        return workspace
    except Exception as e:
        logger.error(f"创建工作空间失败: {e}")
        return None


def _get_or_create_anythingllm_user(username):
    """从AnythingLLM获取或创建用户，返回用户ID"""
    headers = _get_anythingllm_headers()

    # 1. 先尝试获取用户列表
    try:
        resp = http_requests.get(
            f"{PHLEXING_BASE_URL}/api/v1/users",
            headers=headers,
            timeout=10,
            verify=False,
        )
        if resp.status_code == 200:
            response_data = resp.json()
            users = []
            if isinstance(response_data, list):
                users = response_data
            elif isinstance(response_data, dict):
                if 'users' in response_data:
                    users = response_data['users']
                elif 'data' in response_data:
                    users = response_data['data']
                elif 'items' in response_data:
                    users = response_data['items']
                elif 'username' in response_data:
                    return response_data.get('id')

            for u in users:
                if isinstance(u, dict) and u.get('username') == username:
                    return u.get('id')
    except Exception as e:
        logger.error(f"获取用户列表请求异常: {e}")

    # 2. 用户不存在，尝试创建
    try:
        logger.info(f"尝试创建AnythingLLM用户: {username}")
        create_resp = http_requests.post(
            f"{PHLEXING_BASE_URL}/api/v1/users",
            headers=headers,
            json={'username': username},
            timeout=10,
            verify=False,
        )
        if create_resp.status_code in [200, 201]:
            user_data = create_resp.json()
            if isinstance(user_data, dict):
                user_id = user_data.get('id')
                if user_id:
                    logger.info(f"成功创建AnythingLLM用户: {username}, ID: {user_id}")
                    return user_id
    except Exception as e:
        logger.error(f"创建用户请求异常: {e}")

    return None


def _assign_user_to_workspace(workspace_slug, user_id):
    """将用户分配到工作空间"""
    if not workspace_slug or not user_id:
        return None
    try:
        resp = http_requests.post(
            f"{PHLEXING_BASE_URL}/api/v1/admin/workspaces/{workspace_slug}/manage-users",
            headers=_get_anythingllm_headers(),
            json={"userIds": [user_id], "reset": False},
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        logger.info(f"用户 {user_id} 已分配到工作空间: {workspace_slug}")
        return resp.json()
    except Exception as e:
        logger.error(f"分配用户到工作空间失败: {e}")
        return None


def init_user_workspace(user, workspace_name=None):
    """
    初始化用户工作空间（供登录时和其他场景复用）
    工作空间名称优先级：workspace_name参数 > 部门名称 > 用户名
    :param user: Django用户对象
    :param workspace_name: 自定义工作空间名称（可选）
    :return: 包含用户ID和工作空间信息的字典
    """
    result = {
        'user_id': None,
        'workspace_id': None,
        'workspace_slug': None,
        'workspace_name': None,
        'success': False,
    }

    username = user.username

    # 1. 确定工作空间名称
    if not workspace_name:
        workspace_name = _get_user_department_name(user) or username

    # 2. 获取或创建AnythingLLM用户
    user_id = _get_or_create_anythingllm_user(username)
    if not user_id:
        logger.error(f"无法获取或创建AnythingLLM用户: {username}")
        return result
    result['user_id'] = user_id

    # 3. 确保工作空间存在
    workspace = _ensure_workspace_exists(workspace_name)
    if not workspace:
        logger.error(f"无法获取或创建工作空间: {workspace_name}")
        result['success'] = True
        return result

    result['workspace_id'] = workspace.get('id')
    result['workspace_slug'] = workspace.get('slug')
    result['workspace_name'] = workspace.get('name')

    # 4. 将用户分配到工作空间
    if result['workspace_slug']:
        assign_result = _assign_user_to_workspace(result['workspace_slug'], user_id)
        if assign_result:
            logger.info(f"用户 {username} 已成功分配到工作空间 {workspace_name}")
        else:
            logger.warning(f"用户分配到工作空间失败，但用户已创建: {username}")
        result['success'] = True
    else:
        result['success'] = True

    return result


class PhlexingSSOView(APIView):
    """
    Phlexing知识库SSO单点登录代理接口
    使用 AnythingLLM SimpleSSO 临时令牌机制
    支持自动创建工作空间并分配用户
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def _get_headers(self):
        """获取请求头"""
        return {
            'Authorization': f'Bearer {ANYTHINGLLM_API_KEY}',
            'Content-Type': 'application/json',
        }

    def _list_workspaces(self):
        """获取所有工作空间列表"""
        try:
            resp = http_requests.get(
                f"{PHLEXING_BASE_URL}/api/v1/workspaces",
                headers=self._get_headers(),
                timeout=10,
                verify=False,
            )
            resp.raise_for_status()
            result = resp.json()
            workspaces = result.get('workspaces', [])
            # 转换为 {name: workspace} 的字典格式
            return {w.get('name'): w for w in workspaces if w.get('name')}
        except Exception as e:
            logger.error(f"获取工作空间列表失败: {e}")
            return {}

    def _ensure_workspace(self, workspace_name):
        """
        确保工作空间存在，如果不存在则创建
        返回工作空间信息 {id, name, slug, ...}
        """
        if not workspace_name:
            logger.warning("工作空间名称为空，使用默认名称")
            workspace_name = "默认工作空间"

        try:
            # 1. 获取现有工作空间
            workspaces = self._list_workspaces()

            # 2. 如果已存在，直接返回
            if workspace_name in workspaces:
                logger.info(f"工作空间已存在: {workspace_name}, ID: {workspaces[workspace_name].get('id')}")
                return workspaces[workspace_name]

            # 3. 不存在则创建
            logger.info(f"创建工作空间: {workspace_name}")
            resp = http_requests.post(
                f"{PHLEXING_BASE_URL}/api/v1/workspace/new",
                headers=self._get_headers(),
                json={"name": workspace_name},
                timeout=10,
                verify=False,
            )
            resp.raise_for_status()
            result = resp.json()
            workspace = result.get('workspace', result)  # 兼容不同返回格式
            logger.info(f"工作空间创建成功: {workspace_name}, ID: {workspace.get('id')}")
            return workspace

        except Exception as e:
            logger.error(f"创建工作空间失败: {e}")
            return None

    def _assign_user_to_workspace(self, workspace_slug, user_id):
        """
        将用户分配到工作空间
        """
        if not workspace_slug or not user_id:
            logger.error("工作空间slug或用户ID为空")
            return None

        try:
            resp = http_requests.post(
                f"{PHLEXING_BASE_URL}/api/v1/admin/workspaces/{workspace_slug}/manage-users",
                headers=self._get_headers(),
                json={"userIds": [user_id], "reset": False},
                timeout=10,
                verify=False,
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(f"用户 {user_id} 已分配到工作空间: {workspace_slug}")
            return result
        except Exception as e:
            logger.error(f"分配用户到工作空间失败: {e}")
            return None

    def _get_user_id(self, username):
        """
        从 AnythingLLM 获取或创建用户，返回用户ID
        同时处理工作空间创建和用户分配
        """
        headers = self._get_headers()

        # 1. 先尝试获取用户列表
        try:
            resp = http_requests.get(
                f"{PHLEXING_BASE_URL}/api/v1/users",
                headers=headers,
                timeout=10,
                verify=False,
            )

            logger.info(f"获取用户列表响应状态: {resp.status_code}")

            if resp.status_code == 200:
                try:
                    response_data = resp.json()
                    logger.info(f"解析后的数据类型: {type(response_data)}")

                    users = []
                    if isinstance(response_data, list):
                        users = response_data
                    elif isinstance(response_data, dict):
                        if 'users' in response_data:
                            users = response_data['users']
                        elif 'data' in response_data:
                            users = response_data['data']
                        elif 'items' in response_data:
                            users = response_data['items']
                        else:
                            if 'username' in response_data:
                                return response_data.get('id')

                    for user in users:
                        if isinstance(user, dict):
                            if user.get('username') == username:
                                return user.get('id')
                except json.JSONDecodeError as e:
                    logger.error(f"JSON解析失败: {e}")
        except Exception as e:
            logger.error(f"获取用户列表请求异常: {e}")

        # 2. 用户不存在，尝试创建用户
        try:
            logger.info(f"尝试创建用户: {username}")
            create_resp = http_requests.post(
                f"{PHLEXING_BASE_URL}/api/v1/users",
                headers=headers,
                json={'username': username},
                timeout=10,
                verify=False,
            )

            logger.info(f"创建用户响应状态: {create_resp.status_code}")

            if create_resp.status_code in [200, 201]:
                try:
                    user_data = create_resp.json()
                    if isinstance(user_data, dict):
                        user_id = user_data.get('id')
                        if user_id:
                            logger.info(f"成功创建用户: {username}, ID: {user_id}")
                            return user_id
                except json.JSONDecodeError as e:
                    logger.error(f"创建用户响应JSON解析失败: {e}")
        except Exception as e:
            logger.error(f"创建用户请求异常: {e}")

        return None

    def _get_user_department(self, user):
        """
        根据用户的dept_id查询部门名称
        返回部门名称，如果无部门则返回None
        """
        try:
            dept_id = user.dept_id
            if not dept_id:
                logger.info(f"用户 {user.username} 未关联部门(dept_id为空)")
                return None
            from mysystem.models import Dept
            dept = Dept.objects.filter(id=dept_id).first()
            if dept:
                logger.info(f"用户 {user.username} 的部门: {dept.name} (dept_id={dept_id})")
                return dept.name
            else:
                logger.warning(f"用户 {user.username} 的dept_id={dept_id} 对应的部门不存在")
                return None
        except Exception as e:
            logger.error(f"查询用户 {user.username} 部门信息失败: {e}")
            return None

    def _ensure_user_with_workspace(self, username, workspace_name=None):
        """
        确保用户存在并分配到对应的工作空间
        :param username: 用户名
        :param workspace_name: 工作空间名称，为空则默认使用用户名
        返回包含用户ID和工作空间信息的字典
        """
        result = {
            'user_id': None,
            'workspace_id': None,
            'workspace_slug': None,
            'workspace_name': None,
            'success': False,
        }

        # 1. 获取或创建用户
        user_id = self._get_user_id(username)
        if not user_id:
            logger.error(f"无法获取或创建用户: {username}")
            return result

        result['user_id'] = user_id

        # 2. 确定工作空间名称（默认使用用户名）
        workspace_name = workspace_name or username

        # 3. 确保工作空间存在
        workspace = self._ensure_workspace(workspace_name)
        if not workspace:
            logger.error(f"无法获取或创建工作空间: {workspace_name}")
            # 即使工作空间创建失败，也返回用户ID
            result['success'] = True
            return result

        result['workspace_id'] = workspace.get('id')
        result['workspace_slug'] = workspace.get('slug')
        result['workspace_name'] = workspace.get('name')

        # 4. 将用户分配到工作空间
        if result['workspace_slug']:
            assign_result = self._assign_user_to_workspace(
                result['workspace_slug'],
                user_id
            )
            if assign_result:
                logger.info(f"用户 {username} 已成功分配到工作空间 {workspace_name}")
                result['success'] = True
            else:
                logger.warning(f"用户分配到工作空间失败，但用户已创建: {username}")
                result['success'] = True  # 用户创建成功，分配失败不影响登录
        else:
            result['success'] = True

        return result

    def get(self, request):
        """获取SSO配置信息"""
        if not PHLEXING_ENABLED:
            return ErrorResponse(msg="知识库功能未启用，请联系管理员")

        user = request.user
        data = {
            'base_url': PHLEXING_BASE_URL,
            'sso_enabled': PHLEXING_SSO_ENABLED,
            'username': user.username,
        }
        return DetailResponse(data=data, msg="获取成功")

    def post(self, request):
        """
        生成SSO临时令牌
        同时确保用户存在并分配到对应的工作空间
        """
        if not PHLEXING_ENABLED:
            return ErrorResponse(msg="知识库功能未启用，请联系管理员")

        user = request.user
        username = user.username

        # 获取工作空间名称：优先使用请求中自定义的名称，否则用部门名称，最后默认用用户名
        workspace_name = request.data.get('workspace_name')
        if not workspace_name:
            department = request.data.get('department') or _get_user_department_name(user)
            workspace_name = department or user.username

        # 步骤1: 初始化用户工作空间（复用模块级函数）
        user_workspace_info = init_user_workspace(user, workspace_name)

        if not user_workspace_info.get('user_id'):
            return ErrorResponse(
                msg=f"无法获取或创建用户在知识库中的信息: {username}，请检查API Key权限和AnythingLLM服务状态"
            )

        user_id = user_workspace_info['user_id']

        # 步骤2: 用用户ID换取临时token
        try:
            headers = self._get_headers()

            token_resp = http_requests.get(
                f"{PHLEXING_BASE_URL}/api/v1/users/{user_id}/issue-auth-token",
                headers=headers,
                timeout=10,
                verify=False,
            )

            logger.info(f"生成Token响应状态: {token_resp.status_code}")

            if token_resp.status_code == 200:
                try:
                    result = token_resp.json()
                    token = result.get('token')
                    if token:
                        sso_url = f"{PHLEXING_BASE_URL}/sso/simple?token={token}"

                        response_data = {
                            'sso_url': sso_url,
                            'token': token,
                            'user_id': user_id,
                            'username': username,
                            'login_success': True,
                            'workspace': {
                                'id': user_workspace_info.get('workspace_id'),
                                'name': user_workspace_info.get('workspace_name'),
                                'slug': user_workspace_info.get('workspace_slug'),
                            } if user_workspace_info.get('workspace_id') else None,
                        }

                        return DetailResponse(
                            data=response_data,
                            msg="SSO令牌生成成功" + (
                                f"，已分配到工作空间: {user_workspace_info.get('workspace_name')}"
                                if user_workspace_info.get('workspace_name') else ""
                            )
                        )
                    else:
                        return ErrorResponse(msg="生成令牌失败：API返回数据中无token字段")
                except json.JSONDecodeError as e:
                    logger.error(f"Token响应JSON解析失败: {e}")
                    return ErrorResponse(msg=f"Token响应格式异常: {token_resp.text[:100]}")
            else:
                return ErrorResponse(
                    msg=f"生成令牌失败 (HTTP {token_resp.status_code}): {token_resp.text[:200]}"
                )

        except http_requests.exceptions.ConnectionError:
            return ErrorResponse(msg="无法连接知识库服务器，请检查网络")
        except http_requests.exceptions.Timeout:
            return ErrorResponse(msg="知识库服务器响应超时")
        except Exception as e:
            logger.error(f"生成SSO令牌异常: {e}", exc_info=True)
            return ErrorResponse(msg=f"生成SSO令牌异常: {str(e)}")


class PhlexingConfigView(APIView):
    """获取Phlexing知识库的基础配置信息"""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        data = {
            'enabled': PHLEXING_ENABLED,
            'base_url': PHLEXING_BASE_URL if PHLEXING_ENABLED else '',
            'sso_enabled': PHLEXING_SSO_ENABLED if PHLEXING_ENABLED else False,
        }
        return DetailResponse(data=data, msg="获取成功")