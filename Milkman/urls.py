from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MilkmanViewSet, MilkmanActionsViewSet, LegacyMilkmanViewSet

# Legacy router setup
legacy_router = DefaultRouter()
legacy_router.register(r'legacy-milkmen', LegacyMilkmanViewSet, basename='legacy-milkmen')

# Main router setup
router = DefaultRouter()
router.register(r'milkmen', MilkmanViewSet, basename='milkman')
router.register(r'actions', MilkmanActionsViewSet, basename='milkman-actions')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('', include(legacy_router.urls)),
    # Custom endpoint for checking vendor assignment
    path('actions/check-vendor-assignment/<int:pk>/', MilkmanActionsViewSet.as_view({'get': 'check_vendor_assignment'}), name='milkman-check-vendor-assignment'),
]
