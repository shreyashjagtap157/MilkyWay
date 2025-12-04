from django.db import models
from OneWindowHomeSolution.validators import validate_unique_contact
from Systemadmin.models import UniquePhoneNumber


# Create your models here.
class Milkman(models.Model):
    fcm_token = models.CharField(max_length=255, null=True, blank=True, help_text="FCM token for push notifications.")
    full_name = models.CharField(max_length=100, null=True, blank=True)
    phone_number = models.OneToOneField(
        UniquePhoneNumber,
        on_delete=models.CASCADE,
        related_name="milkman",
        null=True,
        blank=True,
        help_text="Reference to the unique phone number.",
    )
    phone_number_str = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text="Legacy/role-based login: stores the phone number string for this milkman. Always kept in sync with UniquePhoneNumber."
    )
    society_name = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=128, null=True, blank=True)
    provider = models.ForeignKey(
        'BusinessRegistration.VendorBusinessRegistration',
        on_delete=models.SET_NULL,
        related_name='milkmen',
        null=True,
        blank=True,
    )
    flat_house = models.CharField(max_length=100, null=True, blank=True)
    village = models.CharField(max_length=100, null=True, blank=True)
    tal = models.CharField(max_length=100, null=True, blank=True)
    dist = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.IntegerField(null=True, blank=True, help_text="Postal code of the milkman's address")

    class Meta:
        db_table = "milkman_milkman"

    @property
    def name(self):
        return self.full_name
    
    @property
    def is_authenticated(self):
        return True
