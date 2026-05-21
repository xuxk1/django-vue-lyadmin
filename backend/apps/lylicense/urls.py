from django.urls import path, include
from rest_framework.routers import SimpleRouter
from apps.lylicense.views import (
    LicenseApplicationViewSet,
    LicenseRecordViewSet,
    LicenseFieldMappingViewSet
)

router = SimpleRouter()
router.register('application', LicenseApplicationViewSet, basename='license-application')
router.register('record', LicenseRecordViewSet, basename='license-record')
router.register('field-mapping', LicenseFieldMappingViewSet, basename='license-field-mapping')

urlpatterns = [
    path('', include(router.urls)),
]
