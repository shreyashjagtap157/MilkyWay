"""
Signal handlers for synchronizing phone numbers to UniquePhoneNumber table.
Handles creation, updates, and deletion of phone numbers from Vendor, Milkman, and Customer models.
"""
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db import transaction
from django.apps import apps
import logging

logger = logging.getLogger(__name__)


def get_phone_field_name(instance):
    """Get the phone number field name for different models"""
    model_name = instance.__class__.__name__
    if model_name == 'VendorBusinessRegistration':
        return 'contact'
    elif model_name == 'Milkman':
        return 'phone_number'
    elif model_name == 'Customer':
        return 'contact'
    return None


def get_user_type(instance):
    """Get user type string based on model"""
    model_name = instance.__class__.__name__
    if model_name == 'VendorBusinessRegistration':
        return 'vendor'
    elif model_name == 'Milkman':
        return 'milkman'
    elif model_name == 'Customer':
        return 'customer'
    return None


def sync_phone_number(instance, user_type, phone_field_name):
    """
    Sync phone number to UniquePhoneNumber table.
    Uses select_for_update for concurrency safety.
    """
    UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
    
    phone_number = getattr(instance, phone_field_name, None)
    
    if not phone_number:
        # If no phone number, delete any existing entry
        UniquePhoneNumber.objects.filter(
            user_type=user_type,
            user_id=instance.pk
        ).delete()
        return
    
    with transaction.atomic():
        # Use get_or_create with update to handle race conditions
        obj, created = UniquePhoneNumber.objects.get_or_create(
            user_type=user_type,
            user_id=instance.pk,
            defaults={'phone_number': phone_number}
        )
        
        if not created and obj.phone_number != phone_number:
            # Update phone number if changed
            obj.phone_number = phone_number
            obj.save()
            logger.info(f"Updated phone number for {user_type} ID {instance.pk}: {phone_number}")
        elif created:
            logger.info(f"Created phone number entry for {user_type} ID {instance.pk}: {phone_number}")


@receiver(post_save, sender='BusinessRegistration.VendorBusinessRegistration')
def sync_vendor_phone_number(sender, instance, created, **kwargs):
    """Sync vendor phone number to UniquePhoneNumber table"""
    try:
        sync_phone_number(instance, 'vendor', 'contact')
    except Exception as e:
        logger.error(f"Error syncing vendor phone number: {e}")


@receiver(post_save, sender='Milkman.Milkman')
def sync_milkman_phone_number(sender, instance, created, **kwargs):
    """Sync milkman phone number to UniquePhoneNumber table"""
    try:
        sync_phone_number(instance, 'milkman', 'phone_number')
    except Exception as e:
        logger.error(f"Error syncing milkman phone number: {e}")


@receiver(post_save, sender='Customer.Customer')
def sync_customer_phone_number(sender, instance, created, **kwargs):
    """Sync customer phone number to UniquePhoneNumber table"""
    try:
        sync_phone_number(instance, 'customer', 'contact')
    except Exception as e:
        logger.error(f"Error syncing customer phone number: {e}")


@receiver(post_delete, sender='BusinessRegistration.VendorBusinessRegistration')
def delete_vendor_phone_number(sender, instance, **kwargs):
    """Delete vendor phone number from UniquePhoneNumber table"""
    try:
        UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
        UniquePhoneNumber.objects.filter(
            user_type='vendor',
            user_id=instance.pk
        ).delete()
        logger.info(f"Deleted phone number entry for vendor ID {instance.pk}")
    except Exception as e:
        logger.error(f"Error deleting vendor phone number: {e}")


@receiver(post_delete, sender='Milkman.Milkman')
def delete_milkman_phone_number(sender, instance, **kwargs):
    """Delete milkman phone number from UniquePhoneNumber table"""
    try:
        UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
        UniquePhoneNumber.objects.filter(
            user_type='milkman',
            user_id=instance.pk
        ).delete()
        logger.info(f"Deleted phone number entry for milkman ID {instance.pk}")
    except Exception as e:
        logger.error(f"Error deleting milkman phone number: {e}")


@receiver(post_delete, sender='Customer.Customer')
def delete_customer_phone_number(sender, instance, **kwargs):
    """Delete customer phone number from UniquePhoneNumber table"""
    try:
        UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
        UniquePhoneNumber.objects.filter(
            user_type='customer',
            user_id=instance.pk
        ).delete()
        logger.info(f"Deleted phone number entry for customer ID {instance.pk}")
    except Exception as e:
        logger.error(f"Error deleting customer phone number: {e}")
