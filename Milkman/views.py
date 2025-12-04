import logging
from datetime import datetime

# Third-party imports
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

# Django imports
from django.apps import apps
from django.contrib.auth.hashers import make_password

# Local application imports
from .models import Milkman
from .serializers import (
    MilkmanSerializer,
    MilkmanUpdateSerializer,
    LegacyMilkmanSerializer,
)
from OneWindowHomeSolution.core_utils import format_address
from OneWindowHomeSolution.responses import success_response, error_response, not_found_response

logger = logging.getLogger(__name__)


class LegacyMilkmanViewSet(viewsets.ModelViewSet):
    queryset = Milkman.objects.all()
    serializer_class = LegacyMilkmanSerializer

    def list(self, request, *args, **kwargs):
        logger.info(f"Listing all legacy milkmen")
        milkmen = self.get_queryset()
        logger.info(f"Retrieved {milkmen.count()} legacy milkmen")
        serializer = self.get_serializer(milkmen, many=True)
        return Response({'status': 'success', 'legacy_milkmen': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        logger.info(f"Retrieving legacy milkman {kwargs.get('pk')}")
        milkman = self.get_object()
        logger.info(f"Legacy milkman {milkman.id} retrieved successfully")
        serializer = self.get_serializer(milkman)
        return Response({'status': 'success', 'legacy_milkman': serializer.data})

    def create(self, request, *args, **kwargs):
        logger.info(f"Creating new legacy milkman")
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Legacy milkman {serializer.data.get('id')} created successfully")
            return Response({'status': 'success', 'legacy_milkman': serializer.data}, status=status.HTTP_201_CREATED)
        logger.warning(f"Failed to create legacy milkman: {serializer.errors}")
        return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        logger.info(f"Updating legacy milkman {kwargs.get('pk')}")
        milkman = self.get_object()
        serializer = self.get_serializer(milkman, data=request.data)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Legacy milkman {milkman.id} updated successfully")
            return Response({'status': 'success', 'legacy_milkman': serializer.data})
        logger.warning(f"Failed to update legacy milkman {milkman.id}: {serializer.errors}")
        return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        logger.info(f"Partially updating legacy milkman {kwargs.get('pk')}")
        milkman = self.get_object()
        serializer = self.get_serializer(milkman, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Legacy milkman {milkman.id} partially updated successfully")
            return Response({'status': 'success', 'legacy_milkman': serializer.data})
        logger.warning(f"Failed to partially update legacy milkman {milkman.id}: {serializer.errors}")
        return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        logger.info(f"Deleting legacy milkman {kwargs.get('pk')}")
        milkman = self.get_object()
        milkman_id = milkman.id
        milkman.delete()
        logger.info(f"Legacy milkman {milkman_id} deleted successfully")
        return Response({'status': 'success', 'message': 'Legacy milkman deleted'})


class MilkmanViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Milkman.objects.all()

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return MilkmanUpdateSerializer
        return MilkmanSerializer

    @staticmethod
    def get_object(pk):
        try:
            return Milkman.objects.get(pk=pk)
        except Milkman.DoesNotExist:
            return None

    def get_permissions(self):
        if getattr(self, 'action', None) == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    @swagger_auto_schema(
        operation_summary="List Milkmen",
        operation_description="Retrieve a list of all milkmen.",
        responses={200: MilkmanSerializer(many=True)}
    )
    def list(self, request):
        logger.info(f"User {request.user.id} requesting list of all milkmen")
        milkmen = Milkman.objects.all()
        
        # Apply pagination
        paginator = PageNumberPagination()
        paginator.page_size = 50
        result_page = paginator.paginate_queryset(milkmen, request, view=self)
        logger.info(f"Retrieved {len(result_page)} milkmen for user {request.user.id}")
        serializer = self.get_serializer_class()(result_page, many=True)
        
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": "Milkmen fetched successfully",
            "data": serializer.data,
        }
        
        # Return paginated response
        return paginator.get_paginated_response(response_data["data"])

    @swagger_auto_schema(
        operation_summary="Retrieve Milkman",
        operation_description="Get details of a specific milkman by their ID.",
        responses={200: MilkmanSerializer()},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milkman ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def retrieve(self, request, pk=None):
        logger.info(f"User {request.user.id} retrieving milkman {pk}")
        milkman = self.get_object(pk)
        if not milkman:
            logger.warning(f"Milkman {pk} not found for user {request.user.id}")
            response_data = {
                "status": "error",
                "code": status.HTTP_404_NOT_FOUND,
                "message": "Milkman not found",
            }
            return Response(response_data, status=status.HTTP_404_NOT_FOUND)
        
        logger.info(f"Milkman {pk} retrieved successfully for user {request.user.id}")
        serializer = self.get_serializer_class()(milkman)
        response_data = {
            "status": "success",
            "code": status.HTTP_200_OK,
            "message": "Milkman retrieved successfully",
            "data": serializer.data,
        }
        return Response(response_data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_summary="Create Milkman",
        operation_description="Register a new milkman.",
        request_body=MilkmanSerializer,
        responses={201: MilkmanSerializer()}
    )
    def create(self, request):
        logger.info(f"Creating new milkman")
        # Clean the data before serialization
        data = request.data.copy()

        # Handle provider being 0 or empty
        if data.get('provider') in [0, '0', '', None]:
            data['provider'] = None

        # Ensure confirm_password is provided if password is provided
        if 'password' in data and 'confirm_password' not in data:
            data['confirm_password'] = data['password']

        serializer = self.get_serializer_class()(data=data)
        if serializer.is_valid():
            # Let the serializer handle password hashing and confirm_password cleanup
            milkman = serializer.save()
            logger.info(f"Milkman {milkman.id} created successfully with phone {milkman.phone_number}")

            # Create combined address for response
            milkman_location = format_address(
                flat_no=getattr(milkman, "flat_house", None),
                village=getattr(milkman, "village", None),
                tal=getattr(milkman, "tal", None),
                dist=getattr(milkman, "dist", None),
                state=getattr(milkman, "state", None),
            )

            # Custom response format
            response_data = {
                "id": milkman.id,
                "full_name": milkman.full_name,
                "phone_number": (
                    getattr(milkman.phone_number, "phone_number", None)
                    or getattr(milkman, "phone_number_str", None)
                ),
                "location": milkman_location,
                "provider": milkman.provider.id if milkman.provider else None,
                "society_name": milkman.society_name,
                "pincode": milkman.pincode,
            }

            return success_response("Milkman created successfully", response_data, status_code=status.HTTP_201_CREATED)
        logger.warning(f"Failed to create milkman: {serializer.errors}")
        return error_response("Failed to create milkman", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Update Milkman",
        operation_description="Update all details of an existing milkman.",
        request_body=MilkmanUpdateSerializer,
        responses={200: MilkmanSerializer()},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milkman ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def update(self, request, pk=None):
        logger.info(f"User {request.user.id} updating milkman {pk}")
        milkman = self.get_object(pk)
        if not milkman:
            logger.warning(f"Milkman {pk} not found for update")
            return not_found_response("Milkman not found")
        serializer = self.get_serializer_class()(milkman, data=request.data)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Milkman {pk} updated successfully")
            return success_response("Milkman updated successfully", serializer.data)
        logger.warning(f"Failed to update milkman {pk}: {serializer.errors}")
        return error_response("Failed to update milkman", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Partially Update Milkman",
        operation_description="Update selected fields of an existing milkman.",
        request_body=MilkmanUpdateSerializer,
        responses={200: MilkmanSerializer()},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milkman ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def partial_update(self, request, pk=None):
        logger.info(f"User {request.user.id} partially updating milkman {pk}")
        milkman = self.get_object(pk)
        if not milkman:
            logger.warning(f"Milkman {pk} not found for partial update")
            return not_found_response("Milkman not found")
        serializer = self.get_serializer_class()(milkman, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.info(f"Milkman {pk} partially updated successfully")
            return success_response("Milkman partially updated successfully", serializer.data)
        logger.warning(f"Failed to partially update milkman {pk}: {serializer.errors}")
        return error_response("Failed to partially update milkman", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Delete Milkman",
        operation_description="Delete a milkman by their ID.",
        responses={204: "No Content"},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milkman ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def destroy(self, request, pk=None):
        logger.info(f"Deleting milkman {pk}")
        milkman = self.get_object(pk)
        if not milkman:
            logger.warning(f"Milkman {pk} not found for deletion")
            return not_found_response("Milkman not found")
        serializer = self.get_serializer_class()()
        serializer.delete(milkman)
        logger.info(f"Milkman {pk} deleted successfully")
        return success_response("Milkman deleted successfully", status_code=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(
        operation_summary="Update FCM Token",
        operation_description="Update the FCM token for a milkman.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'fcm_token': openapi.Schema(type=openapi.TYPE_STRING, description='FCM Token')
            },
            required=['fcm_token']
        ),
        responses={200: "FCM token updated successfully"}
    )
    def update_fcm_token(self, request, pk=None):
        logger.info(f"User {request.user.id} updating FCM token for milkman {pk}")
        milkman = self.get_object(pk)
        if not milkman:
            logger.warning(f"Milkman {pk} not found for FCM token update")
            return not_found_response("Milkman not found")
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            logger.warning(f"FCM token not provided for milkman {pk}")
            return error_response("FCM token is required")
        milkman.fcm_token = fcm_token
        milkman.save()
        logger.info(f"FCM token updated successfully for milkman {pk}")
        return success_response("FCM token updated successfully")


class MilkmanActionsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Check Vendor Assignment",
        operation_description="Check if a milkman is assigned to a vendor after completing a join request. Returns detailed assignment information including vendor details.",
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milkman ID", type=openapi.TYPE_INTEGER)
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
            404: openapi.Response("Milkman not found")
        }
    )
    def check_vendor_assignment(self, pk=None):
        logger.info(f"Checking vendor assignment for milkman {pk}")
        # Check if milkman exists
        try:
            milkman = Milkman.objects.get(id=pk)
        except Milkman.DoesNotExist:
            logger.warning(f"Milkman {pk} not found for vendor assignment check")
            return error_response(f"Milkman with ID {pk} not found.", status_code=404)

        # Check for accepted join request
        try:
            JoinRequest = apps.get_model('vendor', 'JoinRequest')
            join_request = JoinRequest.objects.filter(
                object_id=pk,
                user_type="milkman",
                status="accepted"
            ).select_related('vendor').latest('id')
            
            # Format joined date (fallback logic for missing timestamps)
            joined_date = None
            if hasattr(join_request, 'created_at'):
                joined_date = join_request.created_at.strftime('%Y-%m-%d')
            elif hasattr(join_request.vendor, 'created_at'):
                joined_date = join_request.vendor.created_at.strftime('%Y-%m-%d')
            else:
                joined_date = datetime.now().strftime('%Y-%m-%d')

            vendor_details = {
                "id": join_request.vendor.id,
                "name": join_request.vendor.name or '',
                "contact": join_request.vendor.contact or '',
                "email": join_request.vendor.email or '',
                "address": {
                    "flat_house": join_request.vendor.flat_house or '',
                    "society_area": join_request.vendor.society_area or '',
                    "village": join_request.vendor.village or '',
                    "tal": join_request.vendor.tal or '',
                    "dist": join_request.vendor.dist or '',
                    "state": join_request.vendor.state or '',
                    "pincode": join_request.vendor.pincode
                },
                "milk_rates": {
                    "gir_cow_rate": float(join_request.vendor.gir_cow_rate or 0),
                    "jarshi_cow_rate": float(join_request.vendor.jarshi_cow_rate or 0),
                    "deshi_cow_rate": float(join_request.vendor.deshi_cow_rate or 0),
                    "cow_milk_rate": float(join_request.vendor.cr or 0),
                    "buffalo_rate": float(join_request.vendor.br or 0)
                },
                "capacity": {
                    "gir_cow_milk_litre": join_request.vendor.gir_cow_milk_litre or 0,
                    "jarshi_cow_milk_litre": join_request.vendor.jarshi_cow_milk_litre or 0,
                    "deshi_milk_litre": join_request.vendor.deshi_milk_litre or 0,
                    "buffalo_milk_litre": join_request.vendor.buffalo_milk_litre or 0,
                    "total_cow_milk_capacity": join_request.vendor.total_cow_milk_capacity,
                    "total_milk_capacity": join_request.vendor.total_milk_capacity
                }
            }
            
            logger.info(f"Milkman {pk} is assigned to vendor {join_request.vendor.id}")

            response_data = {
                "isJoined": True,
                "currentVendorId": str(join_request.vendor.id),
                "currentVendorName": join_request.vendor.name or '',
                "joinedDate": joined_date,
                "status": join_request.status,
                "vendorDetails": vendor_details
            }

        except JoinRequest.DoesNotExist:
            logger.info(f"Milkman {pk} is not assigned to any vendor")
            response_data = {
                "isJoined": False,
                "currentVendorId": None,
                "currentVendorName": None,
                "joinedDate": None,
                "status": "none",
                "vendorDetails": None
            }

        return success_response("Vendor assignment status checked successfully", response_data)