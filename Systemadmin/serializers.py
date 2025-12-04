from rest_framework import serializers
from django.apps import apps
from Systemadmin.models import Systemadmin, UniquePhoneNumber, NotificationLog


class AdminSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = Systemadmin
        fields = ['id', 'username', 'password', 'is_active', 'is_staff', 'is_superuser', 'fcm_token', 'last_login']
        read_only_fields = ['last_login']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def create(self, validated_data):
        """Create a new admin with properly hashed password"""
        password = validated_data.pop('password', None)
        admin = Systemadmin(**validated_data)
        
        # Use default password if not provided
        if not password:
            password = 'root@1234'
        
        admin.set_password(password)
        admin.save()
        return admin
    
    def update(self, instance, validated_data):
        """Update admin, hashing password if provided"""
        password = validated_data.pop('password', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance


class AdminLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    fcm_token = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                     help_text="FCM token for push notifications")


class UniquePhoneNumberSerializer(serializers.ModelSerializer):
    """
    Serializer for UniquePhoneNumber model.
    Handles phone number registration and lookup across all user types.
    """
    class Meta:
        model = UniquePhoneNumber
        fields = ['id', 'phone_number', 'user_type', 'user_id', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_phone_number(self, value):
        """Ensure phone number is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Phone number cannot be empty.")
        return value.strip()

    def validate(self, data):
        """Validate that the user exists in the respective model"""
        user_type = data.get('user_type')
        user_id = data.get('user_id')
        
        if user_type and user_id:
            
            model_mapping = {
                'vendor': ('BusinessRegistration', 'VendorBusinessRegistration'),
                'milkman': ('Milkman', 'Milkman'),
                'customer': ('Customer', 'Customer'),
            }
            
            if user_type in model_mapping:
                app_label, model_name = model_mapping[user_type]
                Model = apps.get_model(app_label, model_name)
                if not Model.objects.filter(pk=user_id).exists():
                    raise serializers.ValidationError(
                        f"{user_type.capitalize()} with ID {user_id} does not exist."
                    )
        
        return data


class PhoneNumberLookupSerializer(serializers.Serializer):
    """
    Serializer for looking up phone number details.
    Returns user type and user ID for a given phone number.
    """
    phone_number = serializers.CharField(max_length=30, required=True)
    
    def validate_phone_number(self, value):
        """Ensure phone number exists"""
        if not UniquePhoneNumber.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("Phone number not found.")
        return value

class NotificationLogSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationLog model.
    Handles serialization of notification logs, including priority, channel, and read status.
    """
    class Meta:
        model = NotificationLog
        fields = ['id', 'title', 'body', 'data', 'recipient', 'status', 'channel', 'priority', 'read', 'created_at']
        read_only_fields = ['created_at']

