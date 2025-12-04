from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import VendorBusinessRegistrationViewSet

router = DefaultRouter()
router.register(r'vendor-business-registration', VendorBusinessRegistrationViewSet, basename='vendor-business-registration')

urlpatterns = [
    path('', include(router.urls)),
]