
from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from Customer.models import Customer
from vendorcalendar.models import DeliveryRecord
from vendorcalendar.serializers import DeliveryCalendarSerializer
from django.contrib.auth import get_user_model
from BusinessRegistration.models import VendorBusinessRegistration

class DeliveryRecordTypeTestCase(TestCase):
	def setUp(self):
		User = get_user_model()
		self.vendor = VendorBusinessRegistration.objects.create(name="TestVendor")
		self.customer = Customer.objects.create(name="Test Customer", provider=self.vendor, cow_milk_litre=2)
		self.today = date.today()

	def test_create_regular_and_extra_delivery(self):
		# Create regular delivery
		reg = DeliveryRecord.objects.create(
			customer=self.customer,
			date=self.today,
			status='delivered',
			delivery_type='regular',
			vendor=self.vendor
		)
		# Create extra delivery
		extra = DeliveryRecord.objects.create(
			customer=self.customer,
			date=self.today,
			status='delivered',
			delivery_type='extra',
			vendor=self.vendor,
			cow_milk_extra=1.5
		)
		# Query both
		all_deliveries = DeliveryRecord.objects.filter(customer=self.customer, date=self.today)
		self.assertEqual(all_deliveries.count(), 2)
		self.assertTrue(any(d.delivery_type == 'regular' for d in all_deliveries))
		self.assertTrue(any(d.delivery_type == 'extra' for d in all_deliveries))

	def test_serializer_includes_delivery_type(self):
		reg = DeliveryRecord.objects.create(
			customer=self.customer,
			date=self.today,
			status='delivered',
			delivery_type='regular',
			vendor=self.vendor
		)
		data = DeliveryCalendarSerializer(reg).data
		self.assertIn('delivery_type', data)
		self.assertEqual(data['delivery_type'], 'regular')


class VendorCalendarViewSetAddressTest(TestCase):
	def setUp(self):
		self.vendor = VendorBusinessRegistration.objects.create(name="TestVendor2")
		# Create milkman stub
		from Milkman.models import Milkman
		self.milkman = Milkman.objects.create(name='Test Milkman', provider=self.vendor)
		# Create customer with address fields
		self.customer = Customer.objects.create(first_name="John", last_name="Doe", provider=self.vendor, flat_no='101', society_name='TestSoc', village='TestVillage', tal='TestTal', dist='TestDist', state='TestState', pincode=123456)

	def test_get_customer_address(self):
		from vendorcalendar.views import VendorCalendarViewSet
		viewset = VendorCalendarViewSet()
		addr = viewset.get_customer_address(self.customer)
		self.assertIsInstance(addr, str)
		# Ensure key address piece present
		self.assertIn('TestSoc', addr)
