from django.core.exceptions import ValidationError
from django.apps import apps

def validate_unique_contact(value):
    """
    Ensure the contact or phone_number is unique across Customer, Milkman, and VendorBusinessRegistration.
    Uses the centralized UniquePhoneNumber table for efficient lookup.
    """
    if not value:
        return
    
    # Check against the centralized UniquePhoneNumber table
    UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
    
    if UniquePhoneNumber.objects.filter(phone_number=value).exists():
        existing = UniquePhoneNumber.objects.get(phone_number=value)
        user_type_display = existing.get_user_type_display()
        raise ValidationError(
            f"The phone number {value} is already registered as a {user_type_display}."
        )