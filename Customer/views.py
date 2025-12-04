import logging
from datetime import date, timedelta

# Third-party imports
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

# Django imports
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.hashers import make_password

# Local application imports
from .models import Bill, BillLineItem, Customer, Complaint, MilkRequirement
from .serializers import (
    BillSerializer,
    BillLineItemSerializer,
    CustomerSerializer,
    CustomerUpdateSerializer,
    ComplaintSerializer,
    MilkRequirementSerializer,
    LegacyCustomerSerializer,
)
from Customer.billing_utils import generate_bill_for_period
from OneWindowHomeSolution.core_utils import format_address
from OneWindowHomeSolution.responses import success_response, error_response, not_found_response
from vendorcalendar.models import DeliveryRecord

logger = logging.getLogger(__name__)


class LegacyCustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = LegacyCustomerSerializer

    def list(self, request, *args, **kwargs):
        customers = self.get_queryset()
        serializer = self.get_serializer(customers, many=True)
        return Response({'status': 'success', 'legacy_customers': serializer.data})

    def retrieve(self, request, *args, **kwargs):
        customer = self.get_object()
        serializer = self.get_serializer(customer)
        return Response({'status': 'success', 'legacy_customer': serializer.data})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'status': 'success', 'legacy_customer': serializer.data}, status=status.HTTP_201_CREATED)
        return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        customer = self.get_object()
        serializer = self.get_serializer(customer, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({'status': 'success', 'legacy_customer': serializer.data})
        return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        customer = self.get_object()
        serializer = self.get_serializer(customer, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'status': 'success', 'legacy_customer': serializer.data})
        return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        customer = self.get_object()
        customer.delete()
        return Response({'status': 'success', 'message': 'Legacy customer deleted'})


