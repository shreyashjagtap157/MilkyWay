
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JoinRequestViewSet

router = DefaultRouter()
router.register(r'join-requests', JoinRequestViewSet, basename='joinrequest')

urlpatterns = [
    path('', include(router.urls)),
]
