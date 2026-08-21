#!/bin/python
# -*- coding: utf-8 -*-
"""
工程管理 - 打包管理异步任务

auto_start_delivery_workflow: 勾选"自动传包"触发构建后，轮询 Jenkins 构建状态，
构建成功后自动获取制品路径，创建并自动发起"软件包(D包)发包流程"审批流。

run_package_security_scan: 发包/提交审批流触发包安全扫描后，轮询扫描构建状态，
读取 package_info 中 ScanStatus=/ScanReport= 字段并获取报告 html 内容，
回填审批流程的三个扫描字段（包扫描状态/报告详情/拼接的包路径）。

fetch_build_log: 后台持续轮询拉取构建完整日志并落库（触发构建时/详情页/轮询结束/同步兜底投递），
排队期解析编号、构建中每 30 秒更新日志快照、构建结束后拉全量标记完整并终止，
避免同步请求全量日志导致接口长时间阻塞。
"""
import logging

from celery import shared_task
from django.db import transaction
from config import (DELIVERY_WORKFLOW_TYPE_NAME, PACKAGE_SECURITY_SCAN_JOB, PACKAGE_SCAN_AUTO_FILL_FIELDS,
                    PACKAGE_SCAN_STATUS_FIELD, PACKAGE_SCAN_REPORT_FIELD, PACKAGE_SCAN_BUILD_NUMBER_FIELD,
                    PACKAGE_SCAN_FAIL_MAX_RETRIES, PACKAGE_SCAN_FAIL_RETRY_DELAY,
                    PACKAGE_SCAN_ERROR_STATUS, PACKAGE_SCAN_DEFAULT_REPORT, PACKAGE_SCAN_PATH_FIELD)

logger = logging.getLogger(__name__)


def _update_scan_status(workflow_instance, status, package_build_id=None):
    """同步更新关联打包构建记录的包扫描状态（供打包管理列表展示；手动创建的审批流可能无关联记录）"""
    if not workflow_instance:
        return
    try:
        from apps.engineering.models import PackageBuild
        # 优先按触发扫描时锁定的构建记录精确更新：流程可能关联多条打包构建记录，
        # first() 按创建时间取最新会误更新到其他构建（如 #77 的扫描状态写到 #78）
        package_build = PackageBuild.objects.filter(id=package_build_id).first() if package_build_id else None
        if package_build is None:
            package_build = workflow_instance.package_builds.first()
        if package_build:
            package_build.scan_status = status
            package_build.save(update_fields=['scan_status'])
    except Exception as e:
        logger.warning(f'同步打包记录扫描状态失败: {str(e)}')


def _send_delivery_notification(user, title, content):
    """站内信通知申请人（复用 lymessages 站内信模式，带去重）"""
    if not user:
        logger.warning('发包通知跳过：申请人不存在')
        return
    try:
        from apps.lymessages.models import MyMessage, MyMessageUser

        message, created = MyMessage.objects.get_or_create(
            msg_title=title,
            msg_content=content,
            msg_chanel=1,  # 系统通知
            public=False,
            status=True,
            defaults={
                'msg_title': title,
                'msg_content': content,
                'msg_chanel': 1,
                'public': False,
                'status': True
            }
        )

        message_user, user_created = MyMessageUser.objects.get_or_create(
            messageid=message,
            revuserid=user,
            defaults={
                'is_read': False,
                'is_delete': False
            }
        )
        logger.info(f'发包通知站内信创建成功：用户{user.name}，标题={title}')
    except Exception as e:
        logger.warning(f'发包通知站内信发送失败: {str(e)}')


