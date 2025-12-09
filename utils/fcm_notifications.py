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

def send_group_notifications(tokens, title, body, data=None):
    """
    Send notifications to multiple FCM tokens.

    :param tokens: List of FCM tokens.
    :param title: The title of the notification.
    :param body: The body of the notification.
    :param data: Optional data payload.
    :return: Response from Firebase.
    """
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            tokens=tokens,
            data=data or {}
        )
        response = messaging.send_multicast(message)
        return {
            "status": "success",
            "code": 200,
            "message": "Group notification sent successfully",
            "data": {
                "success_count": response.success_count,
                "failure_count": response.failure_count,
                "responses": response.responses
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "code": 500,
            "message": str(e),
            "data": None
        }

def send_topic_notification(topic, title, body, data=None):
    """
    Send a notification to a specific topic.

    :param topic: The topic to which the notification will be sent.
    :param title: The title of the notification.
    :param body: The body of the notification.
    :param data: Optional data payload.
    :return: Response from Firebase.
    """
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic=topic,
            data=data or {}
        )
        response = messaging.send(message)
        return {
            "status": "success",
            "code": 200,
            "message": "Topic notification sent successfully",
            "data": {"response": response}
        }
    except Exception as e:
        return {
            "status": "error",
            "code": 500,
            "message": str(e),
            "data": None
        }

def send_fcm_notification_with_priority(token, title, body, data=None, priority="high"):
    """
    Send a notification to a specific FCM token with priority.

    :param token: The FCM token of the recipient.
    :param title: The title of the notification.
    :param body: The body of the notification.
    :param data: Optional data payload.
    :param priority: Priority of the notification ("high" or "normal").
    :return: Response from Firebase.
    """
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
            data=data or {},
            android=messaging.AndroidConfig(priority=priority)
        )
        response = messaging.send(message)
        return {
            "status": "success",
            "code": 200,
            "message": "Notification sent successfully",
            "data": {"response": response}
        }
    except Exception as e:
        return {
            "status": "error",
            "code": 500,
            "message": str(e),
            "data": None
        }

def validate_and_cleanup_tokens(tokens):
    """
    Validate and clean up invalid tokens.

    :param tokens: List of FCM tokens.
    :return: List of valid tokens.
    """
    valid_tokens = []
    for token in tokens:
        if token:  # Replace with actual validation logic if needed
            valid_tokens.append(token)
    return valid_tokens

def send_group_notifications_in_batches(tokens, title, body, data=None):
    """
    Send notifications to a group in batches of 500 tokens.

    :param tokens: List of FCM tokens.
    :param title: The title of the notification.
    :param body: The body of the notification.
    :param data: Optional data payload.
    :return: List of responses for each batch.
    """
    batch_size = 500
    responses = []
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i + batch_size]
        response = send_group_notifications(batch_tokens, title, body, data)
        responses.append(response)
    return responses

def retry_failed_notifications(failed_tokens, title, body, data=None, retries=3):
    """
    Retry sending notifications to failed tokens.

    :param failed_tokens: List of failed FCM tokens.
    :param title: The title of the notification.
    :param body: The body of the notification.
    :param data: Optional data payload.
    :param retries: Number of retry attempts.
    :return: List of tokens that still failed after retries.
    """
    for _ in range(retries):
        if not failed_tokens:
            break
        response = send_group_notifications(failed_tokens, title, body, data)
        failed_tokens = [res['token'] for res in response['data']['responses'] if not res['success']]
    return failed_tokens
