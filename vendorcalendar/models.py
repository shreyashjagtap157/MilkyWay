
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
    """Customer requests for leave or extra milk that need vendor approval"""
    REQUEST_TYPE_CHOICES = [
        ("leave", "Leave - Don't Deliver"),
        ("extra_milk", "Extra Milk"),
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

    def __str__(self):
        return f"{self.customer} - {self.get_request_type_display()} on {self.date} ({self.status})"

    def clean(self):
        super().clean()
        if self.request_type == "extra_milk":
            if (self.cow_milk_extra is None or self.cow_milk_extra == 0) and (self.buffalo_milk_extra is None or self.buffalo_milk_extra == 0):
                raise ValidationError("At least one of cow_milk_extra or buffalo_milk_extra is required for extra milk requests.")


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