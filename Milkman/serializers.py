from rest_framework import serializers
from .models import Milkman


class MilkmanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Milkman
        fields = "__all__"
