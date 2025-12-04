import logging

# Third-party imports
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

# Django imports
from django.apps import apps
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.shortcuts import render, get_object_or_404

# Local application imports
from .models import VendorBusinessRegistration
from .serializers import (
    VendorBusinessRegistrationSerializer,
    VendorBusinessRegistrationUpdateSerializer,
    BusinessRegistrationSummarySerializer,
)
from OneWindowHomeSolution.core_utils import format_address
from OneWindowHomeSolution.responses import success_response, error_response, not_found_response
from Customer.models import Customer
from Milkman.models import Milkman

logger = logging.getLogger(__name__)


class VendorBusinessRegistrationViewSet(viewsets.ViewSet):
    queryset = VendorBusinessRegistration.objects.all()

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return VendorBusinessRegistrationUpdateSerializer
        return VendorBusinessRegistrationSerializer

    def get_object(self, pk):
        try:
            return VendorBusinessRegistration.objects.get(pk=pk)
        except VendorBusinessRegistration.DoesNotExist:
            return None

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action == 'create':
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    @swagger_auto_schema(
        operation_summary="List Vendor Business Registrations",
        operation_description="Retrieve a list of all vendor business registrations in the system.",
        responses={200: VendorBusinessRegistrationSerializer(many=True)}
    )
    def list(self, request):
        try:
            # Optional requester context
            user_type = (request.query_params.get("user_type") or "").lower()
            user_id = request.query_params.get("user_id")
            user_id_int = None
            try:
                if user_id is not None:
                    user_id_int = int(user_id)
            except (TypeError, ValueError):
                user_id_int = None

            registrations = VendorBusinessRegistration.objects.with_request_status(user_type, user_id_int)
            serializer = self.get_serializer_class()(registrations, many=True)

            enriched = []
            for vendor_data, vendor_obj in zip(serializer.data, registrations):
                vd = dict(vendor_data)
                vd['cr'] = getattr(vendor_obj, 'cr', None)
                vd['br'] = getattr(vendor_obj, 'br', None)
                vd['request_status'] = getattr(vendor_obj, 'request_status', 'none')
                enriched.append(vd)

            return success_response("Vendor business registrations fetched successfully", enriched)
        except Exception as e:
            return error_response(f"Failed to fetch vendor business registrations: {str(e)}", status_code=500)

    @swagger_auto_schema(
        operation_summary="Create Vendor Business Registration",
        operation_description="Register a new vendor business with detailed address fields and milk details.",
        request_body=VendorBusinessRegistrationSerializer,
        responses={201: VendorBusinessRegistrationSerializer()},
        manual_parameters=[]
    )
    def create(self, request):
        serializer = self.get_serializer_class()(data=request.data)
        if serializer.is_valid():
            # Password hashing is handled in the serializer; avoid double-hashing here
            vendor = serializer.save()
            return success_response("Vendor business registration created successfully", serializer.data, status_code=status.HTTP_201_CREATED)
        return error_response("Failed to create vendor business registration", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Update Vendor Business Registration",
        operation_description="Update all details of an existing vendor business registration, including milk details.",
        request_body=VendorBusinessRegistrationUpdateSerializer,
        responses={200: VendorBusinessRegistrationSerializer()},
        manual_parameters=[]
    )
    def update(self, request, pk=None):
        vendor = self.get_object(pk)
        if not vendor:
            return not_found_response("Vendor Business Registration not found")
        serializer = self.get_serializer_class()(vendor, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response("Vendor business registration updated successfully", serializer.data)
        return error_response("Failed to update vendor business registration", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Partially Update Vendor Business Registration",
        operation_description="Update selected fields of an existing vendor business registration, including milk details.",
        request_body=VendorBusinessRegistrationUpdateSerializer,
        responses={200: VendorBusinessRegistrationSerializer()}
    )
    def partial_update(self, request, pk=None):
        vendor = self.get_object(pk)
        if not vendor:
            return not_found_response("Vendor Business Registration not found")
        serializer = self.get_serializer_class()(vendor, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success_response("Vendor business registration partially updated successfully", serializer.data)
        return error_response("Failed to partially update vendor business registration", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Delete Vendor Business Registration",
        operation_description="Delete a vendor business registration by its ID.",
        responses={204: "No Content"}
    )
    def destroy(self, request, pk=None):
        vendor = self.get_object(pk)
        if not vendor:
            return not_found_response("Vendor Business Registration not found")
        serializer = self.get_serializer_class()()
        serializer.delete(vendor)
        return success_response("Vendor business registration deleted successfully", status_code=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(
        operation_summary="Retrieve Vendor Business Registration Summary",
        operation_description="Get detailed vendor business registration info with computed summary data.",
        responses={200: VendorBusinessRegistrationSerializer()},
        manual_parameters=[]
    )
    def retrieve(self, request, pk=None):
        vendor = self.get_object(pk)
        if not vendor:
            return not_found_response("Vendor Business Registration not found")

        try:
            # Format full address
            vendor_location = format_address(
                flat_no=getattr(vendor, "flat_house", None),
                building=getattr(vendor, "society_area", None),
                village=getattr(vendor, "village", None),
                tal=getattr(vendor, "tal", None),
                dist=getattr(vendor, "dist", None),
                state=getattr(vendor, "state", None),
            )

            # Compute stats based on district
            vendor_district = getattr(vendor, "dist", "")
            total_customers = Customer.objects.filter(dist__icontains=vendor_district).count() if vendor_district else 0
            paid_customers = (
                Customer.objects.filter(dist__icontains=vendor_district, payment_status="paid").count()
                if hasattr(Customer, "payment_status") and vendor_district else 0
            )
            defaulters = (
                Customer.objects.filter(dist__icontains=vendor_district, payment_status="default").count()
                if hasattr(Customer, "payment_status") and vendor_district else 0
            )
            total_milkmans = Milkman.objects.filter(dist__icontains=vendor_district).count() if vendor_district else 0

            # Pending join requests
            try:
                JoinRequest = apps.get_model('vendor', 'JoinRequest')
                pending_requests = JoinRequest.objects.filter(status="pending", vendor=vendor).count()
            except Exception:
                pending_requests = 0

            # Serialize vendor base data
            vendor_data = VendorBusinessRegistrationSerializer(vendor).data

            # Add computed summary fields
            vendor_data.update({
                "location": vendor_location,
                "totalCustomers": total_customers,
                "paidCustomers": paid_customers,
                "defaulters": defaulters,
                "totalMilkmans": total_milkmans,
                "pendingJoinRequests": pending_requests,
            })

            return success_response(
                "Vendor business registration summary retrieved successfully",
                vendor_data
            )
        except Exception as e:
            return error_response(f"Failed to retrieve vendor summary: {str(e)}", status_code=500)

    @swagger_auto_schema(
        operation_summary="Update FCM Token",
        operation_description="Update the FCM token for a vendor business registration.",
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
        vendor = self.get_object(pk)
        if not vendor:
            return not_found_response("Vendor Business Registration not found")
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            return error_response("FCM token is required")
        vendor.fcm_token = fcm_token
        vendor.save()
        return success_response("FCM token updated successfully")

    @swagger_auto_schema(
        operation_summary="Update Cow Milk Rate",
        operation_description="Update the Cow Milk Rate for a vendor business registration.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'cr': openapi.Schema(type=openapi.TYPE_NUMBER, description='Cow Milk Rate')
            },
            required=['cr']
        ),
        responses={200: "Cow Milk Rate updated successfully"}
    )
    def update_cow_milk_rate(self, request, pk=None):
        vendor = self.get_object(pk)
        if not vendor:
            return not_found_response("Vendor Business Registration not found")
        cr = request.data.get('cr')
        if cr is None:
            return error_response("Cow Milk Rate is required")
        vendor.cr = cr
        vendor.save()
        return success_response("Cow Milk Rate updated successfully")

    @action(detail=False, methods=['get'], url_path='available-vendors')
    @swagger_auto_schema(
        operation_summary="List Available Vendors by Capacity",
        operation_description="Retrieve a list of vendors who have enough milk capacity for a new customer.",
        manual_parameters=[
            openapi.Parameter('milk_requirement', openapi.IN_QUERY, description="Total milk requirement of the customer in litres", type=openapi.TYPE_NUMBER, required=True)
        ],
        responses={200: VendorBusinessRegistrationSerializer(many=True)}
    )
    def available_vendors(self, request):
        try:
            milk_requirement_str = request.query_params.get('milk_requirement')
            if not milk_requirement_str:
                return error_response("Milk requirement is required.", status_code=status.HTTP_400_BAD_REQUEST)

            try:
                milk_requirement = float(milk_requirement_str)
            except ValueError:
                return error_response("Invalid milk requirement. Please provide a number.", status_code=status.HTTP_400_BAD_REQUEST)

            # Use prefetch_related to avoid N+1 queries
            vendors = VendorBusinessRegistration.objects.prefetch_related('customers').all()
            available_vendors = []

            for vendor in vendors:
                # Calculate allocated milk from prefetched customers
                allocated_milk = sum(
                    (c.cow_milk_litre or 0) + (c.buffalo_milk_litre or 0)
                    for c in vendor.customers.all()
                )

                available_capacity = vendor.total_milk_capacity - allocated_milk

                if available_capacity >= milk_requirement:
                    available_vendors.append(vendor)

            serializer = self.get_serializer_class()(available_vendors, many=True)
            return success_response("Available vendors fetched successfully", serializer.data)

        except Exception as e:
            return error_response(f"Failed to fetch available vendors: {str(e)}", status_code=500)