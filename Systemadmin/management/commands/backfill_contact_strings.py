from django.core.management.base import BaseCommand
from BusinessRegistration.models import VendorBusinessRegistration
from Customer.models import Customer
from Milkman.models import Milkman

def backfill_vendor_contacts():
    vendors = VendorBusinessRegistration.objects.all()
    to_update = []
    for vendor in vendors:
        if vendor.contact and (not vendor.contact_str or vendor.contact_str != vendor.contact.phone_number):
            vendor.contact_str = vendor.contact.phone_number
            to_update.append(vendor)
    if to_update:
        VendorBusinessRegistration.objects.bulk_update(to_update, ["contact_str"])

def backfill_customer_contacts():
    customers = Customer.objects.all()
    to_update = []
    for customer in customers:
        if customer.contact and (not customer.contact_str or customer.contact_str != customer.contact.phone_number):
            customer.contact_str = customer.contact.phone_number
            to_update.append(customer)
    if to_update:
        Customer.objects.bulk_update(to_update, ["contact_str"])

def backfill_milkman_contacts():
    milkmen = Milkman.objects.all()
    to_update = []
    for milkman in milkmen:
        if milkman.phone_number and (not milkman.phone_number_str or milkman.phone_number_str != milkman.phone_number.phone_number):
            milkman.phone_number_str = milkman.phone_number.phone_number
            to_update.append(milkman)
    if to_update:
        Milkman.objects.bulk_update(to_update, ["phone_number_str"])

class Command(BaseCommand):
    help = "Backfill contact_str/phone_number_str fields for all user roles from UniquePhoneNumber."

    def handle(self, *args, **options):
        self.stdout.write("Backfilling vendor contact_str fields...")
        backfill_vendor_contacts()
        self.stdout.write("Backfilling customer contact_str fields...")
        backfill_customer_contacts()
        self.stdout.write("Backfilling milkman phone_number_str fields...")
        backfill_milkman_contacts()
        self.stdout.write(self.style.SUCCESS("Backfill complete!"))
