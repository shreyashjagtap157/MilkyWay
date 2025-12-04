from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from Customer.models import Customer, Bill, BillLineItem
from vendorcalendar.models import DeliveryRecord
from Customer.billing_utils import generate_bill_for_period
from BusinessRegistration.models import VendorBusinessRegistration as Vendor
from decimal import Decimal
from django.db import transaction

class Command(BaseCommand):
    help = 'Generate bills for all customers for a given period (default: last month)'

    def add_arguments(self, parser):
        parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
        parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')

    def handle(self, *args, **options):
        start_date = options['start']
        end_date = options['end']
        if not start_date or not end_date:
            today = timezone.now().date()
            up_to_date = today
        else:
            up_to_date = datetime.strptime(end_date, '%Y-%m-%d').date()

        self.stdout.write(f'Generating bills up to {up_to_date}')
        vendors = Vendor.objects.all()
        for vendor in vendors:
            customers = Customer.objects.filter(provider=vendor)
            for customer in customers:
                # Find last bill's end date
                last_bill = Bill.objects.filter(customer=customer).order_by('-end_date').first()
                cust_start_date = (last_bill.end_date + timedelta(days=1)) if last_bill else customer.service_start_date
                if not cust_start_date or cust_start_date > up_to_date:
                    continue
                bill = generate_bill_for_period(customer, vendor, cust_start_date, up_to_date)
                if bill:
                    self.stdout.write(f'Created bill {bill.id} for customer {customer.id} ({bill.total_amount})')
