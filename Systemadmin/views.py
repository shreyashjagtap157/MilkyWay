import logging
from datetime import timedelta
from django.utils.timezone import now

# Third-party imports
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from firebase_admin import messaging
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken

# Local application imports
from OneWindowHomeSolution.custom_authentication import CustomJWTAuthentication
from OneWindowHomeSolution.responses import success_response, error_response
from utils.fcm_notifications import (
    send_fcm_notification,
    send_group_notifications,
    send_topic_notification,
    send_fcm_notification_with_priority,
    validate_and_cleanup_tokens,
    send_group_notifications_in_batches,
)
from Systemadmin.models import Systemadmin, UniquePhoneNumber, NotificationLog, NotificationPreference
from Systemadmin.serializers import AdminSerializer, AdminLoginSerializer, UniquePhoneNumberSerializer, NotificationLogSerializer
from Systemadmin.utils import lookup_phone_number

# Additional app models (used later) — imported here for efficiency
from BusinessRegistration.models import VendorBusinessRegistration
from Milkman.models import Milkman
from Customer.models import Customer

logger = logging.getLogger(__name__)

# Create your views here.
class AdminAPI(ModelViewSet):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = Systemadmin.objects.all()
    serializer_class = AdminSerializer

    @swagger_auto_schema(
        operation_summary="List All Admins",
        operation_description="""
        Retrieve a list of all system administrators.

        **Authentication required**: This endpoint requires a valid JWT token.
        Include the token in the Authorization header as: `Authorization: Bearer <token>`
        """,
        responses={200: AdminSerializer(many=True)},
        tags=['Admin Management'],
        security=[{'Bearer': []}]
    )
    def list(self, request, *args, **kwargs):
        logger.info("Entering list method in AdminAPI")
        try:
            admin = Systemadmin.objects.all()
            serializer = self.get_serializer(admin, many=True)
            logger.info("Successfully fetched all admins")
            api_response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'All admins',
                'all_admins': serializer.data,
            }
            return Response(api_response)
        except Exception as e:
            logger.error(f"An error occurred while fetching admin: {str(e)}")
            error_response = {
                'status': 'error',
                'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"An error occurred while fetching admin: {str(e)}"
            }
            return Response(error_response)

    @swagger_auto_schema(
        operation_summary="Retrieve Admin Details",
        operation_description="""
        Retrieve details of a specific system administrator.

        **Authentication required**: This endpoint requires a valid JWT token.
        """,
        responses={200: AdminSerializer()},
        tags=['Admin Management'],
        security=[{'Bearer': []}]
    )
    def retrieve(self, request, *args, **kwargs):
        logger.info("Entering retrieve method in AdminAPI")
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            logger.info("Successfully retrieved admin details")
            api_response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Admin fetched successfully',
                'admin_details': serializer.data,
            }
            return Response(api_response)
        except Exception as e:
            logger.error(f"An error occurred while fetching admin: {str(e)}")
            error_response = {
                'status': 'error',
                'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"An error occurred while fetching admin: {str(e)}"
            }
            return Response(error_response)

    @swagger_auto_schema(
        operation_summary="Create New Admin",
        operation_description="""
        Add a new system administrator.

        **Authentication required**: This endpoint requires a valid JWT token.
        """,
        request_body=AdminSerializer,
        responses={201: AdminSerializer()},
        tags=['Admin Management'],
        security=[{'Bearer': []}]
    )
    def create(self, request, *args, **kwargs):
        logger.info("START AdminAPI.create | request data: %s", request.data)
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            logger.info("END AdminAPI.create | new admin created")

            api_response = {
                'status': 'success',
                'code': status.HTTP_201_CREATED,
                'message': 'Admin added successfully',
                'new_admin': serializer.data,
            }
            return Response(api_response)
        except Exception as e:
            logger.error(f"Failed to add admin: {str(e)}")
            error_message = f'Failed to add admin: {str(e)}'
            error_response = {
                'status': 'error',
                'code': status.HTTP_400_BAD_REQUEST,
                'message': error_message
            }
            return Response(error_response)

    @swagger_auto_schema(
        operation_summary="Update Admin Details",
        operation_description="Update all details of an existing system administrator.",
        request_body=AdminSerializer,
        responses={200: AdminSerializer()}
    )
    def update(self, request, *args, **kwargs):
        logger.info("START AdminAPI.update | request data: %s", request.data)
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            logger.info("END AdminAPI.update | admin updated")

            api_response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Admin updated successfully',
                'updated_admin': serializer.data,
            }
            return Response(api_response)
        except Exception as e:
            logger.error(f"Failed to update admin: {str(e)}")
            error_message = f'Failed to update admin: {str(e)}'
            error_response = {
                'status': 'error',
                'code': status.HTTP_400_BAD_REQUEST,
                'message': error_message
            }
            return Response(error_response)

    @swagger_auto_schema(
        operation_summary="Partially Update Admin Details",
        operation_description="Update selected fields of an existing system administrator.",
        request_body=AdminSerializer,
        responses={200: AdminSerializer()}
    )
    def partial_update(self, request, *args, **kwargs):
        logger.info("START AdminAPI.partial_update | request data: %s", request.data)
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            logger.info("END AdminAPI.partial_update | admin partially updated")

            api_response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Admin updated successfully',
                'updated_admin': serializer.data,
            }
            return Response(api_response)
        except Exception as e:
            logger.error(f"Failed to partially update admin: {str(e)}")
            error_message = f'Failed to partially update admin: {str(e)}'
            error_response = {
                'status': 'error',
                'code': status.HTTP_400_BAD_REQUEST,
                'message': error_message
            }
            return Response(error_response)

    @swagger_auto_schema(
        operation_summary="Delete Admin",
        operation_description="Delete a system administrator.",
        responses={200: "Admin deleted successfully"}
    )
    def destroy(self, request, *args, **kwargs):
        logger.info("START AdminAPI.destroy | request data: %s", request.data)
        try:
            instance = self.get_object()
            instance.delete()
            logger.info("END AdminAPI.destroy | admin deleted")

            api_response = {
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Admin deleted successfully',
            }
            return Response(api_response)
        except Exception as e:
            logger.error(f"Failed to delete admin: {str(e)}")
            error_message = f'Failed to delete admin: {str(e)}'
            error_response = {
                'status': 'error',
                'code': status.HTTP_400_BAD_REQUEST,
                'message': error_message
            }
            return Response(error_response)

    @swagger_auto_schema(
        operation_summary="Update FCM Token",
        operation_description="Update the FCM token for an admin.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'fcm_token': openapi.Schema(type=openapi.TYPE_STRING, description='FCM Token')
            },
            required=['fcm_token']
        ),
        responses={200: "FCM token updated successfully"}
    )
    def update_fcm_token(self, request, pk=None):
        logger.info("START AdminAPI.update_fcm_token | request data: %s", request.data)
        admin = self.get_object()
        fcm_token = request.data.get('fcm_token')
        if not fcm_token:
            logger.error("FCM token is required")
            return error_response("FCM token is required")
        admin.fcm_token = fcm_token
        admin.save()
        logger.info("END AdminAPI.update_fcm_token | FCM token updated")
        return success_response("FCM token updated successfully")


