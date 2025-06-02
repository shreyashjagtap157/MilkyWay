# import razorpay
# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.conf import settings
# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from .models import Payment, Customer


# # client = razorpay.Client(auth=("rzp_live_dbdGN8afzHsBEq", "ZDe5WIylkkaeMSgYQFJpKgQT"))

# # DATA = {
# #     "amount": 5000,
# #     "currency": "INR",
# #     "receipt": "receipt#1",
# #     "notes": {"key1": "value3", "key2": "value2"},
# # }
# # client.order.create(data=DATA)


# # Create your views here.
# # Create Order
# @api_view(["POST"])
# def create_order(request):
#     customer_id = request.data.get("customer_id")
#     amount = request.data.get("amount")  # in rupees

#     customer = Customer.objects.get(id=customer_id)

#     client = razorpay.Client(
#         auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
#     )
#     razorpay_order = client.order.create(
#         {
#             "amount": int(float(amount) * 100),  # Convert to paise
#             "currency": "INR",
#             "payment_capture": 1,
#         }
#     )

#     payment = Payment.objects.create(
#         customer=customer,
#         order_id=razorpay_order["id"],
#         amount=amount,
#         status="created",
#     )

#     return Response(
#         {
#             "razorpay_order_id": razorpay_order["id"],
#             "amount": amount,
#             "customer_name": customer.name,
#             "key": settings.RAZORPAY_KEY_ID,
#         }
#     )


# # Verify & Update Payment Status
# @api_view(["POST"])
# def payment_success(request):
#     from razorpay import Utility

#     data = request.data
#     try:
#         client = razorpay.Client(
#             auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
#         )

#         # Verify signature
#         client.utility.verify_payment_signature(
#             {
#                 "razorpay_order_id": data["razorpay_order_id"],
#                 "razorpay_payment_id": data["razorpay_payment_id"],
#                 "razorpay_signature": data["razorpay_signature"],
#             }
#         )

#         # Update Payment model
#         payment = Payment.objects.get(order_id=data["razorpay_order_id"])
#         payment.payment_id = data["razorpay_payment_id"]
#         payment.status = "paid"
#         payment.save()

#         return Response({"status": "Payment successful"})
#     except:
#         return Response({"status": "Verification failed"}, status=400)
