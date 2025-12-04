from django.test import TestCase
from datetime import date
from Customer.models import Customer
from vendorcalendar.models import DeliveryRecord
from BusinessRegistration.models import VendorBusinessRegistration
from Customer.billing_utils import generate_bill_for_period

class BillingDeliveryTypeTestCase(TestCase):
	def setUp(self):
		self.vendor = VendorBusinessRegistration.objects.create(name="TestVendor", cr=50, br=60)
		self.customer = Customer.objects.create(name="Test Customer", provider=self.vendor, cow_milk_litre=2, buffalo_milk_litre=0)
		self.today = date.today()

	def test_billing_regular_and_extra(self):
		# Regular delivery
		DeliveryRecord.objects.create(
			customer=self.customer,
			date=self.today,
			status='delivered',
			delivery_type='regular',
			vendor=self.vendor
		)
		# Extra delivery
		DeliveryRecord.objects.create(
			customer=self.customer,
			date=self.today,
			status='delivered',
			delivery_type='extra',
			vendor=self.vendor,
			cow_milk_extra=1.5
		)
		bill = generate_bill_for_period(self.customer, self.vendor, self.today, self.today)
		self.assertIsNotNone(bill)
		self.assertEqual(bill.total_amount, 2*50 + 1.5*50)
