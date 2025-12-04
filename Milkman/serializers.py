from rest_framework import serializers

# Django imports
from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.db import transaction

# Local application imports
from Milkman.models import Milkman as LegacyMilkman
from .models import Milkman
from Systemadmin.models import UniquePhoneNumber
from Systemadmin.utils import check_phone_number_availability

class LegacyMilkmanSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegacyMilkman
        fields = '__all__'


class MilkmanSerializer(serializers.ModelSerializer):
    @transaction.atomic
    def delete(self, instance):
        """Delete milkman and clean up UniquePhoneNumber"""
        if instance.phone_number:
            instance.phone_number.delete()
        instance.delete()
    confirm_password = serializers.CharField(write_only=True, required=False)
    phone_number = serializers.CharField(required=True, write_only=True)
    pincode = serializers.IntegerField(required=False, allow_null=True, help_text="Postal code of the milkman's address")

    class Meta:
        model = Milkman
        fields = [
            'id', 'full_name', 'phone_number', 'flat_house', 'village', 'tal', 'dist', 'state',
            'society_name', 'password', 'confirm_password', 'provider', 'pincode'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'provider': {'required': False, 'allow_null': True}
        }

    def validate_phone_number(self, value):
        """Validate phone number uniqueness"""
        if not value:
            raise serializers.ValidationError("Phone number is required")
        
        # Check if phone number already exists in UniquePhoneNumber table
        if UniquePhoneNumber.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError({
                "error": "User already exists",
                "message": "Phone number is already registered. Please login instead.",
                "code": 409,
                "field": "phone_number"
            })
        
        return value

    def to_internal_value(self, data):
        """Convert incoming data and handle special cases for provider"""

        # Handle provider being 0, "0", empty string, or null
        if 'provider' in data and data['provider'] in [0, '0', '', None]:
            data = data.copy()  # Make a mutable copy
            data['provider'] = None

        return super().to_internal_value(data)

    @staticmethod
    def validate_provider(value):
        """Custom validation for provider field"""
        if value is None:
            return None

        # Resolve VendorBusinessRegistration lazily via app registry to avoid circular imports
        VendorBusinessRegistration = apps.get_model('BusinessRegistration', 'VendorBusinessRegistration')

        try:
            if isinstance(value, int):
                return VendorBusinessRegistration.objects.get(pk=value)
            return value
        except VendorBusinessRegistration.DoesNotExist:
            raise serializers.ValidationError("Invalid provider ID")

    def validate(self, data):
        """Check that password and confirm_password match (if both provided)"""
        password = data.get('password')
        confirm_password = self.initial_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            raise serializers.ValidationError("Passwords don't match")

        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create milkman instance, ensure UniquePhoneNumber is correct, and sync phone_number_str."""
        phone_number = validated_data.pop('phone_number', None)
        password = validated_data.get('password')
        if password:
            validated_data['password'] = make_password(password)
        validated_data.pop('confirm_password', None)

        # Always create or get UniquePhoneNumber with correct user_type
        if phone_number:
            phone_obj, created = UniquePhoneNumber.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    'user_type': 'milkman',
                    'user_id': None
                }
            )
            if phone_obj.user_type != 'milkman':
                phone_obj.user_type = 'milkman'
                phone_obj.save()
            validated_data['phone_number'] = phone_obj
            validated_data['phone_number_str'] = phone_obj.phone_number
        else:
            validated_data['phone_number'] = None
            validated_data['phone_number_str'] = None

        milkman = super().create(validated_data)

        if phone_number:
            phone_obj.user_id = milkman.id
            phone_obj.save()

        return milkman

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update milkman instance, handle phone number updates, UniquePhoneNumber sync, and phone_number_str."""
        phone_number = validated_data.pop('phone_number', None)
        password = validated_data.pop('password', None)
        if password:
            instance.password = make_password(password)

        validated_data.pop('confirm_password', None)

        if phone_number:
            if instance.phone_number and instance.phone_number.phone_number != phone_number:
                instance.phone_number.delete()

            phone_obj, created = UniquePhoneNumber.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    'user_type': 'milkman',
                    'user_id': instance.id
                }
            )
            if phone_obj.user_type != 'milkman':
                phone_obj.user_type = 'milkman'
                phone_obj.save()
            phone_obj.user_id = instance.id
            phone_obj.save()
            instance.phone_number = phone_obj
            instance.phone_number_str = phone_obj.phone_number

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    @transaction.atomic
    def delete(self, instance):
        """Delete milkman and clean up UniquePhoneNumber"""
        if instance.phone_number:
            instance.phone_number.delete()
        instance.delete()

    def to_representation(self, instance):
        """Customize the output representation"""
        data = super().to_representation(instance)
        data.pop('fcm_token', None)  # Exclude fcm_token from read-type methods

        if data.get('provider') is None:
            data['provider'] = None

        # Output phone number as string, not as UniquePhoneNumber object
        if hasattr(instance, 'phone_number') and instance.phone_number:
            data['phone_number'] = instance.phone_number.phone_number
        else:
            data['phone_number'] = None

        return data


class MilkmanUpdateSerializer(MilkmanSerializer):
    phone_number = serializers.CharField(read_only=True)
    password = serializers.CharField(read_only=True)

    class Meta(MilkmanSerializer.Meta):
        pass