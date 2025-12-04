import hmac
import hashlib
import logging
import razorpay
from datetime import datetime, date, timedelta
from decimal import Decimal

# Django imports
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

# Third-party / REST framework
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

# Local application imports
from OneWindowHomeSolution.custom_authentication import CustomJWTAuthentication
from OneWindowHomeSolution.responses import success_response, error_response
from BusinessRegistration.models import VendorBusinessRegistration
from Customer.models import Customer
from Customer.billing_utils import generate_bill_for_period, get_or_create_customer_bill
from Dashboard.models import SubscriptionPlan
from Milkman.models import Milkman
from Systemadmin.models import Systemadmin
from vendorcalendar.models import DeliveryRecord, CustomerRequest

from .models import Payment, SubscribedVendor
from .serializers import (
    CreatePaymentOrderSerializer, VerifyPaymentSerializer,
    PaymentSerializer, PaymentHistorySerializer,
    CreateSubscriptionOrderSerializer, VerifySubscriptionPaymentSerializer,
    SubscribedVendorSerializer,
)

from Customer.models import Bill, BillLineItem

logger = logging.getLogger(__name__)

# Initialize Razorpay client
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


class CreatePaymentOrderView(APIView):
    """
    Create a Razorpay payment order for subscription or bill payment.
    Works for vendors (subscription) and customers (bills).
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Create Payment Order",
        operation_description="""
        Create a Razorpay payment order for vendor subscription or customer bill payment.
        
        **Payment Types:**
        - `subscription`: Vendor pays for subscription plan to admin
        - `bill`: Customer pays bill to admin (who settles with vendor)
        
        **Authentication required**: JWT token for vendor or customer
        
        The payer is automatically determined from the authenticated user.
        All payments are made to the admin (systemadmin).
        """,
        request_body=CreatePaymentOrderSerializer,
        responses={
            200: openapi.Response(
                description="Payment order created successfully",
                examples={
                    "application/json": {
                        "status": "success",
                        "code": 200,
                        "message": "Payment order created successfully",
                        "data": {
                            "order_id": "order_xyz123",
                            "amount": 1000.00,
                            "currency": "INR",
                            "payment_type": "subscription",
                            "razorpay_key_id": "rzp_test_xxx"
                        }
                    }
                }
            ),
            400: "Bad request - validation errors",
            500: "Internal server error"
        },
        tags=['Payments']
    )
    def post(self, request):
        logger.info("Entering CreatePaymentOrderView with data: %s", request.data)
        
        try:
            serializer = CreatePaymentOrderSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning("Invalid payment order data: %s", serializer.errors)
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid data",
                    "errors": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = serializer.validated_data
            amount = data['amount']
            payment_type = data['payment_type']
            subscription_plan_id = data.get('subscription_plan_id')
            description = data.get('description', '')
            notes = data.get('notes', {})
            
            # Get the authenticated user
            user = request.user
            user_type = getattr(user, 'user_type', None) or self._get_user_type(user)
            
            logger.info(f"Payment request from user type: {user_type}, user id: {user.id}")
            
            # Validate payment type against user type
            if payment_type == 'subscription' and user_type != 'vendor':
                return Response({
                    "status": "error",
                    "code": status.HTTP_403_FORBIDDEN,
                    "message": "Only vendors can make subscription payments"
                }, status=status.HTTP_403_FORBIDDEN)
            
            if payment_type == 'bill' and user_type != 'customer':
                return Response({
                    "status": "error",
                    "code": status.HTTP_403_FORBIDDEN,
                    "message": "Only customers can make bill payments"
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Get subscription plan if provided
            subscription_plan = None
            if subscription_plan_id:
                try:
                    subscription_plan = SubscriptionPlan.objects.get(id=subscription_plan_id)
                except SubscriptionPlan.DoesNotExist:
                    return Response({
                        "status": "error",
                        "code": status.HTTP_404_NOT_FOUND,
                        "message": "Subscription plan not found"
                    }, status=status.HTTP_404_NOT_FOUND)
            
            # Get admin (payee) - first systemadmin
            try:
                admin = Systemadmin.objects.first()
                if not admin:
                    raise Systemadmin.DoesNotExist("No admin found")
            except Systemadmin.DoesNotExist:
                logger.error("No systemadmin found for payment")
                return Response({
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Payment system not configured properly"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Get payer content type and object
            payer_obj = self._get_payer_object(user, user_type)
            payer_content_type = ContentType.objects.get_for_model(payer_obj)
            
            # Create Razorpay order
            amount_in_paise = int(float(amount) * 100)  # Convert to paise
            receipt = f"{payment_type}_{user_type}_{user.id}_{int(datetime.now().timestamp())}"
            
            razorpay_order = razorpay_client.order.create({
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": receipt,
                "notes": notes
            })
            
            logger.info(f"Razorpay order created: {razorpay_order['id']}")
            
            # Create Payment record in database
            with transaction.atomic():
                payment = Payment.objects.create(
                    razorpay_order_id=razorpay_order['id'],
                    payment_type=payment_type,
                    amount=amount,
                    currency='INR',
                    status='created',
                    payer_content_type=payer_content_type,
                    payer_object_id=payer_obj.id,
                    payee=admin,
                    subscription_plan=subscription_plan,
                    description=description,
                    notes=notes,
                    receipt=receipt,
                    user_id=user.id,
                    user_role=user_type
                )

                # --- Bill creation logic for customer bill payments ---
                if payment_type == 'bill' and user_type == 'customer':
                    # Look for existing pending bill for this customer
                    vendor = payer_obj.provider
                    if not vendor:
                        logger.error(f"No vendor assigned to customer {payer_obj.id}")
                        return Response({
                            "status": "error",
                            "code": status.HTTP_400_BAD_REQUEST,
                            "message": "No vendor assigned to this customer"
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Find existing pending bill (created by list_bills endpoint)
                    bill = Bill.objects.filter(
                        customer=payer_obj,
                        vendor=vendor,
                        status='pending'
                    ).order_by('-created_at').first()
                    
                    if bill:
                        # Link existing pending bill to this payment
                        bill.payment = payment
                        bill.save(update_fields=['payment'])
                        logger.info("Linked existing pending bill %s to payment %s", bill.id, payment.id)
                    else:
                        # No pending bill exists - create one using billing_utils
                        bill, error_msg = get_or_create_customer_bill(payer_obj, vendor)
                        if bill:
                            bill.payment = payment
                            bill.save(update_fields=['payment'])
                            logger.info("Created new bill %s and linked to payment %s", bill.id, payment.id)
                        else:
                            logger.warning("No bill created for customer %s: %s", payer_obj.id, error_msg)

            logger.info(f"Payment record created: {payment.id}")
            
            # Get user name and contact number (try user, then payer_obj)
            user_name = getattr(user, 'get_full_name', None)
            if callable(user_name):
                user_name = user.get_full_name()
            elif hasattr(user, 'first_name') and hasattr(user, 'last_name'):
                user_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
            else:
                user_name = getattr(user, 'username', '') or str(user)


            # Try to get contact number from user, fallback to payer_obj, always as string
            user_contact_number = None
            contact_obj = getattr(user, 'contact', None)
            if not contact_obj and payer_obj:
                contact_obj = getattr(payer_obj, 'contact', None)
            # If contact is a related object, try to get its value
            if contact_obj is not None:
                if hasattr(contact_obj, 'number'):
                    user_contact_number = str(getattr(contact_obj, 'number', ''))
                else:
                    user_contact_number = str(contact_obj)
            # If still not found, try contact_str
            if not user_contact_number:
                user_contact_number = getattr(user, 'contact_str', None) or (getattr(payer_obj, 'contact_str', None) if payer_obj else None)
            if user_contact_number is not None:
                user_contact_number = str(user_contact_number)

            return Response({
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Payment order created successfully",
                "data": {
                    "order_id": razorpay_order['id'],
                    "amount": float(amount),
                    "currency": "INR",
                    "payment_type": payment_type,
                    "razorpay_key_id": settings.RAZORPAY_KEY_ID,
                    "receipt": receipt,
                    "notes": notes,
                    "user_name": user_name,
                    "user_contact_number": user_contact_number
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error creating payment order: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while creating payment order: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_user_type(self, user):
        """Determine user type from user instance"""
        if isinstance(user, VendorBusinessRegistration):
            return 'vendor'
        elif isinstance(user, Customer):
            return 'customer'
        elif isinstance(user, Milkman):
            return 'milkman'
        else:
            return 'unknown'
    
    def _get_payer_object(self, user, user_type):
        """Get the actual payer object based on user type"""
        if user_type == 'vendor':
            return VendorBusinessRegistration.objects.get(id=user.id)
        elif user_type == 'customer':
            return Customer.objects.get(id=user.id)
        elif user_type == 'milkman':
            return Milkman.objects.get(id=user.id)
        else:
            raise ValueError(f"Unsupported user type: {user_type}")


class VerifyPaymentView(APIView):
    """
    Verify a Razorpay payment using signature verification.
    Updates payment status in database.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Verify Payment",
        operation_description="""
        Verify a Razorpay payment using signature verification.
        
        After successful payment on frontend, send the payment details here
        to verify and update the payment status.
        
        **Authentication required**: JWT token
        """,
        request_body=VerifyPaymentSerializer,
        responses={
            200: openapi.Response(
                description="Payment verified successfully",
                examples={
                    "application/json": {
                        "status": "success",
                        "code": 200,
                        "message": "Payment verified successfully",
                        "data": {
                            "payment_id": 1,
                            "order_id": "order_xyz123",
                            "status": "captured",
                            "amount": 1000.00
                        }
                    }
                }
            ),
            400: "Bad request or signature verification failed",
            404: "Payment order not found"
        },
        tags=['Payments']
    )
    def post(self, request):
        logger.info("Entering VerifyPaymentView with data: %s", request.data)
        
        try:
            serializer = VerifyPaymentSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning("Invalid verification data: %s", serializer.errors)
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid data",
                    "errors": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            data = serializer.validated_data
            razorpay_order_id = data['razorpay_order_id']
            razorpay_payment_id = data['razorpay_payment_id']
            razorpay_signature = data['razorpay_signature']
            
            # Get payment record
            try:
                payment = Payment.objects.get(razorpay_order_id=razorpay_order_id)
            except Payment.DoesNotExist:
                logger.error(f"Payment not found for order: {razorpay_order_id}")
                return Response({
                    "status": "error",
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Payment order not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Verify signature
            try:
                params_dict = {
                    'razorpay_order_id': razorpay_order_id,
                    'razorpay_payment_id': razorpay_payment_id,
                    'razorpay_signature': razorpay_signature
                }
                razorpay_client.utility.verify_payment_signature(params_dict)
                logger.info(f"Payment signature verified for order: {razorpay_order_id}")
                
                # Update payment record
                with transaction.atomic():
                    payment.razorpay_payment_id = razorpay_payment_id
                    payment.razorpay_signature = razorpay_signature
                    payment.status = 'captured'
                    payment.payment_completed_at = timezone.now()
                    payment.save()
                    # Update associated Bill status to 'paid'
                    bill = Bill.objects.filter(payment=payment).first()
                    if bill:
                        bill.status = 'paid'
                        bill.save()
                        
                        # Mark all delivery records linked to this bill as paid
                        # Method 1: Via BillLineItem.delivery_record ForeignKey
                        delivery_record_ids = BillLineItem.objects.filter(
                            bill=bill,
                            delivery_record__isnull=False
                        ).values_list('delivery_record_id', flat=True)
                        if delivery_record_ids:
                            DeliveryRecord.objects.filter(id__in=delivery_record_ids).update(bill_paid=True)
                            logger.info(f"Marked {len(delivery_record_ids)} delivery records as paid via BillLineItem")
                        
                        # Method 2: Via DeliveryRecord.bill ForeignKey (backup)
                        updated_count = DeliveryRecord.objects.filter(bill=bill, bill_paid=False).update(bill_paid=True)
                        if updated_count > 0:
                            logger.info(f"Marked {updated_count} additional delivery records as paid via bill FK")
                logger.info(f"Payment {payment.id} updated to captured status")
                return Response({
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Payment verified successfully",
                    "data": {
                        "payment_id": payment.id,
                        "order_id": payment.razorpay_order_id,
                        "payment_type": payment.payment_type,
                        "status": payment.status,
                        "amount": float(payment.amount),
                        "currency": payment.currency,
                        "completed_at": payment.payment_completed_at.isoformat() if payment.payment_completed_at else None
                    }
                }, status=status.HTTP_200_OK)
                
            except razorpay.errors.SignatureVerificationError:
                logger.error(f"Signature verification failed for order: {razorpay_order_id}")
                
                # Update payment as failed
                with transaction.atomic():
                    payment.status = 'failed'
                    payment.save()
                    # Clean up orphaned Bill and BillLineItems if any
                    bill = Bill.objects.filter(payment=payment).first()
                    if bill:
                        BillLineItem.objects.filter(bill=bill).delete()
                        bill.delete()
                
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Payment signature verification failed"
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error verifying payment: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while verifying payment: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentHistoryView(APIView):
    """
    Get payment history for the authenticated user.
    Supports filtering and pagination.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Payment History",
        operation_description="""
        Retrieve payment history for the authenticated user.
        
        **Query Parameters:**
        - `payment_type`: Filter by payment type (subscription/bill)
        - `status`: Filter by payment status
        - `limit`: Number of records per page (default: 20)
        - `offset`: Pagination offset (default: 0)
        
        **Authentication required**: JWT token
        """,
        manual_parameters=[
            openapi.Parameter('payment_type', openapi.IN_QUERY, type=openapi.TYPE_STRING, 
                            description="Filter by payment type (subscription/bill)"),
            openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING,
                            description="Filter by status (created/pending/captured/failed)"),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, 
                            description="Number of records (default: 20)"),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER,
                            description="Pagination offset (default: 0)"),
        ],
        responses={
            200: PaymentHistorySerializer(many=True)
        },
        tags=['Payments']
    )
    def get(self, request):
        logger.info("Entering PaymentHistoryView")
        
        try:
            user = request.user
            user_type = getattr(user, 'user_type', None)
            
            # Determine user type if not in token
            if not user_type:
                if isinstance(user, VendorBusinessRegistration):
                    user_type = 'vendor'
                elif isinstance(user, Customer):
                    user_type = 'customer'
                elif isinstance(user, Milkman):
                    user_type = 'milkman'
            
            # Get payer object and content type
            if user_type == 'vendor':
                payer_obj = VendorBusinessRegistration.objects.get(id=user.id)
            elif user_type == 'customer':
                payer_obj = Customer.objects.get(id=user.id)
            elif user_type == 'milkman':
                payer_obj = Milkman.objects.get(id=user.id)
            else:
                return Response({
                    "status": "error",
                    "code": status.HTTP_403_FORBIDDEN,
                    "message": "Invalid user type for payment history"
                }, status=status.HTTP_403_FORBIDDEN)
            
            payer_content_type = ContentType.objects.get_for_model(payer_obj)
            
            # Build query
            payments = Payment.objects.filter(
                payer_content_type=payer_content_type,
                payer_object_id=payer_obj.id
            ).select_related('subscription_plan', 'payee')
            
            # Apply filters
            payment_type = request.query_params.get('payment_type')
            if payment_type:
                payments = payments.filter(payment_type=payment_type)
            
            payment_status = request.query_params.get('status')
            if payment_status:
                payments = payments.filter(status=payment_status)
            
            # Pagination
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))
            
            total_count = payments.count()
            payments = payments[offset:offset + limit]
            
            serializer = PaymentHistorySerializer(payments, many=True)
            
            logger.info(f"Retrieved {len(serializer.data)} payment records for user {user.id}")
            
            return Response({
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Payment history retrieved successfully",
                "data": {
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "payments": serializer.data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving payment history: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while retrieving payment history: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminPaymentHistoryView(APIView):
    """
    Get all payment history for admin with advanced filtering.
    Admin can see all payments in the system.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get All Payment History (Admin Only)",
        operation_description="""
        Retrieve all payment history across the system. Admin only endpoint.
        
        **Query Parameters:**
        - `payment_type`: Filter by payment type (subscription/bill)
        - `status`: Filter by payment status
        - `payer_type`: Filter by payer type (vendor/customer/milkman)
        - `payer_id`: Filter by specific payer ID
        - `start_date`: Filter payments from this date (YYYY-MM-DD)
        - `end_date`: Filter payments until this date (YYYY-MM-DD)
        - `limit`: Number of records per page (default: 50)
        - `offset`: Pagination offset (default: 0)
        
        **Authentication required**: Admin JWT token
        """,
        manual_parameters=[
            openapi.Parameter('payment_type', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('status', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('payer_type', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('payer_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('limit', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('offset', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
        ],
        responses={
            200: PaymentHistorySerializer(many=True)
        },
        tags=['Payments - Admin']
    )
    def get(self, request):
        logger.info("Entering AdminPaymentHistoryView")
        
        try:
            # Verify user is admin
            user = request.user
            if not isinstance(user, Systemadmin):
                return Response({
                    "status": "error",
                    "code": status.HTTP_403_FORBIDDEN,
                    "message": "Admin access required"
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Build query
            payments = Payment.objects.all().select_related('subscription_plan', 'payee', 'payer_content_type')
            
            # Apply filters
            payment_type = request.query_params.get('payment_type')
            if payment_type:
                payments = payments.filter(payment_type=payment_type)
            
            payment_status = request.query_params.get('status')
            if payment_status:
                payments = payments.filter(status=payment_status)
            
            payer_type = request.query_params.get('payer_type')
            if payer_type:
                # Map payer_type to content type model
                model_map = {
                    'vendor': VendorBusinessRegistration,
                    'customer': Customer,
                    'milkman': Milkman
                }
                if payer_type in model_map:
                    ct = ContentType.objects.get_for_model(model_map[payer_type])
                    payments = payments.filter(payer_content_type=ct)
            
            payer_id = request.query_params.get('payer_id')
            if payer_id:
                payments = payments.filter(payer_object_id=payer_id)
            
            # Date filtering
            start_date = request.query_params.get('start_date')
            if start_date:
                payments = payments.filter(created_at__date__gte=start_date)
            
            end_date = request.query_params.get('end_date')
            if end_date:
                payments = payments.filter(created_at__date__lte=end_date)
            
            # Pagination
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
            
            total_count = payments.count()
            payments = payments[offset:offset + limit]
            
            serializer = PaymentHistorySerializer(payments, many=True)
            
            # Calculate statistics
            stats = Payment.objects.aggregate(
                total_amount=Sum('amount'),
                total_captured=Sum('amount', filter=Q(status='captured')),
                total_pending=Count('id', filter=Q(status__in=['created', 'pending'])),
                total_failed=Count('id', filter=Q(status='failed')),
                total_subscription=Sum('amount', filter=Q(payment_type='subscription', status='captured')),
                total_bills=Sum('amount', filter=Q(payment_type='bill', status='captured'))
            )
            
            logger.info(f"Retrieved {len(serializer.data)} payment records for admin")
            
            return Response({
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Payment history retrieved successfully",
                "data": {
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "statistics": {
                        "total_amount": float(stats['total_amount'] or 0),
                        "total_captured": float(stats['total_captured'] or 0),
                        "total_pending": stats['total_pending'],
                        "total_failed": stats['total_failed'],
                        "subscription_revenue": float(stats['total_subscription'] or 0),
                        "bill_revenue": float(stats['total_bills'] or 0)
                    },
                    "payments": serializer.data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving admin payment history: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while retrieving payment history: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateSubscriptionOrderView(APIView):
    """
    Create a Razorpay order for vendor subscription purchase.
    Creates both Payment and SubscribedVendor records.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Create Subscription Order (Vendor Only)",
        operation_description="""
        Create a Razorpay order for vendor to purchase a subscription plan.
        
        This endpoint:
        1. Creates a Razorpay order
        2. Creates a SubscribedVendor record with payment details
        3. Creates a Payment record for transaction tracking
        
        **Authentication required**: Vendor JWT token
        
        **Workflow:**
        1. Call this endpoint to create order
        2. Use returned `razorpay_key` and `order_id` in frontend Razorpay checkout
        3. After payment, call VerifySubscriptionPaymentView to complete subscription
        """,
        request_body=CreateSubscriptionOrderSerializer,
        responses={
            201: openapi.Response(
                description="Subscription order created successfully",
                examples={
                    "application/json": {
                        "status": "success",
                        "code": 201,
                        "message": "Subscription order created successfully",
                        "data": {
                            "subscription_details": {
                                "id": 1,
                                "vendor_id": 5,
                                "vendor_name": "John's Dairy",
                                "plan_id": 2,
                                "plan_name": "Monthly Plan",
                                "plan_price": "500.00",
                                "razorpay_order_id": "order_xyz123",
                                "payment_status": "Pending",
                                "subscription_status": "ACTIVE"
                            },
                            "razorpay_key": "rzp_live_xxx",
                            "order_id": "order_xyz123",
                            "amount": 500.00,
                            "currency": "INR"
                        }
                    }
                }
            ),
            400: "Bad request - invalid data",
            403: "Forbidden - only vendors can purchase subscriptions",
            404: "Subscription plan not found",
            500: "Internal server error"
        },
        tags=['Subscription Management']
    )
    def post(self, request):
        logger.info("Entering CreateSubscriptionOrderView with data: %s", request.data)
        
        try:
            # Validate request data
            serializer = CreateSubscriptionOrderSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning("Invalid subscription order data: %s", serializer.errors)
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid data",
                    "errors": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get authenticated user and verify it's a vendor
            user = request.user
            user_type = getattr(user, 'user_type', None)
            
            if user_type != 'vendor':
                if not isinstance(user, VendorBusinessRegistration):
                    return Response({
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Only vendors can purchase subscriptions"
                    }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor object
            try:
                vendor = VendorBusinessRegistration.objects.get(id=user.id)
            except VendorBusinessRegistration.DoesNotExist:
                return Response({
                    "status": "error",
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Vendor not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get subscription plan
            subscription_plan_id = serializer.validated_data['subscription_plan_id']
            
            try:
                subscription_plan = SubscriptionPlan.objects.get(id=subscription_plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response({
                    "status": "error",
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Subscription plan not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get admin (payee)
            try:
                admin = Systemadmin.objects.first()
                if not admin:
                    raise Systemadmin.DoesNotExist("No admin found")
            except Systemadmin.DoesNotExist:
                logger.error("No systemadmin found for subscription payment")
                return Response({
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Payment system not configured properly"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Create Razorpay order
            amount = subscription_plan.price
            amount_in_paise = int(float(amount) * 100)
            receipt = f"sub_{vendor.id}_{subscription_plan_id}_{int(datetime.now().timestamp())}"
            
            order_data = {
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": receipt,
                "payment_capture": 1,
            }
            
            try:
                razorpay_order = razorpay_client.order.create(data=order_data)
            except Exception as e:
                logger.error(f"Failed to create Razorpay order: {str(e)}", exc_info=True)
                return Response({
                    "status": "error",
                    "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "message": "Failed to create Razorpay order",
                    "error": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            logger.info(f"Razorpay subscription order created: {razorpay_order['id']}")
            
            # Create database records in transaction
            with transaction.atomic():
                # Create SubscribedVendor record
                subscribed_vendor = SubscribedVendor.objects.create(
                    vendor=vendor,
                    plan=subscription_plan,
                    razorpay_order_id=razorpay_order['id'],
                    payment_status='Pending',
                    subscription_status='ACTIVE',  # Will be active once payment is verified
                    plan_purchase_date=timezone.now().date()
                )
                
                # Create Payment record for transaction tracking
                payer_content_type = ContentType.objects.get_for_model(VendorBusinessRegistration)
                payment = Payment.objects.create(
                    razorpay_order_id=razorpay_order['id'],
                    payment_type='subscription',
                    amount=amount,
                    currency='INR',
                    status='created',
                    payer_content_type=payer_content_type,
                    payer_object_id=vendor.id,
                    payee=admin,
                    subscription_plan=subscription_plan,
                    description=f"Subscription: {subscription_plan.plan_name}",
                    receipt=receipt,
                    notes={
                        'subscription_plan': subscription_plan.plan_name,
                        'vendor_id': vendor.id,
                        'vendor_name': vendor.name
                    },
                    user_id=user.id,
                    user_role=user_type
                )
            
            logger.info(f"SubscribedVendor record created: {subscribed_vendor.id}, Payment record: {payment.id}")
            
            # Serialize subscription details
            subscription_serializer = SubscribedVendorSerializer(subscribed_vendor)
            
            return Response({
                "status": "success",
                "code": status.HTTP_201_CREATED,
                "message": "Subscription order created successfully",
                "data": {
                    "subscription_details": subscription_serializer.data,
                    "razorpay_key": settings.RAZORPAY_KEY_ID,
                    "order_id": razorpay_order['id'],
                    "amount": float(amount),
                    "currency": "INR",
                    "vendor_contact_number": getattr(vendor, "contact_number", None)
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Error creating subscription order: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while creating subscription order: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifySubscriptionPaymentView(APIView):
    """
    Verify subscription payment and activate subscription.
    Updates both SubscribedVendor and Payment records.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Verify Subscription Payment",
        operation_description="""
        Verify Razorpay payment signature for subscription purchase.
        
        This endpoint:
        1. Verifies Razorpay payment signature
        2. Updates SubscribedVendor payment status to 'Completed'
        3. Updates Payment record status to 'captured'
        4. Calculates and sets subscription expiry date
        5. Activates the subscription
        
        **Authentication required**: Vendor JWT token
        """,
        request_body=VerifySubscriptionPaymentSerializer,
        responses={
            200: openapi.Response(
                description="Payment verified and subscription activated",
                examples={
                    "application/json": {
                        "status": "success",
                        "code": 200,
                        "message": "Payment successful and subscription activated",
                        "data": {
                            "id": 1,
                            "vendor_name": "John's Dairy",
                            "plan_name": "Monthly Plan",
                            "payment_status": "Completed",
                            "subscription_status": "ACTIVE",
                            "plan_purchase_date": "2025-10-30",
                            "plan_expiry_date": "2025-11-30",
                            "is_active": True,
                            "days_remaining": 31
                        }
                    }
                }
            ),
            400: "Payment verification failed or invalid data",
            404: "Subscription order not found"
        },
        tags=['Subscription Management']
    )
    def post(self, request):
        logger.info("Entering VerifySubscriptionPaymentView with data: %s", request.data)
        
        try:
            # Validate request data
            serializer = VerifySubscriptionPaymentSerializer(data=request.data)
            if not serializer.is_valid():
                logger.warning("Invalid verification data: %s", serializer.errors)
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid data",
                    "errors": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            order_id = serializer.validated_data['razorpay_order_id']
            payment_id = serializer.validated_data['razorpay_payment_id']
            signature = serializer.validated_data['razorpay_signature']
            
            # Get SubscribedVendor record
            try:
                subscribed_vendor = SubscribedVendor.objects.get(razorpay_order_id=order_id)
            except SubscribedVendor.DoesNotExist:
                logger.error(f"SubscribedVendor not found for order: {order_id}")
                return Response({
                    "status": "error",
                    "code": status.HTTP_404_NOT_FOUND,
                    "message": "Subscription order not found"
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get corresponding Payment record
            try:
                payment = Payment.objects.get(razorpay_order_id=order_id)
            except Payment.DoesNotExist:
                logger.warning(f"Payment record not found for order: {order_id}")
                payment = None
            
            # Verify Razorpay signature
            params_dict = {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
            
            try:
                # Verify payment signature
                razorpay_client.utility.verify_payment_signature(params_dict)
                logger.info(f"Payment signature verified for subscription order: {order_id}")
                
                # Calculate subscription dates
                plan_purchase_date = timezone.now().date()
                plan_start_date = plan_purchase_date
                
                # Get subscription duration
                subscription_plan = subscribed_vendor.plan
                duration = subscription_plan.duration  # This is from PLAN_CHOICES: 30, 180, or 365
                
                # Calculate expiry date
                if duration:
                    try:
                        duration_days = int(duration)
                        plan_expiry_date = plan_start_date + timezone.timedelta(days=duration_days)
                    except (ValueError, TypeError):
                        # If duration is not a number, treat as lifetime
                        plan_expiry_date = None
                else:
                    # No duration means lifetime
                    plan_expiry_date = None
                
                # Update SubscribedVendor record in transaction
                with transaction.atomic():
                    subscribed_vendor.razorpay_payment_id = payment_id
                    subscribed_vendor.razorpay_signature = signature
                    subscribed_vendor.payment_status = 'Completed'
                    subscribed_vendor.subscription_status = 'ACTIVE'
                    subscribed_vendor.plan_purchase_date = plan_purchase_date
                    subscribed_vendor.plan_start_date = plan_start_date
                    subscribed_vendor.plan_expiry_date = plan_expiry_date
                    subscribed_vendor.save()
                    
                    # Update Payment record if exists
                    if payment:
                        payment.razorpay_payment_id = payment_id
                        payment.razorpay_signature = signature
                        payment.status = 'captured'
                        payment.payment_completed_at = timezone.now()
                        payment.save()
                
                logger.info(f"Subscription activated for vendor {subscribed_vendor.vendor.id}, expires: {plan_expiry_date}")
                
                # Serialize and return subscription data
                subscription_serializer = SubscribedVendorSerializer(subscribed_vendor)
                
                return Response({
                    "status": "success",
                    "code": status.HTTP_200_OK,
                    "message": "Payment successful and subscription activated",
                    "data": subscription_serializer.data
                }, status=status.HTTP_200_OK)
                
            except razorpay.errors.SignatureVerificationError:
                logger.error(f"Signature verification failed for subscription order: {order_id}")
                
                # Update payment status to failed
                with transaction.atomic():
                    subscribed_vendor.payment_status = 'Failed'
                    subscribed_vendor.subscription_status = 'CANCELLED'
                    subscribed_vendor.save()
                    
                    if payment:
                        payment.status = 'failed'
                        payment.save()
                
                return Response({
                    "status": "error",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Payment verification failed",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            logger.error(f"Error verifying subscription payment: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while verifying payment: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VendorSubscriptionHistoryView(APIView):
    """
    Get subscription history for the authenticated vendor.
    """
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Vendor Subscription History",
        operation_description="""
        Retrieve all subscription purchases for the authenticated vendor.
        
        **Authentication required**: Vendor JWT token
        """,
        responses={
            200: SubscribedVendorSerializer(many=True)
        },
        tags=['Subscription Management']
    )
    def get(self, request):
        logger.info("Entering VendorSubscriptionHistoryView")
        
        try:
            user = request.user
            user_type = getattr(user, 'user_type', None)
            
            if user_type != 'vendor':
                if not isinstance(user, VendorBusinessRegistration):
                    return Response({
                        "status": "error",
                        "code": status.HTTP_403_FORBIDDEN,
                        "message": "Only vendors can view subscription history"
                    }, status=status.HTTP_403_FORBIDDEN)
            
            # Get vendor subscriptions
            subscriptions = SubscribedVendor.objects.filter(vendor_id=user.id).order_by('-created_at')
            
            serializer = SubscribedVendorSerializer(subscriptions, many=True)
            
            logger.info(f"Retrieved {len(serializer.data)} subscription records for vendor {user.id}")
            
            return Response({
                "status": "success",
                "code": status.HTTP_200_OK,
                "message": "Subscription history retrieved successfully",
                "data": {
                    "total_count": subscriptions.count(),
                    "subscriptions": serializer.data
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving vendor subscription history: {str(e)}", exc_info=True)
            return Response({
                "status": "error",
                "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred while retrieving subscription history: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
