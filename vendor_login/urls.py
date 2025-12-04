from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .custom_jwt import CustomTokenObtainView, TokenRefreshView, LogoutView
from .views import LoginViewSet

router = DefaultRouter()
router.register(r'', LoginViewSet, basename='auth')

urlpatterns = [
    path('', include(router.urls)),
    path('token/', CustomTokenObtainView.as_view(), name='custom_token_obtain'),
    path('refresh/', TokenRefreshView.as_view(), name='custom_token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
