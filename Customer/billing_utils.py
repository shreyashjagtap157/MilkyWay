# billing_utils.py
"""
Helper functions for bill generation and updating for vendors and customers.
"""


from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal
import logging
from django.db import transaction
from django.db.models import Sum
from Customer.models import Customer, Bill, BillLineItem
from vendorcalendar.models import DeliveryRecord, CustomerRequest

logger = logging.getLogger(__name__)


def get_or_create_customer_bill(customer, vendor):
    """
    Get or create a bill for the customer. This function:
    1. Looks for an existing pending/unpaid bill for this customer
    2. If found, updates it with any new unpaid deliveries
    3. If not found, creates a new bill with all unpaid deliveries
    4. Returns the bill (or None if no unpaid deliveries exist)
    
    This ensures the bill is persisted in the database and updated on each call.
    """
    if not vendor:
        return None, "No vendor assigned to this customer."
    
    # Get vendor rates
    cow_rate = Decimal(str(getattr(vendor, 'cr', 0) or 0))
    buffalo_rate = Decimal(str(getattr(vendor, 'br', 0) or 0))
    
    # Get all unpaid deliveries that are NOT yet linked to any bill
    unlinked_regular_deliveries = DeliveryRecord.objects.filter(
        customer=customer,
        vendor=vendor,
        status='delivered',
        delivery_type='regular',
        bill_paid=False,
        bill__isnull=True  # Not yet linked to any bill
    )
    
    unlinked_extra_deliveries = DeliveryRecord.objects.filter(
        customer=customer,
        vendor=vendor,
        status='delivered',
        delivery_type='extra',
        bill_paid=False,
        bill__isnull=True  # Not yet linked to any bill
    )
    
    # Check if there's an existing pending bill for this customer
    existing_bill = Bill.objects.filter(
        customer=customer,
        vendor=vendor,
        status='pending'
    ).order_by('-created_at').first()
    
    with transaction.atomic():
        if existing_bill:
            # Update existing bill with any new unlinked deliveries
            bill = existing_bill
            new_amount = Decimal('0')
            
            # Process unlinked regular deliveries
            for delivery in unlinked_regular_deliveries:
                cow_qty = Decimal(str(customer.cow_milk_litre or 0))
                buffalo_qty = Decimal(str(customer.buffalo_milk_litre or 0))
                
                # Create line item for cow milk
                if cow_qty > 0:
                    amount = cow_qty * cow_rate
                    new_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Cow milk delivery',
                        quantity=cow_qty,
                        rate=cow_rate,
                        amount=amount,
                        is_extra=False,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                # Create line item for buffalo milk
                if buffalo_qty > 0:
                    amount = buffalo_qty * buffalo_rate
                    new_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Buffalo milk delivery',
                        quantity=buffalo_qty,
                        rate=buffalo_rate,
                        amount=amount,
                        is_extra=False,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                # Link delivery to bill and mark as unpaid (pending)
                delivery.bill = bill
                delivery.bill_paid = False
                delivery.save(update_fields=['bill', 'bill_paid'])
            
            # Process unlinked extra deliveries
            for delivery in unlinked_extra_deliveries:
                extra_cow = Decimal(str(delivery.cow_milk_extra or 0))
                extra_buffalo = Decimal(str(delivery.buffalo_milk_extra or 0))
                
                if extra_cow > 0:
                    amount = extra_cow * cow_rate
                    new_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Extra cow milk delivery',
                        quantity=extra_cow,
                        rate=cow_rate,
                        amount=amount,
                        is_extra=True,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                if extra_buffalo > 0:
                    amount = extra_buffalo * buffalo_rate
                    new_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Extra buffalo milk delivery',
                        quantity=extra_buffalo,
                        rate=buffalo_rate,
                        amount=amount,
                        is_extra=True,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                # Link delivery to bill and mark as unpaid (pending)
                delivery.bill = bill
                delivery.bill_paid = False
                delivery.save(update_fields=['bill', 'bill_paid'])
            
            # Update bill total and date range if new deliveries were added
            if new_amount > 0:
                bill.total_amount = (bill.total_amount or Decimal('0')) + new_amount

                # Update date range to include new deliveries
                all_line_items = bill.line_items.all()
                if all_line_items.exists():
                    dates = list(all_line_items.values_list('date', flat=True))
                    bill.start_date = min(dates)
                    bill.end_date = max(dates)

                bill.save(update_fields=['total_amount', 'start_date', 'end_date'])
                logger.info("Updated existing bill %s: +%s", bill.id, new_amount)

            return bill, None
        
        else:
            # No existing pending bill - check if there are any unpaid deliveries
            all_regular = DeliveryRecord.objects.filter(
                customer=customer,
                vendor=vendor,
                status='delivered',
                delivery_type='regular',
                bill_paid=False
            )
            
            all_extra = DeliveryRecord.objects.filter(
                customer=customer,
                vendor=vendor,
                status='delivered',
                delivery_type='extra',
                bill_paid=False
            )
            
            if not all_regular.exists() and not all_extra.exists():
                return None, "No unpaid deliveries found for this customer."
            
            # Calculate date range from all unpaid deliveries
            all_dates = list(all_regular.values_list('date', flat=True)) + list(all_extra.values_list('date', flat=True))
            start_date = min(all_dates) if all_dates else date.today()
            end_date = max(all_dates) if all_dates else date.today()
            
            # Create new bill
            bill = Bill.objects.create(
                customer=customer,
                vendor=vendor,
                start_date=start_date,
                end_date=end_date,
                total_amount=Decimal('0'),
                status='pending'
            )
            
            total_amount = Decimal('0')
            
            # Process all regular deliveries
            for delivery in all_regular:
                cow_qty = Decimal(str(customer.cow_milk_litre or 0))
                buffalo_qty = Decimal(str(customer.buffalo_milk_litre or 0))
                
                if cow_qty > 0:
                    amount = cow_qty * cow_rate
                    total_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Cow milk delivery',
                        quantity=cow_qty,
                        rate=cow_rate,
                        amount=amount,
                        is_extra=False,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                if buffalo_qty > 0:
                    amount = buffalo_qty * buffalo_rate
                    total_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Buffalo milk delivery',
                        quantity=buffalo_qty,
                        rate=buffalo_rate,
                        amount=amount,
                        is_extra=False,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                delivery.bill = bill
                delivery.bill_paid = False
                delivery.save(update_fields=['bill', 'bill_paid'])
            
            # Process all extra deliveries
            for delivery in all_extra:
                extra_cow = Decimal(str(delivery.cow_milk_extra or 0))
                extra_buffalo = Decimal(str(delivery.buffalo_milk_extra or 0))
                
                if extra_cow > 0:
                    amount = extra_cow * cow_rate
                    total_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Extra cow milk delivery',
                        quantity=extra_cow,
                        rate=cow_rate,
                        amount=amount,
                        is_extra=True,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                if extra_buffalo > 0:
                    amount = extra_buffalo * buffalo_rate
                    total_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=delivery,
                        date=delivery.date,
                        description='Extra buffalo milk delivery',
                        quantity=extra_buffalo,
                        rate=buffalo_rate,
                        amount=amount,
                        is_extra=True,
                        is_leave=False,
                        is_unsuccessful=False
                    )
                
                delivery.bill = bill
                delivery.bill_paid = False
                delivery.save(update_fields=['bill', 'bill_paid'])
            
            bill.total_amount = total_amount
            bill.save(update_fields=['total_amount'])
            logger.info("Created bill %s for customer %s amount=%s", bill.id, customer.id, total_amount)

            return bill, None

