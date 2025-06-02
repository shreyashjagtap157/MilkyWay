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

schema_view = get_schema_view(
    openapi.Info(
        title="One Window Home Solution API",
        default_version="v1",
        description="API documentation for One Window Home Solution Service",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/login/", include("vendor_login.urls")),
    path("api/vendor/", include("vendor.urls")),
    path("api/milkman/", include("Milkman.urls")),
    path("api/customer/", include("Customer.urls")),
    # path("api/subscription/", include("Subscription.urls")),
    path("api/registration/", include("BusinessRegistration.urls")),
    path("api/report/", include("Report.urls")),
    # Swagger UI
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
]
