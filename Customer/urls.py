from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, MilkRequirementViewSet, LegacyCustomerViewSet

# Set the lookup_field on each ViewSet
CustomerViewSet.lookup_field = 'id'
MilkRequirementViewSet.lookup_field = 'id'




router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'milkrequirements', MilkRequirementViewSet, basename='milkrequirement')

# Bill and payment history endpoints are now available via CustomerViewSet actions:
# /customers/<id>/bills/
# /customers/<id>/bills/<bill_id>/
# /customers/<id>/payment-history/

legacy_router = DefaultRouter()
legacy_router.register(r'legacy-customers', LegacyCustomerViewSet, basename='legacy-customers')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(legacy_router.urls)),
]
