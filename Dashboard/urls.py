from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    dashboard_data,
    SubscriptionPlanViewSet,
    sync_accepted_join_requests_api,
    NotificationAnalyticsView,
    vendor_dashboard_summary,
    customer_month_summary,
    milkman_month_summary,
)

router = DefaultRouter()
router.register(r'subscription-plans', SubscriptionPlanViewSet, basename='subscriptionplan')

urlpatterns = [
    path('', dashboard_data, name='dashboard-data'),
    path('sync-accepted-join-requests/', sync_accepted_join_requests_api, name='sync-accepted-join-requests'),
    path('analytics/notifications/', NotificationAnalyticsView.as_view(), name='notification-analytics'),
    path('vendor-dashboard-summary/', vendor_dashboard_summary, name='vendor-dashboard-summary'),
    path('customer-month-summary/', customer_month_summary, name='customer-month-summary'),
    path('milkman-month-summary/', milkman_month_summary, name='milkman-month-summary'),
    path('', include(router.urls)),
]
