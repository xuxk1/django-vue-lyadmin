import logging
import json
import os
import posixpath
import threading
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed
import django_filters
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from rest_framework.decorators import action
from utils.viewset import CustomModelViewSet
from utils.jsonResponse import SuccessResponse, DetailResponse, ErrorResponse
from apps.engineering.models import PackageBuild, PackageProjectPermission
from apps.engineering.serializers import PackageBuildSerializer, PackageBuildCreateSerializer, PackageBuildListSerializer
from utils.jenkins_service import JenkinsService
from config import (DELIVERY_WORKFLOW_TYPE_NAME, DELIVERY_AUTO_FILL_FIELDS, PACKAGE_SCAN_AUTO_FILL_FIELDS,
                    PACKAGE_SCAN_STATUS_FIELD, PACKAGE_SCAN_REPORT_FIELD, PACKAGE_SCAN_PATH_FIELD,
                    PACKAGE_SCAN_BUILD_NUMBER_FIELD, PACKAGE_SECURITY_SCAN_JOB, PACKAGE_SCAN_PRODUCT_NAME_FIELD)

logger = logging.getLogger(__name__)

# 同步任务互斥锁/冷却 Redis key：
# 互斥锁保证同一时刻仅一个同步任务在执行（多进程/多 worker 下同样生效，避免频繁点击
# 或多人并发触发多个全量同步，并发请求打满 Jenkins 连接池导致超时失败）
SYNC_PROJECTS_LOCK_KEY = 'engineering:sync_projects:lock'
SYNC_PROJECTS_LAST_KEY = 'engineering:sync_projects:last'


def _extract_version_name(package_path):
    """从制品路径提取软件包版本名称：取路径文件名（保留文件后缀，与前端 deliverVersionName 逻辑对齐）"""
    return posixpath.basename((package_path or '').rstrip('/'))


# 自动回填取值注册表：{回填来源标识: 取值函数(制品路径) -> 回填值}
# 回填来源标识与 config.DELIVERY_AUTO_FILL_FIELDS 中配置的值一一对应；新增回填来源标识时在此注册一行取值逻辑
AUTO_FILL_VALUE_PROVIDERS = {
    'package_path': lambda package_path: package_path,
    'package_version_name': _extract_version_name,
}


class PackageBuildFilter(django_filters.FilterSet):
    """打包构建列表筛选：项目名称模糊匹配，构建状态/扫描状态精确匹配

    使用显式 FilterSet 而非 filterset_fields：AutoFilterSet 分支会直接按原始参数
    构造 Q 条件，构建状态（数值字段）传空串会触发字段类型转换错误；
    django-filter 原生对空值自动跳过过滤，无需前端剔除空参数。
    """
    project_name = django_filters.CharFilter(field_name='project_name', lookup_expr='icontains')
    build_status = django_filters.NumberFilter(field_name='build_status')
    scan_status = django_filters.CharFilter(method='filter_scan_status')

    def filter_scan_status(self, queryset, name, value):
        # 未扫描：scan_status 为空（NULL 或空串）的记录；其余取值精确匹配（PASS/FAIL/REJECT/ERROR/SCANNING）
        if value == '__empty__':
            return queryset.filter(Q(scan_status__isnull=True) | Q(scan_status=''))
        return queryset.filter(scan_status=value)

    class Meta:
        model = PackageBuild
        fields = ['project_name', 'build_status', 'scan_status']


