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
    Get or create a bill for the customer based on unpaid deliveries.
    
    Logic:
    1. Find the last PAID bill's end date for this customer
    2. If no paid bills exist, use the customer's first delivery date
    3. Calculate bill from (last_paid_end_date + 1) to today
    4. Include ALL unpaid deliveries (bill_paid=False) in that range
    5. Create or update the pending bill with all unpaid deliveries
    
    Returns: (Bill, error_message) tuple
    """
    from django.db.models import Q
    from datetime import date as date_type
    
    if not vendor:
        return None, "No vendor assigned to this customer."
    
    # Get vendor rates
    cow_rate = Decimal(str(getattr(vendor, 'cr', 0) or 0))
    buffalo_rate = Decimal(str(getattr(vendor, 'br', 0) or 0))
    
    # Vendor filter: include deliveries where vendor matches OR vendor is NULL
    vendor_filter = Q(vendor=vendor) | Q(vendor__isnull=True)
    
    # Step 1: Find the last PAID bill's end date
    last_paid_bill = Bill.objects.filter(
        customer=customer,
        vendor=vendor,
        status='paid'
    ).order_by('-end_date').first()
    
    if last_paid_bill:
        # Start from day after last paid bill ended
        start_date = last_paid_bill.end_date + timedelta(days=1)
    else:
        # No paid bills - find the first delivery date for this customer
        first_delivery = DeliveryRecord.objects.filter(
            vendor_filter,
            customer=customer,
            status='delivered'
        ).order_by('date').first()
        
        if first_delivery:
            start_date = first_delivery.date
        else:
            return None, "No deliveries found for this customer."
    
    # End date is today
    end_date = date_type.today()
    
    # Step 2: Get ALL unpaid deliveries (bill_paid=False) in the date range
    unpaid_regular = DeliveryRecord.objects.filter(
        vendor_filter,
        customer=customer,
        status='delivered',
        delivery_type='regular',
        bill_paid=False,
        date__gte=start_date,
        date__lte=end_date
    )
    
    unpaid_extra = DeliveryRecord.objects.filter(
        vendor_filter,
        customer=customer,
        status='delivered',
        delivery_type='extra',
        bill_paid=False,
        date__gte=start_date,
        date__lte=end_date
    )
    
    if not unpaid_regular.exists() and not unpaid_extra.exists():
        return None, "No unpaid deliveries found for this customer."
    
    # Step 3: Delete any existing pending bills and their line items for this customer
    # (we'll recreate with all unpaid deliveries)
    with transaction.atomic():
        # Delete existing pending bills for this customer
        Bill.objects.filter(
            customer=customer,
            vendor=vendor,
            status='pending'
        ).delete()
        
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
        
        # Process all unpaid regular deliveries
        for delivery in unpaid_regular:
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
            
            # Link delivery to this bill
            delivery.bill = bill
            delivery.save(update_fields=['bill'])
        
        # Process all unpaid extra deliveries
        for delivery in unpaid_extra:
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
            
            # Link delivery to this bill
            delivery.bill = bill
            delivery.save(update_fields=['bill'])
        
        # Update bill total
        bill.total_amount = total_amount
        bill.save(update_fields=['total_amount'])
        
        logger.info("Created bill %s for customer %s: start=%s, end=%s, amount=%s, items=%d",
                    bill.id, customer.id, start_date, end_date, total_amount,
                    unpaid_regular.count() + unpaid_extra.count())
        
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
