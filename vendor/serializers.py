from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import JoinRequest
from BusinessRegistration.models import VendorBusinessRegistration
from Customer.models import Customer
from Milkman.models import Milkman


class JoinRequestSerializer(serializers.ModelSerializer):
    # Simple payload: user_id, vendor, and user_type
    user_id = serializers.IntegerField(write_only=True, required=True)
    vendor = serializers.PrimaryKeyRelatedField(
        queryset=VendorBusinessRegistration.objects.all(),
        required=True
    )
    user_type = serializers.ChoiceField(
        choices=[('customer', 'Customer'), ('milkman', 'Milkman')],
        required=True
    )
    user_contact = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    milk_requirement = serializers.SerializerMethodField(read_only=True)
    accepted_at = serializers.DateTimeField(read_only=True)
    rejected_at = serializers.DateTimeField(read_only=True)

    def get_user_contact(self, obj):
        return obj.user_contact

    def get_milk_requirement(self, obj):
        return obj.milk_requirement

    class Meta:
        model = JoinRequest
        fields = [
            "id",
            "name",
            "vendor",
            "status",
            "user_id",
            "user_type",
            "user_contact",
            "vendor_name",
            "milk_requirement",
            "object_id",  # This represents customer_id or milkman_id
            "accepted_at",
            "rejected_at",
        ]
        read_only_fields = ["id", "name", "status", "object_id", "accepted_at", "rejected_at"]

    def validate(self, data):
        user_id = data.get("user_id")
        vendor = data.get("vendor")
        user_type = data.get("user_type").lower()

        if user_type == 'customer':
            try:
                user_object = Customer.objects.get(pk=user_id)
                content_type = ContentType.objects.get_for_model(Customer)
            except Customer.DoesNotExist:
                raise serializers.ValidationError({"user_id": "Customer not found."})
        elif user_type == 'milkman':
            try:
                user_object = Milkman.objects.get(pk=user_id)
                content_type = ContentType.objects.get_for_model(Milkman)
            except Milkman.DoesNotExist:
                raise serializers.ValidationError({"user_id": "Milkman not found."})
        else:
            raise serializers.ValidationError({"user_type": "Invalid user type."})


        # Prevent duplicate join requests for same user, vendor, and user type if already accepted or pending
        if JoinRequest.objects.filter(
            content_type=content_type,
            object_id=user_id,
            vendor=vendor,
            user_type=user_type,
            status__in=["pending", "accepted"]
        ).exists():
            raise serializers.ValidationError("A join request already exists for this user and vendor.")

        # Attach internal fields for the new generic relationship
        data['content_type'] = content_type
        data['object_id'] = user_id
        # Use phone number string if name is not set and contact exists
        contact_str = None
        if hasattr(user_object, 'contact') and user_object.contact:
            # If contact is a UniquePhoneNumber instance, get the string
            contact = user_object.contact
            contact_str = getattr(contact, 'phone_number', str(contact))
        data['name'] = user_object.name or contact_str

        return data

    def create(self, validated_data):
        # user_id is not a model field, it's used to set object_id
        validated_data.pop("user_id", None)
        return super().create(validated_data)


class VendorBusinessRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorBusinessRegistration
        fields = '__all__'
