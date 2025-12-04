from django.db import models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from OneWindowHomeSolution.validators import validate_unique_contact
from Systemadmin.models import UniquePhoneNumber

class VendorQuerySet(models.QuerySet):
    def with_request_status(self, user_type: str | None, user_id: int | None):
        """
        Annotate each vendor with request_status for the given requester.
        Returns values: 'pending' | 'accepted' | 'rejected' | 'none'
        """
        if not user_type or not user_id:
            return self.annotate(request_status=Value('none'))

        user_type = str(user_type).lower()
        if user_type not in {"customer", "milkman"}:
            return self.annotate(request_status=Value('none'))

        # Late import to avoid circulars
        from django.contrib.contenttypes.models import ContentType
        if user_type == "customer":
            from Customer.models import Customer as RequesterModel
        else:
            from Milkman.models import Milkman as RequesterModel
        ct = ContentType.objects.get_for_model(RequesterModel)

        # Subquery to pick status of the first matching JoinRequest (lazy-resolve model)
        from django.apps import apps
        JoinRequest = apps.get_model('vendor', 'JoinRequest')
        jr_subq = (
            JoinRequest.objects
            .filter(content_type=ct, object_id=user_id, vendor_id=OuterRef('pk'))
            .order_by('id')
            .values('status')[:1]
        )
        return self.annotate(request_status=Coalesce(Subquery(jr_subq), Value('none')))

class VendorManager(models.Manager):
    def get_queryset(self):
        return VendorQuerySet(self.model, using=self._db)

    def with_request_status(self, user_type: str | None, user_id: int | None):
        return self.get_queryset().with_request_status(user_type, user_id)

class VendorBusinessRegistration(models.Model):
    name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True
    )
    contact = models.OneToOneField(
        UniquePhoneNumber,
        on_delete=models.CASCADE,
        related_name="vendor",
        null=True,
        blank=True,
        help_text="Reference to the unique phone number."
    )
    contact_str = models.CharField(
        max_length=30,
        null=True,
        blank=True,
        help_text="Legacy/role-based login: stores the phone number string for this vendor. Always kept in sync with UniquePhoneNumber."
    )
    flat_house = models.CharField(max_length=100, null=True, blank=True)
    society_area = models.CharField(max_length=100, null=True, blank=True)
    village = models.CharField(max_length=100, null=True, blank=True)
    tal = models.CharField(max_length=100, null=True, blank=True)
    dist = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.IntegerField(
        null=True,
        blank=True,
        help_text="Postal code of the vendor's address",
        db_index=True
    )

    @property
    def is_authenticated(self):
        return True
    
    password = models.CharField(max_length=100, null=True, blank=True)

    # Subfields for cow milk litres
    gir_cow_milk_litre = models.IntegerField(null=True, blank=True)
    jarshi_cow_milk_litre = models.IntegerField(null=True, blank=True)
    deshi_milk_litre = models.IntegerField(null=True, blank=True)

    # Subfields for cow milk rates
    gir_cow_rate = models.DecimalField("Gir Cow Rate", max_digits=10, decimal_places=2, default=0)
    jarshi_cow_rate = models.DecimalField("Jarshi Cow Rate", max_digits=10, decimal_places=2, default=0)
    deshi_cow_rate = models.DecimalField("Deshi Cow Rate", max_digits=10, decimal_places=2, default=0)
    cr = models.DecimalField("Cow Milk Rate", max_digits=10, decimal_places=2, default=0)

    buffalo_milk_litre = models.IntegerField(null=True, blank=True)
    br = models.DecimalField("Buffalo Milk rate", max_digits=10, decimal_places=2, default=0)
    fcm_token = models.CharField(max_length=255, null=True, blank=True)
    email = models.EmailField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True
    )

    # Attach the custom manager
    objects = VendorManager()

    def __str__(self):
        return f"{self.name}"

    # Backward-compatible alias: older code may refer to `phone_number`
    @property
    def phone_number(self):
        return self.contact or ""

    @property
    def total_milk_capacity(self):
        return self.total_cow_milk_capacity + (self.buffalo_milk_litre or 0)

    @property
    def total_cow_milk_capacity(self):
        return (self.gir_cow_milk_litre or 0) + \
               (self.jarshi_cow_milk_litre or 0) + \
               (self.deshi_milk_litre or 0)

    def request_status_for(self, user_type: str | None, user_id: int | None) -> str:
        qs = VendorBusinessRegistration.objects.filter(pk=self.pk).with_request_status(user_type, user_id)
        return qs.values_list('request_status', flat=True).first() or 'none'

    class Meta:
        db_table = "businessregistration_vendorbusinessregistration"