def generate_bill_for_period(customer, vendor, start_date, end_date, payment=None):
    """
    Generate a bill for a customer for a given period, aggregating deliveries and extra milk.
    Returns the Bill instance or None if no deliveries.
    """
    deliveries = DeliveryRecord.objects.filter(
        customer=customer,
        status='delivered',
        date__gte=start_date,
        date__lte=end_date,
        bill__isnull=True
    ).order_by('date', 'delivery_type')
    if not deliveries.exists():
        return None
    total_amount = 0
    with transaction.atomic():
        bill = Bill.objects.create(
            customer=customer,
            vendor=vendor,
            start_date=start_date,
            end_date=end_date,
            total_amount=0,
            status='pending',
            payment=payment
        )
        # Group deliveries by date
        deliveries_by_date = {}
        for delivery in deliveries:
            deliveries_by_date.setdefault(delivery.date, []).append(delivery)
        for delivery_date, records in deliveries_by_date.items():
            # Always process regular first, then extra if present
            regular = next((r for r in records if r.delivery_type == 'regular'), None)
            extra = next((r for r in records if r.delivery_type == 'extra'), None)

            # Bill regular delivery
            if regular:
                cow_qty = float(customer.cow_milk_litre or 0) if hasattr(customer, 'cow_milk_litre') else 0
                buffalo_qty = float(customer.buffalo_milk_litre or 0) if hasattr(customer, 'buffalo_milk_litre') else 0
                cow_rate = float(getattr(vendor, 'cr', 0) or 0) if vendor else 0
                buffalo_rate = float(getattr(vendor, 'br', 0) or 0) if vendor else 0

                # Bill cow milk if customer has it
                if cow_qty > 0:
                    amount = cow_qty * cow_rate
                    total_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=regular,
                        date=regular.date,
                        description='Cow milk delivery',
                        quantity=cow_qty,
                        rate=cow_rate,
                        amount=amount,
                        is_extra=False,
                        is_leave=(getattr(regular, 'status', '') == 'cancelled'),
                        is_unsuccessful=(getattr(regular, 'status', '') == 'not_delivered')
                    )

                # Bill buffalo milk if customer has it
                if buffalo_qty > 0:
                    amount = buffalo_qty * buffalo_rate
                    total_amount += amount
                    BillLineItem.objects.create(
                        bill=bill,
                        delivery_record=regular,
                        date=regular.date,
                        description='Buffalo milk delivery',
                        quantity=buffalo_qty,
                        rate=buffalo_rate,
                        amount=amount,
                        is_extra=False,
                        is_leave=(getattr(regular, 'status', '') == 'cancelled'),
                        is_unsuccessful=(getattr(regular, 'status', '') == 'not_delivered')
                    )

                regular.bill = bill
                regular.bill_paid = False
                regular.save()

            # Bill extra delivery if present
            if extra:
                # Use the extra quantities from the DeliveryRecord
                extra_cow = float(getattr(extra, 'cow_milk_extra', 0) or 0)
                extra_buffalo = float(getattr(extra, 'buffalo_milk_extra', 0) or 0)
                # Only bill if there is extra
                if extra_cow > 0 or extra_buffalo > 0:
                    # Bill cow milk extra
                    if extra_cow > 0:
                        rate = float(getattr(vendor, 'cr', 0) or 0)
                        amount = extra_cow * rate
                        total_amount += amount
                        BillLineItem.objects.create(
                            bill=bill,
                            delivery_record=extra,
                            date=extra.date,
                            description='Extra cow milk delivery',
                            quantity=extra_cow,
                            rate=rate,
                            amount=amount,
                            is_extra=True,
                            is_leave=False,
                            is_unsuccessful=False
                        )
                    # Bill buffalo milk extra
                    if extra_buffalo > 0:
                        rate = float(getattr(vendor, 'br', 0) or 0)
                        amount = extra_buffalo * rate
                        total_amount += amount
                        BillLineItem.objects.create(
                            bill=bill,
                            delivery_record=extra,
                            date=extra.date,
                            description='Extra buffalo milk delivery',
                            quantity=extra_buffalo,
                            rate=rate,
                            amount=amount,
                            is_extra=True,
                            is_leave=False,
                            is_unsuccessful=False
                        )
                    extra.bill = bill
                    extra.bill_paid = False
                    extra.save()
        bill.total_amount = total_amount
        bill.save()
    return bill


def generate_or_update_bills_for_vendor(vendor, month=None, year=None):
    """
    Generate or update bills for all customers of a vendor for the given month/year (defaults to current month).
    Skips customers with no deliveries in the period or if a bill already exists for the period.
    """
    today = date.today()
    if not month:
        month = today.month
    if not year:
        year = today.year
    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    customers = Customer.objects.filter(provider=vendor)
    for customer in customers:
        # Skip if bill already exists for this period
        if Bill.objects.filter(customer=customer, vendor=vendor, start_date=start_date, end_date=end_date).exists():
            continue
        generate_bill_for_period(customer, vendor, start_date, end_date)
