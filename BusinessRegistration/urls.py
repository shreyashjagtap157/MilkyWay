from django.urls import path
from .views import VendorBusinessRegistrationViewSet


urlpatterns = [
    # Vendor Business Registration CRUD
    path(
        "allvendorbusinessregistration/",
        VendorBusinessRegistrationViewSet.as_view({"get": "list"}),
        name="vendorbusinessregistration-list",
    ),
    path(
        "vendorbusinessregistrationdetails/<int:pk>/",
        VendorBusinessRegistrationViewSet.as_view({"get": "retrieve"}),
        name="vendorbusinessregistration-retrieve",
    ),
    path(
        "addvendorbusinessregistration/",
        VendorBusinessRegistrationViewSet.as_view({"post": "create"}),
        name="vendorbusinessregistration-create",
    ),
    path(
        "updatevendorbusinessregistration/<int:pk>/",
        VendorBusinessRegistrationViewSet.as_view({"put": "update"}),
        name="vendorbusinessregistration-update",
    ),
    path(
        "deletevendorbusinessregistration/<int:pk>/",
        VendorBusinessRegistrationViewSet.as_view({"delete": "destroy"}),
        name="vendorbusinessregistration-delete",
    ),
]
