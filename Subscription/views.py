from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Count, Q

from .models import SubscribedVendor
from Dashboard.models import SubscriptionPlan
from .serializers import SubscribedVendorSerializer, SubscriptionSummarySerializer
from Customer.models import Customer
from OneWindowHomeSolution.responses import success_response, error_response
import logging

logger = logging.getLogger(__name__)


@swagger_auto_schema(
    method="get",
    operation_summary="List Subscribed Customers for Vendor",
    operation_description="Retrieve a list of all subscribed customers for a given vendor (provider). Pass vendor_id as a query parameter.",
    manual_parameters=[
        openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor (provider) ID", type=openapi.TYPE_INTEGER, required=True)
    ],
    responses={200: SubscribedVendorSerializer(many=True)}
)
@api_view(["GET"])
def subscribed_customers_for_vendor(request):
    logger.info("START subscribed_customers_for_vendor | query params: %s", request.query_params)
    vendor_id = request.query_params.get('vendor_id')
    if not vendor_id:
        logger.warning("vendor_id is missing in the query parameters")
        return error_response("vendor_id query parameter is required", status_code=status.HTTP_400_BAD_REQUEST)
    try:
        customers = Customer.objects.filter(provider_id=vendor_id)
        subs = SubscribedVendor.objects.select_related("Customer", "plan").filter(Customer__in=customers)
        serializer = SubscribedVendorSerializer(subs, many=True)
        logger.info("END subscribed_customers_for_vendor | vendor_id: %s, count: %d", vendor_id, len(serializer.data))
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": "Subscribed customer list for vendor fetched successfully",
            "data": serializer.data,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("An error occurred in subscribed_customers_for_vendor: %s", str(e))
        response_data = {
            "status": "error",
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": str(e),
        }
        return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    method="get",
    operation_summary="List Subscribed Customers",
    operation_description="Retrieve a list of all subscribed customers.",
    responses={200: SubscribedVendorSerializer(many=True)}
)
@api_view(["GET"])
def subscribed_customers_list(request):
    logger.info("START subscribed_customers_by_frequency | query params: %s", request.query_params)
    logger.info("START subscribed_customers_list")
    try:
        subs = SubscribedVendor.objects.select_related("Customer", "plan").all()
        serializer = SubscribedVendorSerializer(subs, many=True)
        logger.info("END subscribed_customers_list | count: %d", len(serializer.data))
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": "Subscribed customer list fetched successfully",
            "data": serializer.data,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("An error occurred in subscribed_customers_list: %s", str(e))
        response_data = {
            "status": "error",
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": str(e),
        }
        return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    method="get",
    operation_description="Get the total number of subscribed customers.",
    responses={200: openapi.Response(description="Total subscribed customers")}
)
@api_view(["GET"])
def total_subscribed_customers(request):
    logger.info("START total_subscribed_customers")
    try:
        total = SubscribedVendor.objects.count()
        logger.info("END total_subscribed_customers | count: %d", total)
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": "Total subscribed customers fetched successfully",
            "total_subscribed_customers": total,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("An error occurred in total_subscribed_customers: %s", str(e))
        response_data = {
            "status": "error",
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "message": str(e),
        }
        return Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    method="get",
    operation_summary="Subscription Summary",
    operation_description="Get summary of subscriptions by duration.",
    responses={200: openapi.Response(description="Subscription summary")}
)
@api_view(["GET"])
def subscription_summary(request):
    logger.info("START subscription_summary")
    summary = (
        SubscribedVendor.objects.values("plan__duration")
        .annotate(count=Count("id"))
        .order_by("plan__duration")
    )
    summary_data = [
        {"duration_days": item["plan__duration"], "count": item["count"]}
        for item in summary
    ]
    serializer = SubscriptionSummarySerializer(summary_data, many=True)
    logger.info("END subscription_summary | durations: %s", [item["duration_days"] for item in summary_data])
    return Response(serializer.data)


@swagger_auto_schema(
    method="get",
    operation_summary="List Subscribed Customers by Frequency",
    operation_description=(
        "List customers who have a subscription of a given frequency. "
        "Provide query parameter 'frequency' with values: monthly, semiannual, annual. "
        "Optional query parameter 'vendor_id' to restrict to a vendor's customers."
    ),
    manual_parameters=[
        openapi.Parameter('frequency', openapi.IN_QUERY, description="Subscription frequency: monthly|semiannual|annual", type=openapi.TYPE_STRING, required=True),
        openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor (provider) ID", type=openapi.TYPE_INTEGER, required=False),
    ],
    responses={200: SubscribedVendorSerializer(many=True)}
)
@api_view(["GET"])
def subscribed_customers_by_frequency(request):
    logger.info("Entering subscribed_customers_by_frequency with query params: %s", request.query_params)
    frequency = (request.query_params.get("frequency") or "").strip().lower()
    vendor_id = request.query_params.get("vendor_id")

    if frequency not in ("monthly", "semiannual", "annual"):
        logger.warning("Invalid frequency value: %s", frequency)
        return error_response("Query parameter 'frequency' must be one of: monthly, semiannual, annual", status_code=status.HTTP_400_BAD_REQUEST)

    try:
        # Build plan filter by name (if available) or by duration_days ranges
        if frequency == "monthly":
            plan_q = Q(plan__name__icontains="month") | Q(plan__duration_days__range=(28, 31)) | Q(plan__duration_days=30)
        elif frequency == "semiannual":
            # Accept ~6 months (170-200 days) or names containing 'semi' / 'half'
            plan_q = Q(plan__name__icontains="semi") | Q(plan__name__icontains="half") | Q(plan__duration_days__range=(170, 200))
        else:  # annual
            plan_q = Q(plan__name__icontains="year") | Q(plan__name__icontains="annual") | Q(plan__duration_days__range=(360, 370)) | Q(plan__duration_days=365)

        subs_q = SubscribedVendor.objects.select_related("Customer", "plan").filter(plan_q)

        if vendor_id:
            customers = Customer.objects.filter(provider_id=vendor_id)
            subs_q = subs_q.filter(Customer__in=customers)

        serializer = SubscribedVendorSerializer(subs_q, many=True)
        logger.info("Successfully fetched subscribed customers with '%s' frequency", frequency)
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": f"Subscribed customers with '{frequency}' subscriptions fetched successfully",
            "data": serializer.data,
        }
        return Response(response_data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error("An error occurred in subscribed_customers_by_frequency: %s", str(e))
        return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
