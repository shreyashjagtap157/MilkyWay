from django.db import models
import uuid

# Create your models here.
MILK_QUANTITY_CHOICES = [
    ("half_litre", "Half Litre"),
    ("one_litre", "One Litre"),
    ("two_litre", "Two Litre"),
]

MILK_TYPE_CHOICES = [
    ("cow", "Cow"),
    ("buffalo", "Buffalo"),
]

DELIVERY_TIME_CHOICES = [
    ("morning", "Morning"),
    ("evening", "Evening"),
]


class Customer(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    contact = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(max_length=100, null=True, blank=True)
    address = models.TextField(max_length=100, null=True, blank=True)
    society_name = models.CharField(max_length=100, null=True, blank=True)
    wing = models.CharField(max_length=10, null=True, blank=True)
    floor = models.CharField(max_length=10, null=True, blank=True)
    flat_no = models.CharField(max_length=10, null=True, blank=True)
    start_date = models.CharField(max_length=100, null=True, blank=True)
    delivery_time = models.CharField(
        max_length=100, choices=DELIVERY_TIME_CHOICES, default="morning"
    )
    create_username = models.CharField(max_length=100, null=True, blank=True)
    create_password = models.CharField(max_length=100, null=True, blank=True)
    confirm_password = models.CharField(max_length=100, null=True, blank=True)
    # raise_complaint = models.TextField(max_length=100, null=True, blank=True)
    milk_quantity = models.CharField(
        max_length=20, choices=MILK_QUANTITY_CHOICES, default="one_litre"
    )
    milk_type = models.CharField(
        max_length=10, choices=MILK_TYPE_CHOICES, default="cow"
    )

    def __str__(self):
        return f"{self.name} ({self.email})"


# Complaint Model
COMPLAINT_STATUS_CHOICES = [
    ("open", "Open"),
    ("in_progress", "In Progress"),
    ("resolved", "Resolved"),
]


class Complaint(models.Model):
    ticket_id = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, null=True, blank=True
    )
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="complaints"
    )
    complaint_text = models.TextField(null=True, blank=True)
    complaint_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=COMPLAINT_STATUS_CHOICES, default="open"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    admin_response = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Ticket {self.ticket_id} - {self.customer.name}"
