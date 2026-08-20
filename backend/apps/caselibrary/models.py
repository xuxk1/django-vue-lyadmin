# -*- coding: utf-8 -*-

"""
案例库管理（apps.caselibrary）数据模型

【持久化规划】当前案例看板为临时方案，GitLab 连接/页面/白名单配置均在
config.py 中维护；后续改造为落库维护时，在本文件定义以下模型并执行
makemigrations / migrate：
    1. GitLabConnection  GitLab 连接配置（地址/账号/密码/超时/cookie TTL/启用开关）
    2. CaseBoardPage     看板页面配置（页面路径/白名单前缀/启用开关/排序）
对应 services.py 中的 _load_gitlab_config / get_board_config 改为
"数据库优先、config.py 兜底"，服务层接口保持稳定，视图层无需改动。
"""
