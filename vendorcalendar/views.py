from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, date

from .models import DeliveryRecord, MilkmanLeaveRequest, CustomerRequest
from .serializers import DeliveryCalendarSerializer, LeaveRequestSerializer, MilkmanLeaveRequestSerializer, DeliveryRecordSerializer, CustomerRequestSerializer, DeliveryAdjustmentSerializer
from Customer.models import Customer
from Milkman.models import Milkman
from BusinessRegistration.models import VendorBusinessRegistration
from django.apps import apps
from Customer.serializers import CustomerSerializer
from OneWindowHomeSolution.responses import success_response, error_response, not_found_response
from OneWindowHomeSolution.core_utils import safe_str, format_address
from utils.fcm_notifications import send_fcm_notification
import logging
from decimal import Decimal, InvalidOperation

JoinRequest = apps.get_model('vendor', 'JoinRequest')
logger = logging.getLogger(__name__)

class VendorCalendarViewSet(viewsets.ViewSet):
    @swagger_auto_schema(
        operation_summary="Assign/Update Milkman for Extra Milk Request",
        operation_description="Assign or update the milkman (distributor) for an extra milk delivery request.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'request_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Extra milk request ID"),
                'milkman_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Milkman (distributor) ID")
            },
            required=['request_id', 'milkman_id']
        ),
        responses={
            200: openapi.Response("Milkman assigned successfully", CustomerRequestSerializer),
            400: "Invalid input or request",
            404: "Request or milkman not found"
        }
    )
    @action(detail=False, methods=['patch'], url_path='assign-milkman')
    def assign_milkman(self, request):
        """Assign or update the milkman (distributor) for an extra milk delivery request."""
        request_id = request.data.get('request_id')
        milkman_id = request.data.get('milkman_id')
        if not request_id:
            return error_response("request_id is required.", status_code=400)
        if not milkman_id:
            return error_response("milkman_id is required.", status_code=400)
        try:
            customer_request = CustomerRequest.objects.get(pk=request_id, request_type='extra_milk')
        except CustomerRequest.DoesNotExist:
            return error_response("Extra milk request not found.", status_code=404)
        try:
            milkman = Milkman.objects.get(id=milkman_id)
        except Milkman.DoesNotExist:
            return error_response("Milkman not found.", status_code=404)

        customer_request.extra_milk_delivery_milkman = milkman
        customer_request.save()

        # NOTE: Do NOT create DeliveryRecord here.
        # DeliveryRecord for extra milk should ONLY be created when the milkman
        # marks the delivery as completed via mark_extra_milk_delivery endpoint.

        return success_response("Milkman assigned successfully.", CustomerRequestSerializer(customer_request).data)

    @swagger_auto_schema(
        operation_summary="List Approved Extra Milk Requests Assigned to Milkman (From Date Onwards)",
        operation_description="List all approved extra milk requests assigned to a milkman from the given date onwards. Only shows requests that have been approved by the vendor.",
        manual_parameters=[
            openapi.Parameter(
                'milkman_id', openapi.IN_QUERY, description="Milkman ID", type=openapi.TYPE_INTEGER, required=True
            ),
            openapi.Parameter(
                'date', openapi.IN_QUERY, description="Start date (YYYY-MM-DD). Returns all requests from this date onwards.", type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={
            200: openapi.Response("Approved extra milk requests assigned to milkman from date onwards.", CustomerRequestSerializer(many=True)),
            400: "Invalid input or request",
            404: "Milkman not found"
        }
    )
    @action(detail=False, methods=['get'], url_path='milkman-extra-milk-requests')
    def milkman_extra_milk_requests(self, request):
        """
        List all approved extra milk requests assigned to a milkman from the given date onwards.
        Only returns requests that have been approved by the vendor.
        
        Query Parameters:
            - milkman_id (int, required): Milkman ID
            - date (str, required): Start date in YYYY-MM-DD format
        
        Returns:
            List of extra milk requests assigned to the specified milkman with approved status, from the given date onwards.
        """
        milkman_id = request.query_params.get('milkman_id')
        date_str = request.query_params.get('date')
        if not milkman_id or not date_str:
            return error_response("milkman_id and date are required.")
        try:
            from Milkman.models import Milkman
            milkman = Milkman.objects.get(id=milkman_id)
        except Exception:
            return error_response("Milkman not found.")
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD.")
        # Only show approved requests to the milkman
        requests = CustomerRequest.objects.filter(
            request_type='extra_milk',
            extra_milk_delivery_milkman=milkman,
            date__gte=date_obj,
            status='approved',  # Only approved requests
            extra_milk_delivery_status='pending'  # Still pending delivery
        )
        serialized = CustomerRequestSerializer(requests, many=True).data
        # Add customer name and address to each object
        for idx, req in enumerate(requests):
            customer = req.customer
            serialized[idx]['customer_name'] = str(customer.name) if customer and customer.name else ""
            # Use the helper for address if available
            if hasattr(self, 'construct_customer_address'):
                serialized[idx]['customer_address'] = self.get_customer_address(customer)
            else:
                # Fallback: concatenate address fields
                address_parts = [
                    getattr(customer, 'flat_no', None),
                    getattr(customer, 'society_name', None),
                    getattr(customer, 'village', None),
                    getattr(customer, 'tal', None),
                    getattr(customer, 'dist', None),
                    getattr(customer, 'state', None),
                    getattr(customer, 'pincode', None),
                ]
                serialized[idx]['customer_address'] = ', '.join([str(part) for part in address_parts if part])
        return success_response("Approved extra milk requests assigned to milkman from date onwards.", serialized)

    @swagger_auto_schema(
        operation_summary="List All Extra Milk Requests Assigned to Milkman (From Date Onwards)",
        operation_description="List all extra milk requests (pending, approved, rejected) assigned to a milkman from the given date onwards. For vendor/management view.",
        manual_parameters=[
            openapi.Parameter(
                'milkman_id', openapi.IN_QUERY, description="Milkman ID", type=openapi.TYPE_INTEGER, required=True
            ),
            openapi.Parameter(
                'date', openapi.IN_QUERY, description="Start date (YYYY-MM-DD). Returns all requests from this date onwards.", type=openapi.TYPE_STRING, required=True
            ),
        ],
        responses={
            200: openapi.Response("All extra milk requests assigned to milkman from date onwards.", CustomerRequestSerializer(many=True)),
            400: "Invalid input or request",
            404: "Milkman not found"
        }
    )
    @action(detail=False, methods=['get'], url_path='milkman-all-extra-milk-requests')
    def milkman_all_extra_milk_requests(self, request):
        """
        List all extra milk requests (pending, approved, rejected) assigned to a milkman from the given date onwards.
        This endpoint is for vendor/management purposes to see all request statuses.
        
        Query Parameters:
            - milkman_id (int, required): Milkman ID
            - date (str, required): Start date in YYYY-MM-DD format
        
        Returns:
            List of all extra milk requests assigned to the specified milkman from the given date onwards.
        """
        milkman_id = request.query_params.get('milkman_id')
        date_str = request.query_params.get('date')
        if not milkman_id or not date_str:
            return error_response("milkman_id and date are required.")
        try:
            from Milkman.models import Milkman
            milkman = Milkman.objects.get(id=milkman_id)
        except Exception:
            return error_response("Milkman not found.")
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD.")
        # Return all requests regardless of approval status
        requests = CustomerRequest.objects.filter(
            request_type='extra_milk',
            extra_milk_delivery_milkman=milkman,
            date__gte=date_obj,
        )
        serialized = CustomerRequestSerializer(requests, many=True).data
        # Add customer name and address to each object
        for idx, req in enumerate(requests):
            customer = req.customer
            serialized[idx]['customer_name'] = str(customer.name) if customer and customer.name else ""
            # Fallback: concatenate address fields
            address_parts = [
                getattr(customer, 'flat_no', None),
                getattr(customer, 'society_name', None),
                getattr(customer, 'village', None),
                getattr(customer, 'tal', None),
                getattr(customer, 'dist', None),
                getattr(customer, 'state', None),
                getattr(customer, 'pincode', None),
            ]
            serialized[idx]['customer_address'] = ', '.join([str(part) for part in address_parts if part])
        return success_response("All extra milk requests assigned to milkman from date onwards.", serialized)

    @swagger_auto_schema(
        operation_summary="Mark Extra Milk Delivery Status",
        operation_description="Mark the delivery status for an extra milk request. Only the assigned milkman, staff, or superuser can mark the delivery. Idempotent: cannot mark if already delivered/unsuccessful. Also updates related DeliveryRecord.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["request_id", "status"],
            properties={
                "request_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the extra milk request to mark"),
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["delivered", "unsuccessful"],
                    description="Delivery status to mark ('delivered' or 'unsuccessful')"
                )
            },
            example={"request_id": 123, "status": "delivered"}
        ),
        responses={
            200: openapi.Response(
                "Extra milk delivery status updated.",
                CustomerRequestSerializer
            ),
            400: "Invalid input or already marked.",
            403: "Not authorized.",
            404: "Extra milk request not found."
        }
    )
    @action(detail=False, methods=['patch'], url_path='mark-extra-milk-delivery')
    def mark_extra_milk_delivery(self, request):
        """
        Mark delivery status for an extra milk request (unified endpoint).
        
        Request Body:
            - request_id (int, required): The ID of the extra milk request
            - status (str, required): 'delivered' or 'unsuccessful'
        Returns:
            Standard response with updated CustomerRequest data.
        """
        request_id = request.data.get('request_id')
        status_val = request.data.get('status')
        if not request_id or not status_val:
            return error_response("Both request_id and status are required.")
        try:
            customer_request = CustomerRequest.objects.get(pk=request_id, request_type='extra_milk')
        except CustomerRequest.DoesNotExist:
            return error_response("Extra milk request not found.")

        valid_statuses = ['delivered', 'unsuccessful']
        if status_val not in valid_statuses:
            return error_response(f"Invalid status. Allowed: {', '.join(valid_statuses)}.")

        # Idempotency: Don't allow update if already marked as delivered/unsuccessful
        if customer_request.extra_milk_delivery_status in valid_statuses:
            return error_response(f"Request already marked as {customer_request.extra_milk_delivery_status}.", status_code=400)

        # Authorization: Only assigned milkman, staff, or superuser can mark delivery
        user = request.user if request.user.is_authenticated else None
        milkman = customer_request.extra_milk_delivery_milkman or getattr(customer_request.customer, 'milkman', None)
        is_staff = hasattr(user, 'is_staff') and user.is_staff
        is_superuser = hasattr(user, 'is_superuser') and user.is_superuser
        is_milkman = milkman and user and hasattr(user, 'id') and milkman.id == user.id
        if not (is_milkman or is_staff or is_superuser):
            return error_response("You are not authorized to mark this delivery.", status_code=403)

        # Audit trail update
        history = customer_request.extra_milk_delivery_status_history or []
        history.append({
            'timestamp': timezone.now().isoformat(),
            'status': status_val,
            'user': getattr(user, 'id', None)
        })
        customer_request.extra_milk_delivery_status = status_val
        customer_request.extra_milk_delivery_marked_at = timezone.now()
        customer_request.extra_milk_delivery_status_history = history
        customer_request.save()

        # Update related DeliveryRecord if exists
        DeliveryRecord.objects.update_or_create(
            customer=customer_request.customer,
            date=customer_request.date,
            delivery_type="extra",
            defaults={
                'vendor': customer_request.vendor,
                'milkman': milkman,
                'cow_milk_extra': getattr(customer_request, 'cow_milk_extra', 0) or 0,
                'buffalo_milk_extra': getattr(customer_request, 'buffalo_milk_extra', 0) or 0,
                'status': status_val,
            }
        )

        # Notification logic (pseudo, replace with actual notification)
        if milkman and hasattr(milkman, 'fcm_token') and milkman.fcm_token:
            send_fcm_notification(
                milkman.fcm_token,
                "Extra Milk Delivery Status Updated",
                f"Delivery for request {customer_request.id} marked as {status_val}."
            )
        return success_response("Extra milk delivery status updated.", CustomerRequestSerializer(customer_request).data)

    # Centralized allowed statuses to avoid magic strings
    # Note: Only actual delivery outcomes should be set directly via create()
    DELIVERY_ALLOWED_STATUSES = ("delivered", "not_delivered", "cancelled", "missed")

    @swagger_auto_schema(
        operation_summary="Deassign Milkman from Customer",
        operation_description="Remove the milkman assignment from a customer.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'customer_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Customer ID")
            },
            required=['customer_id']
        ),
        responses={200: "Milkman deassigned from customer successfully."}
    )
    @action(detail=False, methods=['post'], url_path='deassign-milkman')
    def deassign_milkman(self, request):
        logger.info("Entering deassign_milkman method with request data: %s", request.data)
        customer_id = request.data.get('customer_id')
        if not customer_id:
            logger.warning("customer_id is missing in the request data")
            return error_response("customer_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(id=customer_id)
            previous_milkman = customer.milkman
            customer.milkman = None
            customer.save()
            logger.info("Successfully deassigned milkman from customer %s", customer_id)
            return success_response("Milkman deassigned from customer successfully.", {
                "customer_id": customer.id,
                "customer_name": str(customer.name) if customer.name else "",
                "customer_address": self.get_customer_address(customer),
                "previous_milkman": {
                    "milkman_id": previous_milkman.id,
                    "milkman_name": str(previous_milkman.name) if previous_milkman.name else "",
                    "milkman_contact": str(previous_milkman.phone_number) if previous_milkman.phone_number else ""
                } if previous_milkman else None,
                "current_milkman_id": None
            })
        except Customer.DoesNotExist:
            logger.error("Customer with id %s does not exist", customer_id)
            return error_response("Customer not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("An error occurred in deassign_milkman: %s", str(e))
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Assign Milkman to Customer for Regular Deliveries",
        operation_description="Assign a milkman (distributor) to a customer for regular milk deliveries. The milkman must belong to the same vendor as the customer.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'customer_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Customer ID"),
                'milkman_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Milkman ID")
            },
            required=['customer_id', 'milkman_id']
        ),
        responses={
            200: openapi.Response("Milkman assigned to customer successfully."),
            400: "Invalid input or milkman/customer not under same vendor",
            404: "Customer or Milkman not found"
        }
    )
    @action(detail=False, methods=['post'], url_path='assign-milkman-to-customer')
    def assign_milkman_to_customer(self, request):
        """Assign a milkman (distributor) to a customer for regular milk deliveries."""
        logger.info("Entering assign_milkman_to_customer method with request data: %s", request.data)
        customer_id = request.data.get('customer_id')
        milkman_id = request.data.get('milkman_id')

        if not customer_id:
            return error_response("customer_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        if not milkman_id:
            return error_response("milkman_id is required.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return error_response("Customer not found.", status_code=status.HTTP_404_NOT_FOUND)

        try:
            milkman = Milkman.objects.get(id=milkman_id)
        except Milkman.DoesNotExist:
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)

        # Validate that customer has a vendor
        if not customer.provider:
            return error_response("Customer is not assigned to any vendor.", status_code=status.HTTP_400_BAD_REQUEST)

        # Validate that milkman belongs to the same vendor as the customer
        if not milkman.provider or milkman.provider.id != customer.provider.id:
            return error_response(
                "Milkman must belong to the same vendor as the customer.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        previous_milkman = customer.milkman
        customer.milkman = milkman
        customer.save()

        customer_address = self.get_customer_address(customer)
        logger.info("Successfully assigned milkman %s to customer %s; address=%s", milkman_id, customer_id, customer_address)
        return success_response("Milkman assigned to customer successfully.", {
            "customer_id": customer.id,
            "customer_name": str(customer.name) if customer.name else "",
            "customer_address": customer_address,
            "previous_milkman": {
                "milkman_id": previous_milkman.id,
                "milkman_name": str(previous_milkman.name) if previous_milkman.name else "",
                "milkman_contact": str(previous_milkman.phone_number) if previous_milkman.phone_number else ""
            } if previous_milkman else None,
            "assigned_milkman": {
                "milkman_id": milkman.id,
                "milkman_name": str(milkman.name) if milkman.name else "",
                "milkman_contact": str(milkman.phone_number) if milkman.phone_number else ""
            }
        })

    @swagger_auto_schema(
        operation_summary="Get Customer Delivery Calendar",
        operation_description="Get delivery status for each day for a customer in a given month.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('month', openapi.IN_QUERY, description="Month in YYYY-MM format", type=openapi.TYPE_STRING, required=True)
        ],
        responses={200: openapi.Response("Calendar data", DeliveryCalendarSerializer(many=True))}
    )
    def list(self, request):
        logger.info("START CustomerCalendarViewSet.list | request by user: %s", getattr(request.user, 'id', None))
        customer_id = request.query_params.get("customer_id")
        month_param = request.query_params.get("month")

        if not customer_id or not month_param:
            return error_response("Both customer_id and month are required.")

        try:
            year, month = map(int, month_param.split("-"))
        except ValueError:
            return error_response("Invalid month format. Use YYYY-MM.")

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found.")

        # Fetch actual delivery records
        delivery_records = DeliveryRecord.objects.filter(
            customer=customer, date__year=year, date__month=month
        ).select_related("milkman")

        # Fetch approved customer requests (leave and extra milk)
        approved_requests = CustomerRequest.objects.filter(
            customer=customer,
            date__year=year,
            date__month=month,
            status="approved"
        )

        # Fetch approved milkman leave requests affecting this customer
        milkman_leaves = []
        if customer.milkman:
            milkman_leaves = MilkmanLeaveRequest.objects.filter(
                milkman=customer.milkman,
                start_date__year=year,
                start_date__month=month,
                status="approved"
            )

        # Fetch pending customer requests to show in calendar
        pending_requests = CustomerRequest.objects.filter(
            customer=customer,
            date__year=year,
            date__month=month,
            status="pending"
        )

        # Build unified calendar data
        calendar_data = []
        
        # Add actual delivery records (ONLY regular deliveries)
        # Extra milk delivery status is shown via CustomerRequest logic below
        for record in delivery_records:
            if record.delivery_type == 'regular':
                entry = {
                    "date": record.date.strftime("%Y-%m-%d"),
                    "status": record.status,
                }
                # Include cancellation reason if delivery was cancelled
                if record.status == 'cancelled' and record.cancellation_reason:
                    entry["cancellation_reason"] = record.cancellation_reason
                calendar_data.append(entry)

        # Add approved customer leave requests only (not milkman leaves)
        for req in approved_requests:
            if req.request_type == "leave":
                calendar_data.append({
                    "date": req.date.strftime("%Y-%m-%d"),
                    "status": "leave",
                })
            elif req.request_type == "extra_milk":
                # Check the delivery status of the extra milk
                delivery_status = getattr(req, 'extra_milk_delivery_status', 'pending')
                
                if delivery_status == 'delivered':
                    # Extra milk has been delivered by milkman
                    calendar_data.append({
                        "date": req.date.strftime("%Y-%m-%d"),
                        "status": "delivered_extra_milk",
                    })
                elif delivery_status == 'unsuccessful':
                    # Extra milk delivery was unsuccessful
                    calendar_data.append({
                        "date": req.date.strftime("%Y-%m-%d"),
                        "status": "unsuccessful_extra_milk",
                    })
                else:
                    # Extra milk is approved but not yet delivered (pending delivery)
                    calendar_data.append({
                        "date": req.date.strftime("%Y-%m-%d"),
                        "status": "extra_milk",
                    })

        # Add pending customer requests (only extra milk since leaves are auto-approved)
        for req in pending_requests:
            if req.request_type != "leave":  # Skip pending leaves as they're auto-approved
                # Pending means vendor hasn't approved yet
                calendar_data.append({
                    "date": req.date.strftime("%Y-%m-%d"),
                    "status": "pending_extra_milk",
                })

        logger.info("END CustomerCalendarViewSet.list | calendar fetched for customer_id: %s", customer_id)
        return success_response("Calendar fetched successfully", calendar_data)

    @swagger_auto_schema(
        operation_summary="Mark Delivery Status",
        operation_description=(
            "Mark delivery status for a customer on a specific date with milkman ID.\n\n"
            "Possible status values:\n"
            "- delivered: Milk delivered successfully\n"
            "- not_delivered: Delivery missed or not completed\n"
            "- cancelled: Delivery was cancelled\n"
            "- missed: Delivery was missed\n\n"
            "Note: For leave requests, use the /apply-for-leave/ endpoint.\n"
            "For extra milk requests, use the /extra-milk-request/ endpoint.\n\n"
            "Example payloads:\n"
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["customer_id", "milkman_id", "date", "status"],
            properties={
                "customer_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "milkman_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "date": openapi.Schema(type=openapi.TYPE_STRING, description="YYYY-MM-DD"),
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    enum=["delivered", "not_delivered", "cancelled", "missed"],
                    description="Delivery status for the date"
                ),
            },
            example={
                "customer_id": 1,
                "milkman_id": 2,
                "date": "2025-08-10",
                "status": "delivered",
            }
        ),
        responses={200: openapi.Response("Delivery status updated", DeliveryCalendarSerializer())}
    )
    def create(self, request):
        logger.info("START CustomerCalendarViewSet.create | request data: %s", request.data)
        customer_id = request.data.get("customer_id")
        milkman_id = request.data.get("milkman_id")
        date_str = request.data.get("date")
        status_val = request.data.get("status")

        allowed_statuses = list(self.DELIVERY_ALLOWED_STATUSES)

        if not customer_id or not milkman_id or not date_str or not status_val:
            return error_response("customer_id, milkman_id, date, and status are required.")

        if status_val not in allowed_statuses:
            return error_response(f"Invalid status. Allowed values: {', '.join(allowed_statuses)}.")

        try:
            customer = Customer.objects.get(id=customer_id)
            milkman = Milkman.objects.get(id=milkman_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found.")
        except Milkman.DoesNotExist:
            return not_found_response("Milkman not found.")

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD.")

        # Update or create DeliveryRecord
        record, created = DeliveryRecord.objects.get_or_create(
            customer=customer, date=date_obj, delivery_type="regular",
            defaults={"status": status_val, "milkman": milkman, "vendor": customer.provider}
        )
        if not created:
            record.status = status_val
            record.milkman = milkman
            record.vendor = customer.provider
            record.save()

        serializer = DeliveryCalendarSerializer(record)
        logger.info("END CustomerCalendarViewSet.create | delivery status updated for customer_id: %s, date: %s", customer_id, date_str)
        return success_response("Delivery status updated", serializer.data)

    @swagger_auto_schema(
        operation_summary="Apply for Leave",
        operation_description="Customer requests leave for a specific day. Leave is automatically approved without vendor intervention.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["customer_id", "date"],
            properties={
                "customer_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "date": openapi.Schema(type=openapi.TYPE_STRING, description="YYYY-MM-DD"),

            },
            example={"customer_id": 1, "date": "2025-08-08"}
        ),
        responses={200: openapi.Response(
            "Leave recorded and approved",
            openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        )}
    )
    @action(detail=False, methods=["post"], url_path="apply-for-leave")
    def apply_for_leave(self, request):
        logger.info("START apply_for_leave | request data: %s", request.data)
        customer_id = request.data.get("customer_id")
        date_str = request.data.get("date")


        if not customer_id or not date_str:
            return error_response("customer_id and date are required.")

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found.")

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD.")

        # Check if customer has a vendor
        if not customer.provider:
            return error_response("Customer must be associated with a vendor to request leave.", status_code=status.HTTP_400_BAD_REQUEST)

        # Create CustomerRequest instead of DeliveryRecord
        # Auto-approve leave requests (customer decides their own leaves)
        request_obj, created = CustomerRequest.objects.get_or_create(
            customer=customer,
            date=date_obj,
            request_type="leave",
            defaults={"vendor": customer.provider, "status": "approved"}
        )
        if not created:
            # Update existing request - auto-approve it
            request_obj.status = "approved"
            request_obj.vendor = customer.provider
            request_obj.save()

        # Return simplified response for calendar compatibility; include id for verification
        response_data = {
            "id": getattr(request_obj, 'id', None),
            "date": request_obj.date.strftime("%Y-%m-%d"),
            "status": "leave",  # Changed from "pending_leave" to "leave" since it's approved
        }
        logger.info("END apply_for_leave | leave request approved for customer_id: %s, date: %s", customer_id, date_str)
        return success_response("Leave request recorded successfully", response_data)

    @swagger_auto_schema(
        operation_summary="Vendor/Milkman Unavailability",
        operation_description="Vendor or milkman notifies unavailability for a day. Creates a delivery record marked as 'not_delivered'.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["customer_id", "date"],
            properties={
                "customer_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "date": openapi.Schema(type=openapi.TYPE_STRING, description="YYYY-MM-DD"),

            },
            example={"customer_id": 1, "date": "2025-08-09"}
        ),
        responses={200: openapi.Response("Vendor/Milkman unavailable", DeliveryCalendarSerializer())}
    )
    @action(detail=False, methods=["post"], url_path="vendor-unavailable")
    def vendor_unavailable(self, request):
        logger.info("START vendor_unavailable | request data: %s", request.data)
        customer_id = request.data.get("customer_id")
        date_str = request.data.get("date")


        if not customer_id or not date_str:
            return error_response("customer_id and date are required.")

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found.")

        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD.")

        # Mark as not_delivered with vendor unavailability reason
        record, created = DeliveryRecord.objects.get_or_create(
            customer=customer, date=date_obj, delivery_type="regular",
            defaults={
                "status": "not_delivered",
                "vendor": customer.provider,
                "milkman": customer.milkman
            }
        )
        if not created:
            record.status = "not_delivered"
            record.vendor = customer.provider
            record.milkman = customer.milkman
            record.save()

        serializer = DeliveryCalendarSerializer(record)
        logger.info("END vendor_unavailable | unavailability recorded for customer_id: %s, date: %s", customer_id, date_str)
        return success_response("Vendor/Milkman unavailability recorded", serializer.data)

    @swagger_auto_schema(
        operation_summary="Request Extra Milk",
        operation_description="Customer requests extra milk for a specific day.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["customer_id", "date"],
            properties={
                "customer_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "date": openapi.Schema(type=openapi.TYPE_STRING, description="YYYY-MM-DD"),
                "cow_milk_extra": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Extra cow milk requested (liters, decimals allowed)", default=0),
                "buffalo_milk_extra": openapi.Schema(type=openapi.TYPE_NUMBER, format="decimal", description="Extra buffalo milk requested (liters, decimals allowed)", default=0),
            },
            example={"customer_id": 1, "date": "2025-08-15", "cow_milk_extra": 1.5, "buffalo_milk_extra": 0}
        ),
        responses={200: openapi.Response(
            "Extra milk request recorded",
            openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                    'date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
                    'status': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        )}
    )
    @action(detail=False, methods=["post"], url_path="extra-milk-request")
    def extra_milk_request(self, request):
        logger.info("START extra_milk_request | request data: %s", request.data)
        """
        Handles extra milk requests with improved validation, error handling, and clarity.
        """
        # Constants for status and request type
        STATUS_PENDING = "pending"
        REQUEST_TYPE_EXTRA_MILK = "extra_milk"

        def parse_decimal(value, field_name):
            try:
                if value in [None, "", "null"]:
                    return Decimal('0')
                val = Decimal(str(value))
                if val < 0:
                    raise ValueError
                return val
            except (InvalidOperation, ValueError, TypeError):
                raise ValidationError(f"{field_name} must be a non-negative number.")

        customer_id = request.data.get("customer_id")
        date_str = request.data.get("date")
        cow_milk_extra = request.data.get("cow_milk_extra")
        buffalo_milk_extra = request.data.get("buffalo_milk_extra")

        # Validate required fields
        if not customer_id or not date_str:
            return error_response("customer_id and date are required.")

        # Parse and validate milk quantities
        try:
            cow_milk_extra = parse_decimal(cow_milk_extra, "cow_milk_extra")
            buffalo_milk_extra = parse_decimal(buffalo_milk_extra, "buffalo_milk_extra")
        except ValidationError as ve:
            return error_response(str(ve))

        if cow_milk_extra == 0 and buffalo_milk_extra == 0:
            return error_response("At least one of cow_milk_extra or buffalo_milk_extra must be greater than zero.")

        # Validate customer existence
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found.")

        # Validate date
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return error_response("Invalid date format. Use YYYY-MM-DD.")

        # Check vendor association
        if not customer.provider:
            return error_response("Customer must be associated with a vendor to request extra milk.", status_code=status.HTTP_400_BAD_REQUEST)

        # Check for existing pending/approved request for the same date
        existing_request = CustomerRequest.objects.filter(
            customer=customer,
            date=date_obj,
            request_type=REQUEST_TYPE_EXTRA_MILK,
            status__in=[STATUS_PENDING, "approved"]
        ).first()
        if existing_request:
            return error_response("An extra milk request for this date already exists and is pending or approved.")
        
        # Delete any rejected requests for the same date to allow re-requesting
        # This is needed because of the unique_together constraint on (customer, date, request_type)
        CustomerRequest.objects.filter(
            customer=customer,
            date=date_obj,
            request_type=REQUEST_TYPE_EXTRA_MILK,
            status="rejected"
        ).delete()

        # Ensure customer has a milkman for assignment
        assigned_milkman = customer.milkman
        if not assigned_milkman:
            logger.warning(f"Customer {customer.id} does not have a milkman assigned for extra milk delivery.")
        
        # Create the extra milk request
        try:
            with transaction.atomic():
                request_obj = CustomerRequest(
                    customer=customer,
                    date=date_obj,
                    request_type=REQUEST_TYPE_EXTRA_MILK,
                    vendor=customer.provider,
                    cow_milk_extra=cow_milk_extra,
                    buffalo_milk_extra=buffalo_milk_extra,
                    status=STATUS_PENDING,
                    extra_milk_delivery_milkman=assigned_milkman
                )
                # Model validation
                try:
                    request_obj.full_clean()
                except ValidationError as ve:
                    logger.warning("Validation error for CustomerRequest: %s", ve)
                    return error_response(f"Invalid request data: {ve}", status_code=status.HTTP_400_BAD_REQUEST)
                request_obj.save()
                logger.info("Extra milk request saved (id=%s) for customer=%s date=%s", getattr(request_obj, 'id', None), customer.id, date_obj)
                # Notification to assigned milkman
                if assigned_milkman and hasattr(assigned_milkman, 'fcm_token') and assigned_milkman.fcm_token:
                    send_fcm_notification(
                        assigned_milkman.fcm_token,
                        "New Extra Milk Delivery Assigned",
                        f"You have been assigned to deliver extra milk for customer {customer.id} on {date_obj}."
                    )
        except Exception as e:
            logger.exception("Failed to create CustomerRequest for extra milk: %s", e)
            return error_response(f"Failed to submit extra milk request: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Use serializer for response
        response_data = CustomerRequestSerializer(request_obj).data
        response_data["status"] = "pending_extra_milk"  # For frontend compatibility
        logger.info("END extra_milk_request | extra milk request submitted for customer_id: %s, date: %s", customer_id, date_str)
        return success_response("Extra milk request submitted for approval", response_data)

    @swagger_auto_schema(
        operation_summary="Get Delivery Records by Date",
        operation_description="Get delivery records for a customer for one or more specific dates.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('dates', openapi.IN_QUERY, description="Comma-separated dates in YYYY-MM-DD format (e.g., 2025-09-10,2025-09-12)", type=openapi.TYPE_STRING, required=True)
        ],
        responses={200: openapi.Response("Delivery records", DeliveryCalendarSerializer(many=True))}
    )
    @action(detail=False, methods=['get'], url_path='delivery-records-by-date')
    def get_delivery_records_by_date(self, request):
        logger.info("START get_delivery_records_by_date | request params: %s", request.query_params)
        customer_id = request.query_params.get("customer_id")
        dates_param = request.query_params.get("dates")

        if not customer_id or not dates_param:
            return error_response("Both customer_id and dates are required.")

        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return not_found_response("Customer not found.")

        date_strs = dates_param.split(',')
        date_objs = []
        for date_str in date_strs:
            try:
                date_objs.append(datetime.strptime(date_str, "%Y-%m-%d").date())
            except ValueError:
                return error_response(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

        records = (
            DeliveryRecord.objects.filter(
                customer=customer, date__in=date_objs
            )
            .select_related("milkman")
        )

        serializer = DeliveryCalendarSerializer(records, many=True)
        logger.info("END get_delivery_records_by_date | delivery records fetched for customer_id: %s, dates: %s", customer_id, dates_param)
        return success_response("Delivery records fetched successfully", serializer.data)

    def construct_customer_address(self, customer):
        """Construct a readable address for customer"""
        return format_address(
            flat_no=getattr(customer, "flat_no", None),
            building=getattr(customer, "society_name", None),
            village=getattr(customer, "village", None),
            tal=getattr(customer, "tal", None),
            dist=getattr(customer, "dist", None),
            state=getattr(customer, "state", None),
            pincode=getattr(customer, "pincode", None),
        )

    def get_customer_address(self, customer):
        """Return constructed address using construct_customer_address if available else fallback to format_address.

        This method ensures the viewset won't break if construct_customer_address is missing or not defined on subclass.
        """
        if hasattr(self, 'construct_customer_address'):
            try:
                return self.construct_customer_address(customer)
            except Exception:
                # If construct_customer_address raises unexpectedly, fallback to a safe formatter
                pass
        # Fallback: directly use format_address util
        return format_address(
            flat_no=getattr(customer, "flat_no", None),
            building=getattr(customer, "society_name", None),
            village=getattr(customer, "village", None),
            tal=getattr(customer, "tal", None),
            dist=getattr(customer, "dist", None),
            state=getattr(customer, "state", None),
            pincode=getattr(customer, "pincode", None),
        )

class DistributorCalendarViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Mark Delivery Status",
        operation_description=(
            "Mark delivery status as either delivered or cancelled.\n\n"
            "Supports custom quantities:\n"
            "- cow_milk: Total cow milk quantity delivered (liters)\n"
            "- buffalo_milk: Total buffalo milk quantity delivered (liters)\n"
            "- reason: Reason for custom quantities (e.g., 'Customer requested less today')\n\n"
            "If quantities are provided, they represent the total amount delivered.\n"
            "If not provided, regular daily quantities from customer profile will be assumed."
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'customer_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Customer ID"),
                'date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, description="Delivery date"),
                'milkman_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Milkman ID who handled the delivery"),
                'status': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    enum=["delivered", "cancelled"],
                    description="Delivery status", 
                    default="delivered"
                ),
                'cow_milk': openapi.Schema(type=openapi.TYPE_NUMBER, description="Total cow milk quantity delivered (liters)"),
                'buffalo_milk': openapi.Schema(type=openapi.TYPE_NUMBER, description="Total buffalo milk quantity delivered (liters)"),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description="Reason for custom quantities"),
                'cancellation_reason': openapi.Schema(type=openapi.TYPE_STRING, description="Reason for cancellation (required when status is cancelled)"),
            },
            required=['customer_id', 'date', 'milkman_id']
        ),
        responses={200: "Delivery status updated successfully."}
    )
    @action(detail=False, methods=['post'], url_path='mark-delivery')
    def mark_delivery(self, request):
        try:
            customer_id = request.data.get('customer_id')
            date = request.data.get('date')
            milkman_id = request.data.get('milkman_id')
            delivery_status = request.data.get('status', 'delivered')  # Default to delivered

            # Only support delivered and cancelled statuses
            valid_statuses = ["delivered", "cancelled"]

            # Validate required parameters
            if not customer_id:
                return error_response("Customer ID is required.", status_code=status.HTTP_400_BAD_REQUEST)
            if not date:
                return error_response("Date is required.", status_code=status.HTTP_400_BAD_REQUEST)
            if not milkman_id:
                return error_response("Milkman ID is required.", status_code=status.HTTP_400_BAD_REQUEST)

            # Validate status
            if delivery_status not in valid_statuses:
                return error_response(f"Invalid status. Valid options: {', '.join(valid_statuses)}", status_code=status.HTTP_400_BAD_REQUEST)

            # Get customer and validate existence
            customer = Customer.objects.get(id=customer_id)

            # Get milkman and validate existence
            try:
                milkman = Milkman.objects.get(id=milkman_id)
            except Milkman.DoesNotExist:
                return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)

            # Map frontend status to model status (direct mapping)
            model_status = delivery_status

            # Prepare defaults for delivery record
            defaults = {
                "status": model_status,
                "milkman": milkman,
            }

            # Get custom quantities (total milk delivered)
            cow_milk = request.data.get('cow_milk')
            buffalo_milk = request.data.get('buffalo_milk')
            reason = request.data.get('reason')
            cancellation_reason = request.data.get('cancellation_reason')
            
            # Store cancellation reason if status is cancelled
            if delivery_status == 'cancelled' and cancellation_reason:
                defaults['cancellation_reason'] = cancellation_reason
            
            # Check if custom quantities are provided
            has_custom_quantities = (cow_milk is not None and cow_milk != "") or \
                                   (buffalo_milk is not None and buffalo_milk != "")
            
            # Parse and validate quantities
            if has_custom_quantities:
                try:
                    cow_qty = Decimal(str(cow_milk)) if cow_milk not in [None, ""] else Decimal('0')
                    buffalo_qty = Decimal(str(buffalo_milk)) if buffalo_milk not in [None, ""] else Decimal('0')
                    
                    if cow_qty < 0 or buffalo_qty < 0:
                        return error_response("Milk quantities cannot be negative.", status_code=status.HTTP_400_BAD_REQUEST)
                    
                    # Store quantities in cow_milk_extra and buffalo_milk_extra fields
                    # These represent the total delivered quantities
                    defaults['cow_milk_extra'] = cow_qty
                    defaults['buffalo_milk_extra'] = buffalo_qty
                    
                    # Log reason if provided
                    if reason:
                        logger.info(f"Custom delivery for customer {customer_id} on {date}: cow={cow_qty}L, buffalo={buffalo_qty}L, reason={reason}")
                    
                except (InvalidOperation, ValueError, TypeError):
                    return error_response("cow_milk and buffalo_milk must be valid numbers.", status_code=status.HTTP_400_BAD_REQUEST)

            # Add vendor if customer has a provider
            if customer.provider:
                defaults["vendor"] = customer.provider

            # Always use "regular" delivery type since we're not distinguishing between regular and extra
            delivery_type = "regular"
            
            delivery_record, created = DeliveryRecord.objects.update_or_create(
                customer=customer,
                date=date,
                delivery_type=delivery_type,
                defaults=defaults
            )

            # NOTE: Extra milk delivery status should ONLY be updated via the dedicated
            # mark_extra_milk_delivery endpoint, NOT here. This ensures:
            # 1. Regular deliveries only create 'regular' type delivery records
            # 2. Extra milk deliveries only create 'extra' type delivery records
            # 3. No accidental duplication of records

            # Update response message based on status
            if delivery_status == "delivered":
                if has_custom_quantities:
                    message = f"Delivery marked as successful with quantities: {cow_qty}L cow, {buffalo_qty}L buffalo."
                else:
                    message = "Delivery marked as successful."
            else:  # cancelled
                if cancellation_reason:
                    message = f"Delivery marked as cancelled. Reason: {cancellation_reason}"
                else:
                    message = "Delivery marked as cancelled."

            return success_response(message, DeliveryRecordSerializer(delivery_record).data)
        except Customer.DoesNotExist:
            return error_response("Customer not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="List Assigned Customers",
        operation_description="List all customers assigned to the specified milkman or the authenticated milkman.",
        manual_parameters=[
            openapi.Parameter('milkman_id', openapi.IN_QUERY, description="Milkman ID (optional)", type=openapi.TYPE_INTEGER)
        ],
        responses={200: "List of assigned customers."}
    )
    @action(detail=False, methods=['get'], url_path='list-customers')
    def list_customers(self, request):
        logger.info("Entering list_customers method with query params: %s", request.query_params)
        try:
            milkman_id = request.query_params.get('milkman_id')

            if milkman_id:
                milkman = Milkman.objects.get(id=milkman_id)
                logger.info("Fetching customers for milkman ID: %s (Name: %s)", milkman.id, milkman.name)
            else:
                # request.user is a Systemadmin user; map by id to Milkman record
                milkman = Milkman.objects.get(id=request.user.id)
                logger.info("Fetching customers for authenticated milkman ID: %s (Name: %s)", milkman.id, milkman.name)

            # Log milkman's assigned vendor
            if milkman.provider:
                logger.info("Milkman's assigned vendor: ID=%s, Name=%s", milkman.provider.id, milkman.provider.name)
            else:
                logger.warning("Milkman ID %s has no assigned vendor (provider field is None)", milkman.id)

            assigned_customers = Customer.objects.filter(milkman=milkman).select_related("provider", "milkman")
            logger.info("Found %d assigned customers for milkman %s", assigned_customers.count(), milkman.id)
            
            # Calculate total daily milk requirements
            total_cow_milk = 0
            total_buffalo_milk = 0
            
            # Prepare detailed response with customer and milkman IDs
            customers_data = []
            for customer in assigned_customers:
                # Log each customer's vendor assignment for debugging
                customer_vendor_id = customer.provider.id if customer.provider else None
                customer_vendor_name = customer.provider.name if customer.provider else None
                logger.info(
                    "Customer ID=%s (Name=%s) -> Vendor ID=%s (Name=%s)",
                    customer.id,
                    customer.name,
                    customer_vendor_id,
                    customer_vendor_name
                )
                
                # Calculate milk requirements for this customer
                cow_milk = float(customer.cow_milk_litre) if customer.cow_milk_litre else 0
                buffalo_milk = float(customer.buffalo_milk_litre) if customer.buffalo_milk_litre else 0
                
                total_cow_milk += cow_milk
                total_buffalo_milk += buffalo_milk
                
                customers_data.append({
                    "customer_id": customer.id,
                    "customer_name": safe_str(customer.name),
                    "customer_contact": safe_str(customer.contact),
                    "customer_address": self.get_customer_address(customer),
                    "cow_milk_litre": cow_milk,
                    "buffalo_milk_litre": buffalo_milk,
                    "provider": {
                        "provider_id": customer.provider.id if customer.provider else None,
                        "provider_name": safe_str(customer.provider.name) if customer.provider and customer.provider.name else "",
                    },
                    "milkman": {
                        "milkman_id": milkman.id if milkman else None,
                        "milkman_name": safe_str(milkman.name) if milkman else "",
                        "milkman_contact": safe_str(milkman.phone_number) if milkman else "",
                    }
                })

            logger.info("Successfully prepared response with %d customers for milkman %s", len(customers_data), milkman.id)
            
            # Add daily milk requirement summary
            response_data = {
                "customers": customers_data,
                "daily_milk_requirement": {
                    "cow_milk_litres": total_cow_milk,
                    "buffalo_milk_litres": total_buffalo_milk,
                    "total_litres": total_cow_milk + total_buffalo_milk
                }
            }
            
            return success_response("List of assigned customers.", response_data)

        except Milkman.DoesNotExist:
            logger.error("Milkman not found for ID %s or user %s", milkman_id, request.user.id if hasattr(request, 'user') else 'unknown')
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("An error occurred in list_customers: %s", str(e), exc_info=True)
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Get Milkman Delivery Calendar",
        operation_description="Get delivery calendar for a milkman showing status for each day in a given month.",
        manual_parameters=[
            openapi.Parameter('milkman_id', openapi.IN_QUERY, description="Milkman ID (optional for milkman users)", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter('month', openapi.IN_QUERY, description="Month in YYYY-MM format", type=openapi.TYPE_STRING, required=True)
        ],
        responses={200: openapi.Response(description="Milkman calendar data")}
    )
    @action(detail=False, methods=['get'], url_path='milkman-calendar')
    def milkman_calendar(self, request):
        """
        Returns delivery calendar for milkman with statuses: leave, delivered, pending, cancelled.
        For each date, shows how many customers were delivered to, pending, or cancelled.
        """
        from calendar import monthrange
        from datetime import timedelta
        
        milkman_id = request.query_params.get('milkman_id')
        month_param = request.query_params.get('month')
        
        if not month_param:
            return error_response("month is required.")
        
        try:
            year, month = map(int, month_param.split("-"))
        except ValueError:
            return error_response("Invalid month format. Use YYYY-MM.")
        
        try:
            if milkman_id:
                milkman = Milkman.objects.get(id=milkman_id)
            else:
                milkman = Milkman.objects.get(id=request.user.id)
        except Milkman.DoesNotExist:
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)
        
        # Get date range for the month
        _, days_in_month = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, days_in_month)
        
        # Get all customers assigned to this milkman
        assigned_customers = Customer.objects.filter(milkman=milkman)
        total_customers = assigned_customers.count()
        customer_ids = list(assigned_customers.values_list('id', flat=True))
        
        if total_customers == 0:
            return success_response("No customers assigned to this milkman.", [])
        
        # Get approved leave requests for this milkman in the month
        leave_dates = set(
            MilkmanLeaveRequest.objects.filter(
                milkman=milkman,
                start_date__gte=start_date,
                start_date__lte=end_date,
                status='approved'
            ).values_list('start_date', flat=True)
        )
        
        # Get all delivery records for assigned customers in the month
        delivery_records = DeliveryRecord.objects.filter(
            customer_id__in=customer_ids,
            date__gte=start_date,
            date__lte=end_date,
            delivery_type='regular'
        ).select_related('customer')
        
        # Build a dict: {date: {customer_id: status}}
        delivery_by_date = {}
        for record in delivery_records:
            if record.date not in delivery_by_date:
                delivery_by_date[record.date] = {}
            delivery_by_date[record.date][record.customer_id] = {
                'status': record.status,
                'name': record.customer.name or f"Customer-{record.customer_id}"
            }
        
        # Build customer name lookup
        customer_names = {c.id: c.name or f"Customer-{c.id}" for c in assigned_customers}
        
        # Build calendar data for each day
        calendar_data = []
        current_date = start_date
        today = date.today()
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            # If milkman is on leave, show leave status and skip other records
            if current_date in leave_dates:
                calendar_data.append({
                    "date": date_str,
                    "status": "leave"
                })
            else:
                # Get delivery info for this date
                date_deliveries = delivery_by_date.get(current_date, {})
                
                delivered_count = 0
                cancelled_count = 0
                cancelled_names = []
                pending_count = 0
                pending_names = []
                
                for customer_id in customer_ids:
                    if customer_id in date_deliveries:
                        status = date_deliveries[customer_id]['status']
                        name = date_deliveries[customer_id]['name']
                        if status == 'delivered':
                            delivered_count += 1
                        elif status == 'cancelled':
                            cancelled_count += 1
                            cancelled_names.append(name)
                        else:
                            # not_delivered, missed, etc. treated as pending
                            pending_count += 1
                            pending_names.append(name)
                    else:
                        # No delivery record = pending (for today and past dates only)
                        if current_date <= today:
                            pending_count += 1
                            pending_names.append(customer_names.get(customer_id, f"Customer-{customer_id}"))
                
                # Add delivered entry if any deliveries made
                if delivered_count > 0:
                    calendar_data.append({
                        "date": date_str,
                        "status": "delivered",
                        "customers": delivered_count
                    })
                
                # Add cancelled entry if any cancellations
                if cancelled_count > 0:
                    calendar_data.append({
                        "date": date_str,
                        "status": "cancelled",
                        "customers": cancelled_count,
                        "name": ", ".join(cancelled_names)
                    })
                
                # Add pending entry if any pending (for today and past dates)
                if pending_count > 0 and current_date <= today:
                    calendar_data.append({
                        "date": date_str,
                        "status": "pending",
                        "customers": pending_count,
                        "name": ", ".join(pending_names)
                    })
                
                # For future dates with no activity, show all as pending
                if current_date > today and delivered_count == 0 and cancelled_count == 0:
                    calendar_data.append({
                        "date": date_str,
                        "status": "pending",
                        "customers": total_customers
                    })
            
            current_date += timedelta(days=1)
        
        return success_response("Milkman calendar fetched successfully.", calendar_data)

    @swagger_auto_schema(
        operation_summary="Get approved extra milk for today for a customer",
        operation_description="Returns approved extra milk quantities (cow and buffalo) for today for the given customer_id if any.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response(description="Extra milk details for today")}
    )
    @action(detail=False, methods=['get'], url_path='customer-extra-today')
    def customer_extra_today(self, request):
        customer_id = request.query_params.get('customer_id')
        if not customer_id:
            return error_response("customer_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return error_response("Customer not found.", status_code=status.HTTP_404_NOT_FOUND)

        today = date.today()
        extra_request = CustomerRequest.objects.filter(
            customer=customer,
            date=today,
            request_type='extra_milk',
            status='approved'
        ).first()

        if not extra_request:
            return success_response("No approved extra milk request for today.", {
                'cow_milk_extra': 0,
                'buffalo_milk_extra': 0,
                'approved': False
            })

        return success_response("Approved extra milk for today.", {
            'cow_milk_extra': float(extra_request.cow_milk_extra or 0),
            'buffalo_milk_extra': float(extra_request.buffalo_milk_extra or 0),
            'approved': True,
            'request_id': extra_request.id,
            'date': extra_request.date
        })

    @swagger_auto_schema(
        operation_summary="Get total milk to deliver for today for a customer",
        operation_description="Calculates base milk + any approved extra milk for today for the given customer_id.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response(description="Total milk to deliver for today")}
    )
    @action(detail=False, methods=['get'], url_path='customer-total-today')
    def customer_total_today(self, request):
        customer_id = request.query_params.get('customer_id')
        if not customer_id:
            return error_response("customer_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            return error_response("Customer not found.", status_code=status.HTTP_404_NOT_FOUND)

        # Base quantities from customer profile
        cow_milk = float(customer.cow_milk_litre) if getattr(customer, 'cow_milk_litre', None) else 0
        buffalo_milk = float(customer.buffalo_milk_litre) if getattr(customer, 'buffalo_milk_litre', None) else 0

        # Approved extra for today from CustomerRequest
        today = date.today()
        extra_request = CustomerRequest.objects.filter(
            customer=customer,
            date=today,
            request_type='extra_milk',
            status='approved'
        ).first()
        extra_cow = float(extra_request.cow_milk_extra or 0) if extra_request else 0
        extra_buffalo = float(extra_request.buffalo_milk_extra or 0) if extra_request else 0

        total_cow = cow_milk + extra_cow
        total_buffalo = buffalo_milk + extra_buffalo

        return success_response("Total milk to deliver for today.", {
            'customer_id': customer.id,
            'date': today,
            'cow_milk_base': cow_milk,
            'buffalo_milk_base': buffalo_milk,
            'cow_milk_extra': extra_cow,
            'buffalo_milk_extra': extra_buffalo,
            'total_cow_milk': total_cow,
            'total_buffalo_milk': total_buffalo,
            'total_litres': total_cow + total_buffalo
        })


    @swagger_auto_schema(
        operation_summary="Request Leave",
        operation_description="Submit a leave request to the vendor for a single day.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'milkman_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Milkman ID (optional for milkman users)"),
                'date': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE, description="Leave date (YYYY-MM-DD)"),
                'reason': openapi.Schema(type=openapi.TYPE_STRING, description="Optional reason for leave request")
            },
            required=['date']
        ),
        responses={200: "Leave request submitted successfully."}
    )
    @action(detail=False, methods=['post'], url_path='request-leave')
    def request_leave(self, request):
        try:
            milkman_id = request.data.get('milkman_id')
            # Accept both 'date' and 'startDate' for flexibility
            date_str = request.data.get('date') or request.data.get('startDate')
            reason = request.data.get('reason')  # Optional

            if not date_str:
                return error_response("date or startDate is required.")

            if milkman_id:
                milkman = Milkman.objects.get(id=milkman_id)
            else:
                # Map authenticated user to Milkman by id
                milkman = Milkman.objects.get(id=request.user.id)

            vendor = milkman.provider  # Fetch the vendor linked to the milkman

            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                return error_response("Invalid date format. Use YYYY-MM-DD.")

            # Validation: Ensure only one leave can be taken for a specific date
            existing_qs = MilkmanLeaveRequest.objects.filter(milkman=milkman, start_date=date_obj)
            if existing_qs.exists():
                existing = existing_qs.first()
                # If the existing request is still pending, allow updating the reason
                if existing.status == 'pending':
                    if reason:
                        existing.reason = reason
                        existing.save()
                    response_data = LeaveRequestSerializer(existing).data
                    response_data["milkman_id"] = milkman.id
                    return success_response("Leave request already exists; returned existing pending request (updated reason if provided).", response_data)
                else:
                    return error_response("A leave request already exists for this date.", status_code=status.HTTP_400_BAD_REQUEST)

            leave_request = MilkmanLeaveRequest.objects.create(
                milkman=milkman,
                vendor=vendor,  # Associate the leave request with the vendor
                start_date=date_obj,
                end_date=date_obj,  # Same day for single date leave
                reason=reason
            )

            response_data = LeaveRequestSerializer(leave_request).data
            response_data["milkman_id"] = milkman.id
            return success_response("Leave request submitted successfully.", response_data)
        except Milkman.DoesNotExist:
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Get Milkman Leave Calendar",
        operation_description="Get all leave requests made by the milkman for a given month.",
        manual_parameters=[
            openapi.Parameter('milkman_id', openapi.IN_QUERY, description="Milkman ID (optional for milkman users)", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter('month', openapi.IN_QUERY, description="Month in YYYY-MM format", type=openapi.TYPE_STRING, required=True)
        ],
        responses={
            200: openapi.Response(
                description="List of leave requests for the month.",
                schema=MilkmanLeaveRequestSerializer(many=True)
            )
        }
    )
    @action(detail=False, methods=['get'], url_path='check-leave-allocation')
    def check_leave_allocation(self, request):
        try:
            milkman_id = request.query_params.get('milkman_id')
            month_param = request.query_params.get('month')

            if not month_param:
                return error_response("month is required.")

            try:
                year, month = map(int, month_param.split("-"))
            except ValueError:
                return error_response("Invalid month format. Use YYYY-MM.")

            if milkman_id:
                milkman = Milkman.objects.get(id=milkman_id)
            else:
                # Map authenticated user to Milkman by id
                milkman = Milkman.objects.get(id=request.user.id)

            # Filter leave requests for the specified month - show approved and pending requests
            leave_requests = MilkmanLeaveRequest.objects.filter(
                milkman=milkman,
                start_date__year=year,
                start_date__month=month,
                status__in=['approved', 'pending']  # Include both approved and pending
            ).order_by('start_date')

            # Prepare simplified response data with appropriate status
            # approved -> "leave", pending -> "pending"
            simplified_data = [
                {
                    "date": lr.start_date, 
                    "status": "leave" if lr.status == "approved" else "pending"
                }
                for lr in leave_requests
            ]

            serializer = MilkmanLeaveRequestSerializer(simplified_data, many=True)
            return success_response("Leave requests for the month retrieved.", serializer.data)
        except Milkman.DoesNotExist:
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="List Milkman Leave Requests",
        operation_description="List all leave requests made by the milkman to the vendor.",
        responses={200: "List of leave requests."}
    )
    @action(detail=False, methods=['get'], url_path='list-leave-requests')
    def list_leave_requests(self, request):
        try:
            # Map authenticated user to Milkman by id
            milkman = Milkman.objects.get(id=request.user.id)
            leave_requests = MilkmanLeaveRequest.objects.filter(milkman=milkman)
            return success_response("List of leave requests.", LeaveRequestSerializer(leave_requests, many=True).data)
        except Milkman.DoesNotExist:
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("An error occurred in list_leave_requests: %s", str(e), exc_info=True)
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def notify_customer_about_milkman_change(self, customer, new_milkman):
        """Notify a customer that their assigned milkman has changed.

        This helper composes a human-readable message and sends a notification
        via the project's notification channel (placeholder implementation).

        Args:
            customer: Customer model instance to notify.
            new_milkman: Milkman model instance assigned to the customer.

        Note: Current implementation is a placeholder that prints the message.
        Replace with SMS/email/FCM integration as required.
        """
        message = (
            f"Dear {customer.name}, your milkman has been changed. "
            f"Your new milkman is {new_milkman.name} (Contact: {new_milkman.phone_number})."
        )
        # Replace the following line with actual notification logic
        print(f"Notification sent to {customer.name}: {message}")

    @swagger_auto_schema(
        operation_summary="List All Customers Assigned to Distributor",
        operation_description="List all customers assigned to the distributor's vendor.",
        responses={200: "List of customers assigned to the distributor."}
    )
    @action(detail=False, methods=['get'], url_path='list-customers-distributor')
    def list_customers_distributor(self, request):
        try:
            # Fetch the distributor's vendor
            distributor = request.user
            vendor = VendorBusinessRegistration.objects.get(distributor=distributor)

            # Retrieve all milkmen under the vendor
            milkmen = Milkman.objects.filter(provider=vendor)

            # Retrieve all customers assigned to these milkmen
            customers = Customer.objects.filter(milkman__in=milkmen).select_related("provider", "milkman")

            # Prepare the response data
            data = []
            for customer in customers:
                customer_data = {
                    "customer_id": customer.id,
                    "customer_name": safe_str(customer.name),
                    "customer_contact": safe_str(customer.contact),
                    "customer_address": self.get_customer_address(customer),
                    "cow_milk_litre": float(customer.cow_milk_litre) if customer.cow_milk_litre else 0,
                    "buffalo_milk_litre": float(customer.buffalo_milk_litre) if customer.buffalo_milk_litre else 0,
                    "provider": {
                        "provider_id": customer.provider.id if customer.provider else None,
                        "provider_name": safe_str(customer.provider.name) if customer.provider and customer.provider.name else "",
                    },
                    "milkman": {
                        "milkman_id": customer.milkman.id if customer.milkman else None,
                        "milkman_name": safe_str(customer.milkman.name) if customer.milkman else "",
                        "milkman_contact": safe_str(customer.milkman.phone_number) if customer.milkman else "",
                    }
                }
                data.append(customer_data)

            return success_response("List of customers assigned to the distributor.", data)
        except VendorBusinessRegistration.DoesNotExist:
            return error_response("Vendor not found for the distributor.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def construct_customer_address(self, customer):
        """Construct a readable address for customer"""
        return format_address(
            flat_no=getattr(customer, "flat_no", None),
            building=getattr(customer, "society_name", None),
            village=getattr(customer, "village", None),
            tal=getattr(customer, "tal", None),
            dist=getattr(customer, "dist", None),
            state=getattr(customer, "state", None),
            pincode=getattr(customer, "pincode", None),
        )

    def get_customer_address(self, customer):
        """Return constructed address using construct_customer_address if available else fallback to format_address.

        This method ensures the viewset won't break if construct_customer_address is missing or not defined on subclass.
        """
        if hasattr(self, 'construct_customer_address'):
            try:
                return self.construct_customer_address(customer)
            except Exception:
                # If construct_customer_address raises unexpectedly, fallback to a safe formatter
                pass
        # Fallback: directly use format_address util
        return format_address(
            flat_no=getattr(customer, "flat_no", None),
            building=getattr(customer, "society_name", None),
            village=getattr(customer, "village", None),
            tal=getattr(customer, "tal", None),
            dist=getattr(customer, "dist", None),
            state=getattr(customer, "state", None),
            pincode=getattr(customer, "pincode", None),
        )

    @swagger_auto_schema(
        operation_summary="List Milkman Leave Requests for Vendor",
        operation_description="List pending leave requests from milkmen that need vendor approval, for today and future dates.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response("List of pending milkman leave requests", LeaveRequestSerializer(many=True))}
    )
    @action(detail=False, methods=['get'], url_path='list-milkman-leave-requests')
    def list_milkman_leave_requests(self, request):
        vendor_id = request.query_params.get('vendor_id')
        if not vendor_id:
            return error_response("vendor_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            vendor = VendorBusinessRegistration.objects.get(id=vendor_id)
        except VendorBusinessRegistration.DoesNotExist:
            return error_response("Vendor not found.", status_code=status.HTTP_404_NOT_FOUND)

        today = date.today()
        # Query only pending requests for vendor to act on
        leave_requests = MilkmanLeaveRequest.objects.filter(
            vendor=vendor, start_date__gte=today, status='pending'
        ).select_related('milkman', 'vendor').order_by('start_date')

        # Build response with milkman and vendor names
        data = []
        for leave in leave_requests:
            data.append({
                "id": leave.id,
                "milkman_id": leave.milkman.id,
                "milkman_name": leave.milkman.name if hasattr(leave.milkman, "name") else "",
                "vendor_id": leave.vendor.id,
                "vendor_name": leave.vendor.name if hasattr(leave.vendor, "name") else "",
                "start_date": leave.start_date,
                "end_date": leave.end_date,
                "reason": leave.reason,
                "status": leave.status,
                "created_at": leave.created_at,
            })

        return success_response("List of pending milkman leave requests.", data)

    @swagger_auto_schema(
        operation_summary="List Customer Extra Milk Requests for Vendor",
        operation_description="List pending extra milk requests from customers that need vendor approval. Leave requests are automatically approved and not shown here.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response(
            "Pending customer extra milk requests",
            openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'extra_milk_requests': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Schema(type=openapi.TYPE_OBJECT)),
                }
            )
        )}
    )
    @action(detail=False, methods=['get'], url_path='list-customer-requests')
    def list_customer_requests(self, request):
        vendor_id = request.query_params.get('vendor_id')
        if not vendor_id:
            return error_response("vendor_id is required.", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            vendor = VendorBusinessRegistration.objects.get(id=vendor_id)
        except VendorBusinessRegistration.DoesNotExist:
            return error_response("Vendor not found.", status_code=status.HTTP_404_NOT_FOUND)

        today = date.today()
        # Leave requests are auto-approved, so we only fetch extra milk requests
        extra_milk_requests = CustomerRequest.objects.filter(
            vendor=vendor,
            request_type='extra_milk',
            status='pending',
            date__gte=today
        ).select_related('customer').order_by('date')

        # Serialize extra milk requests with customer details
        extra_milk_data = []
        for req in extra_milk_requests:
            extra_milk_data.append({
                "id": req.id,
                "customer": CustomerSerializer(req.customer).data,
                "date": req.date,
                "request_type": req.request_type,
                "cow_milk_extra": req.cow_milk_extra,
                "buffalo_milk_extra": req.buffalo_milk_extra,
                "status": req.status,
                "created_at": req.created_at,
            })

        response = {
            'extra_milk_requests': extra_milk_data,
        }
        return success_response("Customer extra milk requests fetched successfully.", response)

    @swagger_auto_schema(
        operation_summary="Accept/Reject Milkman Leave Request",
        operation_description="Vendor can approve or reject a milkman's leave request with optional rejection reason.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'leave_request_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Leave Request ID"),
                'action': openapi.Schema(type=openapi.TYPE_STRING, enum=['approve', 'reject'], description="Action to take"),
                'rejection_reason': openapi.Schema(type=openapi.TYPE_STRING, description="Reason for rejection (required if action is reject)"),
            },
            required=['leave_request_id', 'action']
        ),
        responses={200: openapi.Response("Leave request updated", LeaveRequestSerializer())}
    )
    @action(detail=False, methods=['post'], url_path='manage-milkman-leave')
    def manage_milkman_leave(self, request):
        leave_request_id = request.data.get('leave_request_id')
        action = request.data.get('action')
        rejection_reason = request.data.get('rejection_reason')

        if not leave_request_id or not action:
            return error_response("leave_request_id and action are required.", status_code=status.HTTP_400_BAD_REQUEST)

        if action not in ['approve', 'reject']:
            return error_response("action must be 'approve' or 'reject'.", status_code=status.HTTP_400_BAD_REQUEST)

        if action == 'reject' and not rejection_reason:
            return error_response("rejection_reason is required when rejecting a request.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            leave_request = MilkmanLeaveRequest.objects.select_related('milkman').get(id=leave_request_id)
        except MilkmanLeaveRequest.DoesNotExist:
            return error_response("Leave request not found.", status_code=status.HTTP_404_NOT_FOUND)

        milkman = leave_request.milkman

        # Update status and send notifications
        if action == 'approve':
            leave_request.status = 'approved'
            leave_request.approved_rejected_at = timezone.now()
            leave_request.rejection_reason = None  # Clear any previous rejection reason
            
            # Notify milkman: leave approved
            if milkman and getattr(milkman, 'fcm_token', None):
                send_fcm_notification(
                    milkman.fcm_token,
                    "Leave Request Approved",
                    f"Your leave request from {leave_request.start_date} to {leave_request.end_date} has been approved."
                )
            
            # Notify all assigned customers: milkman on leave
            assigned_customers = Customer.objects.filter(milkman=milkman)
            for customer in assigned_customers:
                if getattr(customer, 'fcm_token', None):
                    send_fcm_notification(
                        customer.fcm_token,
                        "Milkman Leave Approved",
                        f"Your milkman will be on leave from {leave_request.start_date} to {leave_request.end_date}. Delivery may be affected."
                    )
        else:
            leave_request.status = 'rejected'
            leave_request.approved_rejected_at = timezone.now()
            leave_request.rejection_reason = rejection_reason
            
            # Notify milkman: leave rejected
            if milkman and getattr(milkman, 'fcm_token', None):
                send_fcm_notification(
                    milkman.fcm_token,
                    "Leave Request Rejected",
                    f"Your leave request from {leave_request.start_date} to {leave_request.end_date} was rejected. Reason: {rejection_reason}"
                )

        leave_request.save()

        return success_response(
            f"Leave request {action}d successfully.", 
            LeaveRequestSerializer(leave_request).data
        )

    @swagger_auto_schema(
        operation_summary="Accept/Reject Customer Extra Milk Request",
        operation_description="Vendor can approve or reject a customer's extra milk request with optional rejection reason. Leave requests are automatically approved and cannot be managed through this endpoint.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'customer_request_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Customer Request ID"),
                'action': openapi.Schema(type=openapi.TYPE_STRING, enum=['approve', 'reject'], description="Action to take"),
                'rejection_reason': openapi.Schema(type=openapi.TYPE_STRING, description="Reason for rejection (required if action is reject)"),
            },
            required=['customer_request_id', 'action']
        ),
        responses={200: openapi.Response("Customer request updated", CustomerRequestSerializer())}
    )
    @action(detail=False, methods=['post'], url_path='manage-customer-request')
    def manage_customer_request(self, request):
        customer_request_id = request.data.get('customer_request_id')
        action = request.data.get('action')
        rejection_reason = request.data.get('rejection_reason')

        if not customer_request_id or not action:
            return error_response("customer_request_id and action are required.", status_code=status.HTTP_400_BAD_REQUEST)

        if action not in ['approve', 'reject']:
            return error_response("action must be 'approve' or 'reject'.", status_code=status.HTTP_400_BAD_REQUEST)

        if action == 'reject' and not rejection_reason:
            return error_response("rejection_reason is required when rejecting a request.", status_code=status.HTTP_400_BAD_REQUEST)

        try:
            customer_request = CustomerRequest.objects.select_related('customer', 'vendor').get(id=customer_request_id)
        except CustomerRequest.DoesNotExist:
            return error_response("Customer request not found.", status_code=status.HTTP_404_NOT_FOUND)

        # Leave requests are auto-approved and cannot be managed by vendor
        if customer_request.request_type == 'leave':
            return error_response(
                "Leave requests are automatically approved by the system and cannot be managed manually. "
                "Customers have full control over their leave requests.",
                status_code=status.HTTP_400_BAD_REQUEST
            )

        # Only allow approval/rejection for pending requests
        if customer_request.status != 'pending':
            return error_response(f"This request is already {customer_request.status}.", status_code=status.HTTP_400_BAD_REQUEST)

        customer = customer_request.customer
        milkman = getattr(customer, 'milkman', None)


        # Update status based on action and send notifications
        if action == 'approve':
            customer_request.status = 'approved'
            customer_request.approved_rejected_at = timezone.now()
            customer_request.rejection_reason = None  # Clear any previous rejection reason
            
            # DO NOT create DeliveryRecord here for extra milk
            # DeliveryRecords should only be created when the milkman marks delivery as delivered
            # For extra milk, the CustomerRequest.extra_milk_delivery_status tracks the actual delivery
            # Billing will only include DeliveryRecords with status='delivered'
            
            # Only create DeliveryRecord for leave requests (not extra milk)
            if customer_request.request_type == 'leave':
                DeliveryRecord.objects.update_or_create(
                    customer=customer_request.customer,
                    date=customer_request.date,
                    delivery_type="regular",
                    defaults={
                        'vendor': customer_request.vendor,
                        'milkman': milkman,
                        'status': 'leave',
                        'cow_milk_extra': 0,
                        'buffalo_milk_extra': 0,
                    }
                )
            
            # FCM notifications for approval
            if customer_request.request_type == 'extra_milk':
                # Build message for extra milk
                extras = []
                if customer_request.cow_milk_extra:
                    extras.append(f"{customer_request.cow_milk_extra}L cow milk")
                if customer_request.buffalo_milk_extra:
                    extras.append(f"{customer_request.buffalo_milk_extra}L buffalo milk")
                extras_str = ' and '.join(extras)
                # Notify customer about approval
                if getattr(customer, 'fcm_token', None):
                    send_fcm_notification(
                        customer.fcm_token,
                        "Extra Milk Request Approved",
                        f"Your extra milk request for {customer_request.date} ({extras_str}) has been approved. Delivery will be made."
                    )
                # Notify milkman about delivery
                if milkman and getattr(milkman, 'fcm_token', None):
                    customer_name = getattr(customer, 'name', None) or f"Customer #{customer.id}"
                    send_fcm_notification(
                        milkman.fcm_token,
                        "Deliver Extra Milk",
                        f"Deliver extra {extras_str} to {customer_name} on {customer_request.date}."
                    )
            elif customer_request.request_type == 'leave':
                # Notify customer about leave approval
                if getattr(customer, 'fcm_token', None):
                    send_fcm_notification(
                        customer.fcm_token,
                        "Leave Request Approved",
                        f"Your leave request for {customer_request.date} has been approved. No delivery will be made."
                    )
                # Notify milkman about customer's leave
                if milkman and getattr(milkman, 'fcm_token', None):
                    customer_name = getattr(customer, 'name', None) or f"Customer #{customer.id}"
                    send_fcm_notification(
                        milkman.fcm_token,
                        "Customer Leave Approved",
                        f"{customer_name} is on leave for {customer_request.date}. No delivery required."
                    )
        else:
            # Reject the request
            customer_request.status = 'rejected'
            customer_request.approved_rejected_at = timezone.now()
            customer_request.rejection_reason = rejection_reason
            
            # FCM notifications for rejection
            if customer_request.request_type == 'extra_milk':
                extras = []
                if customer_request.cow_milk_extra:
                    extras.append(f"{customer_request.cow_milk_extra}L cow milk")
                if customer_request.buffalo_milk_extra:
                    extras.append(f"{customer_request.buffalo_milk_extra}L buffalo milk")
                extras_str = ' and '.join(extras)
                if getattr(customer, 'fcm_token', None):
                    send_fcm_notification(
                        customer.fcm_token,
                        "Extra Milk Request Rejected",
                        f"Your extra milk request for {customer_request.date} ({extras_str}) was rejected. Reason: {rejection_reason}"
                    )
            elif customer_request.request_type == 'leave':
                if getattr(customer, 'fcm_token', None):
                    send_fcm_notification(
                        customer.fcm_token,
                        "Leave Request Rejected",
                        f"Your leave request for {customer_request.date} was rejected. Reason: {rejection_reason}"
                    )

        customer_request.save()

        return success_response(
            f"Customer request {action}d successfully.", 
            CustomerRequestSerializer(customer_request).data
        )


