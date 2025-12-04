from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from rest_framework.permissions import IsAuthenticated, BasePermission
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from .models import JoinRequest
from .serializers import JoinRequestSerializer
from OneWindowHomeSolution.responses import success_response, error_response
from OneWindowHomeSolution.core_utils import safe_str, format_address
from rest_framework.decorators import action
from BusinessRegistration.models import VendorBusinessRegistration
from BusinessRegistration.serializers import VendorBusinessRegistrationSerializer
from Customer.models import Customer
from Milkman.models import Milkman
import logging

logger = logging.getLogger(__name__)


class IsVendorForJoinRequest(BasePermission):
    """
    Custom permission to only allow vendors to accept/reject join requests for their own business.
    """
    
    def has_permission(self, request, view):
        # First check if user is authenticated
        if not request.user or not hasattr(request.user, 'id'):
            return False
        
        # For accept/reject actions, we need to check if the user is a vendor
        if view.action in ['accept', 'reject']:
            # Check if the authenticated user is a vendor by looking at the user model type
            if isinstance(request.user, VendorBusinessRegistration):
                return True
            
            # Alternative check: try to get vendor by ID
            try:
                vendor = VendorBusinessRegistration.objects.get(id=request.user.id)
                return True
            except VendorBusinessRegistration.DoesNotExist:
                return False
        
        # For other actions, just require authentication
        return True
    
    def has_object_permission(self, request, view, obj):
        # For accept/reject actions, ensure the vendor owns the join request
        if view.action in ['accept', 'reject']:
            if isinstance(request.user, VendorBusinessRegistration):
                return obj.vendor.id == request.user.id
            
            try:
                vendor = VendorBusinessRegistration.objects.get(id=request.user.id)
                return obj.vendor.id == vendor.id
            except VendorBusinessRegistration.DoesNotExist:
                return False
        
        return True

class JoinRequestViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    queryset = JoinRequest.objects.all()
    serializer_class = JoinRequestSerializer

    def _validate_and_get_vendor_id(self, request):
        """
        Helper method to validate and extract vendor_id from query parameters.
        Returns (vendor_id: int, error_response: Response | None)
        """
        vendor_id = request.query_params.get("vendor_id")
        if not vendor_id:
            logger.warning(f"User {request.user.id} missing vendor_id parameter")
            return None, error_response("vendor_id query parameter is required.", status_code=400)
        try:
            vendor_id = int(vendor_id)
            return vendor_id, None
        except (ValueError, TypeError) as e:
            logger.error(f"User {request.user.id} provided invalid vendor_id: {vendor_id}")
            return None, error_response("Invalid vendor_id. Must be an integer.", status_code=400)

    def _validate_vendor_permission(self, request, obj):
        """Helper method to validate vendor permissions for join requests."""
        user_type = type(request.user).__name__
        
        if not isinstance(request.user, VendorBusinessRegistration):
            try:
                vendor = VendorBusinessRegistration.objects.get(id=request.user.id)
            except VendorBusinessRegistration.DoesNotExist:
                logger.warning(f"Non-vendor user {request.user.id} ({user_type}) attempted to process join request {obj.id}")
                return None, error_response(f"Only vendors can process join requests. Current user type: {user_type}", status_code=403)
        else:
            vendor = request.user
        
        if obj.vendor.id != vendor.id:
            logger.warning(f"Vendor {vendor.id} attempted to process join request {obj.id} for different vendor {obj.vendor.id}")
            return None, error_response("You can only process join requests for your own business.", status_code=403)
        
        return vendor, None

    @swagger_auto_schema(
        operation_summary="List Pending Join Requests for Vendor",
        operation_description="Retrieve a list of pending join requests for a specific vendor. Pass vendor_id as a query parameter.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response("List of pending join requests for vendor", JoinRequestSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="requests-for-vendor")
    def requests_for_vendor(self, request):
        logger.info("START requests_for_vendor | request by user: %s", getattr(request.user, 'id', None))
        vendor_id, error = self._validate_and_get_vendor_id(request)
        if error:
            return error
        
        join_requests = JoinRequest.objects.filter(
            status="pending", 
            vendor_id=vendor_id
        ).select_related('vendor')
        serializer = JoinRequestSerializer(join_requests, many=True, context={'request': request})
        logger.info(f"Retrieved {len(join_requests)} pending requests for vendor {vendor_id}")
        logger.info("END requests_for_vendor | vendor_id: %s, count: %d", vendor_id, len(join_requests))
        return success_response("Join requests for vendor fetched successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="List All Join Requests",
        operation_description="Retrieve a list of all join requests ever made.",
        responses={200: openapi.Response("List of join requests", JoinRequestSerializer(many=True))}
    )
    def list(self, request):
        logger.info("START list | request by user: %s", getattr(request.user, 'id', None))
        join_requests = JoinRequest.objects.all().select_related('vendor')
        serializer = self.serializer_class(join_requests, many=True, context={'request': request})
        logger.info("END list | total join requests: %d", len(serializer.data))
        return success_response("Join requests fetched successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="List Accepted Customers for Vendor",
        operation_description="Retrieve a list of all customers whose join requests were accepted by a specific vendor. Pass vendor_id as a query parameter.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response("List of accepted customers", JoinRequestSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="accepted-customers")
    def accepted_customers(self, request):
        logger.info("START accepted_customers | request by user: %s", getattr(request.user, 'id', None))
        vendor_id, error = self._validate_and_get_vendor_id(request)
        if error:
            return error
        logger.info("Fetching accepted customers for vendor %s", vendor_id)
        join_requests = JoinRequest.objects.filter(
            status="accepted", 
            user_type="customer", 
            vendor_id=vendor_id
        ).select_related('vendor')
        customer_ids = [jr.object_id for jr in join_requests]
        customers = Customer.objects.filter(id__in=customer_ids).select_related('milkman')
        customer_map = {c.id: c for c in customers}
        customers_data = []
        for join_request in join_requests:
            customer = customer_map.get(join_request.object_id)
            if not customer:
                logger.warning(f"Customer {join_request.object_id} not found for join request {join_request.id}")
                continue
            customers_data.append({
                "join_request_id": join_request.id,
                "customer_id": customer.id,
                "customer_name": safe_str(customer.name),
                "customer_contact": safe_str(customer.contact),
                "customer_address": {
                    "flat_no": safe_str(customer.flat_no),
                    "society_name": safe_str(customer.society_name),
                    "village": safe_str(customer.village),
                    "tal": safe_str(customer.tal),
                    "dist": safe_str(customer.dist),
                    "state": safe_str(customer.state),
                    "pincode": safe_str(customer.pincode)
                },
                "cow_milk_litre": float(customer.cow_milk_litre) if customer.cow_milk_litre else 0,
                "buffalo_milk_litre": float(customer.buffalo_milk_litre) if customer.buffalo_milk_litre else 0,
                "assigned_milkman": {
                    "milkman_id": customer.milkman.id if customer.milkman else None,
                    "milkman_name": safe_str(customer.milkman.name) if customer.milkman else None,
                    "milkman_contact": safe_str(customer.milkman.phone_number) if customer.milkman else None,
                } if customer.milkman else None,
                "status": join_request.status,
                "vendor_name": safe_str(join_request.vendor.name)
            })
        logger.info("END accepted_customers | vendor_id: %s, count: %d", vendor_id, len(customers_data))
        return success_response("Accepted customers fetched successfully", customers_data)

    @swagger_auto_schema(
        operation_summary="List Accepted Milkmen for Vendor",
        operation_description="Retrieve a list of all milkmen whose join requests were accepted by a specific vendor. Pass vendor_id as a query parameter.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response("List of accepted milkmen", JoinRequestSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="accepted-milkmen")
    def accepted_milkmen(self, request):
        logger.info("START accepted_milkmen | request by user: %s", getattr(request.user, 'id', None))
        vendor_id, error = self._validate_and_get_vendor_id(request)
        if error:
            return error
        
        logger.info(f"Fetching accepted milkmen for vendor {vendor_id}")
        join_requests = JoinRequest.objects.filter(
            status="accepted", 
            user_type="milkman", 
            vendor_id=vendor_id
        ).select_related('vendor')
        
        # Batch fetch all milkmen and assigned customers count to avoid N+1 queries
        milkman_ids = [jr.object_id for jr in join_requests]
        milkmen = Milkman.objects.filter(id__in=milkman_ids)
        milkman_map = {m.id: m for m in milkmen}
        # Batch count assigned customers
        from django.db.models import Count
        customer_counts = Customer.objects.filter(milkman_id__in=milkman_ids).values('milkman_id').annotate(count=Count('id'))
        customer_count_map = {c['milkman_id']: c['count'] for c in customer_counts}

        milkmen_data = []
        for join_request in join_requests:
            milkman = milkman_map.get(join_request.object_id)
            if not milkman:
                logger.warning(f"Milkman {join_request.object_id} not found for join request {join_request.id}")
                continue
            assigned_customers_count = customer_count_map.get(milkman.id, 0)
            milkmen_data.append({
                "join_request_id": join_request.id,
                "milkman_id": milkman.id,
                "milkman_name": safe_str(milkman.name),
                "milkman_contact": safe_str(milkman.phone_number),
                "milkman_address": {
                    "flat_house": safe_str(milkman.flat_house),
                    "village": safe_str(milkman.village),
                    "tal": safe_str(milkman.tal),
                    "dist": safe_str(milkman.dist),
                    "state": safe_str(milkman.state),
                    "pincode": safe_str(milkman.pincode)
                },
                "assigned_customers_count": assigned_customers_count,
                "status": join_request.status,
                "vendor_name": safe_str(join_request.vendor.name)
            })
        logger.info(f"Retrieved {len(milkmen_data)} accepted milkmen for vendor {vendor_id}")
        return success_response("Accepted milkmen fetched successfully", milkmen_data)

    @swagger_auto_schema(
        operation_summary="List Rejected Customers for Vendor",
        operation_description="Retrieve a list of all customers whose join requests were rejected by a specific vendor. Pass vendor_id as a query parameter.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response("List of rejected customers", JoinRequestSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="rejected-customers")
    def rejected_customers(self, request):
        logger.info(f"User {request.user.id} requesting rejected customers for vendor")
        vendor_id, error = self._validate_and_get_vendor_id(request)
        if error:
            return error
        
        logger.info(f"Fetching rejected customers for vendor {vendor_id}")
        join_requests = JoinRequest.objects.filter(
            status="rejected", 
            user_type="customer", 
            vendor_id=vendor_id
        ).select_related('vendor')
        logger.info(f"Retrieved {len(join_requests)} rejected customers for vendor {vendor_id}")
        serializer = self.serializer_class(join_requests, many=True, context={'request': request})
        return success_response("Rejected customers fetched successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="List Rejected Milkmen for Vendor",
        operation_description="Retrieve a list of all milkmen whose join requests were rejected by a specific vendor. Pass vendor_id as a query parameter.",
        manual_parameters=[
            openapi.Parameter('vendor_id', openapi.IN_QUERY, description="Vendor ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={200: openapi.Response("List of rejected milkmen", JoinRequestSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="rejected-milkmen")
    def rejected_milkmen(self, request):
        logger.info(f"User {request.user.id} requesting rejected milkmen for vendor")
        vendor_id, error = self._validate_and_get_vendor_id(request)
        if error:
            return error
        
        logger.info(f"Fetching rejected milkmen for vendor {vendor_id}")
        join_requests = JoinRequest.objects.filter(
            status="rejected", 
            user_type="milkman", 
            vendor_id=vendor_id
        ).select_related('vendor')
        logger.info(f"Retrieved {len(join_requests)} rejected milkmen for vendor {vendor_id}")
        serializer = self.serializer_class(join_requests, many=True, context={'request': request})
        return success_response("Rejected milkmen fetched successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Create Join Request",
        operation_description="Submit a new join request. Required fields: user_id, vendor, user_type. The user_type should be 'customer' or 'milkman' in lowercase.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["user_id", "vendor", "user_type"],
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the customer or milkman"),
                "vendor": openapi.Schema(type=openapi.TYPE_INTEGER, description="Vendor ID"),
                "user_type": openapi.Schema(type=openapi.TYPE_STRING, enum=["customer", "milkman"], description="Type of user making the request (lowercase)"),
            },
            example={
                "user_id": 12,
                "vendor": 172,
                "user_type": "customer"
            }
        ),
        responses={
            201: openapi.Response(
                "Join request created", 
                openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "name": openapi.Schema(type=openapi.TYPE_STRING, description="Auto-generated name"),
                        "vendor": openapi.Schema(type=openapi.TYPE_INTEGER),
                        "status": openapi.Schema(type=openapi.TYPE_STRING, enum=["pending", "accepted", "rejected"]),
                        "user_type": openapi.Schema(type=openapi.TYPE_STRING, enum=["customer", "milkman"]),
                        "user_name": openapi.Schema(type=openapi.TYPE_STRING, description="Name of the requester"),
                        "user_contact": openapi.Schema(type=openapi.TYPE_STRING, description="Contact of the requester"),
                        "user_object_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the customer/milkman"),
                    }
                )
            )
        }
    )
    def create(self, request):
        # Validate user_type before processing
        user_type = request.data.get('user_type')
        user_id = request.data.get('user_id')
        vendor_id = request.data.get('vendor')
        
        if user_type and user_type not in ['customer', 'milkman']:
            logger.warning(f"Invalid user_type '{user_type}' provided in join request creation")
            return error_response("Invalid user_type. Must be 'customer' or 'milkman'.", status_code=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Lock existing requests to prevent race condition
            # Check if user already has an accepted join request with ANY vendor
            existing_accepted = JoinRequest.objects.select_for_update().filter(
                object_id=user_id,
                user_type=user_type,
                status="accepted"
            ).first()
            
            if existing_accepted:
                logger.warning(f"{user_type.capitalize()} {user_id} already has accepted join request with vendor {existing_accepted.vendor.id}")
                return error_response(
                    f"You are already joined with vendor '{existing_accepted.vendor.name}'. Please separate from them first before joining another vendor.",
                    {
                        "current_vendor_id": existing_accepted.vendor.id,
                        "current_vendor_name": existing_accepted.vendor.name,
                        "message": "Use the 'separate' endpoint to leave your current vendor before joining another."
                    },
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if there's already a pending request with this vendor (with lock)
            existing_pending = JoinRequest.objects.select_for_update().filter(
                object_id=user_id,
                user_type=user_type,
                vendor_id=vendor_id,
                status="pending"
            ).first()
            
            if existing_pending:
                logger.warning(f"{user_type.capitalize()} {user_id} already has pending request with vendor {vendor_id}")
                return error_response(
                    "You already have a pending join request with this vendor. Please wait for the vendor's response.",
                    {"existing_request_id": existing_pending.id},
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            # Allow multiple pending requests with different vendors
            # Cancellation will happen only when a vendor accepts the request
            
            serializer = self.serializer_class(data=request.data, context={'request': request})
            if serializer.is_valid():
                join_request = serializer.save()
                logger.info(f"Join request {join_request.id} created for {user_type} {user_id} to vendor {vendor_id}")
                
                # Count other pending requests to inform the user
                other_pending_count = JoinRequest.objects.filter(
                    object_id=user_id,
                    user_type=user_type,
                    status="pending"
                ).exclude(id=join_request.id).count()
                
                message = "Join request created successfully."
                if other_pending_count > 0:
                    message += f" You have {other_pending_count} other pending request(s) with different vendor(s)."
                
                return success_response(
                    message,
                    {
                        "id": join_request.id,
                        "status": join_request.status,
                        "vendor_id": vendor_id,
                        "other_pending_requests": other_pending_count
                    },
                    status_code=status.HTTP_201_CREATED
                )
            logger.warning(f"Failed to create join request: {serializer.errors}")
            return error_response(
                "Failed to create join request.",
                serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST
            )

    @swagger_auto_schema(
        operation_summary="Retrieve Join Request",
        operation_description="Get details of a specific join request by its ID.",
        responses={200: openapi.Response("Join request details", JoinRequestSerializer())},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="JoinRequest ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def retrieve(self, request, pk=None):
        logger.info(f"User {request.user.id} retrieving join request {pk}")
        obj = get_object_or_404(JoinRequest, pk=pk)
        logger.info(f"Join request {pk} retrieved successfully")
        serializer = self.serializer_class(obj, context={'request': request})
        return success_response("Join request retrieved successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Partially Update Join Request",
        operation_description="Update selected fields of an existing join request.",
        request_body=JoinRequestSerializer,
        responses={200: openapi.Response("Join request updated", JoinRequestSerializer())},
        manual_parameters=[
            openapi.Parameter('pk', openapi.IN_PATH, description="JoinRequest ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def partial_update(self, request, pk=None):
        logger.info(f"User {request.user.id} attempting to partially update join request {pk}")
        obj = get_object_or_404(JoinRequest, pk=pk)
        serializer = self.serializer_class(obj, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Join request {pk} updated successfully by user {request.user.id}")
            return success_response("Join request updated successfully", serializer.data)
        logger.warning(f"Failed to update join request {pk}: {serializer.errors}")
        return error_response("Failed to update join request", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Delete Join Request",
        operation_description="Delete a join request by its ID.",
        responses={204: openapi.Response("No Content")}
    )
    def destroy(self, request, pk=None):
        logger.info(f"User {request.user.id} attempting to delete join request {pk}")
        obj = get_object_or_404(JoinRequest, pk=pk)
        obj.delete()
        logger.info(f"Join request {pk} deleted successfully by user {request.user.id}")
        return success_response("Join request deleted successfully", status_code=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(
        operation_summary="Accept Join Request",
        operation_description="Accept a join request by its ID. Sets status to accepted. Only vendors can accept join requests for their own business.",
        responses={
            200: openapi.Response("Join request accepted", JoinRequestSerializer()),
            403: openapi.Response("Forbidden - Only vendors can accept join requests for their business"),
            404: openapi.Response("Join request not found")
        }
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsVendorForJoinRequest])
    def accept(self, request, pk=None):
        with transaction.atomic():
            # Lock the join request row to prevent concurrent modifications
            obj = get_object_or_404(JoinRequest.objects.select_for_update(), pk=pk)
            logger.info(f"Processing accept request for join request {obj.id} by user {request.user.id}")
            
            vendor, error_response_data = self._validate_vendor_permission(request, obj)
            if error_response_data:
                return error_response_data
            
            if obj.status == "accepted":
                logger.warning(f"Attempted to accept already accepted join request {obj.id}")
                return error_response("Join request is already accepted.", status_code=400)

            # Check if user already has an accepted join request with ANY vendor
            # Lock these rows to prevent race condition where multiple vendors accept simultaneously
            already_accepted = JoinRequest.objects.select_for_update().filter(
                object_id=obj.object_id,
                user_type=obj.user_type,
                status="accepted"
            ).exclude(pk=obj.pk).first()
            
            if already_accepted:
                logger.warning(f"{obj.user_type.capitalize()} {obj.object_id} already accepted by vendor {already_accepted.vendor.id}, cannot accept request {obj.id}")
                return error_response(
                    f"This {obj.user_type} is already joined with vendor '{already_accepted.vendor.name}'. They must separate first.",
                    {
                        "current_vendor_id": already_accepted.vendor.id,
                        "current_vendor_name": already_accepted.vendor.name
                    },
                    status_code=400
                )
            
            # Cancel ALL other join requests (pending, rejected) for this user across all vendors
            # This ensures the user can only be associated with one vendor at a time
            cancelled_count = JoinRequest.objects.filter(
                object_id=obj.object_id,
                user_type=obj.user_type,
                status__in=["pending", "rejected"]  # Cancel pending and rejected requests
            ).exclude(pk=obj.pk).update(status="cancelled")
            
            logger.info(f"Cancelled {cancelled_count} other requests (pending/rejected) for {obj.user_type} {obj.object_id} when accepting request {obj.id}")

            obj.status = "accepted"
            obj.accepted_at = timezone.now()
            obj.save()
            logger.info(f"Join request {obj.id} accepted by vendor {vendor.id}")

            # Update Customer or Milkman model with vendor assignment
            if obj.user_type == "customer":
                try:
                    customer = Customer.objects.get(id=obj.object_id)
                    customer.provider = obj.vendor
                    customer.milkman = None  # Not assigned at join, only after assignment
                    customer.save()
                    logger.info(f"Assigned vendor {obj.vendor.id} to customer {obj.object_id}")
                except Customer.DoesNotExist:
                    logger.error(f"Customer {obj.object_id} not found during vendor assignment")
                except Exception as e:
                    logger.error(f"Error updating customer {obj.object_id}: {str(e)}")
            elif obj.user_type == "milkman":
                try:
                    milkman = Milkman.objects.get(id=obj.object_id)
                    milkman.provider = obj.vendor
                    milkman.save()
                    logger.info(f"Assigned vendor {obj.vendor.id} to milkman {obj.object_id}")
                except Milkman.DoesNotExist:
                    logger.error(f"Milkman {obj.object_id} not found during vendor assignment")
                except Exception as e:
                    logger.error(f"Error updating milkman {obj.object_id}: {str(e)}")

        return success_response(
            "Join request accepted successfully. All other requests for this user have been cancelled.",
            {
                **self.serializer_class(obj, context={'request': request}).data,
                "cancelled_other_requests": cancelled_count
            }
        )

    @swagger_auto_schema(
        operation_summary="Reject Join Request",
        operation_description="Reject a join request by its ID. Sets status to rejected. Only vendors can reject join requests for their own business.",
        responses={
            200: openapi.Response("Join request rejected", JoinRequestSerializer()),
            403: openapi.Response("Forbidden - Only vendors can reject join requests for their business"),
            404: openapi.Response("Join request not found")
        }
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsVendorForJoinRequest])
    def reject(self, request, pk=None):
        with transaction.atomic():
            obj = get_object_or_404(JoinRequest, pk=pk)
            logger.info(f"Processing reject request for join request {obj.id} by user {request.user.id}")
            
            vendor, error_response_data = self._validate_vendor_permission(request, obj)
            if error_response_data:
                return error_response_data
            
            if obj.status == "rejected":
                logger.warning(f"Attempted to reject already rejected join request {obj.id}")
                return error_response("Join request is already rejected.", status_code=400)
            
            obj.status = "rejected"
            obj.rejected_at = timezone.now()
            obj.save()
            logger.info(f"Join request {obj.id} rejected by vendor {vendor.id}")
        
        return success_response("Join request rejected", self.serializer_class(obj, context={'request': request}).data)

    @swagger_auto_schema(
        operation_summary="Check if Customer is Accepted",
        operation_description="Check if a specific customer has been accepted by any vendor after a join request.",
        manual_parameters=[
            openapi.Parameter('customer_id', openapi.IN_QUERY, description="Customer ID", type=openapi.TYPE_INTEGER, required=True)
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'isAccepted': openapi.Schema(type=openapi.TYPE_BOOLEAN, description="True if the customer is accepted, otherwise False")
                }
            ),
            404: openapi.Response("Customer not found")
        }
    )
    @action(detail=False, methods=["get"], url_path="is-customer-accepted")
    def is_customer_accepted(self, request):
        logger.info(f"User {request.user.id} checking if customer is accepted")
        customer_id = request.query_params.get("customer_id")

        if not customer_id:
            logger.warning(f"User {request.user.id} missing customer_id parameter")
            return error_response("customer_id is required.", status_code=400)

        try:
            customer_id = int(customer_id)
        except ValueError:
            logger.error(f"User {request.user.id} provided invalid customer_id: {customer_id}")
            return error_response("Invalid customer_id. Must be an integer.", status_code=400)

        try:
            join_request = JoinRequest.objects.get(
                object_id=customer_id,
                user_type="customer"
            )
            logger.info(f"Found join request for customer {customer_id} with status: {join_request.status}")
        except JoinRequest.DoesNotExist:
            logger.warning(f"Join request not found for customer {customer_id}")
            return error_response("Join request not found for the given customer.", status_code=404)

        return success_response("Customer acceptance status retrieved successfully", {
            "isAccepted": join_request.status == "accepted"
        })

    @swagger_auto_schema(
        operation_summary="Withdraw Join Request",
        operation_description="Withdraw a join request by its ID. Only the user who created the request can withdraw it. This will delete the join request from the database and notify the vendor.",
        responses={
            200: openapi.Response("Join request withdrawn successfully"),
            403: openapi.Response("Forbidden - Only the requester can withdraw the join request"),
            404: openapi.Response("Join request not found")
        }
    )
    @action(detail=True, methods=["delete"], url_path="withdraw")
    def withdraw(self, request, pk=None):
        logger.info(f"User {request.user.id} attempting to withdraw join request {pk}")
        try:
            join_request = JoinRequest.objects.get(pk=pk)
        except JoinRequest.DoesNotExist:
            logger.warning(f"Join request {pk} not found for withdrawal")
            return error_response("Join request not found", status_code=404)

        # Check if the user is the requester
        if request.user.id != join_request.object_id:
            logger.warning(f"User {request.user.id} is not the requester of join request {pk}")
            return error_response("Only the requester can withdraw the join request", status_code=403)

        # Notify the vendor
        # send_notification(user=join_request.vendor, message=f"The join request from {join_request.requester.name} has been withdrawn.")

        # Delete the join request
        join_request.delete()
        logger.info(f"Join request {pk} withdrawn successfully by user {request.user.id}")

        return success_response("Join request withdrawn successfully", {
            "join_request_id": pk
        })

    @swagger_auto_schema(
        operation_summary="Separate from Current Vendor",
        operation_description="Allows a customer or milkman to separate/leave from their current vendor. This will cancel their accepted join request, clear vendor assignment, and allow them to join another vendor. Required parameters: user_id and user_type.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["user_id", "user_type"],
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the customer or milkman"),
                "user_type": openapi.Schema(type=openapi.TYPE_STRING, enum=["customer", "milkman"], description="Type of user (lowercase)"),
                "reason": openapi.Schema(type=openapi.TYPE_STRING, description="Optional reason for separation")
            },
            example={
                "user_id": 2,
                "user_type": "milkman",
                "reason": "Switching to a closer vendor"
            }
        ),
        responses={
            200: openapi.Response("Successfully separated from vendor"),
            400: openapi.Response("Bad Request - Invalid parameters or no active vendor"),
            404: openapi.Response("User not found")
        }
    )
    @action(detail=False, methods=["post"], url_path="separate-from-vendor")
    def separate_from_vendor(self, request):
        user_id = request.data.get("user_id")
        user_type = request.data.get("user_type")
        reason = request.data.get("reason", "User requested separation")
        
        logger.info(f"Processing separation request for {user_type} {user_id}")
        
        # Validate parameters
        if not user_id or not user_type:
            logger.warning(f"Missing required parameters in separation request")
            return error_response("user_id and user_type are required.", status_code=400)
        
        try:
            user_id = int(user_id)
        except ValueError:
            logger.error(f"Invalid user_id provided: {user_id}")
            return error_response("user_id must be an integer.", status_code=400)
        
        if user_type not in ["customer", "milkman"]:
            logger.error(f"Invalid user_type provided: {user_type}")
            return error_response("user_type must be 'customer' or 'milkman'.", status_code=400)
        
        with transaction.atomic():
            # Find the accepted join request
            accepted_request = JoinRequest.objects.filter(
                object_id=user_id,
                user_type=user_type,
                status="accepted"
            ).first()
            
            if not accepted_request:
                logger.warning(f"No accepted join request found for {user_type} {user_id}")
                return error_response(
                    f"This {user_type} is not currently joined with any vendor.",
                    status_code=400
                )
            
            vendor_name = accepted_request.vendor.name
            vendor_id = accepted_request.vendor.id
            
            # Mark the request as separated
            accepted_request.status = "separated"
            accepted_request.save()
            logger.info(f"Marked join request {accepted_request.id} as separated for {user_type} {user_id} from vendor {vendor_id}")
            
            # Clear vendor assignment in user model
            if user_type == "customer":
                try:
                    customer = Customer.objects.get(id=user_id)
                    customer.provider = None
                    customer.milkman = None  # Also clear milkman assignment
                    customer.save()
                    logger.info(f"Cleared vendor assignment for customer {user_id}")
                except Customer.DoesNotExist:
                    logger.error(f"Customer {user_id} not found during separation")
                    return error_response("Customer not found.", status_code=404)
            elif user_type == "milkman":
                try:
                    milkman = Milkman.objects.get(id=user_id)
                    milkman.provider = None
                    milkman.save()
                    
                    # Clear this milkman from all assigned customers
                    # CRITICAL: Also clear vendor from these customers since their milkman no longer has a vendor
                    unassigned_customers = Customer.objects.filter(milkman=milkman)
                    unassigned_count = unassigned_customers.count()
                    unassigned_customers.update(
                        milkman=None,
                        provider=None  # Clear vendor since milkman is leaving
                    )
                    logger.info(f"Cleared vendor assignment for milkman {user_id} and unassigned {unassigned_count} customers (also cleared their vendor)")
                except Milkman.DoesNotExist:
                    logger.error(f"Milkman {user_id} not found during separation")
                    return error_response("Milkman not found.", status_code=404)
        
        logger.info(f"Successfully separated {user_type} {user_id} from vendor {vendor_id}")
        return success_response(
            f"Successfully separated from vendor '{vendor_name}'. You can now join another vendor.",
            {
                "user_id": user_id,
                "user_type": user_type,
                "previous_vendor_id": vendor_id,
                "previous_vendor_name": vendor_name,
                "status": "separated",
                "reason": reason
            }
        )

    @swagger_auto_schema(
        operation_summary="List Vendors by Pincode Tolerance with Rejection Filter",
        operation_description="Retrieve vendors filtered by pincode (±20 tolerance). Excludes vendors who rejected the requesting user within the last 30 days. Requires user_id and user_type query parameters for rejection filtering.",
        manual_parameters=[
            openapi.Parameter('pincode', openapi.IN_QUERY, description="Pincode for filtering (optional)", required=False, type=openapi.TYPE_INTEGER),
            openapi.Parameter('user_id', openapi.IN_QUERY, description="ID of the requesting user (customer/milkman)", required=False, type=openapi.TYPE_INTEGER),
            openapi.Parameter('user_type', openapi.IN_QUERY, description="Type of user ('customer' or 'milkman')", required=False, type=openapi.TYPE_STRING)
        ],
        responses={200: openapi.Response("List of vendors", VendorBusinessRegistrationSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="list-vendors")
    def list_vendors(self, request):
        logger.info(f"User {request.user.id} requesting list of vendors")
        pincode = request.query_params.get("pincode")
        user_id = request.query_params.get("user_id")
        user_type = request.query_params.get("user_type")
        
        vendors = VendorBusinessRegistration.objects.all()
        
        # Filter by pincode with tolerance
        if pincode:
            try:
                pincode_int = int(pincode)
                logger.info(f"Filtering vendors by pincode {pincode_int} with tolerance ±20")
                # Filter vendors by pincode range ±20, excluding NULL values
                vendors = vendors.filter(
                    pincode__isnull=False,
                    pincode__gte=pincode_int - 20,
                    pincode__lte=pincode_int + 20
                )
            except ValueError:
                logger.error(f"User {request.user.id} provided invalid pincode: {pincode}")
                return error_response("Invalid pincode. Must be an integer.", status_code=400)
        
        # Exclude vendors who rejected this user in the last month
        if user_id and user_type:
            one_month_ago = timezone.now() - timedelta(days=30)
            rejected_vendor_ids = JoinRequest.objects.filter(
                object_id=user_id,
                user_type=user_type.lower(),
                status='rejected',
                rejected_at__gte=one_month_ago
            ).values_list('vendor_id', flat=True)
            
            if rejected_vendor_ids:
                vendors = vendors.exclude(id__in=rejected_vendor_ids)
                logger.info(f"Excluded {len(rejected_vendor_ids)} vendors who rejected {user_type} {user_id} in the last 30 days")

        # Apply pagination
        paginator = PageNumberPagination()
        paginator.page_size = 50
        result_page = paginator.paginate_queryset(vendors, request, view=self)
        logger.info(f"Retrieved {len(result_page)} vendors for user {request.user.id}")
        serializer = VendorBusinessRegistrationSerializer(result_page, many=True)

        return paginator.get_paginated_response(serializer.data)

    @swagger_auto_schema(
        operation_summary="Cleanup Old Join Requests",
        operation_description="Archive or delete old cancelled, rejected, and separated join requests older than a specified number of days (default: 30 days). This helps keep the join requests table clean and focused on active requests.",
        manual_parameters=[
            openapi.Parameter('days', openapi.IN_QUERY, description="Delete requests older than this many days (default: 30)", type=openapi.TYPE_INTEGER, required=False),
            openapi.Parameter('dry_run', openapi.IN_QUERY, description="If true, only return count without deleting (default: false)", type=openapi.TYPE_BOOLEAN, required=False)
        ],
        responses={
            200: openapi.Response("Cleanup completed successfully"),
            403: openapi.Response("Forbidden - Admin only")
        }
    )
    @action(detail=False, methods=["post"], url_path="cleanup-old-requests")
    def cleanup_old_requests(self, request):
        logger.info(f"User {request.user.id} initiating cleanup of old join requests")
        
        # Get parameters
        days = int(request.query_params.get("days", 30))
        dry_run = request.query_params.get("dry_run", "false").lower() == "true"
        
        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Find old requests with inactive statuses
        old_requests = JoinRequest.objects.filter(
            status__in=["cancelled", "rejected", "separated", "withdrawn"],
            updated_at__lt=cutoff_date
        )
        
        count = old_requests.count()
        logger.info(f"Found {count} old join requests older than {days} days")
        
        if dry_run:
            logger.info(f"Dry run mode - no requests deleted")
            return success_response(
                f"Dry run: Found {count} old join requests that would be deleted.",
                {
                    "count": count,
                    "days": days,
                    "cutoff_date": cutoff_date.isoformat(),
                    "dry_run": True
                }
            )
        
        # Delete the requests
        deleted_info = old_requests.delete()
        logger.info(f"Deleted {deleted_info[0]} old join requests")
        
        return success_response(
            f"Successfully cleaned up {deleted_info[0]} old join requests.",
            {
                "deleted_count": deleted_info[0],
                "days": days,
                "cutoff_date": cutoff_date.isoformat(),
                "dry_run": False
            }
        )

    @swagger_auto_schema(
        operation_summary="Check Vendor Assignment Status",
        operation_description="Check if a user (milkman or customer) is assigned to a vendor after completing a join request. Returns detailed assignment information including vendor details and join status.",
        manual_parameters=[
            openapi.Parameter('user_id', openapi.IN_QUERY, description="ID of the user (milkman or customer)", type=openapi.TYPE_INTEGER, required=True),
            openapi.Parameter('user_type', openapi.IN_QUERY, description="Type of user ('milkman' or 'customer')", type=openapi.TYPE_STRING, required=True)
        ],
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'isJoined': openapi.Schema(type=openapi.TYPE_BOOLEAN, description="True if assigned to a vendor"),
                    'currentVendorId': openapi.Schema(type=openapi.TYPE_STRING, description="ID of the assigned vendor"),
                    'currentVendorName': openapi.Schema(type=openapi.TYPE_STRING, description="Name of the assigned vendor"),
                    'joinedDate': openapi.Schema(type=openapi.TYPE_STRING, description="Date when join request was accepted"),
                    'status': openapi.Schema(type=openapi.TYPE_STRING, description="Status of the join request"),
                    'vendorDetails': openapi.Schema(type=openapi.TYPE_OBJECT, description="Complete vendor information")
                }
            ),
            400: openapi.Response("Bad Request - Missing required parameters"),
            404: openapi.Response("User or join request not found")
        }
    )
    @action(detail=False, methods=["get"], url_path="check-assignment")
    def check_assignment(self, request):
        logger.info(f"User {request.user.id} checking vendor assignment status")
        user_id = request.query_params.get("user_id")
        user_type = request.query_params.get("user_type")

        # Validate required parameters
        if not user_id or not user_type:
            logger.warning(f"User {request.user.id} missing required parameters for check_assignment")
            return error_response("user_id and user_type query parameters are required.", status_code=400)

        try:
            user_id = int(user_id)
        except ValueError:
            logger.error(f"User {request.user.id} provided invalid user_id: {user_id}")
            return error_response("user_id must be an integer.", status_code=400)

        if user_type not in ["milkman", "customer"]:
            logger.error(f"User {request.user.id} provided invalid user_type: {user_type}")
            return error_response("user_type must be 'milkman' or 'customer'.", status_code=400)

        logger.info(f"Checking assignment for {user_type} with ID {user_id}")
        
        # Check if user exists
        try:
            if user_type == "milkman":
                user = Milkman.objects.get(id=user_id)
            else:
                user = Customer.objects.get(id=user_id)
        except (Milkman.DoesNotExist, Customer.DoesNotExist):
            logger.warning(f"{user_type.capitalize()} with ID {user_id} not found")
            return error_response(f"{user_type.capitalize()} with ID {user_id} not found.", status_code=404)

        # Check for accepted join request - get the most recent one
        try:
            join_request = JoinRequest.objects.filter(
                object_id=user_id,
                user_type=user_type,
                status="accepted"
            ).select_related('vendor').latest('id')
            
            logger.info(f"Found accepted join request {join_request.id} for {user_type} {user_id} with vendor {join_request.vendor.id}")

            # Format joined date
            joined_date = join_request.created_at.strftime('%Y-%m-%d') if hasattr(join_request, 'created_at') else None

            vendor_details = {
                "id": join_request.vendor.id,
                "name": join_request.vendor.name or '',
                "contact": join_request.vendor.contact or '',
                "address": {
                    "flat_house": join_request.vendor.flat_house or '',
                    "society_area": join_request.vendor.society_area or '',
                    "village": join_request.vendor.village or '',
                    "tal": join_request.vendor.tal or '',
                    "dist": join_request.vendor.dist or '',
                    "state": join_request.vendor.state or '',
                    "pincode": join_request.vendor.pincode
                },
                "gir_cow_rate": float(join_request.vendor.gir_cow_rate or 0),
                "jarshi_cow_rate": float(join_request.vendor.jarshi_cow_rate or 0),
                "deshi_cow_rate": float(join_request.vendor.deshi_cow_rate or 0),
                "buffalo_rate": float(join_request.vendor.br or 0),
                "total_cow_milk_capacity": join_request.vendor.total_cow_milk_capacity,
                "buffalo_milk_litre": join_request.vendor.buffalo_milk_litre or 0,
                "total_milk_capacity": join_request.vendor.total_milk_capacity
            }

            response_data = {
                "isJoined": True,
                "currentVendorId": str(join_request.vendor.id),
                "currentVendorName": join_request.vendor.name or '',
                "joinedDate": joined_date,
                "status": join_request.status,
                "vendorDetails": vendor_details
            }

        except JoinRequest.DoesNotExist:
            logger.info(f"No accepted join request found for {user_type} {user_id}")
            response_data = {
                "isJoined": False,
                "currentVendorId": None,
                "currentVendorName": None,
                "joinedDate": None,
                "status": "none",
                "vendorDetails": None
            }

        logger.info(f"Check assignment completed for {user_type} {user_id}")
        return Response(response_data)

    @swagger_auto_schema(
        operation_summary="List Customers",
        operation_description="Retrieve a list of customers assigned to the vendor. Optionally filter by milkman_id to see customers assigned to a specific milkman.",
        manual_parameters=[
            openapi.Parameter('milkman_id', openapi.IN_QUERY, description="Milkman ID for filtering (optional)", type=openapi.TYPE_INTEGER, required=False)
        ],
        responses={200: openapi.Response("List of assigned customers", JoinRequestSerializer(many=True))}
    )
    @action(detail=False, methods=["get"], url_path="list-customers")
    def list_customers(self, request):
        logger.info("Entering list_customers method with query params: %s", request.query_params)
        try:
            milkman_id = request.query_params.get('milkman_id')

            if milkman_id:
                milkman = Milkman.objects.get(id=milkman_id)
            else:
                milkman = Milkman.objects.get(user=request.user)

            assigned_customers = Customer.objects.filter(milkman=milkman).select_related("provider", "milkman")
            
            logger.info("Successfully fetched assigned customers for milkman %s", milkman_id or request.user.id)
            customers_data = []
            for customer in assigned_customers:
                customers_data.append({
                    "customer_id": customer.id,
                    "customer_name": safe_str(customer.name),
                    "customer_contact": safe_str(customer.contact),
                    "customer_address": self.construct_customer_address(customer),
                    "cow_milk_litre": float(customer.cow_milk_litre) if customer.cow_milk_litre else 0,
                    "buffalo_milk_litre": float(customer.buffalo_milk_litre) if customer.buffalo_milk_litre else 0,
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

            return success_response("List of assigned customers.", customers_data)
        except Milkman.DoesNotExist:
            logger.error("Milkman not found for ID %s", milkman_id or request.user.id)
            return error_response("Milkman not found.", status_code=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error("An error occurred in list_customers: %s", str(e))
            return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def construct_customer_address(self, customer):
        """Helper method to construct customer address for response."""
        return format_address(
            flat_no=customer.flat_no,
            building=customer.society_name,
            village=customer.village,
            tal=customer.tal,
            dist=customer.dist,
            state=customer.state,
            pincode=customer.pincode
        )
