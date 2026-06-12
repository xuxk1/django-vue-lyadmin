# -*- coding: utf-8 -*-

"""
@Remark: 消息的路由文件
"""

from django.urls import path, re_path
from rest_framework import routers

from apps.lymessages.views import MyMessageTemplateViewSet,MyMessageViewSet,UserMessagesView,UserMessagesNoticeView,GetUnreadMessageNumView

system_url = routers.SimpleRouter()
system_url.register(r'messagetemplate', MyMessageTemplateViewSet)
system_url.register(r'messagenotice', MyMessageViewSet)


# 用户消息相关路由（供前端 myMessages.vue 使用）
user_messages_urls = [
    path('user-messages/', UserMessagesView.as_view(), name='获取用户消息列表/标记已读/删除'),
    path('notices/', UserMessagesNoticeView.as_view(), name='获取平台公告列表'),
    path('unread-num/', GetUnreadMessageNumView.as_view(), name='获取未读消息数量'),
]

urlpatterns = user_messages_urls
urlpatterns += system_url.urls