def get_delivery_quantity_for_date(customer, delivery_date):
    """
    Get the appropriate milk quantity for a customer on a specific date.
    Checks for approved delivery adjustments first, falls back to regular quantities.
    
    Returns:
        dict: {
            'cow_milk': Decimal,
            'buffalo_milk': Decimal,
            'is_adjusted': bool,
            'adjustment_type': str,  # 'leave', 'extra', 'reduced', or 'regular'
            'adjustment_id': int or None,
            'reason': str or None
        }
    """
    # Check for approved quantity adjustment
    adjustment = CustomerRequest.objects.filter(
        customer=customer,
        date=delivery_date,
        request_type="quantity_adjustment",
        status="approved"
    ).first()
    
    if adjustment:
        adjustment_type = None
        if adjustment.is_leave:
            adjustment_type = 'leave'
        elif adjustment.is_extra_milk:
            adjustment_type = 'extra'
        elif adjustment.is_reduced_quantity:
            adjustment_type = 'reduced'
        else:
            adjustment_type = 'adjusted'
        
        return {
            'cow_milk': adjustment.requested_cow_milk or 0,
            'buffalo_milk': adjustment.requested_buffalo_milk or 0,
            'is_adjusted': True,
            'adjustment_type': adjustment_type,
            'adjustment_id': adjustment.id,
            'reason': adjustment.reason
        }
    
    # Check for approved leave request (old style)
    leave_request = CustomerRequest.objects.filter(
        customer=customer,
        date=delivery_date,
        request_type="leave",
        status="approved"
    ).first()
    
    if leave_request:
        return {
            'cow_milk': 0,
            'buffalo_milk': 0,
            'is_adjusted': True,
            'adjustment_type': 'leave',
            'adjustment_id': leave_request.id,
            'reason': leave_request.reason
        }
    
    # Return regular quantities
    return {
        'cow_milk': customer.cow_milk_litre or 0,
        'buffalo_milk': customer.buffalo_milk_litre or 0,
        'is_adjusted': False,
        'adjustment_type': 'regular',
        'adjustment_id': None,
        'reason': None
    }


