from rest_framework import serializers
from .models import DeliveryHistory, NON_DELIVERY_REASON_CHOICES, DELIVERY_STATUS_CHOICES


class DeliveryHistorySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.first_name", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    distributor_name = serializers.CharField(source="distributor.name", read_only=True)
    non_delivery_reason_display = serializers.CharField(source="get_non_delivery_reason_display", read_only=True)
    total_milk_delivered = serializers.ReadOnlyField()
    is_failed_delivery = serializers.ReadOnlyField()

    class Meta:
        model = DeliveryHistory
        fields = "__all__"

    def validate(self, data):
        """Custom validation for delivery history"""
        status = data.get('status')
        non_delivery_reason = data.get('non_delivery_reason')

        # Validate non-delivery fields
        if status == 'not_delivered' and not non_delivery_reason:
            raise serializers.ValidationError({
                'non_delivery_reason': 'This field is required when status is not_delivered'
            })

        # Clear non-delivery fields if status is not 'not_delivered'
        elif status in ['delivered', 'leave']:
            data['non_delivery_reason'] = None

        return data


class DeliveryStatusUpdateSerializer(serializers.Serializer):
    """Simplified serializer for status updates"""
    status = serializers.ChoiceField(choices=DELIVERY_STATUS_CHOICES)
    non_delivery_reason = serializers.ChoiceField(
        choices=NON_DELIVERY_REASON_CHOICES, 
        required=False, 
        allow_blank=True
    )
    updated_by = serializers.CharField(max_length=100, required=False)

    def validate(self, data):
        status = data.get('status')

        if status == 'not_delivered' and not data.get('non_delivery_reason'):
            raise serializers.ValidationError({
                'non_delivery_reason': 'Required for not_delivered status'
            })

        return data
