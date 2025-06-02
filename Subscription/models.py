# from django.db import models

# # Create your models here.
# PAYMENT_STATUS = [
#     ("created", "Created"),
#     ("paid", "Paid"),
#     ("failed", "Failed"),
# ]


# class Payment(models.Model):
#     customer = models.ForeignKey(
#         "Customer.Customer", on_delete=models.CASCADE, related_name="payments"
#     )
#     order_id = models.CharField(max_length=100, blank=True, null=True)
#     payment_id = models.CharField(max_length=100, blank=True, null=True)
#     amount = models.FloatField()  # e.g., 500.00 for ₹500
#     status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="created")
#     date = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.customer.name} - {self.amount} - {self.status}"
