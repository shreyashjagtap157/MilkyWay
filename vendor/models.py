from django.db import models
import random
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from BusinessRegistration.models import VendorBusinessRegistration


# Request Model for Customers and Milkmen to join a Vendor
class JoinRequest(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    
    # Generic foreign key to support both Customer and Milkman
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, default=1)
    object_id = models.PositiveIntegerField(default=0)
    requester = GenericForeignKey('content_type', 'object_id')
    
    vendor = models.ForeignKey(VendorBusinessRegistration, on_delete=models.CASCADE)

    user_type = models.CharField(
        max_length=10,
        choices=[("customer", "Customer"), ("milkman", "Milkman")],
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=10,
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("withdrawn", "Withdrawn"),
            ("cancelled", "Cancelled"),
            ("separated", "Separated"),
        ],
        default="pending",
    )
    
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Join Request"
        verbose_name_plural = "Join Requests"
        indexes = [
            models.Index(fields=['vendor', 'status']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['user_type', 'status']),
            models.Index(fields=['rejected_at']),
        ]

    def __str__(self):
        return f"{self.name} → {self.vendor.name} ({self.user_type})"

    @property
    def user_object(self):
        """Return the actual user object (Customer or Milkman)"""
        return self.requester

    @property
    def user_contact(self):
        """Return the contact/phone number string of the requester."""
        if self.user_type == "customer":
            contact = getattr(self.requester, 'contact', None)
            if contact:
                return contact.phone_number  # Return the string, not the model
            return None
        elif self.user_type == "milkman":
            phone = getattr(self.requester, 'phone_number', None)
            if phone:
                return phone.phone_number  # Return the string, not the model
            return None
        return None

    @property
    def milk_requirement(self):
        """Fetch the milk requirement of the customer creating the join request."""
        if self.user_type == "customer":
            return {
                "cow_milk_litre": getattr(self.requester, 'cow_milk_litre', None),
                "buffalo_milk_litre": getattr(self.requester, 'buffalo_milk_litre', None)
            }
        return None

    def is_customer_accepted(self):
        """
        Check if the customer has been accepted by the vendor.
        Returns True if the status is 'accepted', otherwise False.
        """
        return self.status == "accepted"


# OTP Verification Model
class OTPVerification(models.Model):
    phone_number = models.CharField(max_length=15, default="9999999999")
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def generate_otp(self):
        self.otp = str(random.randint(100000, 999999))
        self.save()
