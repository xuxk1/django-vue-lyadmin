# -*- coding: utf-8 -*-

"""
@Remark: GitLab 案例看板视图（apps.caselibrary）

临时方案（越简单越好）：
1. 配置 GITLAB_CASE_BOARD_PAGE 指定本地 HTML 页面路径
2. 读取接口直接返回该文件，前端 iframe 嵌入菜单
3. 页面内 GitLab 资源地址被改写为代理地址，由后端携带
   sqa 登录 cookie 转发访问，页面无需手动登录即可访问 GitLab
"""

import logging
import os

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from urllib.parse import quote
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from utils.jsonResponse import DetailResponse, ErrorResponse
from apps.caselibrary.services import GitLabService, GITLAB_WEB_NAV_RE, get_board_config

logger = logging.getLogger(__name__)


class CaseBoardConfigView(APIView):
    """获取案例看板基础配置信息"""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        cfg = get_board_config()
        if not cfg['enabled']:
            return DetailResponse(data={
                'enabled': False,
                'page_url': '',
                'proxy_base': '',
                'base_url': '',
            }, msg="获取成功")

        proxy_base = GitLabService.get_proxy_prefix()
        return DetailResponse(data={
            'enabled': True,
            'page_url': f'{proxy_base}{quote(cfg["page"], safe="/")}',
            'proxy_base': proxy_base,
            'base_url': cfg['base_url'],
        }, msg="获取成功")


@method_decorator(xframe_options_exempt, name='dispatch')
class CaseBoardProxyView(APIView):
    """
    案例看板资源读取接口
    GET /api/caseboard/proxy/?path=xxx 或 /api/caseboard/proxy/<rel_path>
    - 本地文件（页面本身及其同目录 js/css/图片等）：直接读取返回
    - 其他路径：携带 sqa 登录 cookie 从 GitLab 拉取（页面内 GitLab 资源）

    注：页面需要嵌入系统 iframe 展示，必须豁免 X-Frame-Options 限制
    （否则 Django XFrameOptionsMiddleware 会为响应添加 DENY 头，浏览器拒绝显示）
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, rel_path=None):
        cfg = get_board_config()
        if not cfg['enabled']:
            return ErrorResponse(msg="案例看板功能未启用，请联系管理员", status=403)

        page = cfg['page']
        if not os.path.isfile(page):
            return ErrorResponse(msg=f"案例看板页面文件不存在，请检查 GITLAB_CASE_BOARD_PAGE 配置: {page}", status=500)

        path = request.GET.get('path', '')
        # iframe 内相对路径资源（如 js/app.js）会丢失 query，相对页面文件目录解析
        is_relative = False
        if not path and rel_path:
            is_relative = True
            path = os.path.join(os.path.dirname(os.path.abspath(page)),
                                *rel_path.lstrip('/').split('/'))

        if not path:
            return ErrorResponse(msg="缺少 path 参数（页面或资源路径）", status=400)

        service = GitLabService()

        # 本地文件：页面本身或其同目录资源，直接读取（仅限页面目录内，防止误读其他文件）
        if os.path.isfile(path):
            root = os.path.dirname(os.path.abspath(page))
            norm = os.path.normcase(os.path.normpath(path))
            if norm != os.path.normcase(root) and not norm.startswith(os.path.normcase(root) + os.sep):
                return ErrorResponse(msg="该路径不在页面文件目录内，不允许访问", status=403)
            try:
                status_code, content_type, content = service.fetch_local(path)
            except Exception as e:
                logger.error(f"案例看板本地文件读取失败: {path}, 错误: {str(e)}")
                return ErrorResponse(msg=f"读取文件失败: {str(e)}", status=500)
            return HttpResponse(content, content_type=content_type or 'application/octet-stream')

        # 相对路径资源（iframe 内引用，如 iconfont 字体）：本地不存在直接 404 并提示，
        # 不要把本地绝对路径当 GitLab 仓库路径转发（如 /C:\Users\...\index_files\iconfont.ttf）
        if is_relative:
            logger.warning(f"案例看板本地资源不存在: {path}")
            return ErrorResponse(msg=f"案例看板本地资源文件不存在: {path}", status=404)

        # GitLab Web 导航路径（/-/blob、/-/tree 等）：页面内静态 <a> 链接已在
        # 域名改写时还原为真实地址，但 JS 动态生成的链接（如案例目录入口）无法
        # 在改写阶段还原，这里对导航路径统一返回 302 重定向到真实 GitLab，
        # 保证点击后直接打开 GitLab 对应页面；图片/raw 等资源路径不匹配，仍走代理。
        if service.direct_link and GITLAB_WEB_NAV_RE.search(path):
            logger.info(f"案例看板导航链接重定向到 GitLab: {path}")
            return HttpResponseRedirect(f"{service.base_url}{quote(path, safe='/')}")

        # GitLab 资源：携带 sqa 登录 cookie 转发
        if not path.startswith('/'):
            path = '/' + path
        try:
            status_code, content_type, content = service.fetch(path)
        except Exception as e:
            # 返回 502 而非 200：避免 <img>/iframe 拿到 JSON 错误体却按 HTTP 200 静默失败
            logger.error(f"案例看板代理请求失败: {path}, 错误: {str(e)}")
            return ErrorResponse(msg=f"获取 GitLab 资源失败: {str(e)}", status=502)

        if status_code != 200:
            logger.warning(f"案例看板代理返回非 200: path={path}, status={status_code}")
            return HttpResponse(
                f'<html><body style="font-family:Microsoft YaHei,Arial;color:#333;padding:24px;">'
                f'<h3>GitLab 资源获取失败 (HTTP {status_code})</h3>'
                f'<p>路径: {path}</p></body></html>',
                content_type='text/html; charset=utf-8',
                status=status_code,
            )

        # 保留原始 Content-Type，使 iframe/资源按正确类型渲染
        return HttpResponse(content, content_type=content_type or 'application/octet-stream')
