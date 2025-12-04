from django.utils.timezone import now, timedelta
from rest_framework import serializers

from BusinessRegistration.models import VendorBusinessRegistration as Vendor
from Customer.models import Customer


class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower().strip()
        if (
            not Vendor.objects.filter(email__iexact=value).exists()
            and not Customer.objects.filter(email__iexact=value).exists()
        ):
            raise serializers.ValidationError("No vendor or customer with this email.")
        return value


class VerifyOTPResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=6)

    def validate(self, data):

        email = data["email"].lower().strip()
        otp = data["otp"]

        user = None
        model = None

        # First check in Vendor
        try:
            user = Vendor.objects.get(email__iexact=email, otp=otp)
            model = "vendor"
        except Vendor.DoesNotExist:
            # Then check in Customer
            try:
                user = Customer.objects.get(email__iexact=email, otp=otp)
                model = "customer"
            except Customer.DoesNotExist:
                raise serializers.ValidationError("Invalid OTP or email.")

        if user.otp_created_at and now() - user.otp_created_at > timedelta(minutes=5):
            raise serializers.ValidationError("OTP expired.")

        data["user"] = user
        data["model"] = model
        return data


# Role Based Login Serializers
class LoginSerializer(serializers.Serializer):
    contact = serializers.CharField()
    password = serializers.CharField()
    fcm_token = serializers.CharField(required=False, allow_blank=True, allow_null=True, 
                                     help_text="FCM token for push notifications")


# # Vendor (Service Provider) Login Serializer
# class VendorLoginSerializer(serializers.Serializer):
#     contact = serializers.CharField()
#     password = serializers.CharField()


# Admin Login Serializer
class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)

    class Meta:
        ref_name = "VendorLoginAdminLoginSerializer"


class RoleLoginResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=["vendor", "milkman", "customer"])
    name = serializers.CharField(allow_blank=True, required=False)
    location = serializers.CharField(allow_blank=True, required=False)
    access = serializers.CharField()
    refresh = serializers.CharField()
    contact = serializers.CharField(allow_blank=True, required=False)

