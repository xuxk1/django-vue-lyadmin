import logging
from datetime import datetime
import os
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.http import FileResponse
from rest_framework import serializers
from rest_framework.decorators import action, permission_classes
from rest_framework.permissions import IsAuthenticated
from utils.viewset import CustomModelViewSet
from utils.jsonResponse import SuccessResponse, DetailResponse, ErrorResponse
from utils.common import renameuploadimg
from apps.lyworkflow.models import (
    WorkflowType, WorkflowStep, WorkflowCC,
    WorkflowInstance, WorkflowTask, WorkflowCCInstance, WorkflowLog, WorkflowComment,
    ApprovalGroup
)
from apps.lyworkflow.serializers import (
    WorkflowTypeSerializer, WorkflowStepSerializer, WorkflowCCSerializer,
    WorkflowInstanceSerializer, WorkflowInstanceCreateSerializer,
    WorkflowTaskSerializer, WorkflowLogSerializer, WorkflowApproveSerializer,
    ApprovalGroupSerializer, WorkflowCommentSerializer
)
from apps.lyworkflow.filters import WorkflowTypeFilter, WorkflowInstanceFilter, WorkflowTaskFilter
from apps.lyworkflow.engine import FlowEngine
from mysystem.models import Users

import config

logger = logging.getLogger(__name__)


