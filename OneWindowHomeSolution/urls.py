"""
URL configuration for One Window Home Solution project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from .auth_info import AuthenticationInfoView

schema_view = get_schema_view(
    openapi.Info(
        title="One Window Home Solution API",
        default_version="v1",
        description="""
        API documentation for One Window Home Solution Service
        
        ## Authentication
        
        This API supports two types of authentication:
        
        ### 1. Admin Authentication
        - Use `/systemadmin/adminlogin/` to get JWT token for admin users
        - Admin users are managed through the SystemAdmin model
        
        ### 2. Role-based Authentication  
        - Use `/vendor-login/vendor_login/` to get JWT token for vendors, milkman, and customers
        - Supports VendorBusinessRegistration, Milkman, and Customer models
        
        ### Authorization Header
        For both authentication types, include the JWT token in requests:
        ```
        Authorization: Bearer <your_jwt_token>
        ```
        """,
        contact=openapi.Contact(email="support@onewindow.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth-info/", AuthenticationInfoView.as_view(), name="authentication-info"),
    path("vendor/", include("vendor.urls")),
    path("milkman/", include("Milkman.urls")),
    path("customer/", include("Customer.urls")),
    path("subscription/", include("subscription.urls")),
    path("registration/", include("BusinessRegistration.urls")),
    path("report/", include("Report.urls")),
    path("dashboard/", include("Dashboard.urls")),
    # path("delivery-history/", include("Deliveryhistory.urls")),  # Temporarily removed
    path("consumer-calendar/", include("vendorcalendar.urls")),
    path("vendor-login/", include("vendor_login.urls")),
    path("systemadmin/", include("Systemadmin.urls")),
    # Swagger UI
    path(
        "",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
]
