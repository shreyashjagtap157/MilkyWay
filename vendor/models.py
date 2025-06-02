from django.db import models


# Create your models here.
# Main Service Provider(Vendor) Model
class Vendor(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    contact = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    date_of_birth = models.CharField(max_length=100, null=True, blank=True)
    company_name = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.name


# Society managed by Service Provider (Vendor)
class Society(models.Model):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="societies"
    )
    name = models.CharField(max_length=100, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    manager_name = models.CharField(max_length=100, null=True, blank=True)
    manager_contact = models.CharField(max_length=15, null=True, blank=True)

    def __str__(self):
        return f"{self.name} - Vendor: {self.vendor.name}"


# Flat & linked to Society
class FlatDetail(models.Model):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="flats"
    )  # added vendor link
    society = models.ForeignKey(Society, on_delete=models.CASCADE, related_name="flats")
    owner_name = models.CharField(max_length=100, null=True, blank=True)
    owner_contact = models.CharField(max_length=15, null=True, blank=True)
    flat_number = models.CharField(max_length=20, null=True, blank=True)
    parking_lot = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"Flat {self.flat_number} - {self.society.name}"

    # Choices for milk quantity
    MILK_QUANTITY_CHOICES = [
        ("half_litre", "Half Litre"),
        ("one_litre", "One Litre"),
        ("two_litre", "Two Litre"),
    ]

    # Choices for milk type
    MILK_TYPE_CHOICES = [
        ("cow", "Cow"),
        ("buffalo", "Buffalo"),
    ]

    # Fields for quantity, milk type, and company name
    milk_quantity = models.CharField(
        max_length=10,
        choices=MILK_QUANTITY_CHOICES,
        default="one_litre",
    )

    milk_type = models.CharField(
        max_length=10,
        choices=MILK_TYPE_CHOICES,
        default="cow",
    )

    def __str__(self):
        return f"{self.flat_number} - {self.society.name} - {self.milk_quantity} of {self.milk_type} milk "


# Worker Payment linked to Service Provider (Vendor)
class WorkerPayment(models.Model):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="payments"
    )
    worker_name = models.CharField(max_length=100, null=True, blank=True)
    contact = models.CharField(max_length=15, null=True, blank=True)
    assigned_society = models.CharField(max_length=100, null=True, blank=True)
    assigned_flat = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_date = models.DateField(auto_now_add=True, null=True, blank=True)
    payment_mode = models.CharField(
        max_length=50, null=True, blank=True
    )  # e.g., Cash, UPI, NEFT

    def __str__(self):
        return f"{self.worker_name} - ₹{self.amount} - {self.vendor.name}"
