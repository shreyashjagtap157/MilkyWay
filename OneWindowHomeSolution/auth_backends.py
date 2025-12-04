from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from Systemadmin.models import Systemadmin
from vendor.models import Vendor

class SystemAdminBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = Systemadmin.objects.get(email=username)
            if user.check_password(password):
                return user
        except Systemadmin.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return Systemadmin.objects.get(pk=user_id)
        except Systemadmin.DoesNotExist:
            return None

class VendorBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = Vendor.objects.get(email=username)
            if user.check_password(password):
                return user
        except Vendor.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return Vendor.objects.get(pk=user_id)
        except Vendor.DoesNotExist:
            return None