# ---------------- Customer ViewSet ----------------
class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    @swagger_auto_schema(
        operation_summary="Show current bill for the authenticated customer (from last paid bill end date or first delivery)",
        responses={
            200: openapi.Response(
                description="Current bill for the customer",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'bill': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                'customer': openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                                'vendor': openapi.Schema(type=openapi.TYPE_INTEGER, example=2),
                                'start_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                'end_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-31'),
                                'total_amount': openapi.Schema(type=openapi.TYPE_STRING, example='1200.00'),
                                'status': openapi.Schema(type=openapi.TYPE_STRING, example='pending'),
                                'payment': openapi.Schema(type=openapi.TYPE_INTEGER, example=10),
                                'created_at': openapi.Schema(type=openapi.FORMAT_DATETIME, example='2025-10-31T12:00:00Z'),
                                'total_regular_cow': openapi.Schema(type=openapi.TYPE_NUMBER, example=15.5),
                                'total_regular_buffalo': openapi.Schema(type=openapi.TYPE_NUMBER, example=10.0),
                                'total_extra_cow': openapi.Schema(type=openapi.TYPE_NUMBER, example=2.0),
                                'total_extra_buffalo': openapi.Schema(type=openapi.TYPE_NUMBER, example=1.0),
                                'line_items': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                            'date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                            'description': openapi.Schema(type=openapi.TYPE_STRING, example='Regular delivery'),
                                            'quantity': openapi.Schema(type=openapi.TYPE_STRING, example='1.00'),
                                            'rate': openapi.Schema(type=openapi.TYPE_STRING, example='40.00'),
                                            'amount': openapi.Schema(type=openapi.TYPE_STRING, example='40.00'),
                                            'is_extra': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                            'is_leave': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                            'is_unsuccessful': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                            'delivery_record': openapi.Schema(type=openapi.TYPE_INTEGER, example=1001),
                                        },
                                    ),
                                ),
                            },
                        ),
                    },
                ),
            )
        },
        tags=["Billing"]
    )
    @action(detail=False, methods=['get'], url_path='bills', permission_classes=[IsAuthenticated])
    def list_bills(self, request):
        """
        Get or create a bill for the authenticated customer.
        
        This endpoint:
        1. Checks for an existing pending bill for this customer
        2. If found, updates it with any new unpaid deliveries
        3. If not found, creates a new bill with all unpaid deliveries
        4. Returns the bill from the database (persisted, not just calculated)
        
        When the bill is paid, its status changes to 'paid' and all linked
        delivery records are marked as bill_paid=True.
        """
        from Customer.billing_utils import get_or_create_customer_bill
        from django.db.models import Sum
        
        customer = request.user
        if not isinstance(customer, Customer):
            return Response({'status': 'error', 'message': 'Only customers can view bills.'}, status=400)

        # Get vendor
        vendor = customer.provider
        if not vendor:
            return Response({'status': 'success', 'bill': None, 'message': 'No vendor assigned to this customer.'})

        # Get or create the bill (this persists to database)
        bill, error_message = get_or_create_customer_bill(customer, vendor)
        
        if error_message and not bill:
            return Response({'status': 'success', 'bill': None, 'message': error_message})
        
        if not bill:
            return Response({'status': 'success', 'bill': None, 'message': 'No unpaid deliveries found for this customer.'})
        
        # Calculate summary totals from line items
        line_items = bill.line_items.all()
        
        # Regular deliveries (is_extra=False)
        regular_cow_total = line_items.filter(
            is_extra=False, 
            description__icontains='cow'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        regular_buffalo_total = line_items.filter(
            is_extra=False, 
            description__icontains='buffalo'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Extra deliveries (is_extra=True)
        extra_cow_total = line_items.filter(
            is_extra=True, 
            description__icontains='cow'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        extra_buffalo_total = line_items.filter(
            is_extra=True, 
            description__icontains='buffalo'
        ).aggregate(total=Sum('quantity'))['total'] or 0
        
        # Serialize the bill
        bill_data = BillSerializer(bill).data
        
        # Add summary fields
        bill_data['total_regular_cow'] = float(regular_cow_total)
        bill_data['total_regular_buffalo'] = float(regular_buffalo_total)
        bill_data['total_extra_cow'] = float(extra_cow_total)
        bill_data['total_extra_buffalo'] = float(extra_buffalo_total)
        
        return Response({
            'status': 'success', 
            'bill': bill_data, 
            'message': 'Bill retrieved/updated successfully. Status: ' + bill.status
        })

    @swagger_auto_schema(
        operation_summary="Get details of a specific bill for the authenticated customer",
        manual_parameters=[
            openapi.Parameter('bill_id', openapi.IN_PATH, description="ID of the bill", type=openapi.TYPE_INTEGER)
        ],
        responses={
            200: openapi.Response(
                description="Bill details",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'bill': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                'customer': openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                                'vendor': openapi.Schema(type=openapi.TYPE_INTEGER, example=2),
                                'start_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                'end_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-31'),
                                'total_amount': openapi.Schema(type=openapi.TYPE_STRING, example='1200.00'),
                                'status': openapi.Schema(type=openapi.TYPE_STRING, example='pending'),
                                'payment': openapi.Schema(type=openapi.TYPE_INTEGER, example=10),
                                'created_at': openapi.Schema(type=openapi.FORMAT_DATETIME, example='2025-10-31T12:00:00Z'),
                                'line_items': openapi.Schema(
                                    type=openapi.TYPE_ARRAY,
                                    items=openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                            'date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                            'description': openapi.Schema(type=openapi.TYPE_STRING, example='Regular delivery'),
                                            'quantity': openapi.Schema(type=openapi.TYPE_STRING, example='1.00'),
                                            'rate': openapi.Schema(type=openapi.TYPE_STRING, example='40.00'),
                                            'amount': openapi.Schema(type=openapi.TYPE_STRING, example='40.00'),
                                            'is_extra': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                            'is_leave': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                            'is_unsuccessful': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                            'delivery_record': openapi.Schema(type=openapi.TYPE_INTEGER, example=1001),
                                        },
                                    ),
                                ),
                            },
                        ),
                    },
                ),
            )
        },
        tags=["Billing"]
    )
    @action(detail=True, methods=['get'], url_path='bills/(?P<bill_id>[^/.]+)', permission_classes=[IsAuthenticated])
    def bill_detail(self, request, id=None, bill_id=None):
        """Get details of a specific bill for the authenticated customer"""
        customer = self.get_object()
        bill = get_object_or_404(Bill, id=bill_id, customer=customer)
        serializer = BillSerializer(bill)
        return Response({'status': 'success', 'bill': serializer.data})

    @swagger_auto_schema(
        operation_summary="List all paid bills and payment details for the authenticated customer",
        responses={
            200: openapi.Response(
                description="List of paid bills",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'paid_bills': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                    'customer': openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                                    'vendor': openapi.Schema(type=openapi.TYPE_INTEGER, example=2),
                                    'start_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                    'end_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-31'),
                                    'total_amount': openapi.Schema(type=openapi.TYPE_STRING, example='1200.00'),
                                    'status': openapi.Schema(type=openapi.TYPE_STRING, example='paid'),
                                    'payment': openapi.Schema(type=openapi.TYPE_INTEGER, example=10),
                                    'created_at': openapi.Schema(type=openapi.FORMAT_DATETIME, example='2025-10-31T12:00:00Z'),
                                    'line_items': openapi.Schema(
                                        type=openapi.TYPE_ARRAY,
                                        items=openapi.Schema(
                                            type=openapi.TYPE_OBJECT,
                                            properties={
                                                'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                                'date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                                'description': openapi.Schema(type=openapi.TYPE_STRING, example='Regular delivery'),
                                                'quantity': openapi.Schema(type=openapi.TYPE_STRING, example='1.00'),
                                                'rate': openapi.Schema(type=openapi.TYPE_STRING, example='40.00'),
                                                'amount': openapi.Schema(type=openapi.TYPE_STRING, example='40.00'),
                                                'is_extra': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                                'is_leave': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                                'is_unsuccessful': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                                                'delivery_record': openapi.Schema(type=openapi.TYPE_INTEGER, example=1001),
                                            },
                                        ),
                                    ),
                                },
                            ),
                        ),
                    },
                ),
            )
        },
        tags=["Billing"]
    )
    @action(detail=True, methods=['get'], url_path='payment-history', permission_classes=[IsAuthenticated])
    def payment_history(self, request, id=None):
        """List all paid bills and payment details for the authenticated customer"""
        customer = self.get_object()
        bills = Bill.objects.filter(customer=customer, status='paid').order_by('-created_at')
        serializer = BillSerializer(bills, many=True)
        return Response({'status': 'success', 'paid_bills': serializer.data})

    @swagger_auto_schema(
        operation_summary="List all bills (pending and paid) for the authenticated customer",
        responses={
            200: openapi.Response(
                description="List of all bills",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'status': openapi.Schema(type=openapi.TYPE_STRING, example='success'),
                        'bills': openapi.Schema(
                            type=openapi.TYPE_ARRAY,
                            items=openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'id': openapi.Schema(type=openapi.TYPE_INTEGER, example=1),
                                    'customer': openapi.Schema(type=openapi.TYPE_INTEGER, example=5),
                                    'vendor': openapi.Schema(type=openapi.TYPE_INTEGER, example=2),
                                    'start_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-01'),
                                    'end_date': openapi.Schema(type=openapi.FORMAT_DATE, example='2025-10-31'),
                                    'total_amount': openapi.Schema(type=openapi.TYPE_STRING, example='1200.00'),
                                    'status': openapi.Schema(type=openapi.TYPE_STRING, example='pending'),
                                    'payment': openapi.Schema(type=openapi.TYPE_INTEGER, example=None),
                                    'created_at': openapi.Schema(type=openapi.FORMAT_DATETIME, example='2025-10-31T12:00:00Z'),
                                },
                            ),
                        ),
                    },
                ),
            )
        },
        tags=["Billing"]
    )
    @action(detail=True, methods=['get'], url_path='bill-history', permission_classes=[IsAuthenticated])
    def bill_history(self, request, id=None):
        """List all bills (pending and paid) for the customer"""
        customer = self.get_object()
        bills = Bill.objects.filter(customer=customer).order_by('-created_at')
        serializer = BillSerializer(bills, many=True)
        return Response({'status': 'success', 'bills': serializer.data})
    
    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return CustomerUpdateSerializer
        return CustomerSerializer

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['create', 'list']:  # Allow public access for registration and listing
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]

    @swagger_auto_schema(
        operation_summary="Register new customer",
        operation_description="Register a new customer account with detailed address fields.",
        request_body=CustomerSerializer,
        responses={
            201: openapi.Response(
                description="Customer created successfully",
                schema=CustomerSerializer
            ),
            400: openapi.Response(
                description="Validation error"
            )
        },
        tags=['Customer Registration']
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # Let the serializer handle hashing and field cleanup
            customer = serializer.save()

            # Create combined address for response
            customer_location = format_address(
                flat_no=getattr(customer, "flat_no", None),
                building=getattr(customer, "society_name", None),
                village=getattr(customer, "village", None),
                tal=getattr(customer, "tal", None),
                dist=getattr(customer, "dist", None),
                state=getattr(customer, "state", None),
                pincode=getattr(customer, "pincode", None),
            )

            # Output contact as string, not as UniquePhoneNumber object
            contact_str = customer.contact.phone_number if customer.contact else None

            # Custom response format
            response_data = {
                "id": customer.id,
                "first_name": customer.first_name,
                "last_name": customer.last_name,
                "email": customer.email,
                "contact": contact_str,
                "location": customer_location,
                "provider": customer.provider.id if customer.provider else None,
                "pincode": customer.pincode,
            }

            return Response(response_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_summary="List all customers",
        operation_description="Get a list of all registered customers. No authentication required.",
        responses={
            200: openapi.Response(
                description="List of customers",
                schema=CustomerSerializer(many=True)
            )
        },
        tags=['Customer Management']
    )
    def list(self, request, *args, **kwargs):
        """List all customers - publicly accessible"""
        customers = self.get_queryset()
        serializer = self.get_serializer(customers, many=True)
        return Response({'status': 'success', 'customers': serializer.data})

    @swagger_auto_schema(
        operation_summary="Get customer details",
        operation_description="Get details of a specific customer. Authentication required.",
        responses={
            200: openapi.Response(
                description="Customer details",
                schema=CustomerSerializer
            ),
            401: openapi.Response(
                description="Authentication required"
            ),
            404: openapi.Response(
                description="Customer not found"
            )
        },
        tags=['Customer Management']
    )
    def retrieve(self, request, *args, **kwargs):
        """Get specific customer details - requires authentication"""
        logger.info(f"Retrieving customer details for ID: {kwargs.get('pk')}")
        response = super().retrieve(request, *args, **kwargs)
        
        # Log the response data to verify pincode is included
        if hasattr(response, 'data'):
            logger.info(f"Customer retrieve response - ID: {response.data.get('id')}, Pincode: {response.data.get('pincode')}, Pincode type: {type(response.data.get('pincode'))}")
            logger.info(f"Full customer data keys: {list(response.data.keys())}")
        
        return response

    @swagger_auto_schema(
        operation_summary="Update customer",
        operation_description="Update customer information. Authentication required.",
        request_body=CustomerUpdateSerializer,
        responses={
            200: openapi.Response(
                description="Customer updated successfully",
                schema=CustomerSerializer
            ),
            401: openapi.Response(
                description="Authentication required"
            ),
            404: openapi.Response(
                description="Customer not found"
            )
        },
        tags=['Customer Management']
    )
    def update(self, request, *args, **kwargs):
        """Update customer - requires authentication"""
        logger.info(f"Updating customer ID: {kwargs.get('pk')}")
        logger.info(f"Update data received - Pincode: {request.data.get('pincode')}, Type: {type(request.data.get('pincode'))}")
        logger.info(f"Full update data keys: {list(request.data.keys())}")
        
        response = super().update(request, *args, **kwargs)
        
        if hasattr(response, 'data'):
            logger.info(f"Customer update response - ID: {response.data.get('id')}, Pincode: {response.data.get('pincode')}")
        
        return response

    @swagger_auto_schema(
        operation_summary="Partial update customer",
        operation_description="Partially update customer information. Authentication required.",
        request_body=CustomerUpdateSerializer,
        responses={
            200: openapi.Response(
                description="Customer updated successfully",
                schema=CustomerSerializer
            ),
            401: openapi.Response(
                description="Authentication required"
            ),
            404: openapi.Response(
                description="Customer not found"
            )
        },
        tags=['Customer Management']
    )
    def partial_update(self, request, *args, **kwargs):
        """Partially update customer - requires authentication"""
        logger.info(f"Partially updating customer ID: {kwargs.get('pk')}")
        logger.info(f"Partial update data received - Pincode: {request.data.get('pincode')}, Type: {type(request.data.get('pincode'))}")
        logger.info(f"Full partial update data keys: {list(request.data.keys())}")
        
        response = super().partial_update(request, *args, **kwargs)
        
        if hasattr(response, 'data'):
            logger.info(f"Customer partial update response - ID: {response.data.get('id')}, Pincode: {response.data.get('pincode')}")
        
        return response
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Delete customer",
        operation_description="Delete a customer account. Authentication required.",
        responses={
            204: openapi.Response(
                description="Customer deleted successfully"
            ),
            401: openapi.Response(
                description="Authentication required"
            ),
            404: openapi.Response(
                description="Customer not found"
            )
        },
        tags=['Customer Management']
    )
    def destroy(self, request, *args, **kwargs):
        """Delete customer - requires authentication and clean up UniquePhoneNumber"""
        instance = self.get_object()
        serializer = self.get_serializer()
        serializer.delete(instance)
        return Response({'status': 'success', 'message': 'Customer deleted'}, status=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(
        operation_summary="Update FCM Token",
        operation_description="Update the FCM token for a customer.",
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
        customer = self.get_object()
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            return error_response("FCM token is required")
        customer.fcm_token = fcm_token
        customer.save()
        return success_response("FCM token updated successfully")


# ---------------- Milk Requirement ViewSet ----------------
class MilkRequirementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    queryset = MilkRequirement.objects.all()
    serializer_class = MilkRequirementSerializer

    @swagger_auto_schema(auto_schema=None)
    def get_object(self, id):
        try:
            return MilkRequirement.objects.get(id=id)
        except MilkRequirement.DoesNotExist:
            return None

    def perform_create(self, serializer):
        customer = Customer.objects.get(user=self.request.user)
        serializer.save(customer=customer)

    @swagger_auto_schema(
        operation_summary="List Milk Requirements",
        operation_description="Retrieve a list of all milk requirements.",
        responses={200: MilkRequirementSerializer(many=True)}
    )
    def list(self, request):
        milk_requirements = MilkRequirement.objects.all()
        serializer = self.serializer_class(milk_requirements, many=True)
        return success_response("Milk requirements fetched successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Retrieve Milk Requirement",
        operation_description="Get details of a specific milk requirement by its ID.",
        responses={200: MilkRequirementSerializer()},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milk Requirement ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def retrieve(self, request, id=None):
        milk_requirement = self.get_object(id)
        if not milk_requirement:
            return not_found_response("Milk requirement not found")
        serializer = self.serializer_class(milk_requirement)
        return success_response("Milk requirement retrieved successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Create Milk Requirement",
        operation_description="Create a new milk requirement.",
        request_body=MilkRequirementSerializer,
        responses={201: MilkRequirementSerializer()}
    )
    def create(self, request):
        self.permission_classes = [AllowAny]  # Allow any user to create a milk requirement
        self.check_permissions(request)
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return success_response("Milk requirement created successfully", serializer.data, status_code=status.HTTP_201_CREATED)
        return error_response("Failed to create milk requirement", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Update Milk Requirement",
        operation_description="Update all details of an existing milk requirement.",
        request_body=MilkRequirementSerializer,
        responses={200: MilkRequirementSerializer()},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milk Requirement ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def update(self, request, id=None):
        milk_requirement = self.get_object(id)
        if not milk_requirement:
            return not_found_response("Milk requirement not found")
        serializer = self.serializer_class(milk_requirement, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return success_response("Milk requirement updated successfully", serializer.data)
        return error_response("Failed to update milk requirement", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Partially Update Milk Requirement",
        operation_description="Update selected fields of an existing milk requirement.",
        request_body=MilkRequirementSerializer,
        responses={200: MilkRequirementSerializer()},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milk Requirement ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def partial_update(self, request, id=None):
        milk_requirement = self.get_object(id)
        if not milk_requirement:
            return not_found_response("Milk requirement not found")
        serializer = self.serializer_class(milk_requirement, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success_response("Milk requirement partially updated successfully", serializer.data)
        return error_response("Failed to partially update milk requirement", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Delete Milk Requirement",
        operation_description="Delete a milk requirement by its ID.",
        responses={204: "No Content"},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Milk Requirement ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def destroy(self, request, id=None):
        milk_requirement = self.get_object(id)
        if not milk_requirement:
            return not_found_response("Milk requirement not found")
        milk_requirement.delete()
        return success_response("Milk requirement deleted successfully", status_code=status.HTTP_204_NO_CONTENT)


# ---------------- Complaint ViewSet ----------------
class ComplaintViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ComplaintSerializer

    @swagger_auto_schema(
        operation_summary="List Complaints",
        operation_description="Retrieve a list of all complaints.",
        responses={200: openapi.Response("List of complaints", ComplaintSerializer(many=True))}
    )
    def list(self, request):
        complaints = Complaint.objects.all()
        serializer = self.serializer_class(complaints, many=True, context={'request': request})
        return success_response("Complaints fetched successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Retrieve Complaint",
        operation_description="Get details of a specific complaint by its ID.",
        responses={200: openapi.Response("Complaint details", ComplaintSerializer())},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Complaint ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def retrieve(self, request, id=None):
        complaint = get_object_or_404(Complaint, pk=id)
        serializer = self.serializer_class(complaint, context={'request': request})
        return success_response("Complaint retrieved successfully", serializer.data)

    @swagger_auto_schema(
        operation_summary="Create Complaint",
        operation_description="Submit a new complaint.",
        request_body=ComplaintSerializer,
        responses={201: openapi.Response("Complaint created", ComplaintSerializer())}
    )
    def create(self, request):
        self.permission_classes = [AllowAny]  # Allow any user to create a complaint
        self.check_permissions(request)
        serializer = self.serializer_class(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success_response("Complaint created successfully", serializer.data, status_code=status.HTTP_201_CREATED)
        return error_response("Failed to create complaint", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Update Complaint",
        operation_description="Update all details of an existing complaint.",
        request_body=ComplaintSerializer,
        responses={200: openapi.Response("Complaint updated", ComplaintSerializer())},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Complaint ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def update(self, request, id=None):
        complaint = get_object_or_404(Complaint, pk=id)
        serializer = self.serializer_class(complaint, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success_response("Complaint updated successfully", serializer.data)
        return error_response("Failed to update complaint", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Partially Update Complaint",
        operation_description="Update selected fields of an existing complaint.",
        request_body=ComplaintSerializer,
        responses={200: openapi.Response("Complaint partially updated", ComplaintSerializer())},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Complaint ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def partial_update(self, request, id=None):
        complaint = get_object_or_404(Complaint, pk=id)
        serializer = self.serializer_class(complaint, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return success_response("Complaint partially updated successfully", serializer.data)
        return error_response("Failed to partially update complaint", serializer.errors)

    @swagger_auto_schema(
        operation_summary="Delete Complaint",
        operation_description="Delete a complaint by its ID.",
        responses={204: openapi.Response("No Content")},
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_PATH, description="Complaint ID", type=openapi.TYPE_INTEGER)
        ]
    )
    def destroy(self, request, id=None):
        complaint = get_object_or_404(Complaint, pk=id)
        complaint.delete()
        return success_response("Complaint deleted successfully", status_code=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(
        operation_summary="Cancel Extra Milk Request",
        operation_description="Cancel an extra milk request before delivery happens.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'delivery_history_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the delivery record")
            },
            required=['delivery_history_id']
        ),
        responses={200: "Extra milk request cancelled successfully"}
    )
    def cancel_extra_milk(self, request):
        delivery_history_id = request.data.get('delivery_history_id')
        if not delivery_history_id:
            return error_response("Delivery history ID is required")

        try:
            record = DeliveryRecord.objects.get(id=delivery_history_id, status='delivered')
        except DeliveryRecord.DoesNotExist:
            return error_response("Delivery record not found or already cancelled")

        record.status = 'cancelled'
        record.remarks = 'Cancelled by customer before delivery'
        record.save()

        return success_response("Extra milk request cancelled successfully")

    @swagger_auto_schema(
        operation_summary="Cancel Leave Request",
        operation_description="Cancel a leave request before the leave period starts.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'leave_request_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the leave request")
            },
            required=['leave_request_id']
        ),
        responses={200: "Leave request cancelled successfully"}
    )
    def cancel_leave(self, request):
        leave_request_id = request.data.get('leave_request_id')
        if not leave_request_id:
            return error_response("Leave request ID is required")

        try:
            leave_request = LeaveRequest.objects.get(id=leave_request_id, status='approved')
        except LeaveRequest.DoesNotExist:
            return error_response("Leave request not found or already cancelled")

        leave_request.status = 'cancelled'
        leave_request.save()

        return success_response("Leave request cancelled successfully")