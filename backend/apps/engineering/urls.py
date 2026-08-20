from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PackageBuildViewSet

router = DefaultRouter()
router.register(r'package-build', PackageBuildViewSet, basename='package-build')

urlpatterns = [
    path('', include(router.urls)),
]
