import logging
import re

# Third-party imports
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

# Django imports
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.db.models import Q

# Local application imports
from BusinessRegistration.models import VendorBusinessRegistration
from BusinessRegistration.serializers import VendorBusinessRegistrationSerializer
from Customer.billing_utils import generate_or_update_bills_for_vendor
from Customer.models import Customer
from Milkman.models import Milkman
from OneWindowHomeSolution.core_utils import format_address
from OneWindowHomeSolution.custom_authentication import CustomJWTAuthentication
from vendor.models import OTPVerification
from .serializers import LoginSerializer
from .utils import send_otp_sms

logger = logging.getLogger(__name__)

# Replace all references to User with get_user_model()
User = get_user_model()


class LoginViewSet(viewsets.ViewSet):
    authentication_classes = [CustomJWTAuthentication]
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        if self.action in ['vendor_login', 'request_otp', 'verify_otp', 'change_password', 'register_vendor']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]
        return [permission() for permission in permission_classes]
    
    def create_tokens_for_user(self, user_instance, user_type, user_id):
        """
        Create valid JWT tokens for custom user models
        """
        # Create or get a Django User instance for token generation
        django_user, created = User.objects.get_or_create(
            username=f"{user_type}_{user_id}",
            defaults={
                'is_active': True
            }
        )
        
        # Generate proper JWT tokens using the Django User
        refresh = RefreshToken.for_user(django_user)
        
        # Add custom claims
        refresh['user_type'] = user_type
        refresh['user_id'] = user_id
        refresh['custom_user_data'] = {
            'role': user_type,
            'original_id': user_id
        }
        
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh)
        }

    def passwords_match(self, raw_password, stored_password):
        """Safely compare passwords regardless of stored format (hashed/plain)."""
        if not stored_password:
            return False
        try:
            # Works if stored_password is a valid Django hashed password
            return check_password(raw_password, stored_password)
        except Exception:
            # Fallback for legacy/plaintext storage
            return raw_password == stored_password

    @swagger_auto_schema(
        operation_summary="Role-Based Login",
        operation_description="""
        Authenticate a user based on their role (vendor, milkman, customer) using contact and password.
        
        This endpoint supports authentication for:
        - **Vendors**: Use contact number and password from VendorBusinessRegistration
        - **Milkman**: Use phone number and password from Milkman model  
        - **Customers**: Use contact number and password from Customer model
        
        The returned access token should be included in the Authorization header as:
        `Authorization: Bearer <access_token>`
        """,
        request_body=LoginSerializer,
        responses={
            200: openapi.Response(
                description="Login successful",
                examples={
                    "application/json": {
                        "status": "success",
                        "message": "Login successful",
                        "data": {
                            "user_id": 1,
                            "role": "vendor",
                            "name": "John Doe",
                            "location": "123 Main St",
                            "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                            "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                            "contact": "1234567890"
                        }
                    }
                },
            ),
            400: openapi.Response(
                description="Invalid credentials or missing data",
                examples={
                    "application/json": {
                        "status": "failed", 
                        "message": "Invalid contact or password"
                    }
                }
            ),
        },
        tags=['Authentication - Role Based']
    )
    @action(detail=False, methods=["post"], authentication_classes=[])
    def vendor_login(self, request):
        logger.info("START vendor_login | request data: %s", request.data)
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Invalid data provided for vendor login: %s", serializer.errors)
            return Response({"status": "failed", "message": "Both contact and password are required", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        contact_input = serializer.validated_data.get("contact", "")
        normalized_contact = contact_input.strip()
        digits_only = re.sub(r"\D+", "", normalized_contact)
        # Add both with and without '+' prefix for matching
        contact_candidates = set()
        if normalized_contact:
            contact_candidates.add(normalized_contact)
            if normalized_contact.startswith('+'):
                contact_candidates.add(normalized_contact[1:])
            else:
                contact_candidates.add('+' + normalized_contact)
        if digits_only:
            contact_candidates.add(digits_only)
            contact_candidates.add('+' + digits_only)
        contact_candidates = [c for c in contact_candidates if c]
        password = serializer.validated_data.get("password")
        fcm_token = serializer.validated_data.get("fcm_token")  # Get FCM token from request

        logger.info("Attempting role-based login for contact: %s", contact_input)
        
        # Try Vendor (BusinessRegistration)
        vendor = None
        for cand in contact_candidates:
            # Try exact match first, then fallback to endswith digits-only (handles +country and stored variants)
            vendor = VendorBusinessRegistration.objects.filter(
                Q(contact__phone_number__iexact=cand) |
                Q(contact__phone_number__endswith=digits_only) |
                Q(contact_str__iexact=cand) |
                Q(contact_str__endswith=digits_only)
            ).first()
            if vendor:
                logger.debug("Vendor matched candidate '%s' -> vendor id %s", cand, vendor.id)
                break
        if vendor:
            if self.passwords_match(password, vendor.password):
                # Update FCM token if provided
                if fcm_token:
                    vendor.fcm_token = fcm_token
                    vendor.save(update_fields=['fcm_token'])
                    logger.info(f"Updated FCM token for vendor {vendor.id}")
                # Trigger bill generation for vendor
                try:
                    generate_or_update_bills_for_vendor(vendor)
                except Exception as e:
                    logger.error(f"Bill generation failed for vendor {vendor.id}: {e}")
                # Generate proper JWT tokens
                tokens = self.create_tokens_for_user(vendor, 'vendor', vendor.id)
                logger.info("Vendor login successful for vendor ID: %s", vendor.id)
                data = {
                    "user_id": vendor.id,
                    "role": "vendor",
                    "name": getattr(vendor, "name", ""),
                    "location": format_address(
                        flat_no=getattr(vendor, "flat_house", None),
                        building=getattr(vendor, "society_area", None),
                        village=getattr(vendor, "village", None),
                        tal=getattr(vendor, "tal", None),
                        dist=getattr(vendor, "dist", None),
                        state=getattr(vendor, "state", None),
                    ),
                    "access": tokens['access'],
                    "refresh": tokens['refresh'],
                    "contact": (
                        getattr(vendor.contact, "phone_number", None)
                        or getattr(vendor, "contact_str", None)
                        or normalized_contact
                    )
                }
                logger.info("END vendor_login | success for vendor ID: %s", vendor.id)
                return Response({"status": "success", "message": "Login successful", "data": data}, status=status.HTTP_200_OK)
            else:
                logger.warning("Vendor matched but password mismatch (vendor id=%s) for contact: %s", getattr(vendor, 'id', None), contact_input)

        # Try Milkman
        milkman = None
        for cand in contact_candidates:
            milkman = Milkman.objects.filter(
                Q(phone_number__phone_number__iexact=cand) |
                Q(phone_number__phone_number__endswith=digits_only) |
                Q(phone_number_str__iexact=cand) |
                Q(phone_number_str__endswith=digits_only)
            ).first()
            if milkman:
                logger.debug("Milkman matched candidate '%s' -> milkman id %s", cand, milkman.id)
                break
        if milkman:
            milkman_confirm = getattr(milkman, 'confirm_password', None)  # May not exist; handled by matcher
            if self.passwords_match(password, milkman.password) or self.passwords_match(password, milkman_confirm):
                # Update FCM token if provided
                if fcm_token:
                    milkman.fcm_token = fcm_token
                    milkman.save(update_fields=['fcm_token'])
                    logger.info(f"Updated FCM token for milkman {milkman.id}")
                
                # Generate proper JWT tokens
                tokens = self.create_tokens_for_user(milkman, 'milkman', milkman.id)
                logger.info("Milkman login successful for milkman ID: %s", milkman.id)
                data = {
                    "user_id": milkman.id,
                    "role": "milkman",
                    "name": getattr(milkman, "name", "") or getattr(milkman, "full_name", ""),
                    "location": format_address(
                        flat_no=getattr(milkman, "flat_house", None),
                        village=getattr(milkman, "village", None),
                        tal=getattr(milkman, "tal", None),
                        dist=getattr(milkman, "dist", None),
                        state=getattr(milkman, "state", None),
                    ),
                    "access": tokens['access'],
                    "refresh": tokens['refresh'],
                    "contact": (
                        getattr(milkman.phone_number, "phone_number", None)
                        or getattr(milkman, "phone_number_str", None)
                        or normalized_contact
                    )
                }
                logger.info("END vendor_login | success for milkman ID: %s", milkman.id)
                return Response({"status": "success", "message": "Login successful", "data": data}, status=status.HTTP_200_OK)
            else:
                logger.warning("Milkman found but password mismatch for contact: %s", contact_input)

        # Try Customer
        customer = None
        for cand in contact_candidates:
            customer = Customer.objects.filter(
                Q(contact__phone_number__iexact=cand) |
                Q(contact__phone_number__endswith=digits_only) |
                Q(contact_str__iexact=cand) |
                Q(contact_str__endswith=digits_only)
            ).first()
            if customer:
                logger.debug("Customer matched candidate '%s' -> customer id %s", cand, customer.id)
                break
        if customer:
            if self.passwords_match(password, customer.password) or self.passwords_match(password, getattr(customer, 'confirm_password', None)):
                # Update FCM token if provided
                if fcm_token:
                    customer.fcm_token = fcm_token
                    customer.save(update_fields=['fcm_token'])
                    logger.info(f"Updated FCM token for customer {customer.id}")
                
                # Generate proper JWT tokens
                tokens = self.create_tokens_for_user(customer, 'customer', customer.id)
                logger.info("Customer login successful for customer ID: %s", customer.id)
                full_name = f"{getattr(customer, 'first_name', '')} {getattr(customer, 'last_name', '')}".strip()
                if not full_name:
                    full_name = getattr(customer, 'name', '')
                data = {
                    "user_id": customer.id,
                    "role": "customer",
                    "name": full_name,
                    "location": format_address(
                        flat_no=getattr(customer, "flat_no", None),
                        building=getattr(customer, "society_name", None),
                        village=getattr(customer, "village", None),
                        tal=getattr(customer, "tal", None),
                        dist=getattr(customer, "dist", None),
                        state=getattr(customer, "state", None),
                        pincode=getattr(customer, "pincode", None),
                    ),
                    "access": tokens['access'],
                    "refresh": tokens['refresh'],
                    "contact": (
                        getattr(customer.contact, "phone_number", None)
                        or getattr(customer, "contact_str", None)
                        or normalized_contact
                    )
                }
                logger.info("END vendor_login | success for customer ID: %s", customer.id)
                return Response({"status": "success", "message": "Login successful", "data": data}, status=status.HTTP_200_OK)
            else:
                logger.warning("Customer found but password mismatch for contact: %s", contact_input)

        logger.warning("Role-based login failed for contact: %s - no matching user found or password mismatch", contact_input)
        logger.debug("Login candidates: %s; digits_only: %s", contact_candidates, digits_only)
        logger.info("END vendor_login | failed for contact: %s", contact_input)
        return Response({
            "status": "failed",
            "message": "Invalid contact or password"
        }, status=status.HTTP_400_BAD_REQUEST)

    @swagger_auto_schema(
        operation_summary="Request OTP",
        operation_description="Request an OTP for password reset using phone number.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["phone_number"],
            properties={
                "phone_number": openapi.Schema(type=openapi.TYPE_STRING, description="Phone number registered with the system"),
            },
        ),
        responses={
            200: openapi.Response(
                description="OTP sent successfully",
                examples={"application/json": {"message": "OTP sent successfully"}}
            ),
            400: openapi.Response(
                description="Phone number is required",
                examples={"application/json": {"error": "Phone number is required"}}
            ),
            404: openapi.Response(
                description="Phone number not found",
                examples={"application/json": {"error": "Phone number not found"}}
            ),
            500: openapi.Response(
                description="Failed to send OTP",
                examples={"application/json": {"error": "Failed to send OTP"}}
            ),
        }
    )
    @action(detail=False, methods=["post"], authentication_classes=[])
    def request_otp(self, request):
        logger.info("START request_otp | request data: %s", request.data)
        phone = request.data.get("phone_number")
        if not phone:
            logger.info("END request_otp | missing phone_number")
            return Response({"error": "Phone number is required"}, status=400)
        vendor_exists = VendorBusinessRegistration.objects.filter(
            Q(contact__phone_number=phone) | Q(contact_str=phone)
        ).exists()
        customer_exists = Customer.objects.filter(
            Q(contact__phone_number=phone) | Q(contact_str=phone)
        ).exists()
        if not vendor_exists and not customer_exists:
            logger.info("END request_otp | phone number not found: %s", phone)
            return Response({"error": "Phone number not found"}, status=404)
        otp_obj, _ = OTPVerification.objects.get_or_create(phone_number=phone)
        otp_obj.generate_otp()
        try:
            send_otp_sms(phone, otp_obj.otp)
        except Exception as e:
            logger.error("END request_otp | failed to send OTP: %s", str(e))
            return Response({"error": "Failed to send OTP", "details": str(e)}, status=500)
        logger.info("END request_otp | OTP sent successfully to: %s", phone)
        return Response({"message": "OTP sent successfully"}, status=200)

    @swagger_auto_schema(
        operation_summary="Verify OTP",
        operation_description="Verify the OTP sent to the user's phone number.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["phone_number", "otp"],
            properties={
                "phone_number": openapi.Schema(type=openapi.TYPE_STRING, description="Phone number"),
                "otp": openapi.Schema(type=openapi.TYPE_STRING, description="OTP received"),
            },
        ),
        responses={
            200: openapi.Response(
                description="OTP verified successfully",
                examples={"application/json": {"message": "OTP verified successfully", "user_id": 1, "user_type": "vendor"}}
            ),
            400: openapi.Response(
                description="Missing or invalid data",
                examples={"application/json": {"error": "Phone number and OTP are required"}}
            ),
            404: openapi.Response(
                description="Phone number or user not found",
                examples={"application/json": {"error": "Phone number not found"}}
            ),
        }
    )
    @action(detail=False, methods=["post"], authentication_classes=[])
    def verify_otp(self, request):
        logger.info("START verify_otp | request data: %s", request.data)
        phone = request.data.get("phone_number")
        entered_otp = request.data.get("otp")
        if not phone or not entered_otp:
            logger.info("END verify_otp | missing phone or otp")
            return Response({"error": "Phone number and OTP are required"}, status=400)
        try:
            otp_obj = OTPVerification.objects.get(phone_number=phone)
        except OTPVerification.DoesNotExist:
            logger.info("END verify_otp | phone number not found: %s", phone)
            return Response({"error": "Phone number not found"}, status=404)
        if otp_obj.otp != entered_otp:
            logger.info("END verify_otp | invalid OTP for phone: %s", phone)
            return Response({"error": "Invalid OTP"}, status=400)
        user = VendorBusinessRegistration.objects.filter(
            Q(contact__phone_number=phone) | Q(contact_str=phone)
        ).first()
        if user:
            user_type = "vendor"
        else:
            user = Customer.objects.filter(
                Q(contact__phone_number=phone) | Q(contact_str=phone)
            ).first()
            if user:
                user_type = "customer"
            else:
                logger.info("END verify_otp | user not found for phone: %s", phone)
                return Response({"error": "User not found"}, status=404)
        logger.info("END verify_otp | OTP verified for user_id: %s, user_type: %s", user.id, user_type)
        return Response({"message": "OTP verified successfully", "user_id": user.id, "user_type": user_type}, status=200)

    @swagger_auto_schema(
        operation_summary="Change Password",
        operation_description="Change password for a user after OTP verification.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["phone_number", "new_password"],
            properties={
                "phone_number": openapi.Schema(type=openapi.TYPE_STRING, description="Phone number"),
                "new_password": openapi.Schema(type=openapi.TYPE_STRING, description="New password"),
            },
        ),
        responses={
            200: openapi.Response(
                description="Password changed successfully",
                examples={"application/json": {"message": "Password changed successfully", "user_id": 1, "user_type": "vendor"}}
            ),
            400: openapi.Response(
                description="Missing data",
                examples={"application/json": {"error": "Phone number and new password are required"}}
            ),
            404: openapi.Response(
                description="User not found",
                examples={"application/json": {"error": "User not found"}}
            ),
        }
    )
    @action(detail=False, methods=["post"])
    def change_password(self, request):
        logger.info("START change_password | request data: %s", request.data)
        phone = request.data.get("phone_number")
        new_password = request.data.get("new_password")
        if not phone or not new_password:
            logger.info("END change_password | missing phone or new_password")
            return Response({"error": "Phone number and new password are required"}, status=400)
        user = VendorBusinessRegistration.objects.filter(
            Q(contact__phone_number=phone) | Q(contact_str=phone)
        ).first()
        user_type = "vendor"
        if not user:
            user = Customer.objects.filter(
                Q(contact__phone_number=phone) | Q(contact_str=phone)
            ).first()
            user_type = "customer"
        if not user:
            logger.info("END change_password | user not found for phone: %s", phone)
            return Response({"error": "User not found"}, status=404)
        user.password = make_password(new_password)
        user.save()
        logger.info("END change_password | password changed for user_id: %s, user_type: %s", user.id, user_type)
        return Response({"message": "Password changed successfully", "user_id": user.id, "user_type": user_type}, status=200)

    @swagger_auto_schema(
        operation_summary="List all users",
        operation_description="""
        List all vendors, customers, and milkmen together.
        
        **Authentication required**: This endpoint requires a valid JWT token.
        Include the token in the Authorization header as: `Authorization: Bearer <token>`
        """,
        responses={
            200: openapi.Response(
                description="List of all users",
                examples={
                    "application/json": {
                        "vendors": [{"id": 1, "contact": "sample_vendor", "name": "Vendor Name"}],
                        "customers": [{"id": 2, "contact": "sample_customer", "first_name": "Customer", "last_name": "Name"}],
                        "milkmen": [{"id": 3, "phone_number": "1234567890", "full_name": "Milkman Name"}]
                    }
                }
            ),
            401: openapi.Response(
                description="Authentication required",
                examples={
                    "application/json": {
                        "detail": "Authentication credentials were not provided."
                    }
                }
            )
        },
        tags=['User Management'],
        security=[{'Bearer': []}]  # Indicates this endpoint requires Bearer token
    )
    @action(detail=False, methods=["get"])
    def list_all_users(self, request):
        logger.info("START list_all_users | request by user: %s", getattr(request.user, 'id', None))
        # Paginate vendors
        vendor_paginator = PageNumberPagination()
        vendor_paginator.page_size = 50
        vendors = VendorBusinessRegistration.objects.all()
        vendors_page = vendor_paginator.paginate_queryset(vendors, request, view=self)
        vendor_payload = [
            {
                "id": vendor.id,
                "contact": (
                    getattr(vendor.contact, "phone_number", None)
                    or getattr(vendor, "contact_str", None)
                ),
                "name": vendor.name,
            }
            for vendor in vendors_page
        ]
        vendors_data = vendor_paginator.get_paginated_response(vendor_payload)

        # Paginate customers
        customer_paginator = PageNumberPagination()
        customer_paginator.page_size = 50
        customers = Customer.objects.select_related('contact').all()
        customers_page = customer_paginator.paginate_queryset(customers, request, view=self)
        customer_payload = [
            {
                "id": customer.id,
                "contact": (
                    getattr(customer.contact, "phone_number", None)
                    or getattr(customer, "contact_str", None)
                ),
                "first_name": customer.first_name,
                "last_name": customer.last_name,
            }
            for customer in customers_page
        ]
        customers_data = customer_paginator.get_paginated_response(customer_payload)

        # Paginate milkmen
        milkman_paginator = PageNumberPagination()
        milkman_paginator.page_size = 50
        milkmen = Milkman.objects.select_related('phone_number').all()
        milkmen_page = milkman_paginator.paginate_queryset(milkmen, request, view=self)
        milkmen_payload = [
            {
                "id": milkman.id,
                "phone_number": (
                    getattr(milkman.phone_number, "phone_number", None)
                    or getattr(milkman, "phone_number_str", None)
                ),
                "full_name": milkman.full_name,
            }
            for milkman in milkmen_page
        ]
        milkmen_data = milkman_paginator.get_paginated_response(milkmen_payload)

        logger.info("END list_all_users | vendors: %d, customers: %d, milkmen: %d", len(vendors_data.data), len(customers_data.data), len(milkmen_data.data))
        return Response({
            "vendors": vendors_data.data,
            "customers": customers_data.data,
            "milkmen": milkmen_data.data
        })

    @swagger_auto_schema(
        operation_summary="Register new vendor",
        operation_description="Register a new vendor.",
        request_body=VendorBusinessRegistrationSerializer,
        responses={201: VendorBusinessRegistrationSerializer()}
    )
    @action(detail=False, methods=["post"])
    def register_vendor(self, request):
        logger.info("START register_vendor | request data: %s", request.data)
        serializer = VendorBusinessRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            logger.info("END register_vendor | vendor registered successfully")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning("END register_vendor | failed with errors: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)