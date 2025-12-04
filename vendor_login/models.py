# from django.db import models


# class Vendor(models.Model):
#     email = models.EmailField(unique=True)
#     otp = models.CharField(max_length=6, blank=True, null=True)
#     otp_created_at = models.DateTimeField(blank=True, null=True)

#     def __str__(self):
#         return self.email

# SMS Login OTP
# from django.db import models
# import random


# class OTPVerification(models.Model):
#     phone_number = models.CharField(max_length=15, default="9999999999")
#     otp = models.CharField(max_length=6)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def generate_otp(self):
#         self.otp = str(random.randint(100000, 999999))
#         self.save()
