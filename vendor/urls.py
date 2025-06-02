from django.urls import path
from .views import (
    VendorViewSet,
    SocietyViewSet,
    FlatDetailViewSet,
    WorkerPaymentViewSet,
)

urlpatterns = [
    # Vendor CRUD
    path("allvendors/", VendorViewSet.as_view({"get": "list"}), name="vendor-list"),
    path(
        "vendordetails/<int:pk>/",
        VendorViewSet.as_view({"get": "retrieve"}),
        name="vendor-retrieve",
    ),
    path("addvendor/", VendorViewSet.as_view({"post": "create"}), name="vendor-create"),
    path(
        "updatevendor/<int:pk>/",
        SocietyViewSet.as_view({"put": "update"}),
        name="vendor-update",
    ),
    path(
        "deletevendor/<int:pk>/",
        SocietyViewSet.as_view({"delete": "destroy"}),
        name="vendor-delete",
    ),
    # Society CRUD
    path("allsocieties/", SocietyViewSet.as_view({"get": "list"}), name="society-list"),
    path(
        "societydetails/<int:pk>/",
        SocietyViewSet.as_view({"get": "retrieve"}),
        name="society-retrieve",
    ),
    path(
        "addsociety/", SocietyViewSet.as_view({"post": "create"}), name="society-create"
    ),
    path(
        "updatesociety/<int:pk>/",
        SocietyViewSet.as_view({"put": "update"}),
        name="society-update",
    ),
    path(
        "deletesociety/<int:pk>/",
        SocietyViewSet.as_view({"delete": "destroy"}),
        name="society-delete",
    ),
    # FlatDetail CRUD
    path("allflats/", FlatDetailViewSet.as_view({"get": "list"}), name="flat-list"),
    path(
        "flatdetails/<int:pk>/",
        FlatDetailViewSet.as_view({"get": "retrieve"}),
        name="flat-retrieve",
    ),
    path("addflat/", FlatDetailViewSet.as_view({"post": "create"}), name="flat-create"),
    path(
        "updateflat/<int:pk>/",
        FlatDetailViewSet.as_view({"put": "update"}),
        name="flat-update",
    ),
    path(
        "deleteflat/<int:pk>/",
        FlatDetailViewSet.as_view({"delete": "destroy"}),
        name="flat-delete",
    ),
    # Worker Payment CRUD
    path(
        "allpayments/",
        WorkerPaymentViewSet.as_view({"get": "list"}),
        name="payment-list",
    ),
    path(
        "paymentdetails/<int:pk>/",
        WorkerPaymentViewSet.as_view({"get": "retrieve"}),
        name="payment-retrieve",
    ),
    path(
        "addpayment/",
        WorkerPaymentViewSet.as_view({"post": "create"}),
        name="payment-create",
    ),
    path(
        "updatepayment/<int:pk>/",
        WorkerPaymentViewSet.as_view({"put": "update"}),
        name="payment-update",
    ),
    path(
        "deletepayment/<int:pk>/",
        WorkerPaymentViewSet.as_view({"delete": "destroy"}),
        name="payment-delete",
    ),
]
