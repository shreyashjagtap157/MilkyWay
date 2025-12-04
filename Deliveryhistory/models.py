from django.db import models
from Customer.models import Customer
from BusinessRegistration.models import VendorBusinessRegistration
from Milkman.models import Milkman
from django.core.exceptions import ValidationError
import datetime

DELIVERY_STATUS_CHOICES = [
    ("delivered", "Delivered"),
    ("leave", "Leave"),
    ("not_delivered", "Not Delivered"),
]

NON_DELIVERY_REASON_CHOICES = [
    ("customer_unavailable", "Customer Unavailable"),
    ("address_issue", "Address/Location Issue"),
    ("payment_pending", "Payment Pending"),
    ("vehicle_breakdown", "Vehicle Breakdown"),
    ("stock_shortage", "Stock Shortage"),
    ("weather_conditions", "Weather Conditions"),
    ("road_blockage", "Road Blockage"),
    ("customer_cancelled", "Customer Cancelled"),
    ("quality_issue", "Milk Quality Issue"),
    ("other", "Other"),
]


class DeliveryHistory(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    vendor = models.ForeignKey(VendorBusinessRegistration, on_delete=models.SET_NULL, null=True, blank=True)
    distributor = models.ForeignKey(Milkman, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_date = models.DateField()
    milk_quantity = models.DecimalField(max_digits=5, decimal_places=2)
    extra_milk_quantity = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    milk_type = models.CharField(max_length=20)
    status = models.CharField(
        max_length=20, choices=DELIVERY_STATUS_CHOICES, default="not_delivered"
    )
    # Enhanced fields for non-delivery handling
    non_delivery_reason = models.CharField(
        max_length=30, 
        choices=NON_DELIVERY_REASON_CHOICES, 
        blank=True, 
        null=True,
        help_text="Required when status is 'not_delivered'"
    )
    # Tracking fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True, null=True, help_text="Who updated the record")

    def clean(self):
        """Validate the model data"""
        
        # Validate non-delivery reason is provided when status is not_delivered
        if self.status == 'not_delivered' and not self.non_delivery_reason:
            raise ValidationError("Non-delivery reason is required when status is 'not_delivered'")

        # Validate delivery times
        if self.delivery_completed_time and self.status != 'delivered':
            raise ValidationError("Delivery completion time should only be set for delivered status")

    def save(self, *args, **kwargs):
        # Call clean method before saving
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_failed_delivery(self):
        """Check if this is a failed delivery"""
        return self.status == 'not_delivered'

    @property
    def total_milk_delivered(self):
        """Calculate total milk delivered including extra"""
        if self.status == 'delivered':
            return self.milk_quantity + self.extra_milk_quantity
        return 0

    def __str__(self):
        return f"{self.customer.first_name} {self.customer.last_name} - {self.delivery_date} - {self.status}"

    class Meta:
        db_table = "deliveryhistory_deliveryhistory"
        ordering = ['-delivery_date']
        indexes = [
            models.Index(fields=['customer', 'delivery_date']),
            models.Index(fields=['status', 'delivery_date']),
            models.Index(fields=['distributor', 'delivery_date']),
        ]