class DeliveryAdjustmentViewSet(viewsets.ViewSet):
    """
    ViewSet for unified delivery adjustment requests.
    Handles all delivery quantity changes: leave (0), reduced, extra, or any custom quantity.
    """
    
    @swagger_auto_schema(
        operation_summary="Create Delivery Adjustment Request",
        operation_description=(
            "Unified endpoint for all delivery adjustments:\n"
            "- Leave/Skip: Set both quantities to 0\n"
            "- Extra Milk: Set quantities higher than regular\n"
            "- Reduced Quantity: Set quantities lower than regular\n"
            "\n"
            "Examples:\n"
            "- Regular: 5L cow milk → Skip delivery: requested_cow_milk=0\n"
            "- Regular: 5L cow milk → Need 2L only: requested_cow_milk=2\n"
            "- Regular: 5L cow milk → Need 7L: requested_cow_milk=7\n"
        ),
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['customer_id', 'date'],
            properties={
                'customer_id': openapi.Schema(
                    type=openapi.TYPE_INTEGER, 
                    description='Customer ID'
                ),
                'date': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    format='date', 
                    description='Date for adjustment (YYYY-MM-DD)'
                ),
                'requested_cow_milk': openapi.Schema(
                    type=openapi.TYPE_NUMBER, 
                    description='Requested cow milk quantity in liters (0 for skip)'
                ),
                'requested_buffalo_milk': openapi.Schema(
                    type=openapi.TYPE_NUMBER, 
                    description='Requested buffalo milk quantity in liters (0 for skip)'
                ),
                'reason': openapi.Schema(
                    type=openapi.TYPE_STRING, 
                    description='Reason for adjustment'
                ),
                'delivery_time': openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format='time',
                    description='Preferred delivery time (HH:MM) - optional'
                ),
            }
        ),
        responses={
            201: openapi.Response(description="Delivery adjustment request created", schema=DeliveryAdjustmentSerializer),
            400: openapi.Response(description="Bad request"),
            404: openapi.Response(description="Customer not found")
        }
    )
    def create(self, request):
        """Create a unified delivery adjustment request"""
        try:
            customer_id = request.data.get('customer_id')
            date_str = request.data.get('date')
            requested_cow = request.data.get('requested_cow_milk')
            requested_buffalo = request.data.get('requested_buffalo_milk')
            reason = request.data.get('reason', '')
            delivery_time_str = request.data.get('delivery_time')
            
            # Validations
            if not customer_id or not date_str:
                return error_response("customer_id and date are required.", status_code=400)
            
            if requested_cow is None and requested_buffalo is None:
                return error_response("At least one milk type quantity must be specified.", status_code=400)
            
            # Get customer
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                return not_found_response(f"Customer with ID {customer_id} not found.")
            
            # Parse date
            try:
                adjustment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return error_response("Invalid date format. Use YYYY-MM-DD.", status_code=400)
            
            # Validate date (allow today for same-day adjustments)
            if adjustment_date < timezone.now().date():
                return error_response("Cannot create adjustment for past dates.", status_code=400)
            
            # Parse delivery time if provided
            delivery_time = None
            if delivery_time_str:
                try:
                    delivery_time = datetime.strptime(delivery_time_str, '%H:%M').time()
                except ValueError:
                    return error_response("Invalid time format. Use HH:MM (24-hour).", status_code=400)
            
            # Convert to Decimal
            try:
                if requested_cow is not None:
                    requested_cow = Decimal(str(requested_cow))
                if requested_buffalo is not None:
                    requested_buffalo = Decimal(str(requested_buffalo))
            except (InvalidOperation, ValueError):
                return error_response("Invalid quantity values.", status_code=400)
            
            # Validate quantities
            if requested_cow is not None and requested_cow < 0:
                return error_response("Cow milk quantity cannot be negative.", status_code=400)
            
            if requested_buffalo is not None and requested_buffalo < 0:
                return error_response("Buffalo milk quantity cannot be negative.", status_code=400)
            
            # Check for existing request (for quantity_adjustment type)
            existing_request = CustomerRequest.objects.filter(
                customer=customer,
                date=adjustment_date,
                request_type="quantity_adjustment",
                status__in=["pending", "approved"]
            ).first()
            
            if existing_request:
                return error_response(
                    f"A delivery adjustment already exists for {adjustment_date}.",
                    status_code=400,
                    extra_data={
                        "existing_request_id": existing_request.id,
                        "status": existing_request.status,
                        "current_cow_milk": str(existing_request.requested_cow_milk) if existing_request.requested_cow_milk else None,
                        "current_buffalo_milk": str(existing_request.requested_buffalo_milk) if existing_request.requested_buffalo_milk else None,
                    }
                )
            
            # Also check for existing leave/extra_milk requests for same date
            existing_other = CustomerRequest.objects.filter(
                customer=customer,
                date=adjustment_date,
                request_type__in=["leave", "extra_milk"],
                status__in=["pending", "approved"]
            ).first()
            
            if existing_other:
                return error_response(
                    f"A {existing_other.get_request_type_display()} request already exists for {adjustment_date}. Please cancel it first or use that request.",
                    status_code=400,
                    extra_data={
                        "existing_request_id": existing_other.id,
                        "request_type": existing_other.request_type,
                        "status": existing_other.status,
                    }
                )
            
            # Create request
            adjustment_request = CustomerRequest.objects.create(
                customer=customer,
                vendor=customer.provider,
                request_type="quantity_adjustment",
                date=adjustment_date,
                requested_cow_milk=requested_cow,
                requested_buffalo_milk=requested_buffalo,
                reason=reason,
                extra_milk_delivery_time=delivery_time,
                extra_milk_delivery_milkman=customer.milkman,  # Default to regular milkman
                status="pending"
            )
            
            # Determine adjustment type for response
            adjustment_type = adjustment_request.get_adjustment_type()
            
            # Get regular quantities for comparison
            regular_cow = customer.cow_milk_litre or 0
            regular_buffalo = customer.buffalo_milk_litre or 0
            
            # Send FCM notification to vendor
            if customer.provider and hasattr(customer.provider, 'fcm_token') and customer.provider.fcm_token:
                customer_name = getattr(customer, 'name', None) or f"Customer #{customer.id}"
                send_fcm_notification(
                    customer.provider.fcm_token,
                    "New Delivery Adjustment Request",
                    f"{customer_name} has requested a delivery adjustment ({adjustment_type}) for {adjustment_date}."
                )
            
            response_data = {
                "request_id": adjustment_request.id,
                "adjustment_type": adjustment_type,
                "customer_id": customer.id,
                "customer_name": getattr(customer, 'name', None) or str(customer),
                "date": adjustment_date.isoformat(),
                "regular_quantities": {
                    "cow_milk": str(regular_cow),
                    "buffalo_milk": str(regular_buffalo)
                },
                "requested_quantities": {
                    "cow_milk": str(requested_cow) if requested_cow is not None else None,
                    "buffalo_milk": str(requested_buffalo) if requested_buffalo is not None else None
                },
                "status": "pending",
                "requires_vendor_approval": True,
                "created_at": adjustment_request.created_at.isoformat() if adjustment_request.created_at else None
            }
            
            # Add helpful context based on adjustment type
            if adjustment_request.is_leave:
                response_data["note"] = "This is a leave/skip delivery request"
            elif adjustment_request.is_extra_milk:
                response_data["note"] = "This is an extra milk request"
            elif adjustment_request.is_reduced_quantity:
                response_data["note"] = "This is a reduced quantity request"
            
            return success_response("Delivery adjustment request created successfully.", response_data, status_code=201)
            
        except Exception as e:
            logger.error(f"Error in create_delivery_adjustment_request: {str(e)}")
            return error_response(f"An error occurred: {str(e)}", status_code=500)

    @swagger_auto_schema(
        operation_summary="List Delivery Adjustment Requests",
        operation_description="Get all delivery adjustment requests with optional filters",
        manual_parameters=[
            openapi.Parameter(
                'vendor_id', 
                openapi.IN_QUERY, 
                description="Filter by vendor ID", 
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'customer_id', 
                openapi.IN_QUERY, 
                description="Filter by customer ID", 
                type=openapi.TYPE_INTEGER
            ),
            openapi.Parameter(
                'status', 
                openapi.IN_QUERY, 
                description="Filter by status: pending, approved, rejected", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'adjustment_type', 
                openapi.IN_QUERY, 
                description="Filter by type: leave, extra, reduced", 
                type=openapi.TYPE_STRING
            ),
            openapi.Parameter(
                'date_from', 
                openapi.IN_QUERY, 
                description="Filter from date (YYYY-MM-DD)", 
                type=openapi.TYPE_STRING,
                format='date'
            ),
            openapi.Parameter(
                'date_to', 
                openapi.IN_QUERY, 
                description="Filter to date (YYYY-MM-DD)", 
                type=openapi.TYPE_STRING,
                format='date'
            ),
        ],
        responses={200: DeliveryAdjustmentSerializer(many=True)}
    )
    def list(self, request):
        """List delivery adjustment requests with filters"""
        try:
            vendor_id = request.query_params.get('vendor_id')
            customer_id = request.query_params.get('customer_id')
            status_filter = request.query_params.get('status')
            adjustment_type = request.query_params.get('adjustment_type')
            date_from = request.query_params.get('date_from')
            date_to = request.query_params.get('date_to')
            
            # Start with quantity_adjustment requests
            queryset = CustomerRequest.objects.filter(
                request_type="quantity_adjustment"
            ).select_related(
                'customer', 'vendor', 'extra_milk_delivery_milkman'
            )
            
            # Apply filters
            if vendor_id:
                queryset = queryset.filter(vendor_id=vendor_id)
            
            if customer_id:
                queryset = queryset.filter(customer_id=customer_id)
            
            if status_filter:
                queryset = queryset.filter(status=status_filter)
            
            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            
            if date_to:
                queryset = queryset.filter(date__lte=date_to)
            
            # Filter by adjustment type (computed property) - post-filter
            if adjustment_type:
                filtered_ids = []
                for req in queryset:
                    if adjustment_type == 'leave' and req.is_leave:
                        filtered_ids.append(req.id)
                    elif adjustment_type == 'extra' and req.is_extra_milk:
                        filtered_ids.append(req.id)
                    elif adjustment_type == 'reduced' and req.is_reduced_quantity:
                        filtered_ids.append(req.id)
                queryset = queryset.filter(id__in=filtered_ids)
            
            serializer = DeliveryAdjustmentSerializer(queryset, many=True)
            
            return success_response(
                "Delivery adjustments fetched successfully.",
                serializer.data,
                extra_data={"count": len(serializer.data)}
            )
            
        except Exception as e:
            logger.error(f"Error in list_delivery_adjustments: {str(e)}")
            return error_response(f"An error occurred: {str(e)}", status_code=500)

    @swagger_auto_schema(
        operation_summary="Approve/Reject Delivery Adjustment Request",
        operation_description="Vendor approves or rejects a delivery adjustment request",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['request_id', 'action'],
            properties={
                'request_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Adjustment request ID"),
                'action': openapi.Schema(type=openapi.TYPE_STRING, enum=['approve', 'reject'], description="Action to take"),
                'rejection_reason': openapi.Schema(type=openapi.TYPE_STRING, description='Required if action is reject'),
            }
        ),
        responses={
            200: openapi.Response(description="Request processed successfully", schema=DeliveryAdjustmentSerializer),
            400: openapi.Response(description="Bad request"),
            404: openapi.Response(description="Request not found")
        }
    )
    @action(detail=False, methods=['post'], url_path='approve-reject')
    def approve_reject(self, request):
        """Approve or reject a delivery adjustment request"""
        try:
            request_id = request.data.get('request_id')
            action = request.data.get('action')  # 'approve' or 'reject'
            rejection_reason = request.data.get('rejection_reason', '')
            
            if not request_id or action not in ['approve', 'reject']:
                return error_response("request_id and valid action (approve/reject) are required.", status_code=400)
            
            try:
                customer_request = CustomerRequest.objects.get(
                    id=request_id, 
                    request_type="quantity_adjustment"
                )
            except CustomerRequest.DoesNotExist:
                return not_found_response(f"Delivery adjustment request with ID {request_id} not found.")
            
            if customer_request.status != 'pending':
                return error_response(f"Request is already {customer_request.status}.", status_code=400)
            
            customer = customer_request.customer
            adjustment_type = customer_request.get_adjustment_type()
            
            # Update request status
            if action == 'approve':
                customer_request.status = 'approved'
                customer_request.approved_rejected_at = timezone.now()
                
                # Send FCM notification to customer
                if hasattr(customer, 'fcm_token') and customer.fcm_token:
                    send_fcm_notification(
                        customer.fcm_token,
                        "Delivery Adjustment Approved",
                        f"Your {adjustment_type.lower()} request for {customer_request.date} has been approved."
                    )
                
                # If it's a leave (0 quantity), notify milkman
                if customer_request.is_leave:
                    milkman = customer.milkman
                    if milkman and hasattr(milkman, 'fcm_token') and milkman.fcm_token:
                        customer_name = getattr(customer, 'name', None) or f"Customer #{customer.id}"
                        send_fcm_notification(
                            milkman.fcm_token,
                            "Customer Skip Delivery",
                            f"{customer_name} has no delivery scheduled for {customer_request.date}."
                        )
                # If it's extra milk, notify milkman about extra delivery
                elif customer_request.is_extra_milk:
                    milkman = customer_request.extra_milk_delivery_milkman or customer.milkman
                    if milkman and hasattr(milkman, 'fcm_token') and milkman.fcm_token:
                        customer_name = getattr(customer, 'name', None) or f"Customer #{customer.id}"
                        cow = customer_request.requested_cow_milk or 0
                        buffalo = customer_request.requested_buffalo_milk or 0
                        send_fcm_notification(
                            milkman.fcm_token,
                            "Extra Delivery Request",
                            f"{customer_name} needs {cow}L cow + {buffalo}L buffalo milk on {customer_request.date}."
                        )
                # Notify milkman about reduced quantity
                elif customer_request.is_reduced_quantity:
                    milkman = customer.milkman
                    if milkman and hasattr(milkman, 'fcm_token') and milkman.fcm_token:
                        customer_name = getattr(customer, 'name', None) or f"Customer #{customer.id}"
                        cow = customer_request.requested_cow_milk or 0
                        buffalo = customer_request.requested_buffalo_milk or 0
                        send_fcm_notification(
                            milkman.fcm_token,
                            "Reduced Delivery",
                            f"{customer_name} needs only {cow}L cow + {buffalo}L buffalo milk on {customer_request.date}."
                        )
                
            else:  # reject
                if not rejection_reason:
                    return error_response("rejection_reason is required when rejecting a request.", status_code=400)
                customer_request.status = 'rejected'
                customer_request.rejection_reason = rejection_reason
                customer_request.approved_rejected_at = timezone.now()
                
                # Send FCM notification to customer
                if hasattr(customer, 'fcm_token') and customer.fcm_token:
                    send_fcm_notification(
                        customer.fcm_token,
                        "Delivery Adjustment Rejected",
                        f"Your {adjustment_type.lower()} request for {customer_request.date} was rejected. Reason: {rejection_reason}"
                    )
            
            customer_request.save()
            
            return success_response(
                f"Delivery adjustment request {action}d successfully.",
                DeliveryAdjustmentSerializer(customer_request).data
            )
            
        except Exception as e:
            logger.error(f"Error in approve_reject_delivery_adjustment: {str(e)}")
            return error_response(f"An error occurred: {str(e)}", status_code=500)

    @swagger_auto_schema(
        operation_summary="Get Delivery Quantity for Date",
        operation_description="Get the appropriate milk quantity for a customer on a specific date, considering any approved adjustments.",
        manual_parameters=[
            openapi.Parameter(
                'customer_id', 
                openapi.IN_QUERY, 
                description="Customer ID", 
                type=openapi.TYPE_INTEGER,
                required=True
            ),
            openapi.Parameter(
                'date', 
                openapi.IN_QUERY, 
                description="Date (YYYY-MM-DD)", 
                type=openapi.TYPE_STRING,
                format='date',
                required=True
            ),
        ],
        responses={
            200: openapi.Response(description="Delivery quantity information"),
            400: openapi.Response(description="Bad request"),
            404: openapi.Response(description="Customer not found")
        }
    )
    @action(detail=False, methods=['get'], url_path='quantity-for-date')
    def quantity_for_date(self, request):
        """Get the delivery quantity for a customer on a specific date"""
        try:
            customer_id = request.query_params.get('customer_id')
            date_str = request.query_params.get('date')
            
            if not customer_id or not date_str:
                return error_response("customer_id and date are required.", status_code=400)
            
            try:
                customer = Customer.objects.get(id=customer_id)
            except Customer.DoesNotExist:
                return not_found_response(f"Customer with ID {customer_id} not found.")
            
            try:
                delivery_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return error_response("Invalid date format. Use YYYY-MM-DD.", status_code=400)
            
            quantity_info = get_delivery_quantity_for_date(customer, delivery_date)
            
            return success_response(
                "Delivery quantity fetched successfully.",
                {
                    "customer_id": customer.id,
                    "customer_name": getattr(customer, 'name', None) or str(customer),
                    "date": date_str,
                    "cow_milk": str(quantity_info['cow_milk']),
                    "buffalo_milk": str(quantity_info['buffalo_milk']),
                    "is_adjusted": quantity_info['is_adjusted'],
                    "adjustment_type": quantity_info['adjustment_type'],
                    "adjustment_id": quantity_info['adjustment_id'],
                    "reason": quantity_info['reason'],
                    "regular_cow_milk": str(customer.cow_milk_litre or 0),
                    "regular_buffalo_milk": str(customer.buffalo_milk_litre or 0),
                }
            )
            
        except Exception as e:
            logger.error(f"Error in quantity_for_date: {str(e)}")
            return error_response(f"An error occurred: {str(e)}", status_code=500)
