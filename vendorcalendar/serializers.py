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


class DeliveryAdjustmentSerializer(serializers.ModelSerializer):
    """Serializer for unified delivery adjustment requests"""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_phone = serializers.CharField(source='customer.contact_str', read_only=True)
    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    adjustment_type = serializers.SerializerMethodField()
    
    # Show regular quantities for comparison
    regular_cow_milk = serializers.DecimalField(
        source='customer.cow_milk_litre', 
        read_only=True, 
        max_digits=5, 
        decimal_places=2
    )
    regular_buffalo_milk = serializers.DecimalField(
        source='customer.buffalo_milk_litre', 
        read_only=True, 
        max_digits=5, 
        decimal_places=2
    )
    
    # Computed fields
    is_leave = serializers.BooleanField(read_only=True)
    is_extra_milk = serializers.BooleanField(read_only=True)
    is_reduced_quantity = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = CustomerRequest
        fields = [
            'id',
            'customer',
            'customer_name',
            'customer_phone',
            'vendor',
            'vendor_name',
            'date',
            'request_type',
            'regular_cow_milk',
            'regular_buffalo_milk',
            'requested_cow_milk',
            'requested_buffalo_milk',
            'adjustment_type',
            'is_leave',
            'is_extra_milk',
            'is_reduced_quantity',
            'reason',
            'status',
            'rejection_reason',
            'extra_milk_delivery_time',
            'extra_milk_delivery_milkman',
            'created_at',
            'approved_rejected_at',
        ]
        read_only_fields = ['created_at', 'approved_rejected_at']
    
    def get_adjustment_type(self, obj):
        return obj.get_adjustment_type()


class DeliveryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = "__all__"


class MilkmanLeaveRequestSerializer(serializers.Serializer):
    date = serializers.DateField()
    status = serializers.CharField()
