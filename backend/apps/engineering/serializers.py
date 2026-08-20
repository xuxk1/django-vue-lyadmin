from rest_framework import serializers
from utils.serializers import CustomModelSerializer
from apps.engineering.models import PackageBuild


class PackageBuildSerializer(CustomModelSerializer):
    """打包构建记录序列化器（详情/单条查询，含完整构建日志）"""
    build_status_display = serializers.CharField(source='get_build_status_display', read_only=True)
    delivery_workflow_status_display = serializers.CharField(source='get_delivery_workflow_status_display', read_only=True)
    creator_name = serializers.SerializerMethodField()

    class Meta:
        model = PackageBuild
        fields = [
            'id', 'project_name', 'project_version', 'build_type',
            'jenkins_job_name', 'jenkins_build_number', 'jenkins_build_url',
            'build_status', 'build_status_display', 'build_log',
            'build_params', 'need_delivery', 'workflow_instance',
            'delivery_form_data', 'delivery_workflow_status', 'delivery_workflow_status_display',
            'scan_job_name', 'scan_build_number', 'scan_status',
            'creator_name', 'create_datetime', 'update_datetime'
        ]
        read_only_fields = ['id', 'create_datetime', 'update_datetime']

    def get_creator_name(self, obj):
        """构建人：记录触发时的构建用户；同步/模板记录无构建人返回空"""
        creator = obj.creator
        if not creator:
            return ''
        return creator.name or creator.username or ''


class PackageBuildListSerializer(CustomModelSerializer):
    """打包构建记录列表序列化器（不返回完整日志，仅提供摘要，避免列表接口响应过大）"""
    build_status_display = serializers.CharField(source='get_build_status_display', read_only=True)
    build_log_snippet = serializers.SerializerMethodField()
    delivery_workflow_status_display = serializers.CharField(source='get_delivery_workflow_status_display', read_only=True)
    creator_name = serializers.SerializerMethodField()

    class Meta:
        model = PackageBuild
        fields = [
            'id', 'project_name', 'project_version', 'build_type',
            'jenkins_job_name', 'jenkins_build_number', 'jenkins_build_url',
            'build_status', 'build_status_display', 'build_log_snippet',
            'build_params', 'need_delivery', 'workflow_instance',
            'delivery_workflow_status', 'delivery_workflow_status_display',
            'scan_job_name', 'scan_build_number', 'scan_status',
            'creator_name', 'create_datetime', 'update_datetime'
        ]
        read_only_fields = ['id', 'create_datetime', 'update_datetime']

    def get_build_log_snippet(self, obj):
        """返回构建日志摘要（最新 50 行，最多 3000 字符），完整日志通过 build_log 接口按需获取"""
        log = obj.build_log or ''
        if not log:
            return ''
        lines = log.split('\n')
        if len(lines) > 50:
            lines = lines[-50:]
        snippet = '\n'.join(lines).strip()
        if len(snippet) > 3000:
            snippet = '...' + snippet[-3000:]
        return snippet

    def get_creator_name(self, obj):
        """构建人：记录触发时的构建用户；同步/模板记录无构建人返回空"""
        creator = obj.creator
        if not creator:
            return ''
        return creator.name or creator.username or ''


class PackageBuildCreateSerializer(CustomModelSerializer):
    """打包构建创建序列化器"""

    class Meta:
        model = PackageBuild
        fields = ['id', 'project_name', 'project_version', 'build_type',
                  'jenkins_job_name', 'build_params', 'need_delivery']
        read_only_fields = ['id']
