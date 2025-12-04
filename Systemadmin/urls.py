from django.urls import path

from Systemadmin.views import (
    AdminAPI, AdminLoginAPI, FCMNotification, FCMGlobalNotification,
    PhoneNumberLookupView, UniquePhoneNumberViewSet, NotificationView,
    NotificationHistoryView, MarkNotificationReadView, AllUsersListView
)

urlpatterns = [
    path('alladmins/', AdminAPI.as_view({'get': 'list'})),
    path('admindetails/<int:pk>/', AdminAPI.as_view({'get': 'retrieve'})),
    path('addadmin/', AdminAPI.as_view({'post': 'create'})),
    path('updateadmin/<int:pk>/', AdminAPI.as_view({'put': 'update'})),
    path('partialupdateadmin/<int:pk>/', AdminAPI.as_view({'patch': 'partial_update'})),
    path('deleteadmin/<int:pk>/', AdminAPI.as_view({'delete': 'destroy'})),

    path('adminlogin/', AdminLoginAPI.as_view()),

    path('notifications/fcm/', FCMNotification.as_view()),
    path('notifications/fcmglobal/', FCMGlobalNotification.as_view()),
    path('notifications/', NotificationView.as_view(), name='notifications'),

    # Phone number management endpoints
    path('phone-lookup/', PhoneNumberLookupView.as_view(), name='phone-lookup'),
    path('phone-numbers/', UniquePhoneNumberViewSet.as_view({'get': 'list'}), name='phone-numbers-list'),
    path('phone-numbers/<int:pk>/', UniquePhoneNumberViewSet.as_view({
        'get': 'retrieve',
        'delete': 'destroy'
    }), name='phone-numbers-detail'),

    # Notification history and read status endpoints
    path('notifications/history/', NotificationHistoryView.as_view(), name='notification-history'),
    path('notifications/<int:notification_id>/read/', MarkNotificationReadView.as_view(), name='mark-notification-read'),

    # All users list endpoint
    path('users/all/', AllUsersListView.as_view(), name='all-users-list'),
]