class WorkflowTypeViewSet(CustomModelViewSet):
    """流程类型视图集"""
    queryset = WorkflowType.objects.all()
    serializer_class = WorkflowTypeSerializer
    filterset_class = WorkflowTypeFilter
    search_fields = ['name', 'code']
    ordering_fields = ['sort', 'create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    @action(methods=['get'], detail=True, url_path='form-fields')
    def get_form_fields(self, request, pk=None):
        """获取流程类型的表单字段列表"""
        import json
        try:
            print(f'=== 获取流程类型 {pk} 的表单字段 ===')
            workflow_type = self.get_object()
            print(f'流程类型: {workflow_type.name}, form_schema: {workflow_type.form_schema}')
            
            if not workflow_type.form_schema:
                print('警告: form_schema 为空')
                return DetailResponse(
                    data=[],
                    msg='该流程类型未配置表单字段'
                )
            
            form_schema = workflow_type.form_schema
            fields = []
            
            # 如果 form_schema 是字符串，先解析为 JSON
            if isinstance(form_schema, str):
                print('form_schema 是字符串格式，尝试解析为 JSON')
                try:
                    form_schema = json.loads(form_schema)
                    print(f'解析成功，类型为: {type(form_schema)}')
                except json.JSONDecodeError as e:
                    print(f'JSON 解析失败: {e}')
                    return DetailResponse(
                        data=[],
                        msg=f'表单配置格式错误: {str(e)}'
                    )
            
            # 解析 form_schema，提取字段名和标签
            if isinstance(form_schema, list):
                print(f'form_schema 是列表格式，共 {len(form_schema)} 个字段')
                for field in form_schema:
                    if isinstance(field, dict):
                        field_name = field.get('field') or field.get('prop') or field.get('key')
                        field_label = field.get('label') or field.get('title') or field_name
                        if field_name:
                            fields.append({
                                'value': field_name,
                                'label': f'{field_label} ({field_name})'
                            })
                            print(f'  - 字段: {field_name}, 标签: {field_label}')
            elif isinstance(form_schema, dict):
                print(f'form_schema 是字典格式')
                # 检查是否是 {"fields": [...]} 格式
                if 'fields' in form_schema and isinstance(form_schema['fields'], list):
                    print(f'检测到 fields 键，包含 {len(form_schema["fields"])} 个字段')
                    for field in form_schema['fields']:
                        if isinstance(field, dict):
                            field_name = field.get('field') or field.get('prop') or field.get('key')
                            field_label = field.get('label') or field.get('title') or field_name
                            if field_name:
                                fields.append({
                                    'value': field_name,
                                    'label': f'{field_label} ({field_name})'
                                })
                                print(f'  - 字段: {field_name}, 标签: {field_label}')
                else:
                    # 如果 form_schema 是字典格式，每个 key 是一个字段
                    for key, value in form_schema.items():
                        if isinstance(value, dict):
                            field_label = value.get('label') or value.get('title') or key
                            fields.append({
                                'value': key,
                                'label': f'{field_label} ({key})'
                            })
                            print(f'  - 字段: {key}, 标签: {field_label}')
            else:
                print(f'警告: form_schema 格式不正确，类型为 {type(form_schema)}')
            
            print(f'最终返回 {len(fields)} 个字段')
            return DetailResponse(data=fields)
        except Exception as e:
            import traceback
            print(f'错误: {str(e)}')
            print(traceback.format_exc())
            return ErrorResponse(msg=f'获取表单字段失败: {str(e)}', code=500)

    @action(methods=['get'], detail=True, url_path='check-initiator-permission')
    def check_initiator_permission(self, request, pk=None):
        """检查当前用户是否有权限发起该流程类型"""
        workflow_type = self.get_object()
        user = request.user
        
        # 超级管理员不受限制
        if user.is_superuser:
            return DetailResponse(data={'allowed': True, 'reason': '超级管理员不受限制'})
        
        # 获取用户部门
        user_dept = None
        if hasattr(user, 'dept') and user.dept:
            user_dept = user.dept
        
        # 如果没有配置部门限制，则所有部门均可发起
        allowed_depts = workflow_type.allowed_initiator_depts
        if not allowed_depts:
            return DetailResponse(data={'allowed': True, 'reason': '未配置部门限制，所有部门均可发起'})
        
        # 检查用户部门是否在允许列表中
        if not user_dept:
            return DetailResponse(data={'allowed': False, 'reason': '您没有所属部门，无法发起该流程'})
        
        if isinstance(allowed_depts, list):
            if user_dept.id in allowed_depts:
                return DetailResponse(data={'allowed': True, 'reason': '您的部门在允许列表中'})
        else:
            if user_dept.id == allowed_depts:
                return DetailResponse(data={'allowed': True, 'reason': '您的部门在允许列表中'})
        
        return DetailResponse(data={'allowed': False, 'reason': '您的部门不在该流程的允许发起部门列表中'})

    @action(methods=['post'], detail=True, url_path='auto-fill-form')
    def auto_fill_form(self, request, pk=None):
        """
        发起流程前的自动填写：按流程配置中开启"自动回填"开关（auto_fill）的字段，
        由系统异步计算并回填字段值（前端点击"创建"时调用）。

        当前支持软件包存放路径类字段：按"共享路径 + 软件包名称"拼接并校验文件是否真实存在
        （共享目录挂载到后端服务器，基于本地文件系统判断），存在则回填拼接路径；不存在则
        返回 need_confirm 与候选路径，由前端弹窗让用户确认软件包的实际存放路径。

        请求体: {'form_data': {表单字段 key: 值}}
        返回: {'filled_fields': {字段key: 回填值}, 'need_confirm': bool, 'candidate_path': 候选路径}
        """
        import json
        workflow_type = self.get_object()

        form_data = {}
        if request.data and isinstance(request.data, dict):
            form_data = request.data.get('form_data') or {}
        if isinstance(form_data, str):
            try:
                form_data = json.loads(form_data) or {}
            except (TypeError, ValueError):
                form_data = {}

        schema = workflow_type.form_schema
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except (TypeError, ValueError):
                schema = []
        fields = schema if isinstance(schema, list) else []

        from utils.package_scan import file_exists
        filled_fields = {}
        need_confirm = False
        candidate_path = ''
        # 软件包存放路径类字段 key（config.DELIVERY_AUTO_FILL_FIELDS 中回填来源为 package_path 的字段）
        path_field = self._get_auto_fill_path_field(workflow_type)

        for field in fields:
            if not field.get('auto_fill'):
                continue
            if not field.get('field'):
                continue
            field_key = field.get('field')
            # 软件包存放路径类字段：按"共享路径 + 软件包名称"拼接并校验文件是否真实存在
            # （auto_fill 开关与打包管理发包链路共用：打包管理发包时回填制品实际路径，
            #  手动创建时按共享路径拼接回填，两个场景统一由该开关驱动）
            if field_key == path_field:
                package_name = (form_data.get(config.PACKAGE_SCAN_PACKAGE_NAME_FIELD) or '').strip()
                if not package_name:
                    continue
                candidate = os.path.join(config.PACKAGE_SCAN_SHARED_PATH, package_name)
                if file_exists(candidate):
                    filled_fields[field_key] = candidate
                else:
                    need_confirm = True
                    candidate_path = candidate
                continue
            # 其他自动回填字段：打包管理发包链路已按 config.DELIVERY_AUTO_FILL_FIELDS 回填（构建成功后），
            # 手动创建场景暂无取值逻辑（仅日志提示，不阻塞创建）
            if field.get('auto_fill'):
                logger.info(f'字段[{field_key}]开启了自动回填但手动创建场景暂未注册取值逻辑，已跳过')

        return DetailResponse(data={
            'filled_fields': filled_fields,
            'need_confirm': need_confirm,
            'candidate_path': candidate_path,
        }, msg='发起前自动填写完成')

    @staticmethod
    def _get_auto_fill_path_field(workflow_type):
        """
        解析流程表单中"软件包存放路径"字段 key：config.DELIVERY_AUTO_FILL_FIELDS 中
        回填来源为 package_path 的字段（与发包链路自动回填字段一致，避免硬编码字段名）
        """
        for field_key, source in getattr(config, 'DELIVERY_AUTO_FILL_FIELDS', {}).items():
            if source == 'package_path':
                return field_key
        return ''


class WorkflowStepViewSet(CustomModelViewSet):
    """流程步骤视图集"""
    queryset = WorkflowStep.objects.all()
    serializer_class = WorkflowStepSerializer
    search_fields = ['step_name']
    ordering_fields = ['step_order']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取步骤列表（支持按流程类型筛选）"""
        workflow_type_id = request.query_params.get('workflow_type')
        if workflow_type_id:
            self.queryset = self.queryset.filter(workflow_type_id=workflow_type_id)
        return super().list(request, *args, **kwargs)

    @action(methods=['post'], detail=False)
    def batch_update(self, request):
        """批量更新步骤顺序"""
        steps_data = request.data.get('steps', [])
        if not steps_data:
            return ErrorResponse(msg='步骤数据不能为空')

        try:
            with transaction.atomic():
                for step_data in steps_data:
                    step_id = step_data.get('id')
                    step_order = step_data.get('step_order')
                    if step_id and step_order is not None:
                        WorkflowStep.objects.filter(id=step_id).update(step_order=step_order)
            
            return SuccessResponse(msg='批量更新成功')
        except Exception as e:
            logger.error(f'批量更新步骤失败: {str(e)}')
            return ErrorResponse(msg=f'批量更新失败: {str(e)}')


class ApprovalGroupViewSet(CustomModelViewSet):
    """自定义审批组视图集
    
    支持审批组的增删改查，以及动态维护组成员（增加/删除成员）。
    """
    queryset = ApprovalGroup.objects.all()
    serializer_class = ApprovalGroupSerializer
    search_fields = ['name', 'product_line']
    ordering_fields = ['create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取审批组列表（支持按产品线筛选）"""
        product_line = request.query_params.get('product_line')
        if product_line:
            self.queryset = self.queryset.filter(product_line=product_line)
        return super().list(request, *args, **kwargs)


class WorkflowCCViewSet(CustomModelViewSet):
    """流程抄送配置视图集"""
    queryset = WorkflowCC.objects.all()
    serializer_class = WorkflowCCSerializer
    search_fields = ['workflow_type__name']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取抄送配置列表（支持按流程类型筛选）"""
        workflow_type_id = request.query_params.get('workflow_type')
        if workflow_type_id:
            self.queryset = self.queryset.filter(workflow_type_id=workflow_type_id)
        return super().list(request, *args, **kwargs)


class WorkflowInstanceViewSet(CustomModelViewSet):
    """流程实例视图集"""
    queryset = WorkflowInstance.objects.all()
    serializer_class = WorkflowInstanceSerializer
    filterset_class = WorkflowInstanceFilter
    search_fields = ['instance_no', 'title']
    ordering_fields = ['create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def get_serializer_class(self):
        """根据动作返回不同的序列化器"""
        if self.action == 'create':
            return WorkflowInstanceCreateSerializer
        return WorkflowInstanceSerializer

    def list(self, request, *args, **kwargs):
        """获取流程列表（显示用户相关的流程）"""
        # 超级管理员查看所有
        if request.user.is_superuser:
            return super().list(request, *args, **kwargs)
        
        # 非超级管理员：查看自己发起的 + 待自己审批的
        user_id = request.user.id
        user_name = request.user.name
        
        # 记录调试日志
        logger.info(f'[WorkflowInstance] 用户 {user_name} (id={user_id}) 请求流程列表')
        
        # 获取查询参数
        show_only_pending = request.query_params.get('show_only_pending', 'false').lower() == 'true'
        
        # 待自己审批的流程ID
        pending_task_ids = set(WorkflowTask.objects.filter(
            approver_id=user_id,
            status=0  # status=0 表示待审批
        ).values_list('instance_id', flat=True))
        
        logger.info(f'[WorkflowInstance] 用户 {user_name} 有待审批任务的流程IDs: {pending_task_ids}')
        
        # 合并查询集
        if show_only_pending:
            # 只显示有待审批任务的流程
            self.queryset = WorkflowInstance.objects.filter(id__in=pending_task_ids).distinct()
            logger.info(f'[WorkflowInstance] 只显示有待审批任务的流程，数量: {self.queryset.count()}')
        else:
            # 默认显示：自己发起的所有流程 + 有待审批任务的流程
            from django.db.models import Q
            
            # 条件1：自己发起的所有流程（不限状态，包括已通过、已驳回等）
            condition1 = Q(applicant_id=user_id)
            
            # 条件2：有待审批任务（无论是否是自己发起）
            condition2 = Q(id__in=pending_task_ids)
            
            # 合并所有条件
            self.queryset = WorkflowInstance.objects.filter(
                condition1 | condition2
            ).distinct()
            
            my_started_count = WorkflowInstance.objects.filter(applicant_id=user_id).count()
            pending_count = len(pending_task_ids)
            logger.info(f'[WorkflowInstance] 显示自己的流程({my_started_count}) + 有待审批任务的流程({pending_count})，总数: {self.queryset.count()}')
        
        return super().list(request, *args, **kwargs)

    @action(methods=['post'], detail=True)
    def submit(self, request, pk=None):
        """提交流程（使用新的流程引擎）"""
        instance = self.get_object()
        
        if instance.status != 0:  # 只有草稿状态可以提交
            return ErrorResponse(msg='只有草稿状态的流程可以提交')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以提交流程')
        
        # 包安全扫描：软件包发包流程提交时校验共享路径中的软件包并触发异步扫描
        # （返回 need_confirm 响应时由前端弹窗确认路径，确认后调用 confirm_scan_path 再重新提交；
        # 扫描检查异常时返回错误提示，流程保持草稿可重新提交，避免无提示卡在草稿）
        try:
            scan_check = self._handle_package_scan_on_submit(instance)
        except Exception as e:
            logger.error(f'包安全扫描检查异常: {str(e)}')
            return ErrorResponse(msg=f'包安全扫描检查失败: {str(e)}，流程保持草稿状态，请重试提交')
        if scan_check is not None:
            return scan_check
        
        try:
            # 提交轮次+1：区分重新发起后新旧两轮任务记录，避免审批人重复展示
            instance.submit_round = (instance.submit_round or 0) + 1
            instance.save(update_fields=['submit_round'])
            
            # 使用流程引擎启动流程
            engine = FlowEngine(instance)
            engine.start()
            
            return SuccessResponse(msg='流程提交成功')
        except Exception as e:
            logger.error(f'提交流程失败: {str(e)}')
            return ErrorResponse(msg=f'提交流程失败: {str(e)}')

    def _handle_package_scan_on_submit(self, instance):
        """
        软件包发包流程提交前的包安全扫描处理：
        - 软件包名称非空：拼接共享路径校验软件包是否已就位（只要填写了包名就校验路径，
          未就位返回 need_confirm 由前端弹窗确认实际路径）
        - 字段3或隐藏确认路径已有值：视为已触发过扫描/已确认过路径，直接放行
        - 软件包已就位：剪切到备份路径并触发异步扫描（三个扫描字段为固定 key，扫描完成后统一回填）

        Returns:
            None 表示放行继续提交流程；ErrorResponse 表示需前端处理（确认路径或错误）
        """
        from apps.engineering.views import PackageBuildViewSet
        from utils.package_scan import get_shared_package_path

        # form_data 可能存在双重 JSON 编码（字符串），先反序列化保证 .get() 安全
        form_data = PackageBuildViewSet._parse_form_data(instance.form_data)

        # 软件包名称（表单中填写的软件包文件名）用于拼接共享路径
        package_name = (form_data.get(config.PACKAGE_SCAN_PACKAGE_NAME_FIELD) or '').strip()
        if not package_name:
            return None  # 未填写软件包名称（非发包流程），直接放行

        # 已确认过扫描路径（confirm_scan_path 记录，防重新提交时重复拦截）或字段3已有值（已触发过扫描）
        if form_data.get('_scan_package_path') or form_data.get(config.PACKAGE_SCAN_PATH_FIELD):
            return None

        # 软件包存放路径字段已有值（手动创建时按"自动回填"开关自动填写/用户确认的实际路径）：直接校验该路径文件是否已就位，
        # 避免确认路径后提交仍按"共享路径 + 包名"拼接再次拦截（用户确认的路径可能不在共享路径下）
        from utils.package_scan import file_exists
        software_path = ''
        for field_key, source in getattr(config, 'DELIVERY_AUTO_FILL_FIELDS', {}).items():
            if source == 'package_path':
                software_path = (form_data.get(field_key) or '').strip()
                break
        if software_path:
            if not file_exists(software_path):
                return ErrorResponse(
                    data={'need_confirm': True, 'candidate_path': software_path},
                    msg=f'未找到软件包"{package_name}"，请确认软件包的实际存放路径',
                    code=400,
                )
            shared_path = software_path
        else:
            # 未填写路径字段：拼接共享路径并校验软件包是否已就位（路径判断独立于扫描配置，只要填了包名就校验）
            shared_path = get_shared_package_path(package_name)
            if not shared_path:
                candidate = os.path.join(config.PACKAGE_SCAN_SHARED_PATH, package_name)
                return ErrorResponse(
                    data={'need_confirm': True, 'candidate_path': candidate},
                    msg=f'共享路径中未找到软件包"{package_name}"，请确认软件包的实际存放路径',
                    code=400,
                )

        # 软件包已就位：剪切到备份路径并触发异步扫描（失败时阻塞提交，便于用户处理）
        _, error = PackageBuildViewSet._trigger_package_scan(instance, shared_path)
        if error:
            return ErrorResponse(msg=error)
        return None

    @action(methods=['post'], detail=True)
    def confirm_scan_path(self, request, pk=None):
        """
        确认包扫描路径：提交审批流时共享路径中未找到软件包，用户确认实际路径后
        触发复制与异步扫描（字段3立即回填，扫描状态/报告由异步任务完成后回填）

        请求体: {'package_path': '用户确认的软件包绝对路径'}
        """
        instance = self.get_object()
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以确认软件包路径')

        package_path = ''
        if request.data and isinstance(request.data, dict):
            package_path = (request.data.get('package_path') or '').strip()
        if not package_path:
            return ErrorResponse(msg='请填写软件包实际存放路径')

        # 校验用户确认的路径真实存在（避免误填路径后扫描失败）
        from utils.package_scan import file_exists
        if not file_exists(package_path):
            return ErrorResponse(msg=f'路径不存在或无法访问：{package_path}')

        from apps.engineering.views import PackageBuildViewSet

        scan_package_path, error = PackageBuildViewSet._trigger_package_scan(instance, package_path)
        if error:
            return ErrorResponse(msg=error)

        # 单条操作结果用 DetailResponse，避免分页包装导致前端取不到字段
        return DetailResponse(
            data={'scan_package_path': scan_package_path},
            msg='路径已确认，扫描已触发，扫描完成后将自动回填扫描状态与报告'
        )

    @action(methods=['post'], detail=True)
    def withdraw(self, request, pk=None):
        """撤回流程"""
        instance = self.get_object()
        
        if instance.status != 1:  # 只有审批中可以撤回
            return ErrorResponse(msg='只有审批中的流程可以撤回')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以撤回流程')
        
        if instance.current_step > 1:
            return ErrorResponse(msg='流程已进入后续审批环节，无法撤回')
        
        try:
            with transaction.atomic():
                # 更新流程状态
                instance.status = 4  # 已撤回
                instance.current_step = instance.total_steps  # 更新当前步骤为总步骤数
                instance.save()
                
                # 取消所有待审批任务
                WorkflowTask.objects.filter(instance=instance, status=0).update(status=3)
                
                # 记录日志
                self._create_log(instance, request.user, 'withdraw', '撤回流程')
                
            return SuccessResponse(msg='流程撤回成功')
        except Exception as e:
            logger.error(f'撤回流程失败: {str(e)}')
            return ErrorResponse(msg=f'撤回流程失败: {str(e)}')

    @action(methods=['put'], detail=True)
    def reinitiate(self, request, pk=None):
        """重新发起流程（支持草稿、已撤回和已退回状态）"""
        instance = self.get_object()
        
        # 只有草稿(0)、已撤回(4)或已退回(6)状态的流程可以重新发起
        if instance.status not in [0, 4, 6]:
            return ErrorResponse(msg='只有草稿、已撤回或已退回状态的流程可以重新发起')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以重新发起流程')
        
        # 保存原始状态，用于出错时恢复
        original_status = instance.status
        original_current_step = instance.current_step
        
        try:
            with transaction.atomic():
                # 处理请求数据（可能是 JSON 字符串或字典）
                import json
                data = request.data
                logger.info(f'重新发起流程 - 原始数据类型: {type(data)}, 内容: {data}')
                
                if isinstance(data, str):
                    data = json.loads(data)
                    logger.info(f'重新发起流程 - 解析后数据类型: {type(data)}, 内容: {data}')
                
                # 验证数据格式
                if not isinstance(data, dict):
                    raise ValueError(f'请求数据格式错误，应为 JSON 对象，实际为: {type(data)}')
                
                # 更新流程数据（只更新允许的字段）
                serializer = WorkflowInstanceCreateSerializer(instance, data=data, partial=True, context={'request': request})
                serializer.is_valid(raise_exception=True)
                logger.info(f'重新发起流程 - 验证通过，准备保存')
                serializer.save()
                logger.info(f'重新发起流程 - 保存成功')
                
                # 重置流程状态为草稿
                instance.status = 0
                instance.current_step = 1
                instance.save()
                logger.info(f'重新发起流程 - 状态重置成功')
                
                # 注意：不删除之前的审批任务，保留历史记录
                # 已完成的审批任务（status != 0）会保留在数据库中作为历史记录
                # 新的流程发起会创建新的审批任务（status = 0）
                
                # 记录日志
                if original_status == 6:
                    action_type = 'resubmit'
                    action_msg = '退回后重新发起流程'
                elif original_status == 4:
                    action_type = 'reinitiate'
                    action_msg = '重新发起流程'
                else:
                    action_type = 'submit'
                    action_msg = '提交流程'
                self._create_log(instance, request.user, action_type, action_msg)
                logger.info(f'重新发起流程 - 完成')
                
            return SuccessResponse(msg='流程发起成功')
        except Exception as e:
            logger.error(f'重新发起流程失败: {str(e)}', exc_info=True)
            # 出错时恢复原始状态
            try:
                instance.status = original_status
                instance.current_step = original_current_step
                instance.save(update_fields=['status', 'current_step'])
                logger.info(f'重新发起流程 - 状态已恢复为: {original_status}')
            except Exception as restore_error:
                logger.error(f'重新发起流程 - 状态恢复失败: {str(restore_error)}')
            return ErrorResponse(msg=f'流程发起失败: {str(e)}')

    @action(methods=['post'], detail=True)
    def cancel(self, request, pk=None):
        """取消流程"""
        instance = self.get_object()
        
        if instance.status not in [0, 1]:  # 只有草稿和审批中可以取消
            return ErrorResponse(msg='只有草稿或审批中的流程可以取消')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以取消流程')
        
        try:
            with transaction.atomic():
                # 更新流程状态
                instance.status = 5  # 已取消
                instance.current_step = instance.total_steps  # 更新当前步骤为总步骤数
                instance.save()
                
                # 取消所有待审批任务
                WorkflowTask.objects.filter(instance=instance, status=0).update(status=3)
                
                # 记录日志
                self._create_log(instance, request.user, 'cancel', '取消流程')
                
            return SuccessResponse(msg='流程取消成功')
        except Exception as e:
            logger.error(f'取消流程失败: {str(e)}')
            return ErrorResponse(msg=f'取消流程失败: {str(e)}')

    @action(methods=['delete'], detail=True)
    def delete_instance(self, request, pk=None):
        """删除流程（仅草稿状态且是申请人）"""
        instance = self.get_object()
        
        if instance.status != 0:  # 只有草稿状态可以删除
            return ErrorResponse(msg='只有草稿状态的流程可以删除')
        
        if instance.applicant != request.user:
            return ErrorResponse(msg='只有申请人可以删除流程')
        
        try:
            with transaction.atomic():
                # 删除相关的任务
                WorkflowTask.objects.filter(instance=instance).delete()
                
                # 删除相关的抄送记录
                WorkflowCCInstance.objects.filter(instance=instance).delete()
                
                # 删除相关的日志
                WorkflowLog.objects.filter(instance=instance).delete()
                
                # 删除流程实例
                instance.delete()
                
            return SuccessResponse(msg='删除成功')
        except Exception as e:
            logger.error(f'删除流程失败: {str(e)}')
            return ErrorResponse(msg=f'删除流程失败: {str(e)}')
    def _create_tasks(self, instance, step_order):
        """创建审批任务"""
        from mysystem.models import Users
        
        try:
            step = WorkflowStep.objects.get(
                workflow_type=instance.workflow_type,
                step_order=step_order
            )
            
            approver_users = self._get_approver_users(step, instance)
            
            for user in approver_users:
                WorkflowTask.objects.create(
                    instance=instance,
                    step=step,
                    step_order=step_order,
                    approver=user
                )
                
                # 发送通知：根据节点配置的邮件通知/站内信通知开关，优先使用 Celery 异步，失败则同步创建站内消息
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    send_workflow_notification.delay(
                        user.id, instance.id, 'approve',
                        notify_email=bool(step.notify_email),
                        notify_message=bool(step.notify_message)
                    )
                    logger.info(f'已通过 Celery 异步发送审批通知给用户 {user.name}（邮件:{step.notify_email}，站内信:{step.notify_message}）')
                except Exception as e:
                    # Celery 不可用时，同步创建站内消息（仅在节点开启站内信通知时）
                    logger.warning(f'Celery 异步通知失败: {str(e)}，改用同步方式创建站内消息')
                    if step.notify_message:
                        try:
                            self._create_sync_notification(user, instance, 'approve')
                            logger.info(f'已同步创建站内消息给用户 {user.name}')
                        except Exception as sync_error:
                            logger.error(f'同步创建站内消息也失败: {str(sync_error)}')
                    else:
                        logger.info(f'节点未开启站内信通知，跳过同步创建站内消息：用户 {user.name}')
                    
        except WorkflowStep.DoesNotExist:
            logger.warning(f'未找到步骤 {step_order}，流程类型: {instance.workflow_type.name}')

    def _find_dept_leader_by_hierarchy(self, instance, start_dept=None):
        """从指定部门开始，沿部门层级向上查找负责人
        
        查找优先级：
        1. 部门 owner 字段
        2. 角色名称包含"负责人"的用户
        3. 向上遍历父部门，重复1-2
        
        Args:
            instance: 流程实例对象
            start_dept: 起始部门（默认使用申请人部门）
            
        Returns:
            负责人用户列表（通常只有1人）
        """
        from mysystem.models import Dept
        
        dept = start_dept or instance.applicant_dept
        if not dept and hasattr(instance.applicant, 'dept'):
            dept = instance.applicant.dept
        if not dept:
            logger.warning('无法获取起始部门，无法沿层级查找负责人')
            return []
        
        visited_dept_ids = set()
        current_dept = dept
        
        while current_dept and current_dept.id not in visited_dept_ids:
            visited_dept_ids.add(current_dept.id)
            logger.info(f'沿部门层级查找负责人，当前部门: {current_dept.name} (id={current_dept.id})')
            
            # 1. 优先检查部门 owner 字段
            if current_dept.owner:
                try:
                    owner_user = Users.objects.get(name=current_dept.owner)
                    if owner_user != instance.applicant:
                        logger.info(f'找到部门负责人(owner): {owner_user.name} (部门: {current_dept.name})')
                        return [owner_user]
                except Users.DoesNotExist:
                    logger.warning(f'部门 owner 用户不存在: {current_dept.owner}')
            
            # 2. 查找角色名称包含"负责人"的用户
            dept_leaders = list(Users.objects.filter(
                dept=current_dept,
                role__name__icontains='负责人'
            ).exclude(id=instance.applicant.id))
            
            if dept_leaders:
                logger.info(f'找到部门负责人(角色): {[u.name for u in dept_leaders]} (部门: {current_dept.name})')
                return dept_leaders
            
            # 3. 向上遍历到父部门
            if current_dept.parent:
                logger.info(f'当前部门 {current_dept.name} 未找到负责人，继续查找父部门: {current_dept.parent.name}')
                current_dept = current_dept.parent
            else:
                logger.info(f'已到达部门层级顶端 {current_dept.name}，未找到负责人')
                break
        
        return []

    def _get_dept_with_children_ids(self, dept_ids):
        """获取部门及其所有子部门的ID列表（递归）
        
        Args:
            dept_ids: 部门ID或部门ID列表
            
        Returns:
            包含所有部门及子部门的ID列表
        """
        from mysystem.models import Dept
        if not dept_ids:
            return []
        
        if isinstance(dept_ids, list):
            all_ids = set(dept_ids)
        else:
            all_ids = {dept_ids}
        
        # BFS 递归查找所有子部门
        queue = list(all_ids)
        while queue:
            parent_id = queue.pop(0)
            children = Dept.objects.filter(parent_id=parent_id).values_list('id', flat=True)
            for child_id in children:
                if child_id not in all_ids:
                    all_ids.add(child_id)
                    queue.append(child_id)
        
        return list(all_ids)

    def _get_approver_users(self, step, instance):
        """根据步骤配置获取审批人列表"""
        approver_users = []
        
        if step.approver_type == 1:  # 指定角色
            if step.approver_role:
                approver_users = list(Users.objects.filter(role=step.approver_role))
        elif step.approver_type == 2:  # 指定部门（未配置时自动使用申请人部门，包含子部门）
            dept_ids = step.approver_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 获取部门及其所有子部门的ID
                    all_dept_ids = self._get_dept_with_children_ids(dept_ids)
                    depts = Dept.objects.filter(id__in=all_dept_ids)
                    approver_users = list(Users.objects.filter(dept__in=depts).distinct())
                    logger.info(f'指定部门审批人（含子部门）: {[u.name for u in approver_users]}')
                    
                    # 回退：如果指定部门中没有找到用户，沿部门层级查找负责人
                    if not approver_users:
                        logger.info(f'指定部门中未找到用户，尝试沿部门层级查找负责人')
                        approver_users = self._find_dept_leader_by_hierarchy(instance)
                except Exception as e:
                    logger.error(f'获取部门审批人失败: {str(e)}')
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = instance.applicant_dept
                if not applicant_dept and hasattr(instance.applicant, 'dept'):
                    applicant_dept = instance.applicant.dept
                if applicant_dept:
                    logger.info(f'未配置指定部门，自动使用申请人部门: {applicant_dept.name}')
                    approver_users = list(Users.objects.filter(dept=applicant_dept))
        elif step.approver_type == 3:  # 部门负责人（未配置时自动使用申请人部门）
            dept_ids = step.approver_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    
                    # 获取所有选中部门的负责人（去重）
                    for dept in depts:
                        if dept.owner:
                            try:
                                owner_user = Users.objects.get(id=dept.owner)
                                if owner_user not in approver_users:
                                    approver_users.append(owner_user)
                            except Users.DoesNotExist:
                                pass
                        else:
                            dept_leaders = list(Users.objects.filter(
                                dept=dept,
                                role__name__icontains='负责人'
                            ))
                            for leader in dept_leaders:
                                if leader not in approver_users:
                                    approver_users.append(leader)
                            
                            if not dept_leaders:
                                dept_users = list(Users.objects.filter(dept=dept))
                                if instance.applicant in dept_users:
                                    dept_users.remove(instance.applicant)
                                for user in dept_users:
                                    if user not in approver_users:
                                        approver_users.append(user)
                except Exception as e:
                    logger.error(f'获取部门负责人失败: {str(e)}')
            else:
                # 未指定部门，自动使用申请人的实际部门
                applicant_dept = instance.applicant_dept
                if not applicant_dept and hasattr(instance.applicant, 'dept'):
                    applicant_dept = instance.applicant.dept
                if applicant_dept:
                    logger.info(f'未配置部门负责人，自动使用申请人部门: {applicant_dept.name}')
                    # 查找部门负责人
                    if applicant_dept.owner:
                        try:
                            owner_user = Users.objects.get(name=applicant_dept.owner)
                            approver_users.append(owner_user)
                        except Users.DoesNotExist:
                            pass
                    if not approver_users:
                        dept_leaders = list(Users.objects.filter(
                            dept=applicant_dept,
                            role__name__icontains='负责人'
                        ))
                        approver_users.extend(dept_leaders)
                    if not approver_users:
                        dept_users = list(Users.objects.filter(dept=applicant_dept))
                        if instance.applicant in dept_users:
                            dept_users.remove(instance.applicant)
                        approver_users.extend(dept_users)
                else:
                    logger.warning('未配置部门负责人，且无法获取申请人部门')
        elif step.approver_type == 4:  # 指定人员
            approver_users = list(step.approver_users.all())
        elif step.approver_type == 10:  # 自定义审批组
            if step.approver_group:
                approver_users = list(step.approver_group.members.all())
        
        return approver_users

    def _notify_cc_users(self, instance):
        """通知抄送人员"""
        cc_configs = WorkflowCC.objects.filter(
            workflow_type=instance.workflow_type
        ).filter(Q(step__isnull=True) | Q(step__isnull=False))
        
        for cc_config in cc_configs:
            cc_users = self._get_cc_users(cc_config, instance)
            for user in cc_users:
                WorkflowCCInstance.objects.create(
                    instance=instance,
                    cc_user=user,
                    step=None
                )
                
                # 发送通知：优先使用 Celery 异步，失败则同步创建站内消息
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    send_workflow_notification.delay(user.id, instance.id, 'cc')
                    logger.info(f'已通过 Celery 异步发送抄送通知给用户 {user.name}')
                except Exception as e:
                    # Celery 不可用时，同步创建站内消息
                    logger.warning(f'Celery 异步通知失败: {str(e)}，改用同步方式创建站内消息')
                    try:
                        self._create_sync_notification(user, instance, 'cc')
                        logger.info(f'已同步创建站内消息给用户 {user.name}')
                    except Exception as sync_error:
                        logger.error(f'同步创建站内消息也失败: {str(sync_error)}')

    def _get_cc_users(self, cc_config, instance):
        """根据抄送配置获取抄送人员列表"""
        cc_users = []
        
        if cc_config.cc_type == 1:  # 指定角色
            if cc_config.cc_role:
                cc_users = list(Users.objects.filter(role=cc_config.cc_role))
        elif cc_config.cc_type == 2:  # 指定部门（支持单个部门ID或多个部门ID数组）
            dept_ids = cc_config.cc_dept
            if dept_ids:
                try:
                    from mysystem.models import Dept
                    # 兼容：支持单个ID或ID数组
                    if isinstance(dept_ids, list):
                        depts = Dept.objects.filter(id__in=dept_ids)
                    else:
                        depts = Dept.objects.filter(id=dept_ids)
                    cc_users = list(Users.objects.filter(dept__in=depts).distinct())
                except Exception as e:
                    logger.error(f'获取抄送部门人员失败: {str(e)}')
        elif cc_config.cc_type == 3:  # 部门负责人
            if instance.applicant_dept:
                cc_users = list(Users.objects.filter(
                    dept=instance.applicant_dept,
                    role__name__icontains='负责人'
                ))
        elif cc_config.cc_type == 4:  # 指定人员
            cc_users = list(cc_config.cc_users.all())
        elif cc_config.cc_type == 5:  # 发起人（流程申请人）
            cc_users = [instance.applicant]
        elif cc_config.cc_type == 6:  # 自定义审批组（按审批组动态获取成员）
            if cc_config.cc_group:
                try:
                    cc_users = list(cc_config.cc_group.members.all())
                    logger.info(f'自定义审批组 [{cc_config.cc_group.name}] 作为抄送人: {[u.name for u in cc_users]}')
                except Exception as e:
                    logger.error(f'获取抄送审批组成员失败: {str(e)}')
        
        return cc_users

    def _create_log(self, instance, operator, action, action_desc, remark=''):
        """创建流程日志"""
        WorkflowLog.objects.create(
            instance=instance,
            operator=operator,
            action=action,
            action_desc=action_desc,
            remark=remark
        )

    def _create_sync_notification(self, user, instance, notification_type):
        """
        同步创建站内消息通知
        
        Args:
            user: 接收通知的用户对象
            instance: 流程实例对象
            notification_type: 通知类型 (approve, cc, reject, return, approved)
        """
        from apps.lymessages.models import MyMessage, MyMessageUser
        
        # 根据通知类型生成消息内容
        message_title = ''
        message_content = ''
        
        if notification_type == 'approve':
            message_title = f'待审批工作流通知 - {instance.title}'
            message_content = f'您有一个待审批的工作流：{instance.title}，流程编号：{instance.instance_no}，请及时处理'
        elif notification_type == 'cc':
            message_title = f'流程抄送通知 - {instance.title}'
            message_content = f'您被抄送了一个流程：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'reject':
            message_title = f'流程驳回通知 - {instance.title}'
            message_content = f'您的流程申请已被驳回：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'return':
            message_title = f'流程退回通知 - {instance.title}'
            message_content = f'您的流程申请已被退回：{instance.title}，流程编号：{instance.instance_no}'
        elif notification_type == 'approved':
            message_title = f'流程通过通知 - {instance.title}'
            message_content = f'您的流程申请已通过审批：{instance.title}，流程编号：{instance.instance_no}'
        else:
            message_title = f'流程通知 - {instance.title}'
            message_content = f'流程状态更新：{instance.title}'
        
        # 创建站内消息
        message = MyMessage.objects.create(
            msg_title=message_title,
            msg_content=message_content,
            msg_chanel=1,  # 系统通知
            public=False,
            status=True
        )
        
        # 创建用户消息关联
        MyMessageUser.objects.create(
            messageid=message,
            revuserid=user,
            is_read=False,
            is_delete=False
        )


class WorkflowTaskViewSet(CustomModelViewSet):
    """审批任务视图集"""
    queryset = WorkflowTask.objects.all()
    serializer_class = WorkflowTaskSerializer
    filterset_class = WorkflowTaskFilter
    search_fields = ['instance__instance_no', 'instance__title']
    ordering_fields = ['step_order', 'create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取任务列表（只返回当前用户的任务）"""
        # 我的已办：当前用户实际处理过的任务（排除被自动跳过的任务），按审批时间倒序
        if request.query_params.get('handled') == '1':
            self.queryset = self.queryset.filter(
                approver=request.user,
                status__in=[1, 2, 3],
                approve_time__isnull=False
            ).exclude(
                approve_comment__startswith='[自动跳过]'
            ).order_by('-approve_time')

            instance_id = request.query_params.get('instance')
            if instance_id:
                self.queryset = self.queryset.filter(instance_id=instance_id)

            status = request.query_params.get('status')
            if status is not None and status != '':
                self.queryset = self.queryset.filter(status=status)

            return super().list(request, *args, **kwargs)

        # 超级管理员查看所有待审批任务
        if request.user.is_superuser:
            # 超级管理员需要按流程实例去重，避免同一个流程显示多次
            from django.db.models import Min
            
            # 获取所有待审批的流程实例ID（去重）
            distinct_instance_ids = WorkflowTask.objects.filter(
                status=0
            ).values_list('instance_id', flat=True).distinct()
            
            # 对于每个流程实例，只取第一个待审批任务
            first_task_ids = WorkflowTask.objects.filter(
                instance_id__in=distinct_instance_ids,
                status=0
            ).values('instance_id').annotate(
                min_id=Min('id')
            ).values_list('min_id', flat=True)
            
            self.queryset = self.queryset.filter(id__in=first_task_ids)
        else:
            # 普通用户只显示分配给自己的任务
            self.queryset = self.queryset.filter(approver=request.user)
        
        # 如果前端传入了 instance 参数，则进一步过滤
        instance_id = request.query_params.get('instance')
        if instance_id:
            self.queryset = self.queryset.filter(instance_id=instance_id)
        
        # 如果前端传入了 status 参数，则进一步过滤
        status = request.query_params.get('status')
        if status is not None:
            self.queryset = self.queryset.filter(status=status)
        
        response = super().list(request, *args, **kwargs)
        
        # 申请人"已退回"的流程应纳入我的待办，等待申请人修改后重新提交
        if (not request.user.is_superuser
                and status is not None and str(status) == '0'
                and isinstance(getattr(response, 'data', None), dict)
                and response.data.get('code') == 2000):
            returned_instances = WorkflowInstance.objects.filter(
                applicant=request.user,
                status=6  # 已退回
            ).order_by('-update_datetime')
            
            if returned_instances.exists():
                returned_rows = []
                for ins in returned_instances:
                    # 退回所在节点名称，供前端展示当前步骤
                    step = WorkflowStep.objects.filter(
                        workflow_type=ins.workflow_type,
                        step_order=ins.current_step
                    ).first()
                    step_name = f'{step.step_name}(已退回)' if step else '已退回'
                    
                    returned_rows.append({
                        'id': f'returned-{ins.id}',  # 虚拟任务ID，前端据此识别退回待办
                        'instance': ins.id,
                        'instance_no': ins.instance_no,
                        'instance_title': ins.title,
                        'step_name': step_name,
                        'approver_name': ins.applicant.name if ins.applicant else '',
                        'create_datetime': ins.update_datetime.strftime('%Y-%m-%d %H:%M:%S') if ins.update_datetime else '',
                        'status': 3,  # 已退回
                        'status_display': '已退回',
                        'approve_result': 0,
                        'allow_return': False,
                        'allow_reject': False,
                        'is_applicant': True,
                        'is_returned': True,  # 退回待办标识：前端显示"重新提交"按钮
                    })
                
                page_data = response.data.get('data')
                if isinstance(page_data, dict):
                    rows = list(page_data.get('data') or [])
                    rows.extend(returned_rows)
                    page_data['data'] = rows
                    page_data['total'] = (page_data.get('total') or 0) + len(returned_rows)
                    response.data['data'] = page_data
        
        return response

    @action(methods=['post'], detail=True)
    def approve(self, request, pk=None):
        """审批通过"""
        return self._handle_approval(request, pk, approve_result=1)

    @action(methods=['post'], detail=True)
    def reject(self, request, pk=None):
        """驳回流程"""
        return self._handle_approval(request, pk, approve_result=2)

    @action(methods=['post'], detail=True)
    def return_back(self, request, pk=None):
        """退回上一步"""
        return self._handle_approval(request, pk, approve_result=3)

    @action(methods=['post'], detail=True)
    def confirm(self, request, pk=None):
        """申请人确认（用于申请人自选/发起人确认节点）"""
        task = self.get_object()
        
        # 验证权限：只有申请人可以确认自己的流程
        if task.instance.applicant != request.user and not request.user.is_superuser:
            return ErrorResponse(msg='您没有权限确认该流程')
        
        if task.status != 0:
            return ErrorResponse(msg='该任务已处理')
        
        # 校验流程状态：或签节点一人操作后流程已终止，其他人不可再操作
        if task.instance.status != 1:
            return ErrorResponse(msg='流程状态已变更，无法执行审批操作')
        
        serializer = WorkflowApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        approve_comment = serializer.validated_data.get('approve_comment', '').strip()

        try:
            # 使用流程引擎处理确认（approve_result=1 表示通过）
            engine = FlowEngine(task.instance)
            engine.approve_task(
                task=task,
                approve_result=1,
                comment=approve_comment,
                operator=request.user
            )
            
            # 确保产品线抄送记录已创建（兼容存量流程：修复前已流转到确认节点、
            # 但抄送记录未生成的实例；已存在的记录会被引擎幂等跳过。
            # 注：抄送通知已取消，此处仅确保记录存在，供下方确认通知查询抄送人）
            try:
                if task.step and task.step.approver_type == 7 and task.step.product_line_cc_rules:
                    engine._handle_product_line_cc(task.step)
            except Exception as e:
                logger.warning(f'处理产品线抄送失败: {str(e)}')
            
            # 确认后给所有抄送人发送通知（站内消息 + 邮件）
            cc_users = WorkflowCCInstance.objects.filter(
                instance=task.instance
            ).values_list('cc_user_id', flat=True).distinct()
            
            if cc_users:
                try:
                    from apps.lyworkflow.tasks import send_workflow_notification
                    for cc_user_id in cc_users:
                        send_workflow_notification.delay(cc_user_id, task.instance.id, 'confirm')
                    logger.info(f'已向 {len(cc_users)} 个抄送人发送确认通知')
                except Exception as e:
                    logger.warning(f'发送抄送人确认通知失败: {str(e)}')
            
            return SuccessResponse(msg='确认成功')
        except Exception as e:
            logger.error(f'确认操作失败: {str(e)}')
            return ErrorResponse(msg=f'确认操作失败: {str(e)}')

    def _handle_approval(self, request, pk, approve_result):
        """处理审批操作（使用新的流程引擎）"""
        task = self.get_object()
        
        # 验证权限
        if task.approver != request.user and not request.user.is_superuser:
            return ErrorResponse(msg='您没有权限审批该任务')
        
        if task.status != 0:
            return ErrorResponse(msg='该任务已处理')
        
        # 校验流程状态：或签节点一人操作后流程已终止，其他人不可再操作
        if task.instance.status != 1:
            return ErrorResponse(msg='流程状态已变更，无法执行审批操作')
        
        # 关键安全检查：申请人不能审批自己的流程
        if task.instance.applicant == request.user:
            return ErrorResponse(msg='申请人不能审批自己的流程申请')
        
        # 校验节点退回/驳回开关配置，防止绕过前端限制执行操作
        if task.step:
            if approve_result == 2 and not task.step.allow_reject:
                return ErrorResponse(msg='当前节点不允许驳回操作')
            if approve_result == 3 and not task.step.allow_return:
                return ErrorResponse(msg='当前节点不允许退回操作')
        
        serializer = WorkflowApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        approve_comment = serializer.validated_data.get('approve_comment', '').strip()
        
        # 驳回(2)和退回(3)时必须填写审批意见
        if approve_result in [2, 3]:
            if not approve_comment:
                return ErrorResponse(msg='选择驳回或退回时，审批意见为必填项')

        try:
            # 使用流程引擎处理审批
            engine = FlowEngine(task.instance)
            engine.approve_task(
                task=task,
                approve_result=approve_result,
                comment=approve_comment,
                operator=request.user
            )
            
            return SuccessResponse(msg='审批操作成功')
        except Exception as e:
            logger.error(f'审批操作失败: {str(e)}')
            return ErrorResponse(msg=f'审批操作失败: {str(e)}')

    def _create_log(self, instance, operator, action, action_desc, remark=''):
        """创建流程日志"""
        WorkflowLog.objects.create(
            instance=instance,
            operator=operator,
            action=action,
            action_desc=action_desc,
            remark=remark
        )


class WorkflowCommentViewSet(CustomModelViewSet):
    """审批节点评论视图集"""
    queryset = WorkflowComment.objects.all()
    serializer_class = WorkflowCommentSerializer
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取评论列表（按流程实例筛选）"""
        instance_id = request.query_params.get('instance')
        if instance_id:
            self.queryset = self.queryset.filter(instance_id=instance_id)
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """创建评论，并邮件通知当前待审批节点（流程当前活动节点）的审批人及流程发起人

        通知目标规则：
        - 评论时流程停留在哪个节点（存在待审批任务的节点），就通知该节点全部待审批人；
        - 若被评论节点已结束（流程已流转到下一节点），则自动通知下一个待审批节点的审批人；
        - 非发起人发表评论时，追加邮件通知流程发起人；
        - 流程已结束（无待审批任务）时仅保存评论，不发送邮件。
        """
        serializer = self.get_serializer(data=request.data, request=request)
        serializer.is_valid(raise_exception=True)

        instance = serializer.validated_data.get('instance')
        task = serializer.validated_data.get('task')
        content = (serializer.validated_data.get('content') or '').strip()
        if not content:
            return ErrorResponse(msg='评论内容不能为空')
        if task.instance_id != instance.id:
            return ErrorResponse(msg='评论节点与流程实例不匹配')

        # 流程已通过或所有节点已完成（当前轮次无待审批任务）时禁止评论
        if instance.status == 2:
            return ErrorResponse(msg='流程已通过，无法发表评论')
        if not WorkflowTask.objects.filter(
            instance=instance, status=0, round=instance.submit_round
        ).exists():
            return ErrorResponse(msg='流程已结束，无法发表评论')

        # 处理评论附件上传（multipart/form-data 的 files 字段，支持多文件）
        attachments = self._save_attachments(request)

        comment = WorkflowComment.objects.create(
            instance=instance,
            task=task,
            user=request.user,
            content=content,
            attachments=attachments or None
        )
        attach_desc = f'（附件 {len(attachments)} 个）' if attachments else ''
        logger.info(f'流程 {instance.instance_no} 新增评论：{request.user.name} 评论了节点 {task.step.step_name if task.step else ""}{attach_desc}')

        # 邮件通知当前待审批节点（流程当前活动节点）的审批人及流程发起人
        self._notify_current_approvers(instance, comment, request.user)

        return DetailResponse(data=WorkflowCommentSerializer(comment).data, msg='评论成功')

    def _save_attachments(self, request):
        """保存评论附件到 media/workflow/comment/日期目录

        返回附件信息列表：[{'name': 原始文件名, 'path': 相对MEDIA_ROOT路径, 'size': 字节数}]
        """
        upload_files = request.FILES.getlist('files')
        if not upload_files:
            return []

        # 先统一校验大小（单文件不超过 50M），避免部分保存成功部分失败
        for f in upload_files:
            if f.size > 50 * 1024 * 1024:
                raise serializers.ValidationError(f'附件 {f.name} 超过 50M 大小限制')

        time_path = datetime.now().strftime("%Y-%m-%d")
        sub_path = os.path.join(settings.MEDIA_ROOT, 'workflow', 'comment', time_path)
        os.makedirs(sub_path, exist_ok=True)

        attachments = []
        for f in upload_files:
            file_name = renameuploadimg(f.name)
            file_path = os.path.join(sub_path, file_name)
            with open(file_path, 'wb') as target:
                for chunk in f.chunks():
                    target.write(chunk)
            attachments.append({
                'name': f.name,
                'path': f'workflow/comment/{time_path}/{file_name}',
                'size': f.size,
            })
        return attachments

    @permission_classes([IsAuthenticated])
    @action(methods=['get'], detail=True, url_path='download')
    def download(self, request, *args, **kwargs):
        """下载评论附件（以原始文件名下载）"""
        comment = self.get_object()
        name = request.query_params.get('name', '')
        if not name:
            return ErrorResponse(msg='缺少附件名称参数')

        attachment = next(
            (a for a in (comment.attachments or []) if a.get('name') == name),
            None
        )
        if not attachment:
            return ErrorResponse(msg='附件不存在')

        file_path = os.path.join(settings.MEDIA_ROOT, attachment.get('path', ''))
        if not os.path.isfile(file_path):
            return ErrorResponse(msg='附件文件不存在或已被删除')

        response = FileResponse(open(file_path, 'rb'), as_attachment=True, filename=attachment.get('name'))
        response['Content-Length'] = os.path.getsize(file_path)
        return response

    def _notify_current_approvers(self, instance, comment, operator):
        """邮件通知当前待审批节点的审批人及流程发起人（排除评论人本人，按人去重）

        通知目标规则：
        - 当前待审批节点的全部待审批人（排除评论人本人，按人去重）；
        - 非发起人评论时，追加通知流程发起人（发起人若同时是待审批人则合并去重，
          保证同一评论对同一用户只入队一封邮件）。
        """
        pending_tasks = WorkflowTask.objects.filter(
            instance=instance, status=0, round=instance.submit_round
        ).select_related('step')
        user_ids = []
        step_names = []
        for t in pending_tasks:
            if t.approver_id == operator.id:
                continue
            if t.approver_id not in user_ids:
                user_ids.append(t.approver_id)
            if t.step and t.step.step_name not in step_names:
                step_names.append(t.step.step_name)

        # 非发起人评论时，追加通知流程发起人（与待审批人列表合并去重，避免重复邮件）
        applicant = instance.applicant
        if applicant and applicant.id != operator.id and applicant.id not in user_ids:
            user_ids.append(applicant.id)
            logger.info(f'流程 {instance.instance_no} 评论 {comment.id} 由非发起人 {operator.name} 发表，'
                        f'追加邮件通知发起人 {applicant.name}')

        if not user_ids:
            logger.info(f'流程 {instance.instance_no} 无通知对象，评论 {comment.id} 不发送邮件通知')
            return

        try:
            from apps.lyworkflow.tasks import send_workflow_comment_notification
            for user_id in user_ids:
                send_workflow_comment_notification.delay(
                    user_id, instance.id, comment.user.name, comment.content,
                    '、'.join(step_names)
                )
            logger.info(f'流程 {instance.instance_no} 评论 {comment.id} 已向 {len(user_ids)} 个收件人发起邮件通知')
        except Exception as e:
            logger.warning(f'评论邮件通知入队失败（不影响评论保存）: {str(e)}')


class WorkflowLogViewSet(CustomModelViewSet):
    """流程日志视图集"""
    queryset = WorkflowLog.objects.all()
    serializer_class = WorkflowLogSerializer
    search_fields = ['instance__instance_no', 'action']
    ordering_fields = ['create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def list(self, request, *args, **kwargs):
        """获取日志列表（按流程实例筛选）"""
        instance_id = request.query_params.get('instance')
        if instance_id:
            self.queryset = self.queryset.filter(instance_id=instance_id)
        return super().list(request, *args, **kwargs)


class WorkflowDashboardViewSet(CustomModelViewSet):
    """流程监控大屏视图集"""
    queryset = WorkflowInstance.objects.none()
    serializer_class = WorkflowInstanceSerializer
    # 不需要数据权限过滤
    extra_filter_backends = []

    @action(methods=['get'], detail=False)
    def statistics(self, request):
        """获取流程统计数据"""
        from django.db import models
        import logging
        logger = logging.getLogger(__name__)
        
        user = request.user
        
        # 基础统计
        stats = {
            'total': WorkflowInstance.objects.count(),
            'draft': WorkflowInstance.objects.filter(status=0).count(),
            'pending': WorkflowInstance.objects.filter(status=1).count(),
            'approved': WorkflowInstance.objects.filter(status=2).count(),
            'rejected': WorkflowInstance.objects.filter(status=3).count(),
            'withdrawn': WorkflowInstance.objects.filter(status=4).count(),
        }
        
        logger.info(f'流程统计数据: {stats}')
        
        # 用户相关统计
        if not user.is_superuser:
            stats['my_apply'] = WorkflowInstance.objects.filter(applicant=user).count()
            stats['my_pending_tasks'] = WorkflowTask.objects.filter(
                approver=user,
                status=0
            ).count()
        
        # 按流程类型统计
        type_stats = WorkflowInstance.objects.values('workflow_type__name').annotate(
            count=models.Count('id')
        ).order_by('-count')[:10]
        
        stats['by_type'] = list(type_stats)
        
        # 最近7天的流程趋势
        from datetime import timedelta
        from django.utils import timezone
        
        today = timezone.now().date()
        trends = []
        for i in range(7):
            date = today - timedelta(days=6-i)
            count = WorkflowInstance.objects.filter(
                create_datetime__date=date
            ).count()
            trends.append({
                'date': date.strftime('%Y-%m-%d'),
                'count': count
            })
        
        stats['trends'] = trends
        
        logger.info(f'最终返回数据: total={stats["total"]}, rejected={stats["rejected"]}, by_type={len(stats["by_type"])}, trends={len(stats["trends"])}')
        
        return SuccessResponse(data=stats)