@shared_task(bind=True, max_retries=240, default_retry_delay=30)
def fetch_build_log(self, package_build_id, build_number=None):
    """
    后台持续轮询拉取构建完整日志并落库（幂等：日志已完整时跳过）

    与 auto_start_delivery_workflow 相同的持续轮询模式，直到日志完整或超时终止：
    - 排队期：从 build_url 解析 queue item 获取真实编号，queue item 失效（构建已开始）
      时改读 job view 的 lastBuild 兜底，编号解析后回写记录；
    - 构建中：每 30 秒拉取当前全量日志快照覆盖缓存（不标记完整），
      列表/详情随时有最新日志，无需依赖前端手动刷新；
    - 构建结束：拉取全量日志并标记完整，任务终止。
    超时保护：排队或构建超过约 2 小时仍未完成则放弃，
    构建结束轮询/build_status 兜底会重新投递本任务保证最终补齐。

    Args:
        package_build_id: 打包构建记录 ID
        build_number: 构建编号（可选，为空时由任务解析 queue item/lastBuild 后写回记录）
    """
    from apps.engineering.models import PackageBuild
    from utils.jenkins_service import JenkinsService

    try:
        package_build = PackageBuild.objects.get(id=package_build_id)
    except PackageBuild.DoesNotExist:
        logger.error(f'异步拉取构建日志任务终止：打包记录不存在 package_build_id={package_build_id}')
        return

    # 幂等：日志已完整时无需重复拉取（构建结束后首次拉取成功即标记完整）
    if package_build.build_log_complete:
        return

    jenkins = JenkinsService()
    build_number = build_number or package_build.jenkins_build_number

    # 排队中兜底：优先从 build_url 解析 queue item 获取真实构建编号
    # （queue item 在构建开始执行时即被 Jenkins 移除（访问返回 404），此时改读 job view
    # 的 lastBuild 信息，与 get_build_status 读取的是同一视图，保证能解析出编号继续轮询）
    if not build_number:
        queue_item_id = jenkins.parse_queue_item_id(package_build.jenkins_build_url)
        queue_item_lost = False  # queue item 是否已失效（构建已开始执行，访问返回 404）
        if queue_item_id:
            try:
                queue_status = jenkins.get_queue_item_status(queue_item_id)
                if queue_status.get('number'):
                    build_number = queue_status['number']
            except Exception as e:
                # 404：queue item 已失效，说明构建已开始执行
                queue_item_lost = True
                logger.warning(f'异步拉取构建日志任务 queue item 已失效（构建可能已开始），改从 job view 读取编号: {str(e)}')
        if not build_number and (queue_item_lost or not queue_item_id):
            # queue item 不可用（已开始执行或本就没有）：读取 job view 的 lastBuild 编号
            # （仍在排队时 queue item 可正常访问，禁止读 lastBuild，避免误取上一次构建）
            try:
                latest = jenkins.get_job_latest_build(package_build.jenkins_job_name)
                if latest:
                    build_number = latest['number']
            except Exception as e:
                logger.warning(f'异步拉取构建日志任务读取 job view 最新构建失败: {str(e)}')
                raise self.retry(exc=e)
        if build_number:
            # 回写构建编号（排队期间记录编号可能为空，供列表/详情展示）
            try:
                PackageBuild.objects.filter(id=package_build_id).update(jenkins_build_number=build_number)
            except Exception as e:
                logger.warning(f'回写构建编号失败: {str(e)}')
        if not build_number:
            # 仍在排队：持续轮询直到分配编号（超时保护：约 2 小时后放弃，
            # 构建结束轮询/build_status 兜底会重新投递本任务）
            if self.request.retries >= 240:
                logger.warning(f'异步拉取构建日志任务超时：构建排队超过 2 小时未分配编号，{package_build.jenkins_job_name}')
                return
            logger.info(f'构建排队中，等待解析编号后继续拉取日志: {package_build.jenkins_job_name}')
            raise self.retry(countdown=30)

    # 查询 Jenkins 实时构建状态（远程优先于本地缓存：构建结束即可拉全量并终止任务）
    try:
        status = jenkins.get_build_status(package_build.jenkins_job_name, build_number)
    except Exception as e:
        logger.warning(f'异步拉取构建日志任务查询构建状态失败: {str(e)}')
        raise self.retry(exc=e)

    # 拉取日志：构建中为当前全量快照（日志仍在增长），构建结束为最终全量
    try:
        console_text = jenkins.get_build_console(package_build.jenkins_job_name, build_number)
    except Exception as e:
        logger.warning(f'异步拉取构建日志失败: {package_build.jenkins_job_name} #{build_number}, 错误: {str(e)}')
        raise self.retry(exc=e)

    # 重新读取记录再写库（任务排队期间记录可能被同步/其他任务更新）
    package_build = PackageBuild.objects.filter(id=package_build_id).first()
    if not package_build:
        return
    package_build.build_log = console_text
    # 构建中拉取的是当前全量快照（日志仍在增长），不标记完整；构建结束后拉取才标记完整
    package_build.build_log_complete = not status.get('building')
    package_build.save(update_fields=['build_log', 'build_log_complete'])
    logger.info(f'异步拉取构建日志完成: {package_build.jenkins_job_name} #{build_number}, 完整={package_build.build_log_complete}')

    if status.get('building'):
        # 构建中：持续轮询直到构建结束，每轮更新一次日志快照（超时保护：约 2 小时后放弃，
        # 构建结束轮询/build_status 兜底会重新投递本任务）
        if self.request.retries >= 240:
            logger.warning(f'异步拉取构建日志任务超时：构建超过 2 小时未结束，{package_build.jenkins_job_name} #{build_number}')
            return
        logger.info(f'构建进行中，等待下一次拉取日志: {package_build.jenkins_job_name} #{build_number}')
        raise self.retry(countdown=30)


