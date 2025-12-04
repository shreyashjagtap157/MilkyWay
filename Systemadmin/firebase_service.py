import firebase_admin
from firebase_admin import messaging, credentials

# Initialize Firebase Admin SDK
cred = credentials.Certificate("milkyway-5e3e9-firebase-adminsdk-fbsvc-d764a5129f.json")
firebase_admin.initialize_app(cred)

def send_fcm_notification(token, title, body, data=None):
     message = messaging.Message(
          notification=messaging.Notification(title=title, body=body),
          token=token,
          data=data or {}
     )
     try:
          response = messaging.send(message)
          return {
               "status": "success",
               "code": 200,
               "message": "Notification sent successfully",
               "data": {
                    "response": response
               }
          }
     except Exception as e:
          return {
               "status": "error",
               "code": 500,
               "message": str(e),
               "data": None
          }
