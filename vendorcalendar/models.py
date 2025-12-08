
from django.db import models
from Customer.models import Customer
from BusinessRegistration.models import VendorBusinessRegistration
from django.core.exceptions import ValidationError


class DeliveryRecord(models.Model):
    """Records of actual delivery outcomes only - what actually happened"""
    STATUS_CHOICES = [
        ("delivered", "Delivered"),
        ("not_delivered", "Not Delivered"),
        ("cancelled", "Cancelled"),
        ("missed", "Missed"),
    ]
    DELIVERY_TYPE_CHOICES = [
        ("regular", "Regular"),
        ("extra", "Extra"),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='delivery_records')
    vendor = models.ForeignKey(VendorBusinessRegistration, on_delete=models.CASCADE, null=True, blank=True)
    milkman = models.ForeignKey('Milkman.Milkman', on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="delivered")
    delivery_type = models.CharField(max_length=10, choices=DELIVERY_TYPE_CHOICES, default="regular", help_text="Type of delivery: regular or extra")

    # Extra milk delivered on this delivery record (recorded when vendor approves an extra_milk request
    # or when milkman marks delivery with extras). These fields are separate from CustomerRequest
    # so milkman/distributor can see the extra amounts directly on the delivery record.
    cow_milk_extra = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    buffalo_milk_extra = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    bill = models.ForeignKey('Customer.Bill', null=True, blank=True, on_delete=models.SET_NULL, related_name='delivery_records')
    bill_paid = models.BooleanField(default=False, help_text="True if this delivery has been paid for in a bill.")

    class Meta:
        unique_together = ("customer", "date", "delivery_type")
        ordering = ['-date']

    def __str__(self):
        return f"{self.customer} on {self.date} ({self.delivery_type}): {self.get_status_display()}"


