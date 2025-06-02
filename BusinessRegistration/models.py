from django.db import models


# Create your models here.
# Business Registration for Vendor (Service Provider) Model
class VendorBusinessRegistration(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    contact = models.CharField(max_length=15, null=True, blank=True)
    email = models.CharField(max_length=100, null=True, blank=True)
    address = models.TextField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=50, null=True, blank=True)
    date_of_birth = models.CharField(max_length=100, null=True, blank=True)
    company_name = models.CharField(max_length=100, null=True, blank=True)
    gst_number = models.CharField(max_length=15, null=True, blank=True)
    aadhar_number = models.CharField(max_length=12, null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.company_name}"
