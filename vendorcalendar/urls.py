from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    VendorCalendarViewSet, DistributorCalendarViewSet, DeliveryAdjustmentViewSet,
)

router = DefaultRouter()
router.register(r'vendor-calendar', VendorCalendarViewSet, basename='vendor-calendar')
router.register(r'distributor-calendar', DistributorCalendarViewSet, basename='distributor-calendar')
router.register(r'delivery-adjustment', DeliveryAdjustmentViewSet, basename='delivery-adjustment')

urlpatterns = [
    path('', include(router.urls)),
    path('list-milkman-leave-requests/', VendorCalendarViewSet.as_view({'get': 'list_milkman_leave_requests'}), name='list-milkman-leave-requests'),
    path('list-customer-requests/', DistributorCalendarViewSet.as_view({'get': 'list_customer_requests'}), name='list-customer-requests'),
    path('manage-milkman-leave/', VendorCalendarViewSet.as_view({'post': 'manage_milkman_leave'}), name='manage-milkman-leave'),
    path('manage-customer-request/', DistributorCalendarViewSet.as_view({'post': 'manage_customer_request'}), name='manage-customer-request'),
]