class CustomerRequest(models.Model):
    """
    Unified customer request for ANY delivery quantity change on a specific date.
    Handles leave, extra milk, and quantity adjustment workflows in one model.
    """
    REQUEST_TYPE_CHOICES = [
        ("leave", "Leave - Don't Deliver"),
        ("extra_milk", "Extra Milk"),
        ("quantity_adjustment", "Quantity Adjustment"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='service_requests')
    vendor = models.ForeignKey(VendorBusinessRegistration, on_delete=models.CASCADE, related_name='customer_requests')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES)
    date = models.DateField(db_index=True)
    # Deprecated: quantity is replaced by cow_milk_extra and buffalo_milk_extra for extra milk requests
    quantity = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="(Deprecated) Quantity of extra milk (in liters, decimals allowed)")
    cow_milk_extra = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Extra cow milk requested (liters, decimals allowed)")
    buffalo_milk_extra = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Extra buffalo milk requested (liters, decimals allowed)")
    
    # NEW: Unified requested quantities for delivery adjustments
    # If both are 0, it's a "leave" request
    # If higher than regular, it's "extra milk"
    # If lower than regular, it's "reduced quantity"
    requested_cow_milk = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Requested cow milk quantity for this date (liters). 0 for skip/leave."
    )
    requested_buffalo_milk = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Requested buffalo milk quantity for this date (liters). 0 for skip/leave."
    )
    reason = models.TextField(
        blank=True, 
        null=True,
        help_text="Reason for delivery adjustment"
    )
    
    # Extra milk delivery assignment and tracking fields
    extra_milk_delivery_time = models.TimeField(null=True, blank=True, help_text="Requested time for extra milk delivery")
    extra_milk_delivery_milkman = models.ForeignKey('Milkman.Milkman', null=True, blank=True, on_delete=models.SET_NULL, related_name='extra_milk_deliveries', help_text="Milkman assigned for extra milk delivery (defaults to customer's milkman if not set)")
    extra_milk_delivery_status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('delivered', 'Delivered'), ('unsuccessful', 'Unsuccessful')], default='pending', help_text="Delivery status for extra milk request", db_index=True)
    extra_milk_delivery_marked_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when extra milk delivery was marked delivered/unsuccessful")
    # Audit trail for extra milk delivery status changes
    extra_milk_delivery_status_history = models.JSONField(null=True, blank=True, help_text="Audit trail of extra milk delivery status changes (list of dicts with timestamp, status, user)")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", db_index=True)
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection if request was rejected")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_rejected_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ("customer", "date", "request_type")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', 'date', 'status']),
            models.Index(fields=['vendor', 'status', 'date']),
        ]

    def __str__(self):
        if self.request_type == "quantity_adjustment":
            return f"{self.customer} - {self.get_adjustment_type()} on {self.date} ({self.status})"
        return f"{self.customer} - {self.get_request_type_display()} on {self.date} ({self.status})"

    def get_adjustment_type(self):
        """Determine what type of adjustment this is based on requested quantities"""
        if self.request_type != "quantity_adjustment":
            return self.get_request_type_display()
        
        customer = self.customer
        regular_cow = customer.cow_milk_litre or 0
        regular_buffalo = customer.buffalo_milk_litre or 0
        
        requested_cow = self.requested_cow_milk or 0
        requested_buffalo = self.requested_buffalo_milk or 0
        
        # Leave (no delivery)
        if requested_cow == 0 and requested_buffalo == 0:
            return "Leave/Skip Delivery"
        
        # Extra milk
        if requested_cow > regular_cow or requested_buffalo > regular_buffalo:
            return "Extra Milk Request"
        
        # Reduced quantity
        if requested_cow < regular_cow or requested_buffalo < regular_buffalo:
            return "Reduced Quantity"
        
        return "Delivery Adjustment"
    
    @property
    def is_leave(self):
        """Check if this is a leave request (either explicit leave type or 0 quantities)"""
        if self.request_type == "leave":
            return True
        if self.request_type == "quantity_adjustment":
            return (self.requested_cow_milk or 0) == 0 and (self.requested_buffalo_milk or 0) == 0
        return False
    
    @property
    def is_extra_milk(self):
        """Check if this requests more than regular quantity"""
        if self.request_type == "extra_milk":
            return True
        if self.request_type == "quantity_adjustment":
            customer = self.customer
            regular_cow = customer.cow_milk_litre or 0
            regular_buffalo = customer.buffalo_milk_litre or 0
            
            requested_cow = self.requested_cow_milk or 0
            requested_buffalo = self.requested_buffalo_milk or 0
            
            return requested_cow > regular_cow or requested_buffalo > regular_buffalo
        return False
    
    @property
    def is_reduced_quantity(self):
        """Check if this requests less than regular quantity (but not zero)"""
        if self.request_type != "quantity_adjustment":
            return False
        
        customer = self.customer
        regular_cow = customer.cow_milk_litre or 0
        regular_buffalo = customer.buffalo_milk_litre or 0
        
        requested_cow = self.requested_cow_milk or 0
        requested_buffalo = self.requested_buffalo_milk or 0
        
        # Must be less than regular but at least one > 0
        has_some_milk = requested_cow > 0 or requested_buffalo > 0
        is_reduced = (requested_cow < regular_cow) or (requested_buffalo < regular_buffalo)
        
        return has_some_milk and is_reduced

    def clean(self):
        super().clean()
        if self.request_type == "extra_milk":
            if (self.cow_milk_extra is None or self.cow_milk_extra == 0) and (self.buffalo_milk_extra is None or self.buffalo_milk_extra == 0):
                raise ValidationError("At least one of cow_milk_extra or buffalo_milk_extra is required for extra milk requests.")
        
        if self.request_type == "quantity_adjustment":
            # At least one quantity must be specified
            if self.requested_cow_milk is None and self.requested_buffalo_milk is None:
                raise ValidationError("At least one milk type quantity must be specified for quantity adjustment.")
            
            # Quantities cannot be negative
            if (self.requested_cow_milk is not None and self.requested_cow_milk < 0) or \
               (self.requested_buffalo_milk is not None and self.requested_buffalo_milk < 0):
                raise ValidationError("Milk quantities cannot be negative.")


class MilkmanLeaveRequest(models.Model):
    """Milkman leave requests for time off - affects availability for all customers"""
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    milkman = models.ForeignKey('Milkman.Milkman', on_delete=models.CASCADE, related_name='leave_requests')
    vendor = models.ForeignKey(VendorBusinessRegistration, on_delete=models.CASCADE, related_name='milkman_leave_requests')
    start_date = models.DateField(db_index=True)
    end_date = models.DateField()
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", db_index=True)
    rejection_reason = models.TextField(blank=True, null=True, help_text="Reason for rejection if leave was rejected")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_rejected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Leave request for {self.milkman} from {self.start_date} to {self.end_date} ({self.status})"