class AdminLoginAPI(APIView):
    permission_classes = []  # Allow unauthenticated access for login

    @swagger_auto_schema(
        operation_summary="Admin Login",
        operation_description="""
        Authenticate a system administrator and return JWT access and refresh tokens.

        Use this endpoint to get JWT tokens for admin authentication.
        The returned access token should be included in the Authorization header as:
        `Authorization: Bearer <access_token>`
        """,
        request_body=AdminLoginSerializer,
        responses={
            200: openapi.Response(
                description="Login successful",
                examples={
                    "application/json": {
                        "status": "success",
                        "message": "Login successful",
                        "username": "admin_username",
                        "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
                    }
                }
            ),
            401: openapi.Response(
                description="Invalid credentials",
                examples={
                    "application/json": {
                        "status": "error",
                        "message": "Invalid password"
                    }
                }
            ),
            404: openapi.Response(
                description="Admin not found",
                examples={
                    "application/json": {
                        "status": "error",
                        "message": "Admin not found"
                    }
                }
            ),
            400: openapi.Response(
                description="Bad request",
                examples={
                    "application/json": {
                        "username": ["This field is required."],
                        "password": ["This field is required."]
                    }
                }
            )
        },
        tags=['Authentication - Admin']
    )
    def post(self, request):
        logger.info("START AdminLoginAPI.post | request data: %s", request.data)
        serializer = AdminLoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data.get('username')
            password = serializer.validated_data.get('password')
            fcm_token = serializer.validated_data.get('fcm_token')  # Get FCM token from request

            try:
                admin = Systemadmin.objects.filter(username=username).first()

                if admin and admin.check_password(password):
                    # Update FCM token if provided
                    if fcm_token:
                        admin.fcm_token = fcm_token
                        admin.save(update_fields=['fcm_token'])
                        logger.info(f"Updated FCM token for admin {admin.id}")
                    
                    # Generate access and refresh tokens
                    refresh = RefreshToken.for_user(admin)
                    refresh['user_type'] = 'system_admin'
                    access = refresh.access_token

                    logger.info(f"END AdminLoginAPI.post | Admin {username} logged in successfully")
                    return Response({
                        'status': 'success',
                        'message': 'Login successful',
                        'username': admin.username,
                        'access': str(access),
                        'refresh': str(refresh)
                    }, status=status.HTTP_200_OK)
                elif admin:
                    logger.warning(f"Invalid password attempt for admin {username}")
                    return Response({
                        'status': 'error',
                        'message': 'Invalid password'
                    }, status=status.HTTP_401_UNAUTHORIZED)
                else:
                    logger.warning(f"Admin not found: {username}")
                    return Response({
                        'status': 'error',
                        'message': 'Admin not found'
                    }, status=status.HTTP_404_NOT_FOUND)

            except Exception as e:
                logger.error(f"Error during admin login: {str(e)}")
                return Response({
                    'status': 'error',
                    'message': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.warning(f"Invalid data for login attempt: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FCMNotification(APIView):

    def post(self, request):
        logger.info("START FCMNotification.post | request data: %s", request.data)
        token = request.data.get("token")
        title = request.data.get("title")
        body = request.data.get("body")
        data = request.data.get("data", {})

        if not token or not title or not body:
            logger.warning("FCMNotification.post | Missing required fields: token, title, or body.")
            return Response({
                "status": "error",
                "code": 400,
                "message": "Missing required fields: token, title, or body.",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        result = send_fcm_notification(token, title, body, data)
        logger.info("END FCMNotification.post | Notification sent, result: %s", result)
        return Response(result, status=result["code"])

class FCMGlobalNotification(APIView):

    def post(self, request):
        logger.info("START FCMGlobalNotification.post | request data: %s", request.data)
        topic = request.data.get("topic", "global")
        title = request.data.get("title")
        body = request.data.get("body")
        data = request.data.get("data", {})

        if not title or not body:
            logger.warning("FCMGlobalNotification.post | Missing required fields: title or body.")
            return Response({
                "status": "error",
                "code": 400,
                "message": "Missing required fields: title or body.",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            message = messaging.Message(
                topic=topic,
                notification=messaging.Notification(title=title, body=body),
                data=data if isinstance(data, dict) else {}
            )
            response = messaging.send(message)
            logger.info("END FCMGlobalNotification.post | Notification sent to topic '%s', response: %s", topic, response)
            return Response({
                "status": "success",
                "code": 200,
                "message": f"Notification sent to topic '{topic}'.",
                "data": {"response": response}
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error("FCMGlobalNotification.post | Error: %s", str(e))
            return Response({
                "status": "error",
                "code": 500,
                "message": str(e),
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PhoneNumberLookupView(APIView):
    """
    API endpoint to lookup phone number and return user type and ID.
    Useful for authentication and user identification across the system.
    """
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Lookup Phone Number",
        operation_description="""
        Look up a phone number to find which user type (vendor, milkman, or customer) 
        it belongs to and return the user's ID.
        
        This endpoint is useful for:
        - Login flows to determine user type
        - Checking if a phone number is registered
        - Finding which model a user belongs to
        """,
        manual_parameters=[
            openapi.Parameter(
                'phone_number',
                openapi.IN_QUERY,
                description="Phone number to lookup",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={
            200: openapi.Response(
                description="Phone number found",
                examples={
                    "application/json": {
                        "status": "success",
                        "code": 200,
                        "message": "Phone number found",
                        "data": {
                            "phone_number": "+1234567890",
                            "user_type": "vendor",
                            "user_id": 1,
                            "user_type_display": "Vendor",
                            "created_at": "2025-10-17T10:00:00Z",
                            "updated_at": "2025-10-17T10:00:00Z"
                        }
                    }
                }
            ),
            404: openapi.Response(
                description="Phone number not found",
                examples={
                    "application/json": {
                        "status": "error",
                        "code": 404,
                        "message": "Phone number not registered"
                    }
                }
            )
        },
        tags=['Phone Number Management']
    )
    def get(self, request):
        logger.info("START PhoneNumberLookupView.get | query params: %s", request.query_params)
        phone_number = request.query_params.get('phone_number')
        if not phone_number:
            logger.warning("PhoneNumberLookupView.get | Phone number is required")
            return Response({
                'status': 'error',
                'code': status.HTTP_400_BAD_REQUEST,
                'message': 'Phone number is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        result = lookup_phone_number(phone_number)
        if result:
            logger.info("END PhoneNumberLookupView.get | Phone number found: %s", phone_number)
            return Response({
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Phone number found',
                'data': result
            }, status=status.HTTP_200_OK)
        else:
            logger.info("END PhoneNumberLookupView.get | Phone number not registered: %s", phone_number)
            return Response({
                'status': 'error',
                'code': status.HTTP_404_NOT_FOUND,
                'message': 'Phone number not registered'
            }, status=status.HTTP_404_NOT_FOUND)


class UniquePhoneNumberViewSet(ModelViewSet):
    """
    ViewSet for managing unique phone numbers.
    Admin-only access for viewing and managing the centralized phone number registry.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = UniquePhoneNumber.objects.all()
    serializer_class = UniquePhoneNumberSerializer

    @swagger_auto_schema(
        operation_summary="List All Phone Numbers",
        operation_description="""
        Retrieve a list of all registered phone numbers across all user types.
        
        **Authentication required**: This endpoint requires admin JWT token.
        """,
        responses={200: UniquePhoneNumberSerializer(many=True)},
        tags=['Phone Number Management'],
        security=[{'Bearer': []}]
    )
    def list(self, request, *args, **kwargs):
        logger.info("START UniquePhoneNumberViewSet.list | query params: %s", request.query_params)
        try:
            queryset = self.filter_queryset(self.get_queryset())
            # Optional filtering by user_type
            user_type = request.query_params.get('user_type')
            if user_type:
                queryset = queryset.filter(user_type=user_type)
            serializer = self.get_serializer(queryset, many=True)
            logger.info("END UniquePhoneNumberViewSet.list | count: %d", queryset.count())
            return Response({
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Phone numbers retrieved successfully',
                'count': queryset.count(),
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"UniquePhoneNumberViewSet.list | Error: {e}")
            return Response({
                'status': 'error',
                'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Get Phone Number Details",
        operation_description="Retrieve details of a specific phone number entry.",
        responses={200: UniquePhoneNumberSerializer()},
        tags=['Phone Number Management'],
        security=[{'Bearer': []}]
    )
    def retrieve(self, request, *args, **kwargs):
        logger.info("START UniquePhoneNumberViewSet.retrieve | args: %s, kwargs: %s", args, kwargs)
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            logger.info("END UniquePhoneNumberViewSet.retrieve | phone number id: %s", getattr(instance, 'id', None))
            return Response({
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Phone number details retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"UniquePhoneNumberViewSet.retrieve | Error: {e}")
            return Response({
                'status': 'error',
                'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @swagger_auto_schema(
        operation_summary="Delete Phone Number",
        operation_description="""
        Delete a phone number entry. 
        
        **Warning**: This should only be done when the corresponding user is also deleted.
        """,
        responses={200: "Phone number deleted successfully"},
        tags=['Phone Number Management'],
        security=[{'Bearer': []}]
    )
    def destroy(self, request, *args, **kwargs):
        logger.info("START UniquePhoneNumberViewSet.destroy | args: %s, kwargs: %s", args, kwargs)
        try:
            instance = self.get_object()
            instance.delete()
            logger.info("END UniquePhoneNumberViewSet.destroy | phone number id: %s", getattr(instance, 'id', None))
            return Response({
                'status': 'success',
                'code': status.HTTP_200_OK,
                'message': 'Phone number deleted successfully'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"UniquePhoneNumberViewSet.destroy | Error: {e}")
            return Response({
                'status': 'error',
                'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NotificationHistoryPagination(PageNumberPagination):
    page_size = 10

class NotificationView(APIView):
    @swagger_auto_schema(
        operation_summary="Send Notification",
        operation_description="""
        Send FCM notifications to a single user, a group, or a topic. You can specify either a single `token`, a list of `tokens`, or a `topic` to target the notification. The payload can include optional data, priority, and channel for categorization.
        
        - If `token` is provided, sends to a single user.
        - If `tokens` is provided, sends to a group (batch processed).
        - If `topic` is provided, sends to all users subscribed to that topic.
        
        **At least one of `token`, `tokens`, or `topic` must be provided.**
        """,
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'title': openapi.Schema(type=openapi.TYPE_STRING, description='Title of the notification', example='Test Notification'),
                'body': openapi.Schema(type=openapi.TYPE_STRING, description='Body text of the notification', example='This is a test notification.'),
                'data': openapi.Schema(type=openapi.TYPE_OBJECT, description='Optional data payload', nullable=True, example={"key": "value"}),
                'token': openapi.Schema(type=openapi.TYPE_STRING, description='FCM token for a single user', nullable=True, example='fcm_token_123'),
                'tokens': openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description='List of FCM tokens for a group',
                    nullable=True,
                    example=['token1', 'token2']
                ),
                'topic': openapi.Schema(type=openapi.TYPE_STRING, description='Topic name for topic-based notifications', nullable=True, example='news'),
                'priority': openapi.Schema(type=openapi.TYPE_STRING, description='Priority of the notification (high or normal)', default='high', nullable=True, example='high'),
                'channel': openapi.Schema(type=openapi.TYPE_STRING, description='Channel for categorizing notifications', default='general', nullable=True, example='alerts'),
            },
            required=['title', 'body'],
            example={
                "title": "Test Notification",
                "body": "This is a test notification.",
                "token": "fcm_token_123",
                "priority": "high",
                "channel": "alerts"
            }
        ),
        responses={
            200: openapi.Response(
                description="Notification sent successfully",
                examples={
                    "application/json": {
                        "status": "success",
                        "code": 200,
                        "message": "Notification sent successfully",
                        "data": {"response": "firebase_response_id"}
                    }
                }
            ),
            400: openapi.Response(
                description="Bad request",
                examples={
                    "application/json": {
                        "status": "error",
                        "code": 400,
                        "message": "Either 'token', 'tokens', or 'topic' must be provided",
                        "data": None
                    }
                }
            ),
            403: openapi.Response(
                description="User opted out of updates",
                examples={
                    "application/json": {
                        "status": "error",
                        "code": 403,
                        "message": "User has opted out of updates",
                        "data": None
                    }
                }
            )
        }
    )
    def post(self, request, *args, **kwargs):
        logger.info("Entering post method in NotificationView")
        try:
            title = request.data.get('title')
            body = request.data.get('body')
            data = request.data.get('data', {})
            token = request.data.get('token')
            tokens = request.data.get('tokens')
            topic = request.data.get('topic')
            priority = request.data.get('priority', 'high')
            channel = request.data.get('channel', 'general')

            # Validate required fields
            if not title or not body:
                logger.warning("Missing required fields: title or body")
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Missing required fields: title and body are required",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check user preferences only for Systemadmin users
            user = request.user
            if user and hasattr(user, 'id') and isinstance(user, Systemadmin):
                preferences = NotificationPreference.objects.filter(user=user).first()
                if preferences and not preferences.receive_updates:
                    logger.info(f"Systemadmin {user.username} has opted out of updates")
                    return Response({
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "User has opted out of updates",
                        "data": None
                    }, status=status.HTTP_403_FORBIDDEN)

            if token:
                # Single user notification
                logger.info(f"Sending single user notification to token: {token[:20]}...")
                response = send_fcm_notification_with_priority(token, title, body, data, priority)
                NotificationLog.objects.create(
                    title=title, 
                    body=body, 
                    recipient=token, 
                    status=response.get('status', 'unknown'), 
                    channel=channel, 
                    priority=priority,
                    data=data
                )
                logger.info(f"Single notification sent with status: {response.get('status')}")
                return Response({
                    "status": "success" if response.get('status') == 'success' else "error",
                    "code": response.get('code', status.HTTP_200_OK),
                    "message": response.get('message', 'Notification sent successfully'),
                    "data": response.get('data')
                }, status=response.get('code', status.HTTP_200_OK))

            elif tokens:
                # Group notification
                logger.info(f"Sending group notification to {len(tokens)} tokens")
                valid_tokens = validate_and_cleanup_tokens(tokens)
                responses = send_group_notifications_in_batches(valid_tokens, title, body, data)
                NotificationLog.objects.create(
                    title=title, 
                    body=body, 
                    recipient=','.join(valid_tokens), 
                    status="sent", 
                    channel=channel, 
                    priority=priority,
                    data=data
                )
                logger.info(f"Group notifications sent to {len(valid_tokens)} valid tokens")
                return Response({
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Group notifications sent successfully",
                    "data": responses
                }, status=status.HTTP_200_OK)

            elif topic:
                # Topic-based notification
                logger.info(f"Sending topic notification to: {topic}")
                response = send_topic_notification(topic, title, body, data)
                NotificationLog.objects.create(
                    title=title, 
                    body=body, 
                    recipient=topic, 
                    status=response.get('status', 'unknown'), 
                    channel=channel, 
                    priority=priority,
                    data=data
                )
                logger.info(f"Topic notification sent with status: {response.get('status')}")
                return Response({
                    "status": "success" if response.get('status') == 'success' else "error",
                    "code": response.get('code', status.HTTP_200_OK),
                    "message": response.get('message', 'Topic notification sent successfully'),
                    "data": response.get('data')
                }, status=response.get('code', status.HTTP_200_OK))

            logger.warning("No valid recipient provided (token, tokens, or topic)")
            return Response({
                "status": "error",
                "code": status.HTTP_400_BAD_REQUEST,
                "message": "Either 'token', 'tokens', or 'topic' must be provided",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Error sending notification: {str(e)}")
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while sending notification: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NotificationHistoryView(APIView):
    @swagger_auto_schema(
        operation_summary="Get Notification History",
        operation_description="""
        Retrieve a paginated list of notification logs. Supports search by title and filtering by channel. Results are ordered by priority and creation date.
        
        Query Parameters:
        - `search`: Search notifications by title (optional)
        - `channel`: Filter notifications by channel (optional)
        - `page`: Page number for pagination (optional)
        """,
        responses={
            200: openapi.Response(
                description="Paginated notification history",
                examples={
                    "application/json": {
                        "count": 1,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": 1,
                                "title": "Test Notification",
                                "body": "This is a test notification.",
                                "data": {"key": "value"},
                                "recipient": "fcm_token_123",
                                "status": "success",
                                "channel": "alerts",
                                "priority": "high",
                                "read": False,
                                "created_at": "2025-10-29T12:00:00Z"
                            }
                        ]
                    }
                }
            )
        }
    )
    def get(self, request):
        logger.info("Entering get method in NotificationHistoryView")
        try:
            query = request.query_params.get('search')
            channel = request.query_params.get('channel')
            paginator = NotificationHistoryPagination()
            notifications = NotificationLog.objects.all()

            if query:
                notifications = notifications.filter(title__icontains=query)
                logger.info(f"Filtering notifications by search query: {query}")
            
            if channel:
                notifications = notifications.filter(channel=channel)
                logger.info(f"Filtering notifications by channel: {channel}")

            notifications = notifications.order_by('-priority', '-created_at')
            result_page = paginator.paginate_queryset(notifications, request)
            serializer = NotificationLogSerializer(result_page, many=True)
            
            logger.info(f"Retrieved {len(result_page)} notifications")
            return paginator.get_paginated_response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error retrieving notification history: {str(e)}")
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while retrieving notification history: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MarkNotificationReadView(APIView):
    @swagger_auto_schema(
        operation_summary="Mark Notification as Read",
        operation_description="Mark a specific notification as read by its ID.",
        responses={
            200: openapi.Response(
                description="Notification marked as read",
                examples={
                    "application/json": {
                        "status": "success",
                        "message": "Notification marked as read",
                        "data": {
                            "id": 1,
                            "title": "Test Notification",
                            "body": "This is a test notification.",
                            "data": {"key": "value"},
                            "recipient": "fcm_token_123",
                            "status": "success",
                            "channel": "alerts",
                            "priority": "high",
                            "read": True,
                            "created_at": "2025-10-29T12:00:00Z"
                        }
                    }
                }
            ),
            404: openapi.Response(
                description="Notification not found",
                examples={
                    "application/json": {
                        "status": "error",
                        "message": "Notification not found"
                    }
                }
            )
        }
    )
    def post(self, request, notification_id):
        logger.info(f"Entering post method in MarkNotificationReadView for notification ID: {notification_id}")
        try:
            notification = NotificationLog.objects.get(id=notification_id)
            notification.read = True
            notification.save()
            serializer = NotificationLogSerializer(notification)
            
            logger.info(f"Notification {notification_id} marked as read")
            return Response({
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Notification marked as read successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except NotificationLog.DoesNotExist:
            logger.warning(f"Notification not found: {notification_id}")
            return Response({
                "status": "error",
                "code": status.HTTP_404_NOT_FOUND,
                "message": "Notification not found",
                "data": None
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {str(e)}")
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while marking notification as read: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def delete_expired_notifications():
    expiry_date = now() - timedelta(days=30)  # Keep notifications for 30 days
    NotificationLog.objects.filter(created_at__lt=expiry_date).delete()



# Efficient version: import models directly and use .values_list for minimal DB load

class AllUsersListView(APIView):
    """
    API endpoint to list all users grouped by their roles (vendor, milkman, customer).
    Returns only ID and name for each user.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="List All Users by Role (with FCM tokens)",
        operation_description="""
        Retrieve all users across the system grouped by their roles (vendor, milkman, customer).
        Returns the ID, name, and FCM token of each user for efficiency and notification support.

        **Authentication required**: This endpoint requires admin JWT token.

        Response includes:
        - Vendors: id, name, fcm_token
        - Milkmen: id, name, fcm_token
        - Customers: id, name, fcm_token
        - Total count for each user type

        Example response:
        {
            "status": "success",
            "code": 200,
            "message": "All users retrieved successfully",
            "data": {
                "vendors": [
                    {"id": 1, "name": "Vendor 1", "fcm_token": "token1"},
                    ...
                ],
                "milkmen": [
                    {"id": 2, "name": "Milkman 1", "fcm_token": "token2"},
                    ...
                ],
                "customers": [
                    {"id": 3, "name": "Customer 1", "fcm_token": "token3"},
                    ...
                ],
                "total_counts": {
                    "vendors": 10,
                    "milkmen": 5,
                    "customers": 100,
                    "total": 115
                }
            }
        }
        """,
        tags=['User Management'],
        security=[{'Bearer': []}]
    )
    def get(self, request):
        logger.info("Entering get method in AllUsersListView (with FCM tokens)")
        try:
            # Vendors: id, name, fcm_token
            vendors = VendorBusinessRegistration.objects.values_list('id', 'name', 'fcm_token').order_by('name')
            vendors_list = [
                {"id": vid, "name": vname or "", "fcm_token": vtoken or None}
                for vid, vname, vtoken in vendors
            ]

            # Milkmen: id, full_name, fcm_token
            milkmen = Milkman.objects.values_list('id', 'full_name', 'fcm_token').order_by('full_name')
            milkmen_list = [
                {"id": mid, "name": mname or "", "fcm_token": mtoken or None}
                for mid, mname, mtoken in milkmen
            ]

            # Customers: id, first_name, last_name, fcm_token
            customers = Customer.objects.values_list('id', 'first_name', 'last_name', 'fcm_token').order_by('first_name', 'last_name')
            customers_list = [
                {"id": cid, "name": f"{fname or ''} {lname or ''}".strip(), "fcm_token": ctoken or None}
                for cid, fname, lname, ctoken in customers
            ]

            # Calculate counts
            vendors_count = len(vendors_list)
            milkmen_count = len(milkmen_list)
            customers_count = len(customers_list)
            total_count = vendors_count + milkmen_count + customers_count

            logger.info(f"Retrieved {vendors_count} vendors, {milkmen_count} milkmen, {customers_count} customers (with FCM tokens)")

            return Response({
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "All users retrieved successfully",
                "data": {
                    "vendors": vendors_list,
                    "milkmen": milkmen_list,
                    "customers": customers_list,
                    "total_counts": {
                        "vendors": vendors_count,
                        "milkmen": milkmen_count,
                        "customers": customers_count,
                        "total": total_count
                    }
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error retrieving all users: {str(e)}")
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while retrieving users: {str(e)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

