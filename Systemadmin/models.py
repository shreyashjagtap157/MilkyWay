from django.apps import apps
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
# Note: make_password and check_password imports are no longer needed in this file 
# because AbstractBaseUser handles them internally.

class SystemadminManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('The Username field must be set')
        
        user = self.model(username=username, **extra_fields)
        
        # LOGIC FIX: Handle default password here instead of in the model
        # This prevents the "infinite migration loop" issue.
        if not password:
            password = 'root@1234'
            
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)

        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')

        return self.create_user(username, password, **extra_fields)


class Systemadmin(AbstractBaseUser):
    username = models.CharField(max_length=50, unique=True)
    
    # REMOVED: password field. 
    # Reason: AbstractBaseUser adds it automatically. 
    # Defining it with default=make_password() causes migration loops.
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    fcm_token = models.CharField(max_length=255, null=True, blank=True)

    objects = SystemadminManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'systemadmin'

    def __str__(self):
        return self.username

    # REMOVED: set_password and check_password methods.
    # Reason: AbstractBaseUser already provides these implementations.


class UniquePhoneNumber(models.Model):
    """
    Centralized table to store unique phone numbers across all user types.
    This ensures phone number uniqueness and provides efficient lookup.
    """
    USER_TYPE_CHOICES = [
        ('vendor', 'Vendor'),
        ('milkman', 'Milkman'),
        ('customer', 'Customer'),
    ]

    phone_number = models.CharField(
        max_length=30,
        unique=True,
        db_index=True,
        help_text="Unique phone number across all user types"
    )
    user_type = models.CharField(
        max_length=10,
        choices=USER_TYPE_CHOICES,
        db_index=True,
        help_text="Type of user: vendor, milkman, or customer"
    )
    user_id = models.PositiveIntegerField(
        db_index=True,
        null=True,
        blank=True,
        help_text="ID of the user in their respective table"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'systemadmin_unique_phone_number'
        unique_together = [['user_type', 'user_id']]
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['user_type', 'user_id']),
            models.Index(fields=['user_type']),
        ]
        verbose_name = 'Unique Phone Number'
        verbose_name_plural = 'Unique Phone Numbers'

    def __str__(self):
        return self.phone_number

    def clean(self):
        """Validate that the user exists in the respective table"""
        if self.user_type and self.user_id:
            model_mapping = {
                'vendor': ('BusinessRegistration', 'VendorBusinessRegistration'),
                'milkman': ('Milkman', 'Milkman'),
                'customer': ('Customer', 'Customer'),
            }
            
            if self.user_type in model_mapping:
                app_label, model_name = model_mapping[self.user_type]
                try:
                    Model = apps.get_model(app_label, model_name)
                    if not Model.objects.filter(pk=self.user_id).exists():
                        raise ValidationError(
                            f"{self.user_type.capitalize()} with ID {self.user_id} does not exist."
                        )
                except LookupError:
                    # Handles cases where the app/model might not be loaded yet
                    pass

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class NotificationLog(models.Model):
    title = models.CharField(max_length=255)
    body = models.TextField()
    data = models.JSONField(null=True, blank=True)
    recipient = models.TextField()  # Token, topic, or group
    status = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    channel = models.CharField(max_length=50, default='general')  # e.g., 'promotions', 'alerts'
    read = models.BooleanField(default=False)  # Track if the notification has been read
    PRIORITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')]
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')

    class Meta:
        db_table = 'systemadmin_notification_log'
        verbose_name = 'Notification Log'
        verbose_name_plural = 'Notification Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.status}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(Systemadmin, on_delete=models.CASCADE)
    receive_promotions = models.BooleanField(default=True)
    receive_updates = models.BooleanField(default=True)

    def __str__(self):
        return f"Preferences for {self.user.username}"