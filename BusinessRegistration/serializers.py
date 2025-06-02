from rest_framework import serializers
from .models import VendorBusinessRegistration


class VendorBusinessRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorBusinessRegistration
        fields = "__all__"
