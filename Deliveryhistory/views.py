from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from .models import DeliveryHistory
from .serializers import DeliveryHistorySerializer, DeliveryStatusUpdateSerializer
from django.shortcuts import get_object_or_404
from OneWindowHomeSolution.responses import success_response, error_response, not_found_response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models import Sum, Q, Count
from datetime import datetime, date
import calendar
from Customer.models import Customer

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
import logging

logger = logging.getLogger(__name__)

# ---------------- Delivery History ViewSet ----------------
class DeliveryHistoryViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    queryset = DeliveryHistory.objects.all()
    serializer_class = DeliveryHistorySerializer

    @swagger_auto_schema(
        operation_summary="List Delivery Histories",
        operation_description="Retrieve a list of all delivery histories, optionally filtered by customer ID.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID to filter delivery histories", type=openapi.TYPE_INTEGER)
        ],
        responses={200: DeliveryHistorySerializer(many=True)}
    )
    def list(self, request):
        customer_id = request.query_params.get("customer_id")
        if customer_id:
            histories = DeliveryHistory.objects.filter(
                customer__id=customer_id
            ).order_by("-delivery_date")
        else:
            histories = DeliveryHistory.objects.all().order_by("-delivery_date")
        serializer = self.serializer_class(histories, many=True)
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": "Delivery histories fetched successfully",
            "data": serializer.data,
        }
        return Response(response_data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_summary="Retrieve Delivery History",
        operation_description="Get details of a specific delivery history by its ID.",
        responses={200: DeliveryHistorySerializer()},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="DeliveryHistory ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def retrieve(self, request, pk=None):
        try:
            history = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return not_found_response("Delivery history not found")
        serializer = self.serializer_class(history)
        return success_response("Delivery history retrieved successfully", serializer.data)
    @swagger_auto_schema(
        operation_summary="Create Delivery History",
        operation_description="Create a new delivery history record.",
        request_body=DeliveryHistorySerializer,
        responses={201: DeliveryHistorySerializer()}
    )
    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response("Delivery history created successfully", serializer.data, status_code=status.HTTP_201_CREATED)
        return error_response("Failed to create delivery history", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Update Delivery History",
        operation_description="Update all details of an existing delivery history record.",
        request_body=DeliveryHistorySerializer,
        responses={200: DeliveryHistorySerializer()},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="DeliveryHistory ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def update(self, request, pk=None):
        try:
            history = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return not_found_response("Delivery history not found")
        serializer = self.serializer_class(history, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response("Delivery history updated successfully", serializer.data)
        return error_response("Failed to update delivery history", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Partially Update Delivery History",
        operation_description="Update selected fields of an existing delivery history record.",
        request_body=DeliveryHistorySerializer,
        responses={200: DeliveryHistorySerializer()},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="DeliveryHistory ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def partial_update(self, request, pk=None):
        try:
            history = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return not_found_response("Delivery history not found")
        serializer = self.serializer_class(history, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success_response("Delivery history partially updated successfully", serializer.data)
        return error_response("Failed to partially update delivery history", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Delete Delivery History",
        operation_description="Delete a delivery history record by its ID.",
        responses={204: "No Content"},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="DeliveryHistory ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def destroy(self, request, pk=None):
        try:
            history = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return not_found_response("Delivery history not found")
        history.delete()
        return success_response("Delivery history deleted successfully", status_code=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='daily-status')
    @swagger_auto_schema(
        operation_summary="Get Daily Delivery Status",
        operation_description="Retrieve daily delivery status for a customer with optional filtering by month or date range.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID (required)", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('month', openapi.IN_QUERY, description="Month (1-12, optional)", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter('year', openapi.IN_QUERY, description="Year (e.g., 2024, required if month is provided)", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Start date (YYYY-MM-DD, optional)", type=openapi.TYPE_STRING, required=False),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="End date (YYYY-MM-DD, optional)", type=openapi.TYPE_STRING, required=False)
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'dailyStatus': openapi.Schema(
                        type=openapi.TYPE_ARRAY,
                        items=openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'consumerId': openapi.Schema(type=openapi.TYPE_STRING),
                                'venderId': openapi.Schema(type=openapi.TYPE_STRING),
                                'distributerId': openapi.Schema(type=openapi.TYPE_STRING),
                                'date': openapi.Schema(type=openapi.TYPE_STRING),
                                'milkType': openapi.Schema(type=openapi.TYPE_STRING),
                                'monthlyMilkRequest': openapi.Schema(type=openapi.TYPE_STRING),
                                'extraMilkDeliveredinLtr': openapi.Schema(type=openapi.TYPE_STRING),
                                'deliveryStatus': openapi.Schema(type=openapi.TYPE_STRING),
                                'distributerName': openapi.Schema(type=openapi.TYPE_STRING),
                                'nonDeliveryReason': openapi.Schema(type=openapi.TYPE_STRING, description="Present only for not_delivered status"),
                                'nonDeliveryReasonDisplay': openapi.Schema(type=openapi.TYPE_STRING, description="Human readable reason"),
                                'nonDeliveryExplanation': openapi.Schema(type=openapi.TYPE_STRING, description="Additional explanation"),
                                'attemptedDeliveryTime': openapi.Schema(type=openapi.TYPE_STRING, description="Time when delivery was attempted"),
                                'rescheduledDeliveryDate': openapi.Schema(type=openapi.TYPE_STRING, description="Rescheduled date for failed delivery"),
                                'needsReschedule': openapi.Schema(type=openapi.TYPE_BOOLEAN, description="Whether delivery needs rescheduling"),
                                'deliveryCompletedTime': openapi.Schema(type=openapi.TYPE_STRING, description="Present only for delivered status"),
                                'totalMilkDelivered': openapi.Schema(type=openapi.TYPE_STRING, description="Total milk including extra"),
                                'remarks': openapi.Schema(type=openapi.TYPE_STRING, description="General remarks")
                            }
                        )
                    )
                }
            )
        }
    )
    def daily_status(self, request):
        customer_id = request.query_params.get('customer_id')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not customer_id:
            return error_response("customer_id is required")

        try:
            customer_id = int(customer_id)
        except ValueError:
            return error_response("Invalid customer_id format")

        # Verify customer exists
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found")

        # Base query
        delivery_records = DeliveryHistory.objects.filter(
            customer_id=customer_id
        ).select_related('vendor', 'distributor')

        # Apply filtering - prioritize month over date range
        if month:
            try:
                month = int(month)
                if not (1 <= month <= 12):
                    return error_response("Month must be between 1 and 12")
                
                if not year:
                    return error_response("Year is required when month is provided")
                
                year = int(year)
                delivery_records = delivery_records.filter(
                    delivery_date__year=year,
                    delivery_date__month=month
                )
            except ValueError:
                return error_response("Invalid month or year format")

        # Apply date range filtering only if month is not provided
        elif start_date and end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                if start_date_obj > end_date_obj:
                    return error_response("Start date cannot be after end date")
                
                delivery_records = delivery_records.filter(
                    delivery_date__gte=start_date_obj,
                    delivery_date__lte=end_date_obj
                )
            except ValueError:
                return error_response("Invalid date format. Use YYYY-MM-DD")

        elif start_date or end_date:
            return error_response("Both start_date and end_date are required for date range filtering")

        # Order by date
        delivery_records = delivery_records.order_by('-delivery_date')

        # Get customer's monthly milk request
        monthly_milk_request = float(customer.cow_milk_litre or 0) + float(customer.buffalo_milk_litre or 0)

        # Format dailyStatus response
        daily_status = []
        for record in delivery_records:
            status_info = {
                "consumerId": str(record.customer.id),
                "venderId": str(record.vendor.id) if record.vendor else "",
                "distributerId": str(record.distributor.id) if record.distributor else "",
                "date": record.delivery_date.strftime("%Y-%m-%d"),
                "milkType": record.milk_type,
                "monthlyMilkRequest": str(monthly_milk_request),
                "extraMilkDeliveredinLtr": str(record.extra_milk_quantity),
                "deliveryStatus": record.status,
                "distributerName": record.distributor.name if record.distributor else ""
            }
            
            # Add non-delivery information if applicable
            if record.status == 'not_delivered':
                status_info.update({
                    "nonDeliveryReason": record.non_delivery_reason,
                    "nonDeliveryReasonDisplay": record.get_non_delivery_reason_display() if record.non_delivery_reason else "",
                    "nonDeliveryExplanation": record.non_delivery_explanation or "",
                    "attemptedDeliveryTime": record.attempted_delivery_time.strftime("%H:%M") if record.attempted_delivery_time else "",
                    "rescheduledDeliveryDate": record.rescheduled_delivery_date.strftime("%Y-%m-%d") if record.rescheduled_delivery_date else "",
                    "needsReschedule": not record.rescheduled_delivery_date
                })
            elif record.status == 'delivered':
                status_info.update({
                    "deliveryCompletedTime": record.delivery_completed_time.strftime("%H:%M") if record.delivery_completed_time else "",
                    "totalMilkDelivered": str(record.total_milk_delivered)
                })
            
            # Add general remarks if present
            if record.remarks:
                status_info["remarks"] = record.remarks
                
            daily_status.append(status_info)

        response_data = {
            "dailyStatus": daily_status
        }

        return success_response("Daily status retrieved successfully", response_data)

    @action(detail=True, methods=['patch'], url_path='update-status')
    @swagger_auto_schema(
        operation_summary="Update Delivery Status",
        operation_description="Update delivery status with non-delivery reasons if applicable.",
        request_body=DeliveryStatusUpdateSerializer,
        responses={200: DeliveryHistorySerializer()}
    )
    def update_status(self, request, pk=None):
        """Update delivery status with proper non-delivery handling"""
        try:
            delivery = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return not_found_response("Delivery history not found")

        serializer = DeliveryStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Invalid data", serializer.errors)

        validated_data = serializer.validated_data
        
        # Update delivery record
        for field, value in validated_data.items():
            setattr(delivery, field, value)
        
        try:
            delivery.save()
            response_serializer = DeliveryHistorySerializer(delivery)
            return success_response("Delivery status updated successfully", response_serializer.data)
        except Exception as e:
            return error_response("Failed to update delivery status", str(e))

    @action(detail=False, methods=['get'], url_path='non-delivery-stats')
    @swagger_auto_schema(
        operation_summary="Get Non-Delivery Statistics",
        operation_description="Get statistics about non-delivered orders and their reasons.",
        manual_parameters=[
            openapi.Parameter('distributor_id', openapi.IN_QUERY, description="Distributor ID to filter", type=openapi.TYPE_INTEGER),
            openapi.Parameter('start_date', openapi.IN_QUERY, description="Start date (YYYY-MM-DD)", type=openapi.TYPE_STRING),
            openapi.Parameter('end_date', openapi.IN_QUERY, description="End date (YYYY-MM-DD)", type=openapi.TYPE_STRING)
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'total_deliveries': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'not_delivered_count': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'not_delivered_percentage': openapi.Schema(type=openapi.TYPE_NUMBER),
                    'non_delivery_reasons': openapi.Schema(type=openapi.TYPE_OBJECT),
                    'pending_reschedules': openapi.Schema(type=openapi.TYPE_INTEGER)
                }
            )
        }
    )
    def non_delivery_stats(self, request):
        """Get statistics about non-deliveries"""
        distributor_id = request.query_params.get('distributor_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        # Base query
        queryset = DeliveryHistory.objects.all()

        # Apply filters
        if distributor_id:
            queryset = queryset.filter(distributor_id=distributor_id)
        
        if start_date and end_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(
                    delivery_date__gte=start_date_obj,
                    delivery_date__lte=end_date_obj
                )
            except ValueError:
                return error_response("Invalid date format. Use YYYY-MM-DD")

        # Calculate statistics
        total_deliveries = queryset.count()
        not_delivered = queryset.filter(status='not_delivered')
        not_delivered_count = not_delivered.count()
        
        # Non-delivery reasons breakdown
        reason_stats = not_delivered.values('non_delivery_reason').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Pending reschedules
        pending_reschedules = not_delivered.filter(
            rescheduled_delivery_date__isnull=True
        ).count()

        # Calculate percentage
        not_delivered_percentage = (
            (not_delivered_count / total_deliveries * 100) if total_deliveries > 0 else 0
        )

        response_data = {
            'total_deliveries': total_deliveries,
            'not_delivered_count': not_delivered_count,
            'not_delivered_percentage': round(not_delivered_percentage, 2),
            'non_delivery_reasons': {
                item['non_delivery_reason']: item['count'] 
                for item in reason_stats if item['non_delivery_reason']
            },
            'pending_reschedules': pending_reschedules
        }

        return success_response("Non-delivery statistics retrieved successfully", response_data)

    @action(detail=False, methods=['get'], url_path='failed-deliveries')
    @swagger_auto_schema(
        operation_summary="Get Failed Deliveries",
        operation_description="Get list of failed deliveries that need attention or rescheduling.",
        manual_parameters=[
            openapi.Parameter('distributor_id', openapi.IN_QUERY, description="Distributor ID to filter", type=openapi.TYPE_INTEGER),
            openapi.Parameter('needs_reschedule', openapi.IN_QUERY, description="Filter deliveries needing reschedule", type=openapi.TYPE_BOOLEAN)
        ],
        responses={200: DeliveryHistorySerializer(many=True)}
    )
    def failed_deliveries(self, request):
        """Get failed deliveries that need attention"""
        distributor_id = request.query_params.get('distributor_id')
        needs_reschedule = request.query_params.get('needs_reschedule', '').lower() == 'true'

        queryset = DeliveryHistory.objects.filter(status='not_delivered')

        if distributor_id:
            queryset = queryset.filter(distributor_id=distributor_id)
        
        if needs_reschedule:
            queryset = queryset.filter(rescheduled_delivery_date__isnull=True)

        queryset = queryset.select_related('customer', 'vendor', 'distributor').order_by('-delivery_date')

        serializer = DeliveryHistorySerializer(queryset, many=True)
        return success_response("Failed deliveries retrieved successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Mark Delivery as Delivered",
        operation_description="Mark a specific delivery history record as delivered. Only the milkman or vendor associated with the delivery can perform this action.",
        manual_parameters=[
            openapi.Parameter('delivery_id', openapi.IN_PATH, description="Delivery History ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={
            200: openapi.Response("Delivery marked as delivered successfully"),
            403: openapi.Response("Forbidden - Only milkman or vendor can mark the delivery as delivered"),
            404: openapi.Response("Delivery history not found")
        }
    )
    @action(detail=True, methods=["post"], url_path="mark-delivered")
    def mark_delivered(self, request, pk=None):
        try:
            delivery = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return error_response("Delivery history not found", status_code=404)

        # Check if the user is the associated milkman or vendor
        user = request.user
        if user.id != delivery.distributor_id and user.id != delivery.vendor_id:
            return error_response("Only the associated milkman or vendor can mark the delivery as delivered", status_code=403)

        # Mark the delivery as delivered
        delivery.status = "delivered"
        delivery.save()

        return success_response("Delivery marked as delivered successfully", {
            "delivery_id": delivery.id,
            "status": delivery.status
        })

    @swagger_auto_schema(
        operation_summary="Mark Delivery as Not Delivered",
        operation_description="Mark a specific delivery history record as not delivered with a reason.",
        request_body=DeliveryStatusUpdateSerializer,
        responses={
            200: openapi.Response("Delivery marked as not delivered successfully"),
            404: openapi.Response("Delivery history not found"),
            400: openapi.Response("Invalid data")
        }
    )
    @action(detail=True, methods=["post"], url_path="mark-not-delivered")
    def mark_not_delivered(self, request, pk=None):
        try:
            delivery = DeliveryHistory.objects.get(pk=pk)
        except DeliveryHistory.DoesNotExist:
            return error_response("Delivery history not found", status_code=404)

        serializer = DeliveryStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Invalid data", serializer.errors, status_code=400)

        validated_data = serializer.validated_data

        # Update delivery record
        delivery.status = "not_delivered"
        delivery.non_delivery_reason = validated_data.get("non_delivery_reason")
        delivery.remarks = validated_data.get("remarks")
        delivery.updated_by = validated_data.get("updated_by")

        try:
            delivery.save()
            return success_response("Delivery marked as not delivered successfully", {
                "delivery_id": delivery.id,
                "status": delivery.status,
                "non_delivery_reason": delivery.non_delivery_reason
            })
        except Exception as e:
            return error_response("Failed to mark delivery as not delivered", str(e))
