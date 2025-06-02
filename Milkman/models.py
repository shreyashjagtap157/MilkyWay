from django.db import models
from vendor.models import Vendor


# Create your models here.
class Milkman(models.Model):
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="milkmen"
    )  # Milkman works for a specific vendor
    name = models.CharField(max_length=100, null=True, blank=True)
    contact_number = models.CharField(max_length=15, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    assigned_society = models.TextField(null=True, blank=True)
    assigned_flats = models.TextField(null=True, blank=True)
    documents = models.CharField(max_length=255, null=True, blank=True)
    owner_name = models.CharField(max_length=100, null=True, blank=True)
    owner_contact_number = models.CharField(max_length=15, null=True, blank=True)
    daily_status = models.BooleanField(default=True, null=True, blank=True)

    def __str__(self):
        return self.name
