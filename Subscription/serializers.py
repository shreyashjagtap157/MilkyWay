from rest_framework import serializers

from .models import SubscribedVendor, Payment


class SubscribedVendorSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    vendor_id = serializers.IntegerField(source="vendor.id", read_only=True)
    plan_name = serializers.CharField(source="plan.plan_name", read_only=True)
    plan_id = serializers.IntegerField(source="plan.id", read_only=True)
    plan_price = serializers.DecimalField(source="plan.price", max_digits=8, decimal_places=2, read_only=True)
    plan_duration = serializers.CharField(source="plan.duration", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    days_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = SubscribedVendor
        fields = [
            'id', 'vendor_id', 'vendor_name', 'plan_id', 'plan_name', 'plan_price', 'plan_duration',
            'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature',
            'payment_status', 'subscription_status',
            'plan_purchase_date', 'plan_start_date', 'plan_expiry_date',
            'is_active', 'days_remaining',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'is_active', 'days_remaining']


class CreateSubscriptionOrderSerializer(serializers.Serializer):
    """Serializer for creating a vendor subscription order"""
    subscription_plan_id = serializers.IntegerField(help_text="ID of the subscription plan to purchase")


class VerifySubscriptionPaymentSerializer(serializers.Serializer):
    """Serializer for verifying subscription payment"""
    razorpay_order_id = serializers.CharField(max_length=255)
    razorpay_payment_id = serializers.CharField(max_length=255)
    razorpay_signature = serializers.CharField(max_length=255)


class SubscriptionSummarySerializer(serializers.Serializer):
    duration_days = serializers.IntegerField()
    count = serializers.IntegerField()


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model with read-only computed fields"""
    payer_name = serializers.CharField(read_only=True)
    payer_type = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = [
            'id', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature',
            'payment_type', 'amount', 'currency', 'status', 
            'payer_name', 'payer_type', 'payer_object_id',
            'subscription_plan', 'description', 'notes', 'receipt',
            'created_at', 'updated_at', 'payment_completed_at'
        ]
        read_only_fields = ['razorpay_order_id', 'created_at', 'updated_at']
    
    def get_payer_type(self, obj):
        """Get the payer's user type"""
        if obj.payer_content_type:
            return obj.payer_content_type.model
        return None


class CreatePaymentOrderSerializer(serializers.Serializer):
    """Serializer for creating a Razorpay payment order"""
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, help_text="Amount in INR")
    # Accept case-insensitive values for payment_type (e.g., 'Bill' or 'bill')
    payment_type = serializers.CharField(help_text="Type of payment: 'subscription' or 'bill'")
    subscription_plan_id = serializers.IntegerField(required=False, allow_null=True, 
                                                    help_text="Required for subscription payments only")
    description = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.JSONField(required=False, allow_null=True)
    
    def validate(self, data):
        """Normalize and validate payment_type and ensure subscription_plan_id when needed.

        - Accepts case-insensitive 'subscription' or 'bill' for payment_type.
        - Requires subscription_plan_id only when payment_type == 'subscription'.
        """
        payment_type = data.get('payment_type')
        if isinstance(payment_type, str):
            payment_type_norm = payment_type.strip().lower()
            if payment_type_norm not in ('subscription', 'bill'):
                raise serializers.ValidationError({
                    'payment_type': "Invalid payment_type. Must be 'subscription' or 'bill'."
                })
            # normalize back into validated data
            data['payment_type'] = payment_type_norm
        else:
            raise serializers.ValidationError({
                'payment_type': "This field must be a string specifying 'subscription' or 'bill'."
            })

        if data.get('payment_type') == 'subscription' and not data.get('subscription_plan_id'):
            raise serializers.ValidationError({
                'subscription_plan_id': 'This field is required for subscription payments.'
            })

        # For bill payments, subscription_plan_id is not required
        return data


class VerifyPaymentSerializer(serializers.Serializer):
    """Serializer for verifying Razorpay payment"""
    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=255)


class PaymentHistorySerializer(serializers.ModelSerializer):
    """Detailed serializer for payment history"""
    payer_name = serializers.CharField(read_only=True)
    payer_type = serializers.SerializerMethodField()
    subscription_plan_name = serializers.CharField(source='subscription_plan.plan_name', read_only=True, allow_null=True)
    payee_name = serializers.CharField(source='payee.username', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'razorpay_order_id', 'razorpay_payment_id', 
            'payment_type', 'amount', 'currency', 'status',
            'payer_name', 'payer_type', 'payer_object_id',
            'payee_name', 'subscription_plan_name', 
            'description', 'receipt', 'notes',
            'created_at', 'updated_at', 'payment_completed_at'
        ]
    
    def get_payer_type(self, obj):
        """Get the payer's user type"""
        if obj.payer_content_type:
            model_name = obj.payer_content_type.model
            # Map model names to readable types
            type_map = {
                'vendorbusinessregistration': 'vendor',
                'customer': 'customer',
                'milkman': 'milkman'
            }
            return type_map.get(model_name, model_name)
        return None
