from django_filters import rest_framework as filters
from apps.lyworkflow.models import WorkflowType, WorkflowInstance, WorkflowTask


class WorkflowTypeFilter(filters.FilterSet):
    """流程类型过滤器"""
    name = filters.CharFilter(field_name='name', lookup_expr='icontains')
    code = filters.CharFilter(field_name='code', lookup_expr='icontains')
    status = filters.NumberFilter(field_name='status')

    class Meta:
        model = WorkflowType
        fields = ['name', 'code', 'status']


class WorkflowInstanceFilter(filters.FilterSet):
    """流程实例过滤器"""
    title = filters.CharFilter(field_name='title', lookup_expr='icontains')
    workflow_type = filters.NumberFilter(field_name='workflow_type')
    status = filters.NumberFilter(field_name='status')
    applicant = filters.NumberFilter(field_name='applicant')
    instance_no = filters.CharFilter(field_name='instance_no', lookup_expr='icontains')
    start_time = filters.DateFromToRangeFilter(field_name='create_datetime')

    class Meta:
        model = WorkflowInstance
        fields = ['title', 'workflow_type', 'status', 'applicant', 'instance_no']


class WorkflowTaskFilter(filters.FilterSet):
    """审批任务过滤器"""
    instance = filters.NumberFilter(field_name='instance')
    approver = filters.NumberFilter(field_name='approver')
    status = filters.NumberFilter(field_name='status')
    approve_result = filters.NumberFilter(field_name='approve_result')

    class Meta:
        model = WorkflowTask
        fields = ['instance', 'approver', 'status', 'approve_result']
