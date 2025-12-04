
# Standard library imports
import logging

# Third-party imports
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.db import transaction
from django.contrib.auth.hashers import make_password

# Local app imports
from .models import Bill, BillLineItem, Customer, Complaint, MilkRequirement
from BusinessRegistration.models import VendorBusinessRegistration
from Milkman.models import Milkman
from Systemadmin.models import UniquePhoneNumber
from Systemadmin.utils import check_phone_number_availability
from vendorcalendar.models import DeliveryRecord

logger = logging.getLogger(__name__)

# --- Billing Serializers ---

class BillLineItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillLineItem
        fields = [
            'id', 'date', 'description', 'quantity', 'rate', 'amount',
            'is_extra', 'is_leave', 'is_unsuccessful', 'delivery_record'
        ]

class BillSerializer(serializers.ModelSerializer):
    line_items = BillLineItemSerializer(many=True, read_only=True)

    class Meta:
        model = Bill
        fields = [
            'id', 'customer', 'vendor', 'start_date', 'end_date',
            'total_amount', 'status', 'payment', 'created_at', 'line_items'
        ]

class CustomerSerializer(serializers.ModelSerializer):
    @transaction.atomic
    def delete(self, instance):
        """Delete customer and clean up UniquePhoneNumber"""
        if instance.contact:
            instance.contact.delete()
        instance.delete()
    confirm_password = serializers.CharField(write_only=True, required=False)
    provider = serializers.PrimaryKeyRelatedField(
        queryset=VendorBusinessRegistration.objects.all(),
        required=False,
        allow_null=True
    )
    milkman = serializers.PrimaryKeyRelatedField(
        queryset=Milkman.objects.all(),
        required=False,
        allow_null=True
    )
    email = serializers.CharField(
        required=False,
        allow_blank=True,
        validators=[UniqueValidator(queryset=Customer.objects.all(), message="Email must be unique.")]
    )
    contact = serializers.CharField(required=True, write_only=True)
    pincode = serializers.IntegerField(required=False, allow_null=True, help_text="Postal code of the customer's address")

    class Meta:
        model = Customer
        fields = [
            'id', 'first_name', 'last_name', 'email', 'contact', 'flat_no', 'society_name', 'village', 'tal', 'dist', 'state',
            'provider', 'milkman', 'cow_milk_litre', 'buffalo_milk_litre',
            'password', 'confirm_password', 'service_start_date', 'service_end_date', 'pincode'
        ]
        extra_kwargs = {
            'password': {'write_only': True},
            'confirm_password': {'write_only': True},
            'provider': {'required': False, 'allow_null': True},
            'milkman': {'required': False, 'allow_null': True},
            'cow_milk_litre': {'required': False, 'allow_null': True},
            'buffalo_milk_litre': {'required': False, 'allow_null': True}
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

    def to_internal_value(self, data):
        # Handle provider and milkman being 0, '', or None
        if 'provider' in data and data['provider'] in [0, '0', '', None]:
            data = data.copy()
            data['provider'] = None

        if 'milkman' in data and data['milkman'] in [0, '0', '', None]:
            data = data.copy()
            data['milkman'] = None
            
        # Handle cow_milk_litre and buffalo_milk_litre being "string"
        if 'cow_milk_litre' in data and data['cow_milk_litre'] == 'string':
            data = data.copy()
            data['cow_milk_litre'] = None
            
        if 'buffalo_milk_litre' in data and data['buffalo_milk_litre'] == 'string':
            data = data.copy()
            data['buffalo_milk_litre'] = None

        return super().to_internal_value(data)

    def validate(self, data):
        password = data.get('password')
        confirm_password = data.pop('confirm_password', None)

        if password and confirm_password and password != confirm_password:
            raise serializers.ValidationError("Passwords don't match")

        return data

    @transaction.atomic
    def create(self, validated_data):
        contact_phone = validated_data.pop('contact', None)
        password = validated_data.get('password')
        if password:
            validated_data['password'] = make_password(password)

        if contact_phone:
            phone_obj, created = UniquePhoneNumber.objects.get_or_create(
                phone_number=contact_phone,
                defaults={
                    'user_type': 'customer',
                    'user_id': None
                }
            )
            if phone_obj.user_type != 'customer':
                phone_obj.user_type = 'customer'
                phone_obj.save()
            validated_data['contact'] = phone_obj
            validated_data['contact_str'] = phone_obj.phone_number
        else:
            validated_data['contact'] = None
            validated_data['contact_str'] = None

        customer = super().create(validated_data)

        if contact_phone:
            phone_obj.user_id = customer.id
            phone_obj.save()

        return customer

    @transaction.atomic
    def update(self, instance, validated_data):
        contact_phone = validated_data.pop('contact', None)
        password = validated_data.pop('password', None)

        if password:
            instance.password = make_password(password)

        if contact_phone:
            if instance.contact and instance.contact.phone_number != contact_phone:
                instance.contact.delete()

            phone_obj, created = UniquePhoneNumber.objects.get_or_create(
                phone_number=contact_phone,
                defaults={
                    'user_type': 'customer',
                    'user_id': instance.id
                }
            )
            if phone_obj.user_type != 'customer':
                phone_obj.user_type = 'customer'
                phone_obj.save()
            phone_obj.user_id = instance.id
            phone_obj.save()
            instance.contact = phone_obj
            instance.contact_str = phone_obj.phone_number

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop('fcm_token', None)  # Exclude fcm_token from read-type methods
        if data.get('provider') is None:
            data['provider'] = None
        if data.get('milkman') is None:
            data['milkman'] = None

        # Output phone number as string, not as UniquePhoneNumber object
        if hasattr(instance, 'contact') and instance.contact:
            data['contact'] = instance.contact.phone_number
        else:
            data['contact'] = None

        # Log pincode serialization for debugging
        logger.info(f"CustomerSerializer.to_representation - Customer ID: {instance.id}, "
                   f"Pincode from instance: {instance.pincode} (type: {type(instance.pincode)}), "
                   f"Pincode in serialized data: {data.get('pincode')} (type: {type(data.get('pincode'))})")

        return data

class LegacyCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = '__all__'

class MilkRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = MilkRequirement
        fields = '__all__'

class DeliveryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = ['id', 'customer', 'vendor', 'milkman', 'date', 'status']

class CustomerUpdateSerializer(CustomerSerializer):
    contact = serializers.CharField(read_only=True)
    password = serializers.CharField(read_only=True)
    confirm_password = serializers.CharField(read_only=True)

    class Meta(CustomerSerializer.Meta):
        pass