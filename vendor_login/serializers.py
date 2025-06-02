from rest_framework import serializers

# from django.contrib.auth.models import User


# Vendor (Service Provider) Login Serializer
class VendorLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


# Milkman (Worker) Login Serializer
class MilkmanLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
