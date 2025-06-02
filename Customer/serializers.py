from rest_framework import serializers
from .models import Customer, Complaint
from django.contrib.auth.models import User


# Customer (User) Serializer
class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"


# Customer (User) Complaint Serializer
class ComplaintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = ["ticket_id", "customer", "complaint_text", "status", "created_at"]
        read_only_fields = ["ticket_id", "status", "created_at"]


# Customer (User) Login Serializer
class CustomerRegisterSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["username", "password", "confirm_password"]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop("confirm_password")
        user = User.objects.create_user(
            username=validated_data["username"], password=validated_data["password"]
        )
        return user
