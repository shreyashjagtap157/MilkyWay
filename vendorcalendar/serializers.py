from rest_framework import serializers
from .models import DeliveryRecord, MilkmanLeaveRequest, CustomerRequest


# Serializer for vendor calendar
class DeliveryCalendarSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = ["date", "status", "delivery_type"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    """Serializer for MilkmanLeaveRequest - kept name for backward compatibility"""
    class Meta:
        model = MilkmanLeaveRequest
        fields = "__all__"


class CustomerRequestSerializer(serializers.ModelSerializer):
    """Serializer for CustomerRequest model (leave and extra milk requests)"""
    # Expose audit trail and extra milk delivery fields explicitly for clarity
    extra_milk_delivery_time = serializers.TimeField(required=False, allow_null=True)
    extra_milk_delivery_milkman = serializers.PrimaryKeyRelatedField(read_only=True)
    extra_milk_delivery_status = serializers.CharField(read_only=True)
    extra_milk_delivery_marked_at = serializers.DateTimeField(read_only=True)
    extra_milk_delivery_status_history = serializers.JSONField(read_only=True)

    class Meta:
        model = CustomerRequest
        fields = "__all__"


class DeliveryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = "__all__"


class MilkmanLeaveRequestSerializer(serializers.Serializer):
    date = serializers.DateField()
    status = serializers.CharField()
