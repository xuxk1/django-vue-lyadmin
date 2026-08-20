from django.urls import path

from .views import CaseBoardConfigView, CaseBoardProxyView

urlpatterns = [
    # 案例看板配置（前端 iframe 加载地址获取）
    path('config/', CaseBoardConfigView.as_view(), name='case_board_config'),
    # 案例看板 GitLab 资源代理（带 sqa 登录 cookie 转发 + 域名改写）
    path('proxy/', CaseBoardProxyView.as_view(), name='case_board_proxy'),
    # 页面内相对路径资源（iframe 中 query 丢失，子路径相对页面目录解析）
    path('proxy/<path:rel_path>', CaseBoardProxyView.as_view(), name='case_board_proxy_rel'),
]
