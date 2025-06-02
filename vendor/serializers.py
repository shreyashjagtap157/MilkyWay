from rest_framework import serializers
from .models import Vendor, Society, FlatDetail, WorkerPayment


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = "__all__"


class SocietySerializer(serializers.ModelSerializer):
    class Meta:
        model = Society
        fields = "__all__"


class FlatDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = FlatDetail
        fields = "__all__"


class WorkerPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerPayment
        fields = "__all__"
