from django.urls import path
from .views import VendorLoginView, MilkmanLoginView

urlpatterns = [
    path("vendor-login/", VendorLoginView.as_view(), name="vendor-login"),
    path("milkman-login/", MilkmanLoginView.as_view(), name="milkman-login"),
]
