from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.auth.hashers import check_password
from django.contrib.auth import get_user_model
from BusinessRegistration.models import VendorBusinessRegistration
from Customer.models import Customer
from Milkman.models import Milkman

class CustomTokenObtainView(APIView):
    """
    Custom JWT token view for Customer, Milkman, VendorBusinessRegistration.
    Generates tokens compatible with CustomJWTAuthentication (adds user_type & user_id).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        contact = request.data.get("contact")
        password = request.data.get("password")

        if not contact or not password:
            return Response({
                "status": "failed",
                "message": "Both contact and password are required"
            }, status=status.HTTP_400_BAD_REQUEST)

        user_obj = None
        user_type = None
        display_name = ""
        contact_value = contact

        def passwords_match(raw_password, stored_password):
            if not stored_password:
                return False
            try:
                return check_password(raw_password, stored_password)
            except Exception:
                return raw_password == stored_password

        # Try Vendor (by contact)
        vendor = VendorBusinessRegistration.objects.filter(contact__iexact=contact).first()
        if vendor and passwords_match(password, vendor.password):
            user_obj = vendor
            user_type = "vendor"
            display_name = getattr(vendor, "name", "")
            contact_value = vendor.contact or contact_value

        # Try Milkman (by phone_number)
        if not user_obj:
            milkman = Milkman.objects.filter(phone_number__iexact=contact).first()
            if milkman and passwords_match(password, milkman.password):
                user_obj = milkman
                user_type = "milkman"
                display_name = getattr(milkman, "full_name", "") or getattr(milkman, "name", "")
                contact_value = milkman.phone_number or contact_value

        # Try Customer (by contact)
        if not user_obj:
            customer = Customer.objects.filter(contact__iexact=contact).first()
            if customer and passwords_match(password, customer.password):
                user_obj = customer
                user_type = "customer"
                first_name = getattr(customer, "first_name", "")
                last_name = getattr(customer, "last_name", "")
                full_name = f"{first_name} {last_name}".strip()
                display_name = full_name or getattr(customer, "name", "")
                contact_value = customer.contact or contact_value

        if not user_obj:
            return Response({
                "status": "failed",
                "message": "Invalid contact or password"
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Create or get a Django user for proper JWT generation and blacklisting
        DjangoUser = get_user_model()
        django_user, _ = DjangoUser.objects.get_or_create(
            username=f"{user_type}_{user_obj.id}",
            defaults={"is_active": True}
        )

        # Generate proper JWT tokens and attach custom claims
        refresh = RefreshToken.for_user(django_user)
        refresh['user_type'] = user_type
        refresh['user_id'] = user_obj.id
        refresh['name'] = display_name

        return Response({
            "status": "success",
            "message": "Login successful",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "userID": user_obj.id,
            "role": user_type,
            "name": display_name,
            "contact": contact_value,
        }, status=status.HTTP_200_OK)


class TokenRefreshView(APIView):
    """Refresh access token using refresh token"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({"detail": "Refresh token required"}, status=400)
        try:
            refresh = RefreshToken(refresh_token)
            access = str(refresh.access_token)
            return Response({"access": access}, status=200)
        except Exception as e:
            return Response({"detail": "Invalid refresh token", "error": str(e)}, status=401)


class LogoutView(APIView):
    """Blacklist all tokens for the authenticated user (global logout)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        try:
            tokens = OutstandingToken.objects.filter(user=user)
            for t in tokens:
                BlacklistedToken.objects.get_or_create(token=t)
            return Response({"status": "success", "message": "Logged out successfully"}, status=200)
        except Exception as e:
            return Response({"status": "failed", "message": "Logout failed", "error": str(e)}, status=500)
