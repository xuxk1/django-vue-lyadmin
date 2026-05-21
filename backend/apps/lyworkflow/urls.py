from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WorkflowTypeViewSet,
    WorkflowStepViewSet,
    WorkflowCCViewSet,
    WorkflowInstanceViewSet,
    WorkflowTaskViewSet,
    WorkflowLogViewSet,
)

router = DefaultRouter()
router.register(r'workflow-type', WorkflowTypeViewSet, basename='workflow-type')
router.register(r'workflow-step', WorkflowStepViewSet, basename='workflow-step')
router.register(r'workflow-cc', WorkflowCCViewSet, basename='workflow-cc')
router.register(r'workflow-instance', WorkflowInstanceViewSet, basename='workflow-instance')
router.register(r'workflow-task', WorkflowTaskViewSet, basename='workflow-task')
router.register(r'workflow-log', WorkflowLogViewSet, basename='workflow-log')

urlpatterns = [
    path('', include(router.urls)),
]
