
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DeliveryHistoryViewSet

router = DefaultRouter()
router.register(r'delivery-history', DeliveryHistoryViewSet, basename='deliveryhistory')

urlpatterns = [
    path('', include(router.urls)),
]