class PackageBuildViewSet(CustomModelViewSet):
    """打包构建视图集"""
    queryset = PackageBuild.objects.all()
    serializer_class = PackageBuildSerializer
    filterset_class = PackageBuildFilter
    search_fields = ['project_name', 'jenkins_job_name']
    ordering_fields = ['create_datetime']
    # 不需要数据权限过滤
    extra_filter_backends = []

    def get_queryset(self):
        """按项目可见性授权过滤：仅展示当前用户可见的 Jenkins 项目记录

        可见规则（普通用户）：
        1. 自己构建的记录（creator=当前用户）永远可见，即使项目授权后续被撤销；
        2. 已授权项目的默认同步记录（creator 为空，即"系统同步"行）可见：项目设为公共可见，
           或可见部门含用户部门、可见角色与用户角色相交、可见用户含当前用户（任一命中即可）；
           用户已构建过的项目不再显示默认同步行（该行已被自己的构建记录替代）。
        关键边界：已授权项目内**他人构建的记录**（creator 非当前用户）一律隐藏，
        列表只展示"自己的构建记录 + 默认同步行"，避免他人构建记录泄漏到列表。
        未授权项目默认仅管理员（is_superuser）可见，管理员配置授权后普通用户才能看到。
        """
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()
        # 管理员（沿用 filters.py 的 is_superuser 判定）可见全部项目
        if user.is_superuser:
            return qs
        # 组装当前用户可见的 Jenkins 任务集合：公共项目 ∪ 部门命中 ∪ 角色命中 ∪ 用户命中
        visible_q = Q(is_public=True) | Q(visible_users=user)
        if user.dept_id:
            visible_q = visible_q | Q(visible_depts=user.dept_id)
        role_ids = list(user.role.values_list('id', flat=True))
        if role_ids:
            visible_q = visible_q | Q(visible_roles__in=role_ids)
        visible_jobs = set(
            PackageProjectPermission.objects.filter(visible_q).values_list('job_name', flat=True)
        )
        # 用户已构建过的项目：不再显示默认同步行，避免列表出现重复项目
        owned_jobs = set(qs.filter(creator=user).values_list('jenkins_job_name', flat=True))
        # 默认同步行仅限已授权项目；他人构建的记录（creator 非空且非当前用户）不满足任一条件即被过滤
        sync_visible = Q(creator__isnull=True) & Q(jenkins_job_name__in=visible_jobs)
        if owned_jobs:
            sync_visible = sync_visible & ~Q(jenkins_job_name__in=owned_jobs)
        return qs.filter(Q(creator=user) | sync_visible)

    def get_serializer_class(self):
        """根据动作返回不同的序列化器"""
        if self.action == 'create':
            return PackageBuildCreateSerializer
        if self.action == 'list':
            # 列表接口不返回完整构建日志（可能达数十 MB），仅返回摘要，完整日志按需通过 build_log 接口获取
            return PackageBuildListSerializer
        return PackageBuildSerializer

    @action(methods=['get'], detail=False)
    def jenkins_projects(self, request):
        """获取 Jenkins 中包含关键词的项目列表"""
        try:
            jenkins = JenkinsService()
            projects = jenkins.get_projects()
            return SuccessResponse(data=projects, msg='获取成功')
        except Exception as e:
            logger.error(f"获取 Jenkins 项目列表失败: {str(e)}")
            return ErrorResponse(msg=f'获取 Jenkins 项目列表失败: {str(e)}')

    @action(methods=['get'], detail=False)
    def jenkins_job_params(self, request):
        """获取指定 Jenkins 任务的参数定义"""
        job_name = request.query_params.get('job_name')
        if not job_name:
            return ErrorResponse(msg='请提供 job_name 参数')

        try:
            jenkins = JenkinsService()
            parameters = jenkins.get_job_parameters(job_name)
            return DetailResponse(data=parameters, msg='获取成功')
        except Exception as e:
            logger.error(f"获取 Jenkins 任务参数失败: {str(e)}")
            return ErrorResponse(msg=f'获取 Jenkins 任务参数失败: {str(e)}')

    @action(methods=['post'], detail=False)
    def sync_projects(self, request):
        """从 Jenkins 同步项目到本地数据库（含最新构建状态）"""
        from config import JENKINS_SYNC_COOLDOWN, JENKINS_SYNC_LOCK_TIMEOUT

        now = time.time()
        # 互斥锁：同步任务进行中时后续请求直接返回提示，防止频繁点击/多用户并发
        # 同时发起多个全量同步（每个同步 8 线程 × N 项目请求）压垮 Jenkins
        if not cache.add(SYNC_PROJECTS_LOCK_KEY, 1, timeout=JENKINS_SYNC_LOCK_TIMEOUT):
            return ErrorResponse(msg='同步任务正在进行中，请稍候再试')
        try:
            # 冷却限流：同步结束后需等待冷却时间才能再次同步，从源头减少无效重复请求
            last_sync = cache.get(SYNC_PROJECTS_LAST_KEY) or 0
            if now - last_sync < JENKINS_SYNC_COOLDOWN:
                wait = max(1, int(JENKINS_SYNC_COOLDOWN - (now - last_sync)))
                return ErrorResponse(msg=f'同步操作过于频繁，请 {wait} 秒后再试')
            cache.set(SYNC_PROJECTS_LAST_KEY, now, timeout=JENKINS_SYNC_COOLDOWN)

            jenkins = JenkinsService()
            projects = jenkins.get_projects()

            # 预取现有记录（一次查询），供并发任务判断是否需要拉取日志。
            # 复合键 (job, 构建编号)：一次构建一条记录，同一 job 的多条历史构建互不冲突
            existing_map = {(p.jenkins_job_name, p.jenkins_build_number): p for p in PackageBuild.objects.all()}

            # 预取"系统同步"记录（无构建人，creator 为空）并按 job 分组：
            # 同一 job 仅保留一条，Jenkins 编号递增时在其基础上更新，避免同步数据持续增加
            # 注意排除已关联审批流程的记录：用户发包后该记录编号代表其操作对象，
            # 若被同步按 lastBuild 改号（如 #77→#78），流程反查 first() 会把扫描状态写错记录
            unowned_groups = {}
            for p in PackageBuild.objects.filter(creator__isnull=True, workflow_instance__isnull=True):
                unowned_groups.setdefault(p.jenkins_job_name, []).append(p)

            # 预取"构建中"的无主记录：同步时按锁定编号向 Jenkins 确认真实状态，
            # 确认已结束即可解除锁定、参与合并收敛，避免编号前进后重复记录持续累积
            building_unowned_map = {}
            for job_name, lst in unowned_groups.items():
                building = [p for p in lst if p.build_status == 0]
                if building:
                    building_unowned_map[job_name] = building

            # 预取"用户构建"记录（creator 非空）按 job 分组：同步时确认构建中记录的真实状态
            # （前端轮询可能已中断，如页面关闭/刷新），并补齐已结束记录的不完整日志，保证点击
            # 同步按钮即可让所有项目（含自己构建产生的记录）与 Jenkins 保持一致，无需进详情点刷新
            owned_groups = {}
            for p in PackageBuild.objects.filter(creator__isnull=False):
                owned_groups.setdefault(p.jenkins_job_name, []).append(p)

            # 并发拉取各项目数据（网络 IO 密集，串行会随项目数线性变慢）
            results = []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(
                    self._sync_project_data,
                    project,
                    existing_map,
                    building_unowned_map.get(project.get('name')) or None,
                    owned_groups.get(project.get('name')) or [],
                ) for project in projects]
                for future in as_completed(futures):
                    try:
                        data = future.result()
                        if data:
                            results.append(data)
                    except Exception as e:
                        logger.warning(f"同步单个项目失败: {str(e)}")

            # 串行写库（本地操作开销小）
            synced_count = 0
            updated_count = 0
            for data in results:
                job_name = data['job_name']
                build_status = data['build_status']
                build_number = data['build_number']
                build_url = data['build_url']
                tail_log = data['tail_log']

                # 检查是否已存在（复合键：同一 job 允许多条构建记录并存）
                exists = existing_map.get((job_name, build_number))
                if not exists:
                    # existing_map 是同步开始时的快照，写库前重新查询：并发同步或触发排队记录
                    # 可能已写入，避免重复创建；同时规避同键多条记录（如从未构建模板与排队记录并存）
                    exists = PackageBuild.objects.filter(
                        jenkins_job_name=job_name,
                        jenkins_build_number=build_number
                    ).first()

                # "系统同步"记录（无构建人）按 job 去重：同一 job 仅保留一条无主记录。
                # Jenkins lastBuild 编号递增（如他人在 Jenkins 直接构建）时，在保留的记录上
                # 更新编号/状态/日志，避免每次同步都按新编号新增、同步数据持续增加；
                # 已产生的重复无主记录（含复合键命中的那条之外的）一并清理
                unowned_list = unowned_groups.get(job_name) or []

                # 构建中的无主记录：同步线程已按锁定编号向 Jenkins 确认真实状态，
                # 确认已结束的立即落库纠正状态并纳入合并收敛（否则编号前进后旧记录永远停留在
                # "构建中"，且每次同步都按新编号新建记录，重复记录持续累积）；
                # 仍在构建中的保持锁定编号，不参与合并
                confirmed = {}
                if data.get('confirmed_status') is not None and exists is not None \
                        and exists.creator is None and exists.build_status == 0:
                    confirmed[exists.id] = data['confirmed_status']
                for pid, status in (data.get('locked_status_map') or {}).items():
                    confirmed[pid] = status
                for p in unowned_list:
                    if p.id in confirmed:
                        p.build_status = confirmed[p.id]
                        p.save(update_fields=['build_status'])
                        updated_count += 1

                # 合并候选：非构建中 + 已确认结束的无主记录
                mergeable = [p for p in unowned_list if p.build_status != 0]
                if mergeable:
                    # 合并目标：优先复合键命中的非构建中无主记录，否则取最近创建的一条
                    target = exists if (exists is not None and exists.creator is None and exists.build_status != 0) else None
                    if target is None:
                        target = max(mergeable, key=lambda p: p.create_datetime)
                    duplicate_ids = [p.id for p in mergeable if p.id != target.id]
                    if duplicate_ids:
                        # 同一 job 仅保留一条系统同步记录，其余重复记录删除
                        PackageBuild.objects.filter(id__in=duplicate_ids).delete()
                    if not exists:
                        exists = target
                if not exists:
                    # 该 job 已有仍在构建中的无主记录：不得新建（否则每次同步编号前进都新增记录），
                    # 保持现状，等待下次同步确认结束后收敛
                    if any(p.build_status == 0 for p in unowned_list):
                        continue
                    # 创建新的打包记录（携带真实构建状态）
                    PackageBuild.objects.create(
                        project_name=job_name,
                        jenkins_job_name=job_name,
                        build_type='Release',
                        build_status=build_status,
                        jenkins_build_number=build_number,
                        jenkins_build_url=build_url,
                        build_log=tail_log,
                        # 同步写入的是尾部摘要，不标记完整，详情页会按需全量拉取
                        build_log_complete=False,
                    )
                    synced_count += 1
                elif exists.build_status == 0:
                    # 构建中记录保持触发时锁定的编号：Jenkins 上可能已有更新的构建（如他人手动触发），
                    # 同步不得用 lastBuild 覆盖，否则状态查询/制品获取会错取其他构建（如 #44 误判成 #47）。
                    # 但需按锁定编号向 Jenkins 确认真实状态：构建实际已结束时同步本地状态，
                    # 避免轮询中断后列表一直显示"构建中"（#49 构建成功仍显示构建中的根因）
                    if data.get('confirmed_status') is not None:
                        exists.build_status = data['confirmed_status']
                        exists.save()
                        updated_count += 1
                    continue
                else:
                    # 已存在且本地构建已结束：刷新构建状态，保证列表状态准确。
                    # 复合键命中的用户构建记录编号必然一致；被合并的"系统同步"记录
                    # 编号可能已递增（他人构建），需跟随 Jenkins lastBuild 更新
                    changed = False
                    if exists.jenkins_build_number != build_number:
                        exists.jenkins_build_number = build_number
                        changed = True
                    if exists.jenkins_build_url != build_url:
                        exists.jenkins_build_url = build_url
                        changed = True
                    if exists.build_status != build_status:
                        exists.build_status = build_status
                        changed = True
                    if tail_log:
                        # 同步日志列展示内容（最新尾部日志）
                        exists.build_log = tail_log
                        exists.build_log_complete = False
                        changed = True
                    if changed:
                        exists.save()
                        updated_count += 1

            # 用户构建记录同步结果写库：确认到的真实状态 + 补齐的尾部日志摘要
            for update in data.get('owned_updates') or []:
                try:
                    rec = PackageBuild.objects.get(id=update['id'])
                except PackageBuild.DoesNotExist:
                    continue
                changed = False
                new_status = update.get('build_status')
                if new_status is not None and rec.build_status != new_status:
                    rec.build_status = new_status
                    changed = True
                tail_log = update.get('tail_log') or ''
                if tail_log and rec.build_log != tail_log:
                    rec.build_log = tail_log
                    rec.build_log_complete = False
                    changed = True
                if changed:
                    rec.save()
                    updated_count += 1

            # 补齐项目可见性授权占位：保证授权清单与 Jenkins 项目清单一致，
            # 新项目以"未授权"状态入列（默认仅管理员可见），管理员在配置界面授权后放开
            job_names = [data['job_name'] for data in results]
            existing_perms = set(PackageProjectPermission.objects.filter(
                job_name__in=job_names).values_list('job_name', flat=True))
            new_perms = [PackageProjectPermission(job_name=name) for name in job_names
                         if name not in existing_perms]
            if new_perms:
                PackageProjectPermission.objects.bulk_create(new_perms, ignore_conflicts=True)

            return SuccessResponse(
                data={'synced_count': synced_count, 'updated_count': updated_count, 'total': len(projects)},
                msg=f'同步成功，新增 {synced_count} 个，更新 {updated_count} 个'
            )
        except Exception as e:
            logger.error(f"同步 Jenkins 项目失败: {str(e)}")
            return ErrorResponse(msg=f'同步 Jenkins 项目失败: {str(e)}')
        finally:
            # 无论成功/失败/异常均释放互斥锁，避免锁残留导致后续同步被永久拦截
            # （锁本身带 TTL 兜底，即使进程崩溃也会自动过期）
            cache.delete(SYNC_PROJECTS_LOCK_KEY)

    @action(methods=['get', 'put'], detail=False)
    def project_permissions(self, request):
        """项目可见性授权管理（仅管理员）：GET 获取全部授权清单，PUT 按 job_name 幂等保存授权"""
        if not request.user.is_superuser:
            return ErrorResponse(msg='无权限操作项目可见性配置')
        if request.method == 'GET':
            # 授权清单为空时自动从 Jenkins 拉取项目列表补齐占位（不拉状态/日志，轻量），
            # 保证管理员首次打开配置界面即可看到全部项目并授权。
            # 拉取放后台线程执行：Jenkins 不可达时同步等待最长 60s 会拖垮接口/触发前端超时
            if not PackageProjectPermission.objects.exists():
                def _fill_placeholders():
                    try:
                        jenkins = JenkinsService()
                        projects = jenkins.get_projects()
                        PackageProjectPermission.objects.bulk_create(
                            [PackageProjectPermission(job_name=p['name']) for p in projects],
                            ignore_conflicts=True,
                        )
                    except Exception as e:
                        logger.warning(f"后台补齐项目授权占位失败: {str(e)}")

                threading.Thread(target=_fill_placeholders, daemon=True).start()
            perms = PackageProjectPermission.objects.prefetch_related(
                'visible_depts', 'visible_roles', 'visible_users').order_by('job_name')
            data = [{
                'job_name': p.job_name,
                'is_public': p.is_public,
                'depts': [{'id': d.id, 'name': d.name} for d in p.visible_depts.all()],
                'roles': [{'id': r.id, 'name': r.name} for r in p.visible_roles.all()],
                'users': [{'id': u.id, 'name': u.name or u.username} for u in p.visible_users.all()],
            } for p in perms]
            # 授权清单为完整列表（非分页），使用 DetailResponse 避免分页包装导致前端取值失败
            return DetailResponse(data=data, msg='获取成功')
        # PUT：按 job_name 保存授权（部门/角色/用户 id 列表 + 公共开关），M2M 变更由 set() 即时生效
        job_name = request.data.get('job_name')
        if not job_name:
            return ErrorResponse(msg='请提供 job_name 参数')
        perm, _ = PackageProjectPermission.objects.get_or_create(job_name=job_name)
        perm.is_public = bool(request.data.get('is_public', False))
        perm.visible_depts.set(request.data.get('visible_depts') or [])
        perm.visible_roles.set(request.data.get('visible_roles') or [])
        perm.visible_users.set(request.data.get('visible_users') or [])
        perm.save(update_fields=['is_public', 'update_datetime'])
        return DetailResponse(data=[], msg='保存成功')

    def _sync_project_data(self, project, existing_map, building_unowned=None, owned_records=None):
        """
        线程内同步单个项目数据（含日志拉取）

        Args:
            project: Jenkins 项目数据
            existing_map: 已存在的本地记录映射 {(jenkins_job_name, jenkins_build_number): PackageBuild}
            building_unowned: 该 job 的"构建中"无主记录列表，用于确认锁定编号真实状态
            owned_records: 该 job 的"用户构建"记录列表，确认构建中真实状态并补齐日志摘要

        Returns:
            待写库数据 dict；项目名缺失时返回 None
        """
        job_name = project.get('name')
        if not job_name:
            return None

        # 解析 Jenkins 最新构建状态（lastBuild 为 None 表示从未构建）
        last_build = project.get('lastBuild') or {}
        build_status = self._map_jenkins_status(last_build)
        build_number = last_build.get('number') if last_build else None
        build_url = last_build.get('url') if last_build else None

        # 仅当需要时拉取尾部日志（避免无谓请求拖慢同步）：仅新建记录需要拉取。
        # 复合键命中的记录构建编号必然一致，无"编号变化"场景；构建中记录由触发链路维护，同步跳过
        exists = existing_map.get((job_name, build_number))
        need_log = bool(build_number) and exists is None

        # 本地状态为“构建中”：向 Jenkins 精确确认锁定编号的真实状态。
        # 前端轮询可能已中断（关闭页面/刷新），导致本地状态停留在“构建中”；
        # 同步时需纠正，但不得用 lastBuild 覆盖编号/URL，避免状态查询/制品获取错取其他构建
        confirmed_status = None
        if exists is not None and exists.build_status == 0 and exists.jenkins_build_number:
            try:
                # 每个线程独立 JenkinsService（Session 非线程安全）
                jenkins = JenkinsService()
                real = jenkins.get_build_status(exists.jenkins_job_name, exists.jenkins_build_number)
                if not real.get('building'):
                    confirmed_status = 1 if real.get('result') == 'SUCCESS' else 2
            except Exception as e:
                logger.warning(f"确认构建中记录状态失败: {exists.jenkins_job_name}, 错误: {str(e)}")

        # 无主记录"构建中"且锁定编号与 lastBuild 不同（编号已前进）：按锁定编号向 Jenkins
        # 确认真实状态。无主记录（系统同步）无触发链路依赖，确认已结束即可解除锁定、
        # 合并收敛；有主记录（用户构建）的编号锁定保护不受影响（其确认走 confirmed_status 分支）
        locked_status_map = {}
        if building_unowned and build_number is not None:
            for locked in building_unowned:
                if not locked.jenkins_build_number or locked.jenkins_build_number == build_number:
                    continue
                try:
                    # 每个线程独立 JenkinsService（Session 非线程安全）
                    jenkins = JenkinsService()
                    real = jenkins.get_build_status(job_name, locked.jenkins_build_number)
                    if not real.get('building'):
                        locked_status_map[locked.id] = 1 if real.get('result') == 'SUCCESS' else 2
                except Exception as e:
                    logger.warning(f"确认构建中无主记录状态失败: {job_name} #{locked.jenkins_build_number}, 错误: {str(e)}")

        tail_log = ''
        if need_log:
            try:
                # 每个线程独立 JenkinsService（Session 非线程安全）
                jenkins = JenkinsService()
                tail_log = jenkins.get_build_console_tail(job_name, build_number)
            except Exception as e:
                logger.warning(f"同步构建日志失败: {job_name}, 错误: {str(e)}")

        # 用户构建记录同步：构建中记录向 Jenkins 确认真实状态（前端轮询可能已中断），
        # 已结束且日志不完整的记录补拉尾部摘要（详情全量日志由 build_log 接口按需拉取）
        owned_updates = []
        for rec in owned_records or []:
            if not rec.jenkins_build_number:
                continue
            new_status = None
            if rec.build_status == 0:
                try:
                    # 每个线程独立 JenkinsService（Session 非线程安全）
                    jenkins = JenkinsService()
                    real = jenkins.get_build_status(job_name, rec.jenkins_build_number)
                    if not real.get('building'):
                        new_status = 1 if real.get('result') == 'SUCCESS' else 2
                except Exception as e:
                    logger.warning(f"确认用户构建记录状态失败: {job_name} #{rec.jenkins_build_number}, 错误: {str(e)}")
            # 已结束（含本次确认结束）且日志不完整：补拉尾部摘要
            final_status = new_status if new_status is not None else rec.build_status
            tail_log_owned = ''
            if final_status != 0 and not rec.build_log_complete:
                try:
                    # 每个线程独立 JenkinsService（Session 非线程安全）
                    jenkins = JenkinsService()
                    tail_log_owned = jenkins.get_build_console_tail(job_name, rec.jenkins_build_number)
                except Exception as e:
                    logger.warning(f"补齐用户构建记录日志失败: {job_name} #{rec.jenkins_build_number}, 错误: {str(e)}")
            if new_status is not None or tail_log_owned:
                owned_updates.append({'id': rec.id, 'build_status': new_status, 'tail_log': tail_log_owned})

        return {
            'job_name': job_name,
            'build_status': build_status,
            'build_number': build_number,
            'build_url': build_url,
            'tail_log': tail_log,
            'need_log': need_log,
            'confirmed_status': confirmed_status,
            'locked_status_map': locked_status_map,
            'owned_updates': owned_updates,
        }

    @staticmethod
    def _map_jenkins_status(last_build):
        """
        将 Jenkins lastBuild 映射为本地构建状态

        Args:
            last_build: Jenkins lastBuild 数据（dict 或 None）

        Returns:
            0=构建中, 1=成功, 2=失败, 3=未构建
        """
        if not last_build:
            return 3  # 从未构建
        if last_build.get('building'):
            return 0
        if last_build.get('result') == 'SUCCESS':
            return 1
        return 2  # FAILURE / UNSTABLE / ABORTED 均视为失败

    @action(methods=['post'], detail=True)
    def trigger_build(self, request, pk=None):
        """触发 Jenkins 构建（接收前端传来的构建参数，每次触发创建独立构建记录）"""
        # 触发模板：仅取其项目/Jenkins 任务信息，不修改模板记录本身，
        # 保证同一 Jenkins 任务的多位用户构建互不覆盖、历史可追溯
        package_build = self.get_object()

        job_name = package_build.jenkins_job_name
        # 从请求中获取构建参数
        build_params = request.data.get('build_params', {})
        need_delivery = request.data.get('need_delivery', False)
        delivery_form_data = request.data.get('delivery_form_data', {})

        # 勾选自动传包：先校验并保存 D 包审批流表单数据，构建成功后由异步任务自动发起审批流
        if need_delivery:
            workflow_type = self._get_delivery_workflow_type()
            if not workflow_type:
                return ErrorResponse(msg=f'未找到"{DELIVERY_WORKFLOW_TYPE_NAME}"流程类型，无法自动传包')

            # auto_fill 字段由构建成功后自动回填，不接受用户填写；配置清单中字段缺失或未开启开关时显式报错
            field_map = self._get_auto_fill_field_map(workflow_type)
            if field_map is None:
                return ErrorResponse(msg=f'"{DELIVERY_WORKFLOW_TYPE_NAME}"表单自动回填字段配置异常（需存在路径/版本名称字段并开启自动回填），无法自动传包')
            auto_fill_keys = set(f['field'] for f in field_map.values())
            form_data = {k: v for k, v in (delivery_form_data or {}).items() if k not in auto_fill_keys}
            error = self._validate_delivery_form(workflow_type, form_data)
            if error:
                return ErrorResponse(msg=error)

        try:
            # 使用当前登录用户的真实身份认证 Jenkins（构建人显示真实用户而非 sqa），
            # 无 SSO 缓存凭证时内部回退默认账号
            jenkins = JenkinsService.for_user(request.user)

            # 触发构建
            result = jenkins.trigger_build(job_name, build_params)

            # 每次触发新建独立构建记录：编号/参数/发包流程均归属本次构建，
            # 即使构建排队中编号未解析（build_number 为 None），记录也独立存在
            build = PackageBuild.objects.create(
                project_name=package_build.project_name or job_name,
                build_type=package_build.build_type or 'Release',
                jenkins_job_name=job_name,
                jenkins_build_number=result.get('build_number'),
                jenkins_build_url=result.get('build_url', ''),
                build_status=0,  # 构建中
                build_params=build_params,
                need_delivery=need_delivery,
                # 构建人归属本次触发用户：无论是否勾选自动传包都记录，保证列表"构建人"列与按用户过滤准确
                creator=request.user,
            )
            if need_delivery:
                # 保存表单数据（Celery 任务中自动发起流程时使用），并重置发起状态为待发起
                build.delivery_form_data = form_data
                build.delivery_workflow_status = 0
                build.save(update_fields=['delivery_form_data', 'delivery_workflow_status'])

            # 投递异步任务拉取日志快照（不传包也投递）：构建中先拉当前全量日志落库，
            # 详情页打开秒出缓存；构建结束后由前端轮询/build_status 兜底再次投递拉取完整日志。
            # 固定 task_id：多处投递不堆积（队列中最多 1 个未执行任务）；排队中编号为空时任务内部重试等待
            try:
                from apps.engineering.tasks import fetch_build_log
                fetch_build_log.apply_async(
                    args=[build.id, build.jenkins_build_number],
                    task_id=f'fetch-build-log-{build.id}',
                )
            except Exception as e:
                logger.warning(f"投递异步拉取构建日志任务失败: {str(e)}")

            # 如果需要传包：投递异步任务，构建成功后自动获取制品路径并自动创建、发起审批流程
            if need_delivery:
                from apps.engineering.tasks import auto_start_delivery_workflow
                # 传入触发时锁定的构建编号：任务重试期间记录编号可能被其他流程更新，
                # 以参数锁定编号查询状态/制品，避免错取 Jenkins 最新构建
                auto_start_delivery_workflow.delay(build.id, build.jenkins_build_number)
                msg = '构建已触发，构建完成后将自动获取制品路径并发起发包审批流程'
            else:
                msg = '构建已触发'

            return SuccessResponse(
                data={
                    'id': build.id,
                    'build_number': result.get('build_number'),
                    'build_url': result.get('build_url', ''),
                },
                msg=msg
            )
        except Exception as e:
            logger.error(f"触发构建失败: {str(e)}")
            return ErrorResponse(msg=f'触发构建失败: {str(e)}')

    @action(methods=['get'], detail=False)
    def delivery_form_schema(self, request):
        """获取发包流程的表单字段定义（供构建弹窗勾选自动传包时动态渲染）"""
        workflow_type = self._get_delivery_workflow_type()
        if not workflow_type:
            return ErrorResponse(msg=f'未找到"{DELIVERY_WORKFLOW_TYPE_NAME}"流程类型，请先执行初始化命令')

        schema = workflow_type.form_schema
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except (TypeError, ValueError):
                schema = []

        # 自动回填字段列表 [{field, label, source}]：按 config.DELIVERY_AUTO_FILL_FIELDS 配置从流程表单解析，
        # source 为回填来源标识（package_path=制品完整路径 / package_version_name=制品文件名），
        # 前端按 source 直接消费；配置或流程表单开关变更后此列表自动同步
        field_map = self._get_auto_fill_field_map(workflow_type)
        auto_fill_fields = []
        if field_map:
            auto_fill_fields = [{'field': f['field'], 'label': f.get('label', ''), 'source': source} for source, f in field_map.items()]
        return DetailResponse(data={
            'workflow_type_id': workflow_type.id,
            'workflow_type_name': workflow_type.name,
            'form_schema': schema or [],
            'auto_fill_fields': auto_fill_fields,
        }, msg='获取成功')

    @action(methods=['get'], detail=True)
    def build_status(self, request, pk=None):
        """查询构建状态"""
        package_build = self.get_object()
        jenkins = JenkinsService()

        build_number = package_build.jenkins_build_number

        # 触发时仍处于排队中（build_number 未解析出来），从 build_url 兜底查 queue item
        if not build_number:
            queue_item_id = jenkins.parse_queue_item_id(package_build.jenkins_build_url)
            if not queue_item_id:
                return ErrorResponse(msg='该构建任务尚未触发')
            try:
                queue_status = jenkins.get_queue_item_status(queue_item_id)
            except Exception as e:
                logger.error(f"获取构建状态失败: {str(e)}")
                return ErrorResponse(msg=f'获取构建状态失败: {str(e)}')
            if queue_status.get('number'):
                # 已分配到构建编号，更新本地记录后继续
                package_build.jenkins_build_number = queue_status['number']
                package_build.save()
                build_number = queue_status['number']
            else:
                # 仍在排队，返回排队状态（前端持续轮询）；单条查询用 DetailResponse，避免分页包装导致前端取不到字段
                return DetailResponse(
                    data={'building': True, 'queued': True, 'result': None, 'duration': 0},
                    msg='构建排队中'
                )

        try:
            status = jenkins.get_build_status(
                package_build.jenkins_job_name,
                build_number
            )

            # 根据 Jenkins 返回结果更新本地状态
            if status.get('building'):
                package_build.build_status = 0  # 构建中
            elif status.get('result') == 'SUCCESS':
                package_build.build_status = 1  # 成功
            elif status.get('result') in ('FAILURE', 'UNSTABLE', 'ABORTED'):
                package_build.build_status = 2  # 失败

            package_build.save()

            # 兜底：构建已结束但日志不完整时投递异步任务补拉全量日志，保证列表日志摘要自动补齐。
            # 覆盖前端轮询中断/页面关闭/未打开详情等场景；固定 task_id + 任务内幂等检查，重复投递无副作用
            if not status.get('building') and not package_build.build_log_complete:
                try:
                    from apps.engineering.tasks import fetch_build_log
                    fetch_build_log.apply_async(
                        args=[package_build.id, build_number],
                        task_id=f'fetch-build-log-{package_build.id}',
                    )
                except Exception as e:
                    logger.warning(f"build_status 兜底投递日志拉取任务失败: {str(e)}")

            # 手动构建成功且未勾选传包：读取 package_info 制品的扫描信息（ScanStatus/ScanReport），
            # 与发包预览/扫描回填链路保持一致，确保轮询结束后制品内容读取完整——ScanStatus 落库供
            # 列表"包扫描状态"列展示，ScanReport 随响应返回（勾选传包时由自动发包链路负责读取，避免重复请求）
            if (not status.get('building') and status.get('result') == 'SUCCESS'
                    and not package_build.need_delivery):
                try:
                    result = jenkins.get_build_package_info(
                        package_build.jenkins_job_name,
                        build_number
                    )
                    package_info = (result or {}).get('package_info') or {}
                    # 字段名由配置指定：状态/报告对应 package_info 的 ScanStatus=/ScanReport=
                    scan_status = package_info.get(PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_STATUS_FIELD], '')
                    scan_report = package_info.get(PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_REPORT_FIELD], '')
                    if scan_status and package_build.scan_status != scan_status:
                        package_build.scan_status = scan_status
                        package_build.save(update_fields=['scan_status'])
                    status['scan_status'] = scan_status
                    status['scan_report'] = scan_report
                except Exception as e:
                    logger.warning(f"读取构建扫描信息失败: {str(e)}")

            # 兜底：构建成功结束且勾选了自动传包但流程尚未自动发起时，投递异步任务补发起
            # （Celery 任务本身会幂等跳过，此处主要覆盖任务丢失/worker 未启动等场景）
            if (not status.get('building')
                    and status.get('result') == 'SUCCESS'
                    and package_build.need_delivery
                    and package_build.delivery_workflow_status == 0
                    and package_build.delivery_form_data):
                try:
                    from apps.engineering.tasks import auto_start_delivery_workflow
                    auto_start_delivery_workflow.delay(package_build.id, package_build.jenkins_build_number)
                    logger.info(f"build_status 兜底触发自动发包流程创建: {package_build.id}")
                except Exception as e:
                    logger.warning(f"build_status 兜底投递任务失败: {str(e)}")

            # 单条查询用 DetailResponse，避免分页包装导致前端取不到字段
            return DetailResponse(
                data={**status, 'build_number': build_number},
                msg='获取成功'
            )
        except Exception as e:
            logger.error(f"获取构建状态失败: {str(e)}")
            return ErrorResponse(msg=f'获取构建状态失败: {str(e)}')

    @action(methods=['get'], detail=True)
    def build_log(self, request, pk=None):
        """获取构建日志（支持增量拉取：offset=0 全量并保存，offset>0 仅返回新增内容）

        异步化说明：数据库无完整日志缓存时不再同步拉取全量日志，而是立即返回已有内容
        并投递后台任务 fetch_build_log 拉取完整日志，响应带 log_ready 标记：
        - log_ready=True：返回的 log 即为完整/可用内容
        - log_ready=False：完整日志后台加载中，前端轮询本接口直到 log_ready=True
        """
        package_build = self.get_object()

        build_number = package_build.jenkins_build_number

        # 排队中兜底：从 build_url 解析 queue item 获取真实构建编号
        if not build_number:
            jenkins = JenkinsService()
            queue_item_id = jenkins.parse_queue_item_id(package_build.jenkins_build_url)
            if queue_item_id:
                try:
                    queue_status = jenkins.get_queue_item_status(queue_item_id)
                except Exception:
                    queue_status = {}
                if queue_status.get('number'):
                    package_build.jenkins_build_number = queue_status['number']
                    package_build.save()
                    build_number = queue_status['number']
            if not build_number:
                return ErrorResponse(msg='构建排队中，暂无日志')

        # 解析偏移参数（字节偏移，与 Jenkins consoleText start 参数语义一致，避免中文日志字符/字节错位）
        offset = request.query_params.get('offset', 0)
        try:
            offset = max(int(offset), 0)
        except (TypeError, ValueError):
            offset = 0

        db_log = package_build.build_log or ''
        db_bytes = len(db_log.encode('utf-8'))

        # 增量刷新且构建已结束：日志不再增长；数据库日志比前端已展示的更长时补齐差额（如详情曾降级展示尾部摘要）
        if offset > 0 and package_build.build_status != 0:
            if offset < db_bytes:
                content = db_log.encode('utf-8')[offset:].decode('utf-8', errors='replace')
                return DetailResponse(data={'log': content, 'offset': db_bytes, 'log_ready': True}, msg='获取成功')
            return DetailResponse(data={'log': '', 'offset': db_bytes, 'log_ready': True}, msg='获取成功')

        # 全量请求且构建已结束、数据库已有完整日志：直接返回，避免每次打开详情都重复全量拉取超大日志
        if offset == 0 and package_build.build_status != 0 and db_log and package_build.build_log_complete:
            return DetailResponse(data={'log': db_log, 'offset': db_bytes, 'log_ready': True}, msg='获取成功')

        # 异步化：数据库无完整日志缓存时（构建结束但未拉取过 / 构建中无缓存），不再同步拉取全量日志，
        # 立即返回已有内容（可能为空）并投递后台任务拉取完整日志，响应带 log_ready=False 供前端轮询等待；
        # 构建中已有缓存时直接返回缓存（前端通过 offset>0 增量刷新获取最新内容，避免重复全量拉取）
        if offset == 0 and not package_build.build_log_complete:
            if package_build.build_status != 0:
                # 构建已结束但日志不完整（刚触发/同步记录/轮询中断）：后台拉全量
                try:
                    from apps.engineering.tasks import fetch_build_log
                    # 固定 task_id：前端轮询期间重复投递不会堆积（队列中最多 1 个未执行任务）
                    fetch_build_log.apply_async(
                        args=[package_build.id, build_number],
                        task_id=f'fetch-build-log-{package_build.id}',
                    )
                except Exception as e:
                    logger.warning(f"投递异步拉取构建日志任务失败: {str(e)}")
                return DetailResponse(data={'log': db_log, 'offset': db_bytes, 'log_ready': False, 'building': False}, msg='获取成功（日志后台加载中）')
            if not db_log:
                # 构建中且无任何缓存：后台先拉当前全量快照，前端再增量刷新
                try:
                    from apps.engineering.tasks import fetch_build_log
                    fetch_build_log.apply_async(
                        args=[package_build.id, build_number],
                        task_id=f'fetch-build-log-{package_build.id}',
                    )
                except Exception as e:
                    logger.warning(f"投递异步拉取构建日志任务失败: {str(e)}")
                return DetailResponse(data={'log': '', 'offset': 0, 'log_ready': False, 'building': True}, msg='获取成功（日志后台加载中）')
            # 构建中已有缓存：直接返回，不重复投递后台任务
            return DetailResponse(data={'log': db_log, 'offset': db_bytes, 'log_ready': False, 'building': True}, msg='获取成功（构建中缓存）')

        try:
            jenkins = JenkinsService()
            if offset > 0:
                # 构建中增量拉取：仅返回新增内容，不写库（全量由后台任务/offset=0 时维护）
                content = jenkins.get_build_console(
                    package_build.jenkins_job_name,
                    build_number,
                    offset=offset
                )
                return DetailResponse(data={'log': content, 'offset': offset + len(content.encode('utf-8')), 'log_ready': True}, msg='获取成功')

            console_text = jenkins.get_build_console(
                package_build.jenkins_job_name,
                build_number
            )

            # 更新构建日志（构建结束才标记完整，构建中日志仍在增长）
            package_build.build_log = console_text
            package_build.build_log_complete = package_build.build_status != 0
            package_build.save()

            return DetailResponse(data={'log': console_text, 'offset': len(console_text.encode('utf-8')), 'log_ready': True}, msg='获取成功')
        except Exception as e:
            # Jenkins 不可达时降级返回数据库已有日志，保证已同步的日志仍可查看
            if db_log:
                logger.warning(f"获取构建日志失败，降级返回数据库日志: {str(e)}")
                return DetailResponse(data={'log': db_log, 'offset': db_bytes, 'log_ready': True}, msg='获取成功（数据库缓存）')
            logger.error(f"获取构建日志失败: {str(e)}")
            return ErrorResponse(msg=f'获取构建日志失败: {str(e)}')

    @action(methods=['get'], detail=False, url_path='scan_report')
    def scan_report(self, request):
        """获取扫描报告 html 内容（report_path 查询参数，供审批详情"查看报告"弹窗使用）"""
        report_path = (request.query_params.get('report_path') or '').strip()
        if not report_path:
            return ErrorResponse(msg='请提供 report_path 参数')
        try:
            from utils.package_scan import read_file
            content = read_file(report_path)
        except Exception as e:
            logger.error(f"获取扫描报告失败: {str(e)}")
            return ErrorResponse(msg=f'获取扫描报告失败: {str(e)}')
        if not content:
            return ErrorResponse(msg='报告文件为空或不存在')
        # 单条操作结果用 DetailResponse，避免分页包装导致前端取不到字段
        return DetailResponse(data={'content': content}, msg='获取成功')

    @action(methods=['post'], detail=True)
    def deliver_package_preview(self, request, pk=None):
        """
        发包预览：校验构建状态并返回本次构建的制品路径，不创建流程

        供前端"发包确认"弹窗展示制品路径并支持用户手动修改；
        确认后才调用 deliver_package 真正创建流程
        """
        package_build = self.get_object()
        package_path, error = self._resolve_deliver_info(package_build)
        if error:
            return ErrorResponse(msg=error)

        # 包安全扫描信息：本次构建已有 ScanStatus 时返回扫描状态与报告路径，供发包弹窗展示
        scan_status = ''
        scan_report = ''
        try:
            jenkins = JenkinsService()
            result = jenkins.get_build_package_info(
                package_build.jenkins_job_name,
                package_build.jenkins_build_number
            )
            package_info = (result or {}).get('package_info') or {}
            # 字段名由配置指定：状态/报告对应 package_info 的 ScanStatus=/ScanReport=
            scan_status = package_info.get(PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_STATUS_FIELD], '')
            scan_report = package_info.get(PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_REPORT_FIELD], '')
        except Exception as e:
            logger.warning(f"读取构建扫描信息失败: {str(e)}")

        # 扫描状态落库（发包链路不触发新扫描，构建时已完成：读到的 PASS/FAIL 直接写入，供列表展示）
        if scan_status and package_build.scan_status != scan_status:
            try:
                package_build.scan_status = scan_status
                package_build.save(update_fields=['scan_status'])
            except Exception as e:
                logger.warning(f"落库历史扫描状态失败: {str(e)}")

        # 单条操作结果用 DetailResponse，避免分页包装导致前端取不到字段
        return DetailResponse(
            data={
                'package_build_id': package_build.id,
                'project_name': package_build.project_name,
                'jenkins_job_name': package_build.jenkins_job_name,
                'jenkins_build_number': package_build.jenkins_build_number,
                'package_path': package_path,
                'scan_status': scan_status,
                'scan_report': scan_report,
            },
            msg='获取成功'
        )

    def _resolve_deliver_info(self, package_build):
        """
        校验构建状态并解析本次构建的制品路径（发包预览与发包接口复用的公共逻辑）

        Returns:
            (package_path, None) 成功；或 (None, error_msg) 失败
        """
        jenkins = JenkinsService()

        # 本地状态非成功时向 Jenkins 确认实际状态（避免构建刚结束状态未同步导致误拒）
        if package_build.build_status != 1 and package_build.jenkins_build_number:
            try:
                status = jenkins.get_build_status(
                    package_build.jenkins_job_name,
                    package_build.jenkins_build_number
                )
                if status.get('building'):
                    return None, '构建仍在进行中，完成后才能发包'
                if status.get('result') == 'SUCCESS':
                    package_build.build_status = 1
                    package_build.save()
                else:
                    return None, '构建未成功，无法发包'
            except Exception as e:
                logger.warning(f"确认构建状态失败: {str(e)}")

        if package_build.build_status != 1:
            return None, '仅构建成功的记录可发包'
        if not package_build.jenkins_build_number:
            return None, '该记录缺少构建编号，请先同步或重新构建'

        # 获取本次构建的制品路径（package_info 制品中的 Package= 字段）
        try:
            result = jenkins.get_build_package_info(
                package_build.jenkins_job_name,
                package_build.jenkins_build_number
            )
        except Exception as e:
            logger.error(f"获取构建制品失败: {str(e)}")
            return None, f'获取构建制品失败: {str(e)}'

        if not result or not result.get('package_path'):
            return None, '未获取到软件包制品信息，请确认该构建已产出 package_info 制品'

        return result['package_path'], None

    @action(methods=['post'], detail=True)
    def deliver_package(self, request, pk=None):
        """
        发包：获取本次构建（构建编号）成功的制品路径，创建"软件包(D包)发包流程"

        流程：校验构建成功 -> 拉取 package_info 制品解析 Package 路径（或使用
        用户在发包确认弹窗中手动修改后的路径字段，key 由自动回填开关驱动解析）->
        创建 D 包流程实例并将路径写入"软件包存放路径"字段（auto_fill 字段自动回填）
        - 已通过构建弹窗填写过申请表单（delivery_form_data）时：创建后自动发起流程
        - 未填写过表单时：创建草稿，由用户前往流程管理补全后提交
        """
        package_build = self.get_object()

        # 用户可在发包确认弹窗中手动修改制品路径：请求体携带路径字段
        # （form_schema 中开启"自动回填"开关且回填内容为路径的字段 key）优先使用
        workflow_type = self._get_delivery_workflow_type()
        if not workflow_type:
            return ErrorResponse(msg=f'未找到"{DELIVERY_WORKFLOW_TYPE_NAME}"流程类型，无法发包')
        field_map = self._get_auto_fill_field_map(workflow_type)
        if field_map is None:
            return ErrorResponse(msg=f'"{DELIVERY_WORKFLOW_TYPE_NAME}"表单自动回填字段配置异常（需存在路径/版本名称字段并开启自动回填），无法发包')
        # 路径字段 key 从自动回填字段映射中按回填来源标识（package_path，见 config.DELIVERY_AUTO_FILL_FIELDS）
        # 解析，与前端按 source 消费的逻辑保持一致；配置缺失时显式报错而非 KeyError
        path_field = field_map.get('package_path', {}).get('field')
        if not path_field:
            return ErrorResponse(msg=f'"{DELIVERY_WORKFLOW_TYPE_NAME}"表单未配置"软件包存放路径"自动回填字段，无法发包')

        # 未传则回退自动解析（保持向后兼容）
        manual_path = ''
        if request.data and isinstance(request.data, dict):
            manual_path = (request.data.get(path_field) or '').strip()

        if manual_path:
            package_path = manual_path
        else:
            package_path, error = self._resolve_deliver_info(package_build)
            if error:
                return ErrorResponse(msg=error)

        # 打包管理构建后的软件包已就位于制品路径，发包时不再剪切到备份路径：
        # 扫描软件包路径直接使用原始制品路径，回填到审批流
        scan_package_path = package_path

        # 已填写过申请表单：创建流程后自动发起，减少人工干预（传入已确认的路径，避免重复解析 Jenkins）
        if package_build.delivery_form_data:
            instance, error = self._create_and_start_delivery_workflow(package_build, package_path=package_path, scan_package_path=scan_package_path)
            if error:
                return ErrorResponse(msg=error)
            # 单条操作结果用 DetailResponse，避免分页包装导致前端取不到字段
            return DetailResponse(
                data={
                    'workflow_instance_id': instance.id,
                    'instance_no': instance.instance_no,
                    'title': instance.title,
                    'started': True,
                },
                msg=f'已自动创建并发起{DELIVERY_WORKFLOW_TYPE_NAME}'
            )

        # 未填写过申请表单：创建草稿流程，由用户补全申请信息后提交
        instance = self._create_delivery_workflow(request, package_build, package_path=package_path, scan_package_path=scan_package_path)
        if not instance:
            return ErrorResponse(msg=f'创建{DELIVERY_WORKFLOW_TYPE_NAME}失败，请检查流程类型配置')

        # 单条操作结果用 DetailResponse，避免分页包装导致前端 res.data.package_path 取不到字段
        return DetailResponse(
            data={
                'workflow_instance_id': instance.id,
                'instance_no': instance.instance_no,
                'title': instance.title,
                'package_path': package_path,
            },
            msg=f'已创建{DELIVERY_WORKFLOW_TYPE_NAME}，软件包存放路径已自动填写'
        )

    @classmethod
    def _trigger_package_scan(cls, workflow_instance, package_path):
        """
        触发包安全扫描：将软件包剪切到备份路径（目录按当天年月日、文件按"时间戳_包名"重命名）
        后，调用 config.PACKAGE_SECURITY_SCAN_JOB 项目构建，把扫描路径传给 package_path 参数，
        并投递异步任务轮询扫描结果、回填审批流程的三个扫描字段。

        Args:
            workflow_instance: 审批流程实例（回填对象，需含 workflow_type/applicant）
            package_path: 软件包远程绝对路径（共享路径拼接结果或用户确认的路径）

        Returns:
            (scan_package_path, None) 成功；或 (None, error_msg) 失败
        """
        if not package_path:
            return None, '软件包路径为空，无法触发扫描'

        # 幂等防重复触发：同一流程实例已触发过扫描（字段3已回填）时直接返回已有路径，
        # 避免并发/重复提交导致重复触发 Jenkins 扫描构建、重复投递轮询任务（重复驱动审批）
        from apps.lyworkflow.models import WorkflowInstance
        with transaction.atomic():
            locked_instance = WorkflowInstance.objects.select_for_update().get(id=workflow_instance.id)
            existed_form_data = cls._parse_form_data(locked_instance.form_data)
            if existed_form_data.get(PACKAGE_SCAN_PATH_FIELD) or existed_form_data.get('_scan_package_path'):
                logger.info(f'流程 {locked_instance.instance_no} 已触发过包安全扫描，跳过重复触发')
                return (existed_form_data.get(PACKAGE_SCAN_PATH_FIELD) or ''), None

        # 1. 剪切到备份路径（先按产品名创建目录、再按当天年月日创建，文件按时间戳_包名重命名；共享目录直接本地文件操作）
        from utils.package_scan import move_package_to_backup, resolve_backup_product_dir
        # 产品目录从审批表单中选中的产品名解析（GloryEX 系列统一归入 GloryEX，其余一对一）
        form_data = cls._parse_form_data(workflow_instance.form_data)
        product_dir = resolve_backup_product_dir(form_data.get(PACKAGE_SCAN_PRODUCT_NAME_FIELD))
        scan_package_path = move_package_to_backup(package_path, product_dir)
        if not scan_package_path:
            return None, '软件包剪切到备份路径失败，请检查共享路径是否可访问'

        # 传给 Jenkins 扫描项目的路径：即剪切后的备份路径
        scan_path_for_jenkins = scan_package_path

        # 2. 触发 package_security_scan 构建（package_path 入参传扫描路径，入参名由配置指定）
        try:
            jenkins = JenkinsService.for_user(workflow_instance.applicant)
            scan_path_param = PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_PATH_FIELD]
            result = jenkins.trigger_build(PACKAGE_SECURITY_SCAN_JOB, {scan_path_param: scan_path_for_jenkins})
        except Exception as e:
            logger.error(f"触发包安全扫描构建失败: {str(e)}")
            return None, f'触发包安全扫描构建失败: {str(e)}'

        # 3. 扫描状态落库到关联的打包构建记录（列表页展示；手动创建的审批流可能无关联记录，忽略即可）
        package_build = None
        try:
            package_build = workflow_instance.package_builds.first()
            if package_build:
                package_build.scan_job_name = PACKAGE_SECURITY_SCAN_JOB
                package_build.scan_build_number = result.get('build_number')
                package_build.scan_status = 'SCANNING'
                package_build.save(update_fields=['scan_job_name', 'scan_build_number', 'scan_status'])
        except Exception as e:
            logger.warning(f"落库包扫描状态失败: {str(e)}")

        # 4. 立即回填字段3（触发扫描时传给 Jenkins 的包扫描路径）；扫描状态/报告由异步任务完成后回填
        try:
            form_data = cls._parse_form_data(workflow_instance.form_data)
            form_data[PACKAGE_SCAN_PATH_FIELD] = scan_path_for_jenkins
            # 锁定本次扫描对应的打包构建记录：异步任务回填时按 id 精确落库，
            # 避免流程关联多条构建记录时 first() 取创建时间最新的一条而写错（如 #77 的扫描写到 #78）
            if package_build:
                form_data['_scan_package_build_id'] = package_build.id
            workflow_instance.form_data = form_data
            workflow_instance.save(update_fields=['form_data'])
        except Exception as e:
            logger.warning(f"回填包扫描路径字段失败: {str(e)}")

        # 5. 投递异步任务：轮询扫描构建状态并回填扫描状态/报告详情
        try:
            from apps.engineering.tasks import run_package_security_scan
            run_package_security_scan.delay(
                workflow_instance_id=workflow_instance.id,
                package_path=scan_path_for_jenkins,
                job_name=PACKAGE_SECURITY_SCAN_JOB,
                build_number=result.get('build_number'),
                build_url=result.get('build_url', ''),
                package_build_id=package_build.id if package_build else None,
            )
        except Exception as e:
            logger.error(f"投递包安全扫描异步任务失败: {str(e)}")

        return scan_package_path, None

    @staticmethod
    def _parse_form_data(form_data):
        """兼容 form_data 双重 JSON 编码：字符串先反序列化为 dict，保证后续 .get() 安全"""
        if isinstance(form_data, str):
            try:
                return json.loads(form_data) or {}
            except (TypeError, ValueError):
                return {}
        return dict(form_data or {})

    @classmethod
    def _get_scan_info(cls, job_name, build_number, scan_build_number=None, package_path=None):
        """
        读取构建 package_info 中的扫描状态/报告字段（字段名由 config.PACKAGE_SCAN_AUTO_FILL_FIELDS 配置）
        并获取报告 html 内容

        Args:
            job_name: 打包构建 Jenkins 任务名
            build_number: 打包构建编号
            scan_build_number: 关联的扫描构建编号（调用方已解析时传入，避免重复查询）
            package_path: 软件包存放路径（发包直接回填时作为"扫描软件包路径"回填，
                提交审批流时据此识别已扫描过，无需再触发扫描）

        Returns:
            {'package_scan_status': ..., 'package_scan_report': html内容或路径,
             'package_scan_path': ..., 'package_scan_build_number': ...}；
            构建无扫描信息（扫描状态或报告为空）返回 None
        """
        try:
            jenkins = JenkinsService()
            result = jenkins.get_build_package_info(job_name, build_number)
        except Exception as e:
            logger.warning(f"读取构建扫描信息失败: {job_name} #{build_number}, 错误: {str(e)}")
            return None
        package_info = (result or {}).get('package_info') or {}
        # 字段名由配置指定：状态/报告对应 package_info 的 ScanStatus=/ScanReport=
        scan_status_key = PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_STATUS_FIELD]
        scan_report_key = PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_REPORT_FIELD]
        scan_status = package_info.get(scan_status_key, '')
        scan_report = package_info.get(scan_report_key, '')
        # 扫描状态与报告都非空才视为扫描已完成：发包创建审批流时直接回填，无需再触发扫描
        if not scan_status or not scan_report:
            return None
        report_content = cls._fetch_scan_report_content(job_name, build_number, scan_report)
        # 扫描构建编号：调用方已解析时直接使用（避免重复查询）；否则按上游触发关系定位
        if not scan_build_number:
            try:
                scan_build_number = jenkins.find_downstream_build_number(
                    job_name, build_number, PACKAGE_SECURITY_SCAN_JOB
                )
            except Exception as e:
                logger.warning(f"解析扫描构建编号失败: {str(e)}")
                scan_build_number = None
        return {
            'package_scan_status': scan_status,
            # 报告 html 内容优先；内容获取失败时回退路径字符串（前端按路径发起二次获取）
            'package_scan_report': report_content or scan_report,
            'package_scan_path': package_path or '',
            'package_scan_build_number': str(scan_build_number or ''),
        }

    @staticmethod
    def _fetch_scan_report_content(job_name, build_number, scan_report_path):
        """
        获取扫描报告 html 内容：优先从 Jenkins 构建制品下载（文件名匹配），
        兜底直接读取 ScanReport 指向的本地文件（共享目录挂载/映射）

        Returns:
            html 内容字符串；获取失败返回空串
        """
        if not scan_report_path:
            return ''
        content = ''
        try:
            jenkins = JenkinsService()
            content = jenkins.get_build_artifact_content(
                job_name, build_number,
                filename_keyword=os.path.basename(scan_report_path)
            ) or ''
        except Exception as e:
            logger.warning(f"从 Jenkins 制品获取扫描报告失败: {str(e)}")
        if not content:
            try:
                from utils.package_scan import read_file
                content = read_file(scan_report_path) or ''
            except Exception as e:
                logger.warning(f"本地读取扫描报告失败: {str(e)}")
        return content

    @classmethod
    def _create_and_start_delivery_workflow(cls, package_build, build_number=None, package_path=None, scan_package_path=None):
        """
        构建成功后自动创建"软件包(D包)发包流程"并自动发起（由 Celery 异步任务或发包接口调用）

        流程：幂等检查 -> 拉取制品路径 -> 创建流程实例（回填软件包存放路径）-> 自动发起

        Args:
            package_build: 打包构建记录对象
            build_number: 本次构建编号（触发时锁定传入，防止记录编号被更新为 Jenkins 最新构建）
            package_path: 已确认的软件包存放路径（发包接口传入用户修改后的值；
                未传时自动从 Jenkins package_info 制品解析）
            scan_package_path: 扫描软件包路径（发包链路不再剪切备份，直接使用制品路径；
                未传时回退 package_path，与自动发包链路行为一致）

        Returns:
            (instance, None) 成功；或 (None, error_msg) 失败
        """
        from apps.lyworkflow.models import WorkflowInstance
        from apps.lyworkflow.engine import FlowEngine

        # 构建编号以触发时锁定的为准；未传时回退到记录编号（手动发包等场景）
        build_number = build_number or package_build.jenkins_build_number

        # 关联扫描构建编号：扫描由构建脚本内部触发（未走系统触发链路）时，按上游触发
        # 关系（本构建 -> 扫描项目构建）定位扫描构建编号并落库，供打包管理列表展示
        # "扫描项目/扫描构建号"；放在幂等检查前，保证任务重试/重复调用也能补齐
        scan_build_number = None
        if build_number:
            try:
                jenkins = JenkinsService()
                scan_build_number = jenkins.find_downstream_build_number(
                    package_build.jenkins_job_name, build_number, PACKAGE_SECURITY_SCAN_JOB
                )
                if scan_build_number and (
                        package_build.scan_job_name != PACKAGE_SECURITY_SCAN_JOB
                        or package_build.scan_build_number != scan_build_number):
                    # 扫描状态未知时先标记扫描中（构建成功但扫描尚未完成），
                    # 后续扫描信息回填/监控任务完成后更新为真实状态
                    if not package_build.scan_status:
                        package_build.scan_status = 'SCANNING'
                    package_build.scan_job_name = PACKAGE_SECURITY_SCAN_JOB
                    package_build.scan_build_number = scan_build_number
                    package_build.save(update_fields=['scan_job_name', 'scan_build_number', 'scan_status'])
            except Exception as e:
                logger.warning(f"关联扫描构建编号失败: {str(e)}")

        # 幂等：已有草稿或审批中的发包流程时跳过，避免重复创建
        # 外键可能悬空（流程实例被直接删除），防御性获取，悬空时视为不存在
        existing = WorkflowInstance.objects.filter(id=package_build.workflow_instance_id).first() if package_build.workflow_instance_id else None
        if existing and existing.status in (0, 1):
            logger.info(f"已有进行中的发包流程，跳过自动创建: {package_build.id} -> {existing.instance_no}")
            # 已走发包流程：确保"是否传包"标记为是（列表页"是否传包"列展示）
            if not package_build.need_delivery:
                package_build.need_delivery = True
                package_build.save(update_fields=['need_delivery'])
            return existing, None

        workflow_type = cls._get_delivery_workflow_type()
        if not workflow_type:
            return None, f'未找到"{DELIVERY_WORKFLOW_TYPE_NAME}"流程类型，请先执行初始化命令'

        # 未传入已确认路径时，自动从 Jenkins 解析本次构建的制品路径
        if package_path is None:
            # 构建编号必须精确锁定本次构建：缺失时直接失败，避免误取其他构建的制品路径
            if not build_number:
                return None, '该记录缺少本次构建编号，无法精确获取制品路径，请先同步或重新构建'

            # 获取本次构建（build_number）成功后的制品路径（package_info 制品中的 Package= 字段）
            try:
                jenkins = JenkinsService()
                result = jenkins.get_build_package_info(
                    package_build.jenkins_job_name,
                    build_number
                )
            except Exception as e:
                logger.error(f"获取构建制品失败: {str(e)}")
                return None, f'获取构建制品失败: {str(e)}'

            if not result or not result.get('package_path'):
                return None, '未获取到软件包制品信息，请确认该构建已产出 package_info 制品'

            package_path = result['package_path']

        # 表单数据 = 用户填写内容 + 自动回填字段回填（字段与回填内容均由流程表单配置驱动，无需任何配置文件）
        field_map = cls._get_auto_fill_field_map(workflow_type)
        if field_map is None:
            return None, f'"{DELIVERY_WORKFLOW_TYPE_NAME}"表单自动回填字段配置异常（需存在路径/版本名称字段并开启自动回填），无法自动发起'
        form_data = dict(package_build.delivery_form_data or {})
        form_data = cls._fill_auto_fill_values(form_data, field_map, package_path)

        # 包安全扫描信息：本次构建 package_info 中已有扫描状态时，回填扫描状态与报告详情（固定字段）；
        # 扫描软件包路径回填制品路径（scan_package_path，发包不再剪切备份），软件包存放路径仍回填原始制品路径（package_path）
        scan_info = None
        try:
            scan_info = cls._get_scan_info(
                package_build.jenkins_job_name, build_number,
                scan_build_number=scan_build_number, package_path=scan_package_path or package_path
            )
            if scan_info:
                form_data = cls._fill_scan_values(form_data, scan_info)
                # 同步落库扫描状态到打包构建记录（列表页"包扫描状态"列展示，与手动发包预览链路一致）
                scan_status = scan_info.get('package_scan_status') or ''
                if scan_status and package_build.scan_status != scan_status:
                    package_build.scan_status = scan_status
                    package_build.save(update_fields=['scan_status'])
        except Exception as e:
            logger.warning(f"回填包扫描信息失败: {str(e)}")

        applicant = package_build.creator
        if not applicant:
            return None, '该记录缺少申请人信息，无法自动发起流程'

        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        instance_no = f'WF{timestamp}{workflow_type.code}'

        with transaction.atomic():
            instance = WorkflowInstance.objects.create(
                instance_no=instance_no,
                workflow_type=workflow_type,
                # 版本号可能为空，为空时不拼接，避免流程标题出现 'None' 占位
                title='软件包发包 - ' + package_build.project_name + (' ' + package_build.project_version if package_build.project_version else ''),
                applicant=applicant,
                applicant_dept=applicant.dept if hasattr(applicant, 'dept') else None,
                status=0,  # 草稿
                current_step=1,
                total_steps=cls._calculate_total_steps(workflow_type),
                form_data=form_data,
                submit_round=1,  # 首次发起轮次
            )

            # 关联到打包构建记录
            package_build.workflow_instance = instance
            package_build.delivery_workflow_status = 1  # 已自动发起
            # 已走发包流程：记录"是否需要传包"标记为是（列表页"是否传包"列展示；
            # 自动发包链路本就为是，手动发包场景由否置为是）
            package_build.need_delivery = True
            package_build.save()

            # 自动发起流程（创建第一步审批任务并通知审批人/抄送人）
            engine = FlowEngine(instance)
            engine.start()

        logger.info(f'自动创建并发起发包审批流程成功: {instance_no}')

        # 扫描构建由构建脚本内部触发且构建成功时尚未完成（package_info 无扫描状态）：
        # 投递轮询任务继续监控扫描项目构建，扫描完成后回填审批流程扫描字段并驱动审批
        # （与手动触发扫描链路行为一致，避免列表页扫描状态停留在 SCANNING）
        if scan_build_number and not scan_info:
            try:
                from apps.engineering.tasks import run_package_security_scan
                run_package_security_scan.delay(
                    workflow_instance_id=instance.id,
                    package_path='',
                    job_name=PACKAGE_SECURITY_SCAN_JOB,
                    build_number=scan_build_number,
                    package_build_id=package_build.id,
                )
            except Exception as e:
                logger.error(f"投递包安全扫描异步任务失败: {str(e)}")

        return instance, None

    @staticmethod
    def _get_delivery_workflow_type():
        """查找发包流程类型（流程名由 config 配置）"""
        from apps.lyworkflow.models import WorkflowType
        return WorkflowType.objects.filter(name=DELIVERY_WORKFLOW_TYPE_NAME).first()

    @staticmethod
    def _get_auto_fill_field_map(workflow_type):
        """
        按 config.DELIVERY_AUTO_FILL_FIELDS 配置解析自动回填字段，返回 {回填来源标识: 字段定义} 映射

        源头即配置：遍历配置清单 {表单字段 key: 回填来源标识}，在流程表单（form_schema）中查找对应字段，
        并校验已开启"自动回填"开关（auto_fill 非空即视为开启）；任一配置项字段缺失或未开启开关即返回 None，
        由调用方显式报错（配置错误应暴露而非静默兼容）
        """
        schema = workflow_type.form_schema
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except (TypeError, ValueError):
                schema = []
        field_by_key = {f.get('field'): f for f in schema or []}
        field_map = {}
        for field_key, source in DELIVERY_AUTO_FILL_FIELDS.items():
            field = field_by_key.get(field_key)
            if not field or not (field.get('auto_fill') and field.get('field')):
                return None
            field_map[source] = field
        return field_map

    @staticmethod
    def _fill_auto_fill_values(form_data, field_map, package_path):
        """
        按自动回填字段映射回填表单值，返回回填后的 form_data

        遍历 {回填来源: 字段定义} 映射，按来源从 AUTO_FILL_VALUE_PROVIDERS 注册表取值；
        新增回填字段零代码零配置；仅当新增"回填来源类型"时才需在注册表添加取值逻辑
        """
        for source, field in field_map.items():
            provider = AUTO_FILL_VALUE_PROVIDERS.get(source)
            if provider is None:
                logger.warning(f'未注册自动回填来源: {source}（字段: {field.get("field")}），已跳过')
                continue
            form_data[field.get('field')] = provider(package_path)
        return form_data

    @staticmethod
    def _fill_scan_values(form_data, scan_info):
        """
        按包扫描字段配置回填审批流程 form_data（固定字段，无需流程表单配置/自动回填开关）

        scan_info 需包含 package_scan_status / package_scan_report / package_scan_path /
        package_scan_build_number 四个键（可为空串）；值非空才回填，避免扫描未完成时覆盖已有内容
        """
        for field_key in list(PACKAGE_SCAN_AUTO_FILL_FIELDS) + [PACKAGE_SCAN_BUILD_NUMBER_FIELD]:
            value = scan_info.get(field_key)
            if value:
                form_data[field_key] = value
        return form_data

    @staticmethod
    def _is_empty(value):
        """判断表单值是否为空（None/空白串/空数组均视为空）"""
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple)):
            return len(value) == 0
        return False

    @staticmethod
    def _match_condition(rule, form_data):
        """判断条件规则是否满足（与前端 checkCondition 逻辑对齐）"""
        trigger_field = rule.get('trigger_field')
        operator = rule.get('operator')
        condition_value = rule.get('trigger_value')
        trigger_value = form_data.get(trigger_field)

        if not trigger_field or not operator:
            return False

        if isinstance(trigger_value, (list, tuple)):
            contains = condition_value in trigger_value
        elif operator in ('==', 'contains'):
            contains = condition_value in str(trigger_value or '')
        else:
            contains = False

        if operator == 'not_contains':
            return not contains
        return contains

    @classmethod
    def _validate_delivery_form(cls, workflow_type, form_data):
        """
        按 D 包流程表单 schema 校验填写数据（必填 + 条件必填）

        Returns:
            错误提示字符串；校验通过返回 None
        """
        schema = workflow_type.form_schema
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except (TypeError, ValueError):
                schema = []

        for field in schema or []:
            field_key = field.get('field')
            # auto_fill 字段由打包管理链路自动回填（构建成功后），不参与用户填写校验
            if field.get('auto_fill'):
                continue
            required = bool(field.get('required'))
            # 条件必填：满足条件规则时同样要求必填
            for rule in field.get('conditional_rules') or []:
                if rule.get('action') == 'required' and cls._match_condition(rule, form_data):
                    required = True
                    break
            if required and cls._is_empty(form_data.get(field_key)):
                return f'请填写必填字段：{field.get("label") or field_key}'
        return None

    def _create_delivery_workflow(self, request, package_build, package_path=None, scan_package_path=None):
        """
        自动创建"软件包(D包)发包流程"审批流程

        Args:
            request: 请求对象
            package_build: 打包构建记录对象
            package_path: 软件包存放路径（从 Jenkins package_info 制品解析，发包时传入）
            scan_package_path: 扫描软件包路径（发包链路不再剪切备份，直接使用制品路径；
                未传时回退 package_path）

        Returns:
            流程实例 WorkflowInstance；失败时返回 None
        """
        from apps.lyworkflow.models import WorkflowType, WorkflowInstance

        try:
            # 查找发包流程类型（流程名由 config 配置）
            workflow_type = WorkflowType.objects.filter(
                name=DELIVERY_WORKFLOW_TYPE_NAME
            ).first()

            if not workflow_type:
                logger.warning(f'未找到"{DELIVERY_WORKFLOW_TYPE_NAME}"流程类型，请先执行初始化命令')
                return None

            # 创建流程实例
            import datetime
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            instance_no = f'WF{timestamp}{workflow_type.code}'

            # auto_fill 字段由系统按配置清单自动回填（软件包存放路径 + 软件包版本名称等），
            # 其余申请字段由用户在发起时按表单提示填写
            # （不再写入 department/upload_type/description 等非 D 包表单字段，避免申请信息中展示多余项）
            field_map = self._get_auto_fill_field_map(workflow_type)
            if field_map is None:
                logger.warning(f'"{DELIVERY_WORKFLOW_TYPE_NAME}"表单自动回填字段配置异常，无法创建流程')
                return None
            form_data = self._fill_auto_fill_values({}, field_map, package_path)

            # 包安全扫描信息：本次构建已有扫描状态时回填（固定字段，逻辑同自动发起链路）；
            # 扫描软件包路径回填备份后的路径（scan_package_path），软件包存放路径仍回填原始制品路径
            try:
                scan_info = self._get_scan_info(
                    package_build.jenkins_job_name,
                    package_build.jenkins_build_number,
                    package_path=scan_package_path or package_path
                )
                if scan_info:
                    form_data = self._fill_scan_values(form_data, scan_info)
                    # 同步落库扫描状态到打包构建记录（列表页"包扫描状态"列展示，与自动发起链路一致）
                    scan_status = scan_info.get('package_scan_status') or ''
                    if scan_status and package_build.scan_status != scan_status:
                        package_build.scan_status = scan_status
                        package_build.save(update_fields=['scan_status'])
            except Exception as e:
                logger.warning(f"回填包扫描信息失败: {str(e)}")

            with transaction.atomic():
                instance = WorkflowInstance.objects.create(
                    instance_no=instance_no,
                    workflow_type=workflow_type,
                    # 版本号可能为空，为空时不拼接，避免流程标题出现 'None' 占位
                    title='软件包发包 - ' + package_build.project_name + (' ' + package_build.project_version if package_build.project_version else ''),
                    applicant=request.user,
                    applicant_dept=request.user.dept if hasattr(request.user, 'dept') else None,
                    status=0,  # 草稿
                    current_step=1,
                    total_steps=self._calculate_total_steps(workflow_type),
                    form_data=form_data,
                )

                # 关联到打包构建记录
                package_build.workflow_instance = instance
                # 已走发包流程：记录"是否需要传包"标记为是（列表页"是否传包"列展示）
                package_build.need_delivery = True
                package_build.save()

                logger.info(f'自动创建审批流程成功: {instance_no}')
                return instance

        except Exception as e:
            logger.error(f'自动创建审批流程失败: {str(e)}')
            # 不抛出异常，避免影响构建触发
            return None

    @staticmethod
    def _calculate_total_steps(workflow_type):
        """计算流程的总步骤数（考虑多级审批展开）"""
        total = 0
        steps = workflow_type.steps.all()

        for step in steps:
            if step.approver_type == 6 and step.multi_level_config:
                total += len(step.multi_level_config)
            else:
                total += 1

        return total