@shared_task(bind=True, max_retries=120, default_retry_delay=30)
def auto_start_delivery_workflow(self, package_build_id, build_number=None):
    """
    构建成功后自动创建并自动发起"软件包(D包)发包流程"

    流程：排队/构建中 -> 定时重试等待；构建成功 -> 自动获取制品路径并创建、发起流程；
    构建失败/超时 -> 标记自动发起失败并通知申请人手动处理

    Args:
        package_build_id: 打包构建记录 ID
        build_number: 触发时锁定的构建编号（可选，排队中可能为 None，由任务解析 queue item 后写回记录）
    """
    from apps.engineering.models import PackageBuild
    from utils.jenkins_service import JenkinsService

    try:
        package_build = PackageBuild.objects.select_related('workflow_instance', 'creator').get(id=package_build_id)
    except PackageBuild.DoesNotExist:
        logger.error(f'自动发包流程任务终止：打包记录不存在 package_build_id={package_build_id}')
        return

    # 幂等：已有草稿或审批中的发包流程则跳过（避免重复创建）
    # 外键可能悬空（流程实例被直接删除），防御性获取，悬空时视为不存在
    from apps.lyworkflow.models import WorkflowInstance
    existing = WorkflowInstance.objects.filter(id=package_build.workflow_instance_id).first() if package_build.workflow_instance_id else None
    if existing and existing.status in (0, 1):
        logger.info(f'自动发包流程任务跳过：已有进行中的发包流程 {existing.instance_no}')
        return

    jenkins = JenkinsService()
    # 优先使用触发时锁定的编号：任务重试期间记录编号可能被同步等流程更新为 Jenkins 最新构建，
    # 必须以本次触发的编号查询状态与制品，避免错取其他构建（如 #44 误判成 #47）
    build_number = build_number or package_build.jenkins_build_number

    # 排队中兜底：优先从 build_url 解析 queue item 获取真实构建编号
    # （queue item 在构建开始执行时即被 Jenkins 移除（访问返回 404），此时改读 job view 的
    # lastBuild 信息，与 get_build_status 读取的是同一视图，保证能解析出编号继续轮询）
    if not build_number:
        queue_item_id = jenkins.parse_queue_item_id(package_build.jenkins_build_url)
        queue_item_lost = False  # queue item 是否已失效（构建已开始执行，访问返回 404）
        if queue_item_id:
            try:
                queue_status = jenkins.get_queue_item_status(queue_item_id)
                if queue_status.get('number'):
                    build_number = queue_status['number']
            except Exception as e:
                # 404：queue item 已失效，说明构建已开始执行
                queue_item_lost = True
                logger.warning(f'自动发包流程任务 queue item 已失效（构建可能已开始），改从 job view 读取编号: {str(e)}')
        if not build_number and (queue_item_lost or not queue_item_id):
            # queue item 不可用（已开始执行或本就没有）：读取 job view 的 lastBuild 编号
            # （仍在排队时 queue item 可正常访问，禁止读 lastBuild，避免误取上一次构建）
            try:
                latest = jenkins.get_job_latest_build(package_build.jenkins_job_name)
                if latest:
                    build_number = latest['number']
            except Exception as e:
                logger.warning(f'自动发包流程任务读取 job view 最新构建失败: {str(e)}')
                raise self.retry(exc=e)
        if build_number:
            package_build.jenkins_build_number = build_number
            package_build.save()
        if not build_number:
            # 仍在排队，等待下一次重试（超时保护：约 50 分钟后仍无法解析编号则标记失败并通知）
            if self.request.retries >= 100:
                package_build.delivery_workflow_status = 2
                package_build.save(update_fields=['delivery_workflow_status'])
                logger.warning(f'自动发包流程任务超时：构建排队超过 50 分钟未分配编号，{package_build.jenkins_job_name}')
                _send_delivery_notification(
                    package_build.creator,
                    '发包流程自动发起失败',
                    f'构建排队超时（超过 50 分钟）仍未分配构建编号，未自动发起发包审批流程。'
                    f'请到打包管理中确认构建结果后手动发包。\n项目：{package_build.project_name}'
                )
                return
            logger.info(f'构建仍在排队中，等待下一次检查: {package_build.jenkins_job_name}')
            raise self.retry(countdown=30)

    # 查询 Jenkins 构建状态
    try:
        status = jenkins.get_build_status(package_build.jenkins_job_name, build_number)
    except Exception as e:
        logger.warning(f'自动发包流程任务查询构建状态失败: {str(e)}')
        raise self.retry(exc=e)

    if status.get('building'):
        # 构建中：超时保护后继续等待（约 50 分钟，30 秒/次）
        if self.request.retries >= 100:
            package_build.delivery_workflow_status = 2
            package_build.save(update_fields=['delivery_workflow_status'])
            logger.warning(f'自动发包流程任务超时：构建超过 50 分钟未结束，{package_build.jenkins_job_name} #{build_number}')
            _send_delivery_notification(
                package_build.creator,
                '发包流程自动发起失败',
                f'构建超时（超过 50 分钟）仍未结束，未自动发起发包审批流程。'
                f'请到打包管理中确认构建结果后手动发包。\n项目：{package_build.project_name}'
            )
            return
        logger.info(f'构建仍在进行中，等待下一次检查: {package_build.jenkins_job_name} #{build_number}')
        raise self.retry(countdown=30)

    if status.get('result') != 'SUCCESS':
        # 构建失败：不创建流程，标记失败并通知申请人
        package_build.delivery_workflow_status = 2
        package_build.save(update_fields=['delivery_workflow_status'])
        logger.warning(f'构建失败，未自动发起发包流程: {package_build.jenkins_job_name} #{build_number}, result={status.get("result")}')
        _send_delivery_notification(
            package_build.creator,
            '发包流程自动发起失败',
            f'构建未成功（{status.get("result") or "未知原因"}），未自动发起发包审批流程。'
            f'请修复后重新构建并手动发包。\n项目：{package_build.project_name}'
        )
        return

    # 构建成功：加锁重查记录后自动创建并自动发起发包审批流程（行锁防并发任务重复创建）
    from apps.engineering.views import PackageBuildViewSet

    try:
        with transaction.atomic():
            locked = PackageBuild.objects.select_for_update().get(id=package_build_id)
            instance, error = PackageBuildViewSet._create_and_start_delivery_workflow(locked, build_number)
    except PackageBuild.DoesNotExist:
        logger.error(f'自动发包流程任务终止：打包记录不存在 package_build_id={package_build_id}')
        return
    except Exception as e:
        logger.error(f'自动创建发包流程异常: {str(e)}')
        raise self.retry(exc=e)

    if error:
        package_build.delivery_workflow_status = 2
        package_build.save(update_fields=['delivery_workflow_status'])
        logger.error(f'自动创建发包流程失败: {error}')
        _send_delivery_notification(
            package_build.creator,
            '发包流程自动发起失败',
            f'构建成功但自动发起发包审批流程失败：{error}。\n请到打包管理中手动发包。\n项目：{package_build.project_name}'
        )
        return

    # 通知申请人流程已自动发起
    _send_delivery_notification(
        package_build.creator,
        '发包审批流程已自动发起',
        f'构建成功，已自动创建并发起"{DELIVERY_WORKFLOW_TYPE_NAME}"：{instance.instance_no}\n'
        f'软件包存放路径已自动填写，可前往流程管理查看审批进度。\n项目：{package_build.project_name}'
    )
    logger.info(f'自动发包流程完成: {package_build.jenkins_job_name} -> {instance.instance_no}')


