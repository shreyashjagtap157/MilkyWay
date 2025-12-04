
# Standard library imports
import uuid

# Third-party imports
from django.db import models
from django.contrib.auth.hashers import make_password


# Local app imports
from OneWindowHomeSolution.validators import validate_unique_contact
from Systemadmin.models import UniquePhoneNumber
from Systemadmin.utils import check_phone_number_availability

# Do NOT import Payment or VendorBusinessRegistration at the top to avoid circular imports

# --- Billing Models ---

class Bill(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='bills')
    # Use string reference for vendor to avoid import
    vendor = models.ForeignKey('BusinessRegistration.VendorBusinessRegistration', on_delete=models.CASCADE, related_name='bills')
    # Use string reference for payment to avoid import
    # payment field defined only once below
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue')],
        default='pending',
        db_index=True
    )
    payment = models.ForeignKey('subscription.Payment', null=True, blank=True, on_delete=models.SET_NULL, related_name='bills')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'customer_bill'
        ordering = ['-created_at']

    def __str__(self):
        return f"Bill #{self.id} for {self.customer} ({self.start_date} to {self.end_date})"


class BillLineItem(models.Model):
    bill = models.ForeignKey(Bill, related_name='line_items', on_delete=models.CASCADE)
    delivery_record = models.ForeignKey('vendorcalendar.DeliveryRecord', null=True, blank=True, on_delete=models.SET_NULL)
    date = models.DateField(db_index=True)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=6, decimal_places=2)
    rate = models.DecimalField(max_digits=6, decimal_places=2)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    is_extra = models.BooleanField(default=False)
    is_leave = models.BooleanField(default=False)
    is_unsuccessful = models.BooleanField(default=False)

    class Meta:
        db_table = 'customer_billlineitem'
        ordering = ['date']

    def __str__(self):
        return f"{self.date}: {self.description} ({self.amount})"




class Customer(models.Model):
    first_name = models.CharField(max_length=50, null=True, blank=True)
    last_name = models.CharField(max_length=50, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True, unique=True)
    contact = models.OneToOneField(
        UniquePhoneNumber,
        on_delete=models.CASCADE,
        related_name="customer",
        null=True,
        blank=True,
        help_text="Reference to the unique phone number.",
    )
    contact_str = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text="Legacy/role-based login: stores the phone number string for this customer. Always kept in sync with UniquePhoneNumber."
    )
    flat_no = models.CharField(max_length=100, null=True, blank=True)
    society_name = models.CharField(max_length=100, null=True, blank=True)
    village = models.CharField(max_length=100, null=True, blank=True)
    tal = models.CharField(max_length=100, null=True, blank=True)
    dist = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    availability = models.CharField(max_length=300, null=True, blank=True)
    provider = models.ForeignKey(
        'BusinessRegistration.VendorBusinessRegistration',
        on_delete=models.SET_NULL,
        related_name='customers',
        null=True,
        blank=True,
    )
    milkman = models.ForeignKey(
        'Milkman.Milkman',
        on_delete=models.SET_NULL,
        related_name='assigned_customers',
        null=True,
        blank=True,
    )
    cow_milk_litre = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    buffalo_milk_litre = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    password = models.CharField(max_length=100, null=True, blank=True)
    confirm_password = models.CharField(max_length=100, null=True, blank=True)
    service_start_date = models.DateField(null=True, blank=True)
    service_end_date = models.DateField(null=True, blank=True)
    fcm_token = models.CharField(max_length=255, null=True, blank=True)
    pincode = models.IntegerField(null=True, blank=True, help_text="Postal code of the customer's address")

    class Meta:
        db_table = "customer_customer"

    @property
    def name(self):
        parts = [self.first_name or '', self.last_name or '']
        return (" ".join(p for p in parts if p)).strip() or None

    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        return f"{self.first_name} {self.pk}"


class MilkRequirement(models.Model):
    MILK_TYPE_CHOICES = [
        ("gir", "Gir"),
        ("jershi", "Jershi"),
        ("deshi", "Deshi"),
    ]

    milk_type = models.CharField(
        max_length=10, choices=MILK_TYPE_CHOICES, null=True, blank=True
    )
    quantity_liters = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    delivery_time = models.CharField(
        max_length=100, null=True, blank=True
    )

    class Meta:
        db_table = "customer_milkrequirement"

    def __str__(self):
        return f"{self.customer.name} - {self.milk_type} - {self.quantity_liters}L"



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

    class Meta:
        db_table = 'customer_complaint'

    def __str__(self):
        cust_name = getattr(self.customer, 'name', None) or str(self.customer_id)
        return f"Ticket {self.ticket_id} - {cust_name}"