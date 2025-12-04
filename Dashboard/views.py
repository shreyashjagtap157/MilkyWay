from datetime import date
from calendar import monthrange
import logging
from django.db.models import Sum

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework import viewsets
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated, BasePermission

from BusinessRegistration.models import VendorBusinessRegistration as Vendor
from Customer.billing_utils import generate_or_update_bills_for_vendor
from Customer.models import Customer, Bill
from Milkman.models import Milkman
from vendor.models import JoinRequest
from django.db.models import F, ExpressionWrapper, IntegerField, Func, Value

from vendorcalendar.models import CustomerRequest, MilkmanLeaveRequest
from OneWindowHomeSolution.responses import success_response, error_response
from OneWindowHomeSolution.custom_authentication import CustomJWTAuthentication
from .models import SubscriptionPlan
from .serializers import SubscriptionPlanSerializer


@swagger_auto_schema(
    method="post",
    operation_summary="Vendor Dashboard Summary",
    operation_description="Returns vendor dashboard summary with billing and operational metrics.",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'vendor_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Vendor ID'),
            'month': openapi.Schema(type=openapi.TYPE_INTEGER, description='Month (1-12)', default=None),
            'year': openapi.Schema(type=openapi.TYPE_INTEGER, description='Year (e.g., 2025)', default=None),
        },
        required=['vendor_id']
    ),
    responses={200: openapi.Response(description="Vendor dashboard summary")}
)
@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def vendor_dashboard_summary(request):
    """
    API endpoint to return vendor dashboard summary, including billing and operational metrics.
    """
    vendor_id = request.data.get('vendor_id')
    month = request.data.get('month')
    year = request.data.get('year')
    try:
        vendor = Vendor.objects.get(id=vendor_id)
    except Vendor.DoesNotExist:
        return error_response("Vendor not found", status_code=404)

    # Ensure bills are up-to-date for this vendor
    generate_or_update_bills_for_vendor(vendor)

    # Date range for month filter
    today = date.today()
    if month and year:
        start_date = date(year, month, 1)
        end_date = date(year, month, monthrange(year, month)[1])
    else:
        start_date = today.replace(day=1)
        end_date = today

    # Total distributor (milkmen accepted by vendor)
    # Total distributor (milkmen assigned to vendor)
    total_distributor = Milkman.objects.filter(provider=vendor).count()
    # Total consumer (customers assigned to vendor)
    total_consumer = Customer.objects.filter(provider=vendor).count()


    # Consumer extra milk amount: sum of cow and buffalo extra milk for this vendor, only for requests with type 'extra_milk', status pending/approved, and date today or future
    extra_milk_qs = CustomerRequest.objects.filter(
        vendor=vendor,
        request_type="extra_milk",
        status="pending",
        date__gte=today
    )
    consumer_extra_milk_amount = extra_milk_qs.aggregate(
        total_cow=Sum('cow_milk_extra'),
        total_buffalo=Sum('buffalo_milk_extra')
    )
    total_cow = consumer_extra_milk_amount.get('total_cow') or 0
    total_buffalo = consumer_extra_milk_amount.get('total_buffalo') or 0
    consumer_extra_milk_amount = float(total_cow) + float(total_buffalo)

    # Pending join requests for this vendor
    pending_request_count = JoinRequest.objects.filter(
        vendor=vendor,
        status="pending"
    ).count()

    # Distributor leave count: sum of leave days for all milkmen (distributors) with pending leave requests for this vendor
    leave_qs = MilkmanLeaveRequest.objects.filter(vendor=vendor, status='pending').exclude(start_date__isnull=True)
    distributor_leave_count = leave_qs.annotate(
        days=ExpressionWrapper(
            Func(F('end_date'), F('start_date'), function='DATEDIFF', output_field=IntegerField()) + Value(1),
            output_field=IntegerField()
        )
    ).aggregate(total=Sum('days'))['total'] or 0

    # Total billed amount (sum of bills for customers for the month)
    # Bills are linked directly to a vendor in the Bill model
    bills = Bill.objects.filter(
        vendor=vendor,
        start_date__gte=start_date,
        end_date__lte=end_date
    )
    total_billed_amount = bills.aggregate(total=Sum('total_amount'))['total'] or 0

    # Total overdue amount (sum of unpaid bills for previous months)
    # Overdue bills: use the Bill.vendor relation and the 'overdue' status
    overdue_bills = Bill.objects.filter(
        vendor=vendor,
        end_date__lt=start_date,
        status='overdue'
    )
    total_overdue_amount = overdue_bills.aggregate(total=Sum('total_amount'))['total'] or 0

    data = {
        'total_consumer': total_consumer,
        'total_distributor': total_distributor,
        'total_billed_amount': total_billed_amount,
        'total_overdue_amount': total_overdue_amount,
        'pending_request_count': pending_request_count,
        'consumer_extra_milk_amount': consumer_extra_milk_amount,
        'distributor_leave_count': distributor_leave_count,
    }
    return success_response("Vendor dashboard summary fetched successfully", data)