def _retry_scan_with_new_build(self, jenkins, job_name, package_path, workflow_instance_id,
                               package_build_id, scan_fail_retries, reason):
    """重新触发扫描构建并投递新一轮轮询任务（扫描结果读取失败统一重试策略）

    以原软件包路径重新触发 package_security_scan 构建，投递新任务异步等待新构建
    结束后重新读取结果（重试计数 +1，旧构建不再轮询）。
    仅手动创建审批流场景会走到（打包管理自动发包链路投递时 package_path 为空，
    调用方先按 package_path 判空跳过重试，直接回填 ERROR）。

    Args:
        self: Celery 任务实例（触发接口异常时基于 request.kwargs 补全参数后 self.retry 重跑）
        reason: 重试原因（写入日志，含旧构建编号便于排查）

    Returns:
        True 已触发并投递新任务（调用方应结束本次执行）；
        触发接口异常时抛出自重试异常（self.retry），调用方无需处理
    """
    try:
        scan_path_param = PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_PATH_FIELD]
        retry_result = jenkins.trigger_build(job_name, {scan_path_param: package_path})
    except Exception as e:
        # 触发接口异常：本次计入重试次数，间隔后任务重跑再次尝试触发。
        # 注意：retry 的 kwargs 会整体替换原始调用参数，必须基于 request.kwargs
        # 补全全部参数（否则 workflow_instance_id 等丢失，重跑时 TypeError）
        logger.error(f'重新触发包安全扫描构建失败（第 {scan_fail_retries + 1} 次）: {str(e)}')
        retry_kwargs = dict(self.request.kwargs)
        retry_kwargs['scan_fail_retries'] = scan_fail_retries + 1
        raise self.retry(
            countdown=PACKAGE_SCAN_FAIL_RETRY_DELAY,
            kwargs=retry_kwargs,
        )
    logger.warning(
        f'{reason}，已重新触发扫描（第 {scan_fail_retries + 1}/{PACKAGE_SCAN_FAIL_MAX_RETRIES} 次）: '
        f'{job_name} -> 新构建 #{retry_result.get("build_number")}'
    )
    # 投递新一轮轮询任务（锁定新构建编号，重试计数 +1）
    run_package_security_scan.delay(
        workflow_instance_id=workflow_instance_id,
        package_path=package_path,
        job_name=job_name,
        build_number=retry_result.get('build_number'),
        build_url=retry_result.get('build_url', ''),
        package_build_id=package_build_id,
        scan_fail_retries=scan_fail_retries + 1,
    )
    return True


