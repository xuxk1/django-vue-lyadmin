# -*- coding: utf-8 -*-

"""
@Remark: 自定义的JsonResonpse文件
"""

from rest_framework.response import Response


class SuccessResponse(Response):
    """
    标准响应成功的返回, SuccessResponse(data)或者SuccessResponse(data=data)
    (1)默认code返回2000, 不支持指定其他返回码
    """

    def __init__(self, data=None, msg='success', status=None, template_name=None, headers=None, exception=False,
                 content_type=None,page=1,limit=1,total=0):
        # 自动计算total：如果data是列表，使用len(data)；如果data是字典且包含total键，使用data['total']
        if not data:
            total = 0
        elif isinstance(data, list):
            # 如果data是列表，自动计算total
            total = len(data)
        elif isinstance(data, dict) and 'total' in data:
            # 如果data是字典且包含total键，使用data['total']
            total = data['total']
        # 如果total仍为0但传入了明确的total参数，使用传入的值
        std_data = {
            "code": 2000,
            "data": {
                "page": page,
                "limit": limit,
                "total": total,
                "data": data
            },
            "msg": msg
        }
        super().__init__(std_data, status, template_name, headers, exception, content_type)

class DetailResponse(Response):
    """
    不包含分页信息的接口返回,主要用于单条数据查询
    (1)默认code返回2000, 不支持指定其他返回码
    """

    def __init__(self, data=None, msg='success', status=None, template_name=None, headers=None, exception=False,
                 content_type=None,):
        std_data = {
            "code": 2000,
            "data": data,
            "msg": msg
        }
        super().__init__(std_data, status, template_name, headers, exception, content_type)

class ErrorResponse(Response):
    """
    标准响应错误的返回,ErrorResponse(msg='xxx')
    (1)默认错误码返回400, 也可以指定其他返回码:ErrorResponse(code=xxx)
    """

    def __init__(self, data=None, msg='error', code=400, status=None, template_name=None, headers=None,
                 exception=False, content_type=None):
        std_data = {
            "code": code,
            "data": data,
            "msg": msg
        }
        super().__init__(std_data, status, template_name, headers, exception, content_type)
