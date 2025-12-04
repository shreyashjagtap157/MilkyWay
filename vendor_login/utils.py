from twilio.rest import Client
from django.conf import settings


def send_otp_sms(phone_number, otp):
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=f"Your OTP is {otp}", from_=settings.TWILIO_PHONE_NUMBER, to=phone_number
    )
    return message.sid
