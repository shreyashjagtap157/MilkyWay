from django.urls import path
from .views import CustomerViewSet, ComplaintViewSet, CustomerRegisterView


urlpatterns = [
    # Customer CRUD
    path(
        "allcustomers/", CustomerViewSet.as_view({"get": "list"}), name="customer-list"
    ),
    path(
        "customerdetails/<int:pk>/",
        CustomerViewSet.as_view({"get": "retrieve"}),
        name="customer-retrieve",
    ),
    path(
        "addcustomer/",
        CustomerViewSet.as_view({"post": "create"}),
        name="customer-create",
    ),
    path(
        "updatecustomer/<int:pk>/",
        CustomerViewSet.as_view({"put": "update"}),
        name="customer-update",
    ),
    path(
        "deletecustomer/<int:pk>/",
        CustomerViewSet.as_view({"delete": "destroy"}),
        name="customer-delete",
    ),
    # Complaint CRUD
    path(
        "allcomplaints/",
        ComplaintViewSet.as_view({"get": "list"}),
        name="complaint-list",
    ),
    path(
        "complaintdetails/<int:pk>/",
        ComplaintViewSet.as_view({"get": "retrieve"}),
        name="complaint-retrieve",
    ),
    path(
        "addcomplaint/",
        ComplaintViewSet.as_view({"post": "create"}),
        name="complaint-create",
    ),
    path(
        "updatecomplaint/<int:pk>/",
        ComplaintViewSet.as_view({"put": "update"}),
        name="complaint-update",
    ),
    path(
        "deletecomplaint/<int:pk>/",
        CustomerViewSet.as_view({"delete": "destroy"}),
        name="complaint-delete",
    ),
    # Customer Registration Login
    path(
        "customer-register/", CustomerRegisterView.as_view(), name="customer-register"
    ),
]
