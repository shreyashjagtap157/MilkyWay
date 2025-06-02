from django.urls import path
from .views import send_sms_api
from . import views

# from .views import create_order, payment_success

# urlpatterns = [
#     path("create-order/", create_order, name="create-order"),
#     path("payment-success/", payment_success, name="payment-success"),
# ]

urlpatterns = [
    path("send-sms/", views.send_sms_api, name="send_sms_api"),
]
