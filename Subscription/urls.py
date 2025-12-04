from django.urls import path
from . import views
from .payment_views import (
    CreatePaymentOrderView, VerifyPaymentView, 
    PaymentHistoryView, AdminPaymentHistoryView,
    CreateSubscriptionOrderView, VerifySubscriptionPaymentView,
    VendorSubscriptionHistoryView
)

urlpatterns = [
    # List all subscribed customers
    path("subscribed-customers/", views.subscribed_customers_list, name="subscribed-customers"),

    # List subscribed customers for a vendor (expects ?vendor_id=<id> query parameter)
    path(
        "subscribed-customers-for-vendor/",
        views.subscribed_customers_for_vendor,
        name="subscribed-customers-for-vendor",
    ),

    # List subscribed customers by frequency (expects ?frequency=monthly|semiannual|annual, optional ?vendor_id=)
    path(
        "subscribed-by-frequency/",
        views.subscribed_customers_by_frequency,
        name="subscribed-by-frequency",
    ),

    # Get total subscribed customers
    path("total-subscribed/", views.total_subscribed_customers, name="total-subscribed"),

    # Subscription summary (by duration)
    path("summary/", views.subscription_summary, name="subscription-summary"),
    
    # Payment endpoints
    path("payment/create-order/", CreatePaymentOrderView.as_view(), name="create-payment-order"),
    path("payment/verify/", VerifyPaymentView.as_view(), name="verify-payment"),
    path("payment/history/", PaymentHistoryView.as_view(), name="payment-history"),
    path("payment/admin/history/", AdminPaymentHistoryView.as_view(), name="admin-payment-history"),
    
    # Subscription management endpoints (vendor-specific)
    path("subscription/create-order/", CreateSubscriptionOrderView.as_view(), name="create-subscription-order"),
    path("subscription/verify-payment/", VerifySubscriptionPaymentView.as_view(), name="verify-subscription-payment"),
    path("subscription/my-subscriptions/", VendorSubscriptionHistoryView.as_view(), name="vendor-subscription-history"),
]
