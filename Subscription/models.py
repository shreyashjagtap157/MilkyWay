from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone


# Do NOT import VendorBusinessRegistration or DashboardSubscriptionPlan at the top to avoid circular imports



class SubscribedVendor(models.Model):
    """
    Tracks vendor subscription purchases with payment details.
    Stores subscription-specific payment information separately from the main Payment model.
    """
    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
    ]
    
    SUBSCRIPTION_STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('EXPIRED', 'Expired'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Primary relationships
    vendor = models.ForeignKey('BusinessRegistration.VendorBusinessRegistration', on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey('Dashboard.SubscriptionPlan', on_delete=models.CASCADE, related_name='subscribed_vendors')
    
    # Razorpay payment tracking (specific to this subscription purchase)
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True, db_index=True, 
                                         help_text="Razorpay order ID for this subscription")
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True, 
                                           help_text="Razorpay payment ID after successful payment")
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True, 
                                         help_text="Razorpay signature for payment verification")
    
    # Payment and subscription status
    payment_status = models.CharField(max_length=50, choices=PAYMENT_STATUS_CHOICES, default='Pending', db_index=True)
    subscription_status = models.CharField(max_length=50, choices=SUBSCRIPTION_STATUS_CHOICES, default='ACTIVE', db_index=True)
    
    # Subscription dates
    plan_purchase_date = models.DateField(null=True, blank=True, help_text="Date when subscription was purchased")
    plan_start_date = models.DateField(null=True, blank=True, help_text="Date when subscription becomes active")
    plan_expiry_date = models.DateField(null=True, blank=True, help_text="Date when subscription expires (null for lifetime)")
    
    # Device tracking (optional)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'subscription_subscribedvendor'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['vendor', 'subscription_status']),
            models.Index(fields=['payment_status']),
            models.Index(fields=['plan_expiry_date']),
        ]
    
    def __str__(self):
        return f"{self.vendor.name} - {self.plan.plan_name} ({self.subscription_status})"
    
    @property
    def is_active(self):
        """Check if subscription is currently active"""
        if self.subscription_status != 'ACTIVE':
            return False
        if self.plan_expiry_date is None:  # Lifetime subscription
            return True
        return self.plan_expiry_date >= timezone.now().date()
    
    @property
    def days_remaining(self):
        """Calculate days remaining in subscription"""
        if self.plan_expiry_date is None:
            return None  # Lifetime
        if self.subscription_status != 'ACTIVE':
            return 0
        delta = self.plan_expiry_date - timezone.now().date()
        return max(0, delta.days)


class Payment(models.Model):
    """
    Centralized payment tracking for all transactions in the system.
    Tracks both vendor subscription payments and customer bill payments.
    All payments go to admin (systemadmin) who settles with vendors.
    """
    PAYMENT_TYPE_CHOICES = [
        ('subscription', 'Vendor Subscription'),
        ('bill', 'Customer Bill'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('created', 'Created'),
        ('pending', 'Pending'),
        ('authorized', 'Authorized'),
        ('captured', 'Captured'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    
    # Payment identification
    razorpay_order_id = models.CharField(max_length=100, unique=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    razorpay_signature = models.CharField(max_length=255, null=True, blank=True)
    
    # Payment details
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount in INR")
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='created', db_index=True)
    
    # Payer information (generic foreign key for vendor/customer/milkman)
    payer_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='payments_as_payer')
    payer_object_id = models.PositiveIntegerField()
    payer = GenericForeignKey('payer_content_type', 'payer_object_id')
    
    # Payee is always admin from systemadmin
    payee = models.ForeignKey('Systemadmin.Systemadmin', on_delete=models.CASCADE, related_name='payments_received')
    
    # Related records (optional)
    subscription_plan = models.ForeignKey('Dashboard.SubscriptionPlan', on_delete=models.SET_NULL, null=True, blank=True,
                                          help_text="For subscription payments")

    # API user tracking
    user_id = models.PositiveIntegerField(null=True, blank=True, db_index=True, help_text="ID of the user conducting the transaction via API")
    user_role = models.CharField(max_length=50, null=True, blank=True, db_index=True, help_text="Role of the user conducting the transaction (e.g., vendor, customer, milkman)")
    
    # Additional metadata
    description = models.TextField(null=True, blank=True)
    notes = models.JSONField(null=True, blank=True, help_text="Additional payment metadata")
    receipt = models.CharField(max_length=40, null=True, blank=True, help_text="Receipt number")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    payment_completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'subscription_payment'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['payment_type', 'status']),
            models.Index(fields=['payer_content_type', 'payer_object_id']),
            models.Index(fields=['-created_at']),
        ]
    
    def __str__(self):
        return f"{self.payment_type} - {self.razorpay_order_id} - {self.status}"
    
    @property
    def payer_name(self):
        """Get the name of the payer"""
        if hasattr(self.payer, 'name'):
            return self.payer.name
        elif hasattr(self.payer, 'business_name'):
            return self.payer.business_name
        elif hasattr(self.payer, 'full_name'):
            return self.payer.full_name
        return f"User {self.payer_object_id}"