logger = logging.getLogger(__name__)


class IsSystemAdmin(BasePermission):
    """Allows access only to users who are authenticated Systemadmin."""
    def has_permission(self, request, view):
        user = request.user
        return (
            isinstance(user, Systemadmin)
            and user.is_authenticated
        )


class SubscriptionPlanViewSet(viewsets.ViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return SubscriptionPlan.objects.get(pk=pk)
        except SubscriptionPlan.DoesNotExist:
            return None

    def get_serializer(self, *args, **kwargs):
        return self.serializer_class(*args, **kwargs)

    @swagger_auto_schema(
        operation_summary="List Subscription Plans",
        operation_description="Retrieve a list of all subscription plans.",
        responses={200: SubscriptionPlanSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        try:
            info = SubscriptionPlan.objects.all()
            serializer = self.get_serializer(info, many=True)
            return success_response("Subscription plans fetched successfully", serializer.data)
        except Exception as e:
            return error_response(f"An error occurred while fetching subscription plans: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Retrieve Subscription Plan",
        operation_description="Get details of a specific subscription plan by its ID.",
        responses={200: SubscriptionPlanSerializer()},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="Subscription Plan ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def retrieve(self, request, pk=None):
        try:
            instance = self.get_object(pk)
            if not instance:
                return not_found_response("Subscription plan not found")
            serializer = self.get_serializer(instance)
            return success_response("Subscription plan retrieved successfully", serializer.data)
        except Exception as e:
            return error_response(f"An error occurred while fetching subscription plan: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Create Subscription Plan",
        operation_description="Create a new subscription plan.",
        request_body=SubscriptionPlanSerializer,
        responses={201: SubscriptionPlanSerializer()}
    )
    def create(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return success_response("Subscription plan created successfully", serializer.data, status_code=status.HTTP_201_CREATED)
        except Exception as e:
            return error_response(f"Failed to create subscription plan: {str(e)}")

    @swagger_auto_schema(
        operation_summary="Update Subscription Plan",
        operation_description="Update all details of an existing subscription plan.",
        request_body=SubscriptionPlanSerializer,
        responses={200: SubscriptionPlanSerializer()},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="Subscription Plan ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def update(self, request, pk=None):
        try:
            instance = self.get_object(pk)
            if not instance:
                return not_found_response("Subscription plan not found")

            serializer = self.serializer_class(instance, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return success_response("Subscription plan updated successfully", serializer.data)
        except Exception as e:
            return error_response(f"Failed to update subscription plan: {str(e)}")

    @swagger_auto_schema(
        operation_summary="Partially Update Subscription Plan",
        operation_description="Update selected fields of an existing subscription plan.",
        request_body=SubscriptionPlanSerializer,
        responses={200: SubscriptionPlanSerializer()},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="Subscription Plan ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def partial_update(self, request, pk=None):
        try:
            instance = self.get_object(pk)
            if not instance:
                return not_found_response("Subscription plan not found")

            serializer = self.serializer_class(
                instance, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return success_response("Subscription plan partially updated successfully", serializer.data)
        except Exception as e:
            return error_response(f"Failed to partially update subscription plan: {str(e)}")

    @swagger_auto_schema(
        operation_summary="Delete Subscription Plan",
        operation_description="Delete a subscription plan by its ID.",
        responses={204: "No Content"},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="Subscription Plan ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def destroy(self, request, pk=None):
        try:
            instance = self.get_object(pk)
            if not instance:
                return not_found_response("Subscription plan not found")

            instance.delete()

            return success_response("Subscription plan deleted successfully", status_code=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return error_response(f"Failed to delete subscription plan: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
def dashboard_data(request):
    try:
        total_vendors = Vendor.objects.count()
        total_customers = Customer.objects.count()
        total_milkmen = Milkman.objects.count()
        # Subscription functionality temporarily disabled
        # total_active_subscribers = SubscribedVendor.objects.count()
        # total_monthly_subscriptions = SubscribedVendor.objects.filter(plan__duration=30).count()
        # total_six_month_subscriptions = SubscribedVendor.objects.filter(plan__duration=180).count()
        # total_yearly_subscriptions = SubscribedVendor.objects.filter(plan__duration=365).count()

        data = {
            "total_vendors": total_vendors,
            "total_customers": total_customers,
            "total_milkmen": total_milkmen,
            # "subscribers": {
            #     "total": total_active_subscribers,
            #     "monthly": total_monthly_subscriptions,
            #     "six_month": total_six_month_subscriptions,
            #     "yearly": total_yearly_subscriptions,
            # },
        }
        return success_response("Dashboard data fetched successfully", data)
    except Exception as e:
        return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    method="post",
    operation_summary="Sync Accepted Join Requests",
    operation_description="Update all accepted join requests to ensure Customer and Milkman records are properly assigned to their vendor.",
    responses={200: "Sync completed successfully."}
)
@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsSystemAdmin])
def sync_accepted_join_requests_api(request):
    """
    API endpoint to sync accepted join requests and update provider/milkman fields for customers and milkmen.
    """
    with transaction.atomic():
        # Customers
        accepted_customer_requests = JoinRequest.objects.filter(user_type="customer", status="accepted")
        for req in accepted_customer_requests:
            try:
                customer = Customer.objects.get(id=req.object_id)
                customer.provider = req.vendor
                # Optionally, set milkman to None if you want to reset
                # customer.milkman = None
                customer.save()
            except Customer.DoesNotExist:
                continue
        # Milkmen
        accepted_milkman_requests = JoinRequest.objects.filter(user_type="milkman", status="accepted")
        for req in accepted_milkman_requests:
            try:
                milkman = Milkman.objects.get(id=req.object_id)
                milkman.provider = req.vendor
                milkman.save()
            except Milkman.DoesNotExist:
                continue
    return success_response("Sync completed successfully.")

class NotificationAnalyticsView(APIView):
    """
    API endpoint to provide analytics for notifications.

    Returns:
        - Total notifications sent.
        - Notifications grouped by channel.
        - Read vs unread notifications.
    """
    @swagger_auto_schema(
        operation_summary="Get Notification Analytics",
        operation_description="""
        Retrieve analytics for notifications, including:
        - Total notifications sent
        - Notifications grouped by channel
        - Read vs unread notifications
        """,
        responses={
            200: openapi.Response(
                description="Notification analytics data",
                examples={
                    "application/json": {
                        "total_notifications": 100,
                        "notifications_by_channel": [
                            {"channel": "alerts", "count": 60},
                            {"channel": "promotions", "count": 40}
                        ],
                        "read_notifications": 80,
                        "unread_notifications": 20
                    }
                }
            )
        }
    )
    def get(self, request):
        total_notifications = NotificationLog.objects.count()
        notifications_by_channel = NotificationLog.objects.values('channel').annotate(count=Count('id'))
        read_notifications = NotificationLog.objects.filter(read=True).count()
        unread_notifications = NotificationLog.objects.filter(read=False).count()

        data = {
            "total_notifications": total_notifications,
            "notifications_by_channel": list(notifications_by_channel),
            "read_notifications": read_notifications,
            "unread_notifications": unread_notifications,
        }
        return Response(data)