@shared_task(bind=True, max_retries=120, default_retry_delay=30)
def run_package_security_scan(self, workflow_instance_id, package_path=None, job_name=None, build_number=None, build_url=None, package_build_id=None, scan_read_retries=0, scan_fail_retries=0):
    """
    异步包安全扫描：轮询 package_security_scan 构建状态，构建结束后读取
    package_info 中 ScanStatus=/ScanReport= 字段，获取报告 html 内容，
    回填审批流程的三个扫描字段（包扫描状态/报告详情/拼接的包路径）

    Args:
        workflow_instance_id: 审批流程实例 ID（回填对象）
        package_path: 触发扫描时复制的软件包绝对路径（备份路径，重命名后；失败重试时
            作为重新触发扫描构建的 package_path 入参）
        job_name: 扫描 Jenkins 项目名（默认取 config.PACKAGE_SECURITY_SCAN_JOB）
        build_number: 触发时锁定的扫描构建编号（排队中可能为 None，由任务解析后使用）
        build_url: 触发返回的 Location 头（排队中用于解析 queue item）
        package_build_id: 触发扫描时锁定的打包构建记录 ID（回写列表页扫描状态时
            按 id 精确落库，避免流程关联多条记录时 first() 取错；手动创建的审批流可能为 None）
        scan_read_retries: 兼容保留参数（历史版本投递的任务可能携带），当前版本不再使用；
            扫描结果缺失统一按 scan_fail_retries 重新触发扫描构建
        scan_fail_retries: 已重新触发扫描构建的次数。构建结束后 ScanStatus/ScanReport 读取失败或
            为空（构建失败必然读不到，构建成功时结果也可能尚未生成/缺失）时，以原软件包路径重新
            触发扫描构建并异步等待新构建结束，最多 PACKAGE_SCAN_FAIL_MAX_RETRIES 次，重试耗尽
            仍失败则回填 ERROR + 缺省默认报告，不阻塞审批流程；打包管理自动发包链路 package_path
            为空不做重试（读取失败直接回填 ERROR）
    """
    from apps.lyworkflow.models import WorkflowInstance
    from utils.jenkins_service import JenkinsService

    try:
        instance = WorkflowInstance.objects.select_related('workflow_type', 'applicant').get(id=workflow_instance_id)
    except WorkflowInstance.DoesNotExist:
        logger.error(f'包扫描任务终止：流程实例不存在 workflow_instance_id={workflow_instance_id}')
        return

    job_name = job_name or PACKAGE_SECURITY_SCAN_JOB
    # 使用申请人 SSO 真实身份访问 Jenkins（与首次触发扫描一致，重试触发的构建人也显示真实申请人）；
    # 无 SSO 缓存凭证时内部回退默认账号（sqa），不影响功能
    jenkins = JenkinsService.for_user(instance.applicant)

    # 兜底：任务参数缺失时从流程 form_data 恢复触发扫描时锁定的打包构建记录 id
    # （触发时写入 _scan_package_build_id，保证回填落库不依赖 first() 反查）
    if not package_build_id:
        try:
            from apps.engineering.views import PackageBuildViewSet
            package_build_id = PackageBuildViewSet._parse_form_data(instance.form_data).get('_scan_package_build_id')
        except Exception as e:
            logger.warning(f'包扫描任务读取锁定构建记录失败: {str(e)}')

    # 排队中兜底：优先从 build_url 解析 queue item 获取真实构建编号
    # （queue item 在构建开始执行时即被 Jenkins 移除（访问返回 404），此时改读 job view 的
    # lastBuild 信息，与 get_build_status 读取的是同一视图，保证能解析出编号继续轮询）
    if not build_number:
        queue_item_id = jenkins.parse_queue_item_id(build_url)
        queue_item_lost = False  # queue item 是否已失效（构建已开始执行，访问返回 404）
        if queue_item_id:
            try:
                queue_status = jenkins.get_queue_item_status(queue_item_id)
                if queue_status.get('number'):
                    build_number = queue_status['number']
            except Exception as e:
                # 404：queue item 已失效，说明构建已开始执行
                queue_item_lost = True
                logger.warning(f'包扫描任务 queue item 已失效（构建可能已开始），改从 job view 读取编号: {str(e)}')
        if not build_number and (queue_item_lost or not queue_item_id):
            # queue item 不可用（已开始执行或本就没有）：读取 job view 的 lastBuild 编号
            # （仍在排队时 queue item 可正常访问，禁止读 lastBuild，避免误取上一次构建）
            try:
                latest = jenkins.get_job_latest_build(job_name)
                if latest:
                    build_number = latest['number']
            except Exception as e:
                logger.warning(f'包扫描任务读取 job view 最新构建失败: {str(e)}')
                raise self.retry(exc=e)
        if build_number:
            # 回写打包记录的扫描构建编号（触发时排队中可能为空，供列表页展示）
            try:
                from apps.engineering.models import PackageBuild
                package_build = PackageBuild.objects.filter(id=package_build_id).first() if package_build_id else None
                if package_build is None:
                    package_build = instance.package_builds.first()
                if package_build and not package_build.scan_build_number:
                    package_build.scan_build_number = build_number
                    package_build.save(update_fields=['scan_build_number'])
            except Exception as e:
                logger.warning(f'回写扫描构建编号失败: {str(e)}')
        if not build_number:
            # 仍在排队，等待下一次重试（超时保护：约 50 分钟后仍无法解析编号则通知申请人）
            if self.request.retries >= 100:
                logger.warning(f'包扫描任务超时：扫描构建排队超过 50 分钟未分配编号，{job_name}')
                _update_scan_status(instance, 'FAIL', package_build_id)
                _send_delivery_notification(
                    instance.applicant,
                    '包扫描排队超时',
                    f'包安全扫描构建排队超时（超过 50 分钟）仍未分配构建编号，扫描状态与报告未能回填。\n'
                    f'软件包：{package_path or ""}\n流程：{instance.instance_no}'
                )
                return
            logger.info(f'扫描构建仍在排队中，等待下一次检查: {job_name}')
            raise self.retry(countdown=30)

    # 查询扫描构建状态
    try:
        status = jenkins.get_build_status(job_name, build_number)
    except Exception as e:
        logger.warning(f'包扫描任务查询构建状态失败: {str(e)}')
        raise self.retry(exc=e)

    if status.get('building'):
        # 扫描进行中：超时保护后继续等待（约 50 分钟，30 秒/次）
        if self.request.retries >= 100:
            logger.warning(f'包扫描任务超时：扫描构建超过 50 分钟未结束，{job_name} #{build_number}')
            _update_scan_status(instance, 'FAIL', package_build_id)
            _send_delivery_notification(
                instance.applicant,
                '包扫描超时',
                f'包安全扫描构建超时（超过 50 分钟）仍未结束，扫描状态与报告未能回填。\n'
                f'软件包：{package_path or ""}\n流程：{instance.instance_no}'
            )
            return
        logger.info(f'扫描构建进行中，等待下一次检查: {job_name} #{build_number}')
        raise self.retry(countdown=30)

    # 构建结束：读取 package_info 中的 ScanStatus=/ScanReport=，并获取报告 html 内容。
    # 构建失败时必然读不到结果，构建成功时结果也可能尚未生成/缺失——以 ScanStatus 是否为空为判据：
    # 为空时直接回填默认值 ERROR + 缺省报告，不做重试
    from apps.engineering.views import PackageBuildViewSet

    scan_info = {
        'package_scan_status': '',
        'package_scan_report': '',
        'package_scan_path': package_path or '',
        PACKAGE_SCAN_BUILD_NUMBER_FIELD: str(build_number or ''),
    }
    scan_read_error = ''  # 读取失败原因（重试耗尽后写入日志，供后续排查扫描失败原因）
    try:
        result = jenkins.get_build_package_info(job_name, build_number)
        package_info = (result or {}).get('package_info') or {}
        # 字段名由配置指定：状态/报告对应 package_info 的 ScanStatus=/ScanReport=
        scan_status_key = PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_STATUS_FIELD]
        scan_report_key = PACKAGE_SCAN_AUTO_FILL_FIELDS[PACKAGE_SCAN_REPORT_FIELD]
        scan_status = package_info.get(scan_status_key, '')
        scan_report = package_info.get(scan_report_key, '')
        if scan_status:
            scan_info['package_scan_status'] = scan_status
            if scan_report:
                report_content = PackageBuildViewSet._fetch_scan_report_content(
                    job_name, build_number, scan_report
                )
                # 报告 html 内容优先；内容获取失败时回退路径字符串（前端按路径发起二次获取）
                scan_info['package_scan_report'] = report_content or scan_report
    except Exception as e:
        scan_read_error = f'读取扫描结果异常: {str(e)}'
        logger.warning(f'包扫描任务读取扫描结果失败: {str(e)}')

    # 扫描结果不完整（接口异常或 ScanStatus/ScanReport 为空）是唯一失败判据：构建失败必然读不到结果，
    # 构建成功时结果也可能尚未生成/缺失——手动创建审批流（package_path 非空）统一重新触发扫描构建、
    # 异步等待新构建结束后重新读取，最多 PACKAGE_SCAN_FAIL_MAX_RETRIES 次；打包管理自动发包链路
    # （package_path 为空）不做重试；重试耗尽仍无法读取时回填 ERROR + 缺省默认报告，提示用户报告
    # 获取异常，不影响审批流程（ERROR 不影响"包扫描状态为PASS"跳过逻辑）
    if scan_read_error or not scan_info.get('package_scan_status') or not scan_info.get('package_scan_report'):
        if scan_fail_retries < PACKAGE_SCAN_FAIL_MAX_RETRIES and package_path:
            _retry_scan_with_new_build(
                self, jenkins, job_name, package_path, workflow_instance_id,
                package_build_id, scan_fail_retries,
                f'扫描结果不完整（{job_name} #{build_number}, '
                f'原因: {scan_read_error or "ScanStatus/ScanReport 均为空"}）',
            )
            return
        logger.error(
            f'包扫描结果获取异常（已重试 {PACKAGE_SCAN_FAIL_MAX_RETRIES} 次），'
            f'回填 ERROR + 缺省报告: {job_name} #{build_number}, 原因: '
            f'{scan_read_error or "ScanStatus/ScanReport 均为空"}'
        )
        if not scan_info.get('package_scan_status'):
            scan_info['package_scan_status'] = PACKAGE_SCAN_ERROR_STATUS
        scan_info['package_scan_report'] = PACKAGE_SCAN_DEFAULT_REPORT

    # 回填四个扫描字段（扫描状态/报告详情/拼接的包路径/扫描构建编号）
    try:
        with transaction.atomic():
            locked = WorkflowInstance.objects.select_for_update().get(id=workflow_instance_id)
            # form_data 可能存在双重 JSON 编码（字符串），先反序列化保证 .get() 安全
            form_data = PackageBuildViewSet._parse_form_data(locked.form_data)
            form_data = PackageBuildViewSet._fill_scan_values(form_data, scan_info)
            # 扫描状态为空视为扫描失败，回填 ERROR 关闭"等待扫描"状态（否则通知会一直被延后）
            if not str(scan_info.get('package_scan_status') or '').strip():
                form_data[PACKAGE_SCAN_STATUS_FIELD] = PACKAGE_SCAN_ERROR_STATUS
            locked.form_data = form_data
            locked.save(update_fields=['form_data'])
            # 同步更新关联打包构建记录的扫描状态（列表页展示）
            _update_scan_status(locked, scan_info['package_scan_status'] or PACKAGE_SCAN_ERROR_STATUS, package_build_id)
    except WorkflowInstance.DoesNotExist:
        logger.error(f'包扫描任务终止：流程实例不存在 workflow_instance_id={workflow_instance_id}')
        return
    except Exception as e:
        logger.error(f'包扫描任务回填字段失败: {str(e)}')
        raise self.retry(exc=e)

    # 包扫描结果回填后统一驱动审批通知（首次提交时通知已延后，扫描结果确定后才发送）：
    # - PASS：跳过配置了"包扫描状态为PASS"跳过条件的节点并流转下一节点（下一节点任务创建时自动发送通知）；
    #   无跳过节点时（如未配置该条件）补发当前待办审批人通知
    # - 非PASS：补发当前待办审批人的审批邮件/站内信，由审批人正常审批
    try:
        from apps.lyworkflow.engine import FlowEngine
        engine = FlowEngine(locked)
        if (scan_info.get('package_scan_status') or '').strip().upper() == 'PASS':
            if not engine._handle_scan_pass_skip_nodes():
                engine._resume_notifications_after_scan()
        else:
            engine._resume_notifications_after_scan()
    except Exception as e:
        logger.error(f'包扫描结果驱动审批通知失败: {str(e)}')

    # 扫描结果获取异常（ERROR）时通知中明确提示，便于用户了解报告内容为系统缺省提示
    scan_status = scan_info["package_scan_status"] or ""
    scan_notice = (
        f'\n提示：扫描结果获取异常（已重试 {PACKAGE_SCAN_FAIL_MAX_RETRIES} 次），'
        f'报告内容为系统缺省提示，流程可正常审批，后续将排查扫描失败原因。'
        if scan_status == PACKAGE_SCAN_ERROR_STATUS else ''
    )
    _send_delivery_notification(
        instance.applicant,
        '包扫描完成',
        f'包安全扫描已完成（{scan_status}），扫描状态与报告已回填审批流程。\n'
        f'软件包：{scan_info["package_scan_path"] or ""}\n流程：{instance.instance_no}{scan_notice}'
    )
    logger.info(f'包安全扫描完成并回填: {job_name} #{build_number} -> {instance.instance_no}')
