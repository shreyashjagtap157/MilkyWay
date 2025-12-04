"""
Utility functions for phone number management.
Provides concurrency-safe phone number operations.
"""
from django.db import transaction, IntegrityError
from django.apps import apps
import logging

logger = logging.getLogger(__name__)


def register_phone_number(phone_number, user_type, user_id):
    """
    Register a phone number in the UniquePhoneNumber table.
    Thread-safe and handles race conditions.
    
    Args:
        phone_number: The phone number to register
        user_type: 'vendor', 'milkman', or 'customer'
        user_id: The ID of the user in their respective table
        
    Returns:
        tuple: (success: bool, message: str, obj: UniquePhoneNumber or None)
    """
    UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
    
    if not phone_number:
        return False, "Phone number is required", None
    
    try:
        with transaction.atomic():
            # Check if phone number already exists
            existing = UniquePhoneNumber.objects.filter(phone_number=phone_number).first()
            
            if existing:
                # Check if it's the same user
                if existing.user_type == user_type and existing.user_id == user_id:
                    return True, "Phone number already registered to this user", existing
                else:
                    return False, f"Phone number already registered to {existing.get_user_type_display()}", None
            
            # Create new entry
            obj = UniquePhoneNumber.objects.create(
                phone_number=phone_number,
                user_type=user_type,
                user_id=user_id
            )
            logger.info(f"Registered phone number {phone_number} for {user_type} ID {user_id}")
            return True, "Phone number registered successfully", obj
            
    except IntegrityError as e:
        logger.error(f"Integrity error registering phone number: {e}")
        return False, "Phone number already exists", None
    except Exception as e:
        logger.error(f"Error registering phone number: {e}")
        return False, str(e), None


def update_phone_number(old_phone_number, new_phone_number, user_type, user_id):
    """
    Update a phone number in the UniquePhoneNumber table.
    Thread-safe and handles race conditions.
    
    Args:
        old_phone_number: The current phone number
        new_phone_number: The new phone number
        user_type: 'vendor', 'milkman', or 'customer'
        user_id: The ID of the user in their respective table
        
    Returns:
        tuple: (success: bool, message: str)
    """
    UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
    
    if old_phone_number == new_phone_number:
        return True, "Phone number unchanged"
    
    try:
        with transaction.atomic():
            # Check if new phone number is already taken by someone else
            if new_phone_number:
                existing = UniquePhoneNumber.objects.filter(phone_number=new_phone_number).first()
                if existing and not (existing.user_type == user_type and existing.user_id == user_id):
                    return False, f"Phone number already registered to {existing.get_user_type_display()}"
            
            # Get current entry
            current = UniquePhoneNumber.objects.filter(
                user_type=user_type,
                user_id=user_id
            ).first()
            
            if not current:
                # No existing entry, create new one
                if new_phone_number:
                    UniquePhoneNumber.objects.create(
                        phone_number=new_phone_number,
                        user_type=user_type,
                        user_id=user_id
                    )
                    logger.info(f"Created new phone number {new_phone_number} for {user_type} ID {user_id}")
                return True, "Phone number updated successfully"
            
            if new_phone_number:
                # Update existing entry
                current.phone_number = new_phone_number
                current.save()
                logger.info(f"Updated phone number to {new_phone_number} for {user_type} ID {user_id}")
            else:
                # Delete if new phone number is empty
                current.delete()
                logger.info(f"Removed phone number for {user_type} ID {user_id}")
            
            return True, "Phone number updated successfully"
            
    except IntegrityError as e:
        logger.error(f"Integrity error updating phone number: {e}")
        return False, "Phone number already exists"
    except Exception as e:
        logger.error(f"Error updating phone number: {e}")
        return False, str(e)


def check_phone_number_availability(phone_number, exclude_user_type=None, exclude_user_id=None):
    """
    Check if a phone number is available.
    
    Args:
        phone_number: The phone number to check
        exclude_user_type: User type to exclude from check (for updates)
        exclude_user_id: User ID to exclude from check (for updates)
        
    Returns:
        tuple: (available: bool, message: str, existing_user: dict or None)
    """
    UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
    
    if not phone_number:
        return True, "Phone number is empty", None
    
    try:
        existing = UniquePhoneNumber.objects.filter(phone_number=phone_number).first()
        
        if not existing:
            return True, "Phone number is available", None
        
        # Check if it's the same user (for updates)
        if (exclude_user_type and exclude_user_id and 
            existing.user_type == exclude_user_type and 
            existing.user_id == exclude_user_id):
            return True, "Phone number belongs to current user", None
        
        user_info = {
            'user_type': existing.user_type,
            'user_id': existing.user_id,
            'user_type_display': existing.get_user_type_display()
        }
        
        return False, f"Phone number already registered to {existing.get_user_type_display()}", user_info
        
    except Exception as e:
        logger.error(f"Error checking phone number availability: {e}")
        return False, str(e), None


def lookup_phone_number(phone_number):
    """
    Lookup a phone number and return user details.
    
    Args:
        phone_number: The phone number to lookup
        
    Returns:
        dict or None: User details if found, None otherwise
    """
    UniquePhoneNumber = apps.get_model('Systemadmin', 'UniquePhoneNumber')
    
    try:
        entry = UniquePhoneNumber.objects.filter(phone_number=phone_number).first()
        
        if not entry:
            return None
        
        return {
            'phone_number': entry.phone_number,
            'user_type': entry.user_type,
            'user_id': entry.user_id,
            'user_type_display': entry.get_user_type_display(),
            'created_at': entry.created_at,
            'updated_at': entry.updated_at
        }
        
    except Exception as e:
        logger.error(f"Error looking up phone number: {e}")
        return None
