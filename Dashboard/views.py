from datetime import date
from calendar import monthrange
import logging
from django.db.models import Sum, Q

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework import viewsets
from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated, BasePermission

from BusinessRegistration.models import VendorBusinessRegistration as Vendor
from Customer.billing_utils import generate_or_update_bills_for_vendor
from Customer.models import Customer, Bill, BillLineItem
from Milkman.models import Milkman
from vendor.models import JoinRequest
from django.db.models import F, ExpressionWrapper, IntegerField, Func, Value

from vendorcalendar.models import CustomerRequest, MilkmanLeaveRequest, DeliveryRecord
from OneWindowHomeSolution.responses import success_response, error_response
from OneWindowHomeSolution.custom_authentication import CustomJWTAuthentication
from .models import SubscriptionPlan
from .serializers import SubscriptionPlanSerializer
from decimal import Decimal


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


    # Consumer extra milk pending requests count: number of pending extra milk requests
    # from customers that are already accepted/assigned to this vendor.
    consumer_extra_milk_amount = CustomerRequest.objects.filter(
        vendor=vendor,
        request_type="extra_milk",
        status="pending"
    ).count()

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


@swagger_auto_schema(
    method="get",
    operation_summary="Customer Monthly Summary",
    operation_description="Returns monthly summary for a customer including total milk delivered (regular + extra), delivery counts, leaves, and unpaid amount for the month.",
    manual_parameters=[
        openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID", type=openapi.TYPE_INTEGER, required=True),
        openapi.Parameter('month', openapi.IN_QUERY, description="Month (1-12)", type=openapi.TYPE_INTEGER, required=True),
        openapi.Parameter('year', openapi.IN_QUERY, description="Year (e.g., 2025)", type=openapi.TYPE_INTEGER, required=True),
    ],
    responses={200: openapi.Response(description="Customer monthly summary")}
)
@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def customer_month_summary(request):
    """Monthly summary for customer role."""
    customer_id = request.query_params.get('customer_id')
    month = request.query_params.get('month')
    year = request.query_params.get('year')

    if not (customer_id and month and year):
        return error_response("customer_id, month, and year are required", status_code=400)

    try:
        month = int(month)
        year = int(year)
    except ValueError:
        return error_response("month and year must be integers", status_code=400)

    try:
        customer = Customer.objects.get(id=customer_id)
    except Customer.DoesNotExist:
        return error_response("Customer not found", status_code=404)

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    cow_base = Decimal(str(customer.cow_milk_litre or 0))
    buffalo_base = Decimal(str(customer.buffalo_milk_litre or 0))

    # Delivered records within month
    delivered_regular = DeliveryRecord.objects.filter(
        customer=customer,
        date__gte=start_date,
        date__lte=end_date,
        delivery_type='regular',
        status='delivered'
    )
    delivered_extra = DeliveryRecord.objects.filter(
        customer=customer,
        date__gte=start_date,
        date__lte=end_date,
        delivery_type='extra',
        status='delivered'
    )

    regular_dates = set(delivered_regular.values_list('date', flat=True))
    extra_dates = set(delivered_extra.values_list('date', flat=True))

    # Delivery count rule:
    # - Regular delivery counts as 1 for the date
    # - Extra delivery counts as +1 only if there was no regular delivery on that date
    regular_delivery_count = len(regular_dates)
    extra_delivery_count = len([d for d in extra_dates if d not in regular_dates])
    total_deliveries = regular_delivery_count + extra_delivery_count

    # Milk delivered: base quantities for regular delivered days + extras from both regular (inline) and extra deliveries
    base_cow = cow_base * Decimal(str(regular_delivery_count))
    base_buffalo = buffalo_base * Decimal(str(regular_delivery_count))

    inline_extra_cow = delivered_regular.aggregate(total=Sum('cow_milk_extra'))['total'] or 0
    inline_extra_buffalo = delivered_regular.aggregate(total=Sum('buffalo_milk_extra'))['total'] or 0
    extra_cow = delivered_extra.aggregate(total=Sum('cow_milk_extra'))['total'] or 0
    extra_buffalo = delivered_extra.aggregate(total=Sum('buffalo_milk_extra'))['total'] or 0

    total_cow_delivered = base_cow + Decimal(str(inline_extra_cow)) + Decimal(str(extra_cow))
    total_buffalo_delivered = base_buffalo + Decimal(str(inline_extra_buffalo)) + Decimal(str(extra_buffalo))
    total_milk_delivered = total_cow_delivered + total_buffalo_delivered

    # Leaves: approved leaves (legacy) or quantity_adjustment with zero quantities
    leaves_count = CustomerRequest.objects.filter(
        customer=customer,
        date__gte=start_date,
        date__lte=end_date,
        status='approved'
    ).filter(
        Q(request_type='leave') |
        Q(request_type='quantity_adjustment', cow_milk_extra=0, buffalo_milk_extra=0)
    ).count()

    # Unpaid amount for deliveries in this month: pending bills, line items within month
    unpaid_amount = BillLineItem.objects.filter(
        bill__customer=customer,
        bill__status='pending',
        date__gte=start_date,
        date__lte=end_date
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

    data = {
        'customer_id': customer.id,
        'month': month,
        'year': year,
        'total_milk_delivered_litres': float(total_milk_delivered),
        'total_deliveries': total_deliveries,
        'leaves_count': leaves_count,
        'unpaid_amount': float(unpaid_amount),
        'cow_milk_delivered_litres': float(total_cow_delivered),
        'buffalo_milk_delivered_litres': float(total_buffalo_delivered),
    }

    return success_response("Customer monthly summary fetched successfully", data)


@api_view(["GET"])
def dashboard_data(request):
    try:
        total_vendors = Vendor.objects.count()
        total_customers = Customer.objects.count()
        total_milkmen = Milkman.objects.count()

        data = {
            "total_vendors": total_vendors,
            "total_customers": total_customers,
            "total_milkmen": total_milkmen,
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
