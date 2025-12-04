from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import VendorBusinessRegistration
from Systemadmin.models import UniquePhoneNumber
from django.contrib.auth.hashers import make_password
from django.db import transaction
from Systemadmin.utils import check_phone_number_availability


class VendorBusinessRegistrationSerializer(serializers.ModelSerializer):
    @transaction.atomic
    def delete(self, instance):
        """Delete vendor and clean up UniquePhoneNumber"""
        if instance.contact:
            instance.contact.delete()
        instance.delete()
    confirm_password = serializers.CharField(write_only=True, required=True)
    contact = serializers.CharField(required=True, write_only=True)
    br = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    buffalo_milk_litre = serializers.IntegerField(required=False)

    # Subfields for cow milk litres and rates
    gir_cow_milk_litre = serializers.IntegerField(required=False)
    jarshi_cow_milk_litre = serializers.IntegerField(required=False)
    deshi_milk_litre = serializers.IntegerField(required=False)
    gir_cow_rate = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    jarshi_cow_rate = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    deshi_cow_rate = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    cr = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)  # Replaced field for Cow Milk Rate
    request_status = serializers.SerializerMethodField()
    total_milk_capacity = serializers.ReadOnlyField()
    total_cow_milk_capacity = serializers.ReadOnlyField()
    pincode = serializers.IntegerField(required=False, allow_null=True, help_text="Postal code of the vendor's address")

    class Meta:
        model = VendorBusinessRegistration
        fields = [
            'id', 'name', 'contact', 'flat_house', 'society_area', 'village', 'tal', 'dist', 'state',
            'password', 'confirm_password', 'buffalo_milk_litre', 'br',
            'gir_cow_milk_litre', 'jarshi_cow_milk_litre', 'deshi_milk_litre',
            'gir_cow_rate', 'jarshi_cow_rate', 'deshi_cow_rate', 'cr', 'email', 'request_status',
            'total_milk_capacity', 'total_cow_milk_capacity', 'pincode'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate_contact(self, value):
        """Validate phone number uniqueness"""
        if not value:
            raise serializers.ValidationError("Contact number is required")
        
        # Check if phone number already exists in UniquePhoneNumber table
        if UniquePhoneNumber.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError({
                "error": "User already exists",
                "message": "Phone number is already registered. Please login instead.",
                "code": 409,
                "field": "contact"
            })
        
        return value

    def validate(self, data):
        """Check that password and confirm_password match"""
        password = data.get('password')
        confirm_password = data.pop('confirm_password', None)

        if password and confirm_password and password != confirm_password:
            raise serializers.ValidationError("Passwords don't match")

        return data

    @transaction.atomic
    def create(self, validated_data):
        """Create and return a new Vendor with phone number foreign key and ensure UniquePhoneNumber is correct. Also sync contact_str."""
        contact_phone = validated_data.pop('contact', None)
        password = validated_data.get('password')
        if password:
            validated_data['password'] = make_password(password)

        validated_data.pop('confirm_password', None)

        if contact_phone:
            phone_obj, created = UniquePhoneNumber.objects.get_or_create(
                phone_number=contact_phone,
                defaults={
                    'user_type': 'vendor',
                    'user_id': None
                }
            )
            if phone_obj.user_type != 'vendor':
                phone_obj.user_type = 'vendor'
                phone_obj.save()
            validated_data['contact'] = phone_obj
            validated_data['contact_str'] = phone_obj.phone_number
        else:
            validated_data['contact'] = None
            validated_data['contact_str'] = None

        vendor = super().create(validated_data)

        if contact_phone:
            phone_obj.user_id = vendor.id
            phone_obj.save()

        return vendor

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update vendor and handle phone number updates, UniquePhoneNumber sync, and contact_str."""
        contact_phone = validated_data.pop('contact', None)
        password = validated_data.pop('password', None)
        if password:
            instance.password = make_password(password)
        validated_data.pop('confirm_password', None)

        if contact_phone:
            if instance.contact and instance.contact.phone_number != contact_phone:
                instance.contact.delete()

            phone_obj, created = UniquePhoneNumber.objects.get_or_create(
                phone_number=contact_phone,
                defaults={
                    'user_type': 'vendor',
                    'user_id': instance.id
                }
            )
            if phone_obj.user_type != 'vendor':
                phone_obj.user_type = 'vendor'
                phone_obj.save()
            phone_obj.user_id = instance.id
            phone_obj.save()
            instance.contact = phone_obj
            instance.contact_str = phone_obj.phone_number

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    @transaction.atomic
    def delete(self, instance):
        """Delete vendor and clean up UniquePhoneNumber"""
        if instance.contact:
            instance.contact.delete()
        instance.delete()

    def to_representation(self, instance):
        """Customize the output representation."""
        data = super().to_representation(instance)
        data.pop('fcm_token', None)  # Exclude fcm_token from read-type methods

        # Output phone number as string, not as UniquePhoneNumber object
        if hasattr(instance, 'contact') and instance.contact:
            data['contact'] = instance.contact.phone_number
        else:
            data['contact'] = None

        return data

    def get_request_status(self, obj):
        user_type = self.context.get('user_type')
        user_id = self.context.get('user_id')
        return obj.request_status_for(user_type, user_id)


class BusinessRegistrationSummarySerializer(serializers.Serializer):
    name = serializers.CharField()
    location = serializers.CharField()
    totalCustomers = serializers.IntegerField()
    defaulters = serializers.IntegerField()
    paidCustomers = serializers.IntegerField()
    totalMilkmans = serializers.IntegerField()
    pendingJoinRequests = serializers.IntegerField()


class VendorBusinessRegistrationUpdateSerializer(VendorBusinessRegistrationSerializer):
    contact = serializers.CharField(read_only=True)
    password = serializers.CharField(read_only=True)

    class Meta(VendorBusinessRegistrationSerializer.Meta):
        pass