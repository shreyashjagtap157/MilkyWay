from django.db import models
from Customer.models import Customer


# Create your models here.
# Model for Subscription Plans
class SubscriptionPlan(models.Model):
    PLAN_CHOICES = [
        (30, "Monthly"),
        (180, "6_Months"),
        (365, "12_Months"),
    ]
    plan_name = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, db_index=True)
    duration = models.CharField(
        max_length=100, choices=PLAN_CHOICES, null=True, blank=True, db_index=True
    )
    description = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["plan_name"]),
            models.Index(fields=["duration"]),
            models.Index(fields=["price"]),
        ]

# class SubscribedUser(models.Model):
