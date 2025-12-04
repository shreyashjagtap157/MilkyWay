from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken
from django.contrib.auth import get_user_model
from Systemadmin.models import Systemadmin
from BusinessRegistration.models import VendorBusinessRegistration as Vendor
from Customer.models import Customer
from Milkman.models import Milkman
import jwt
from django.conf import settings

class CustomJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        """
        Attempts to find and return a user using the given validated token.
        """
        try:
            user_id = validated_token.get('user_id')
            user_type = validated_token.get('user_type')

            if not user_id:
                raise InvalidToken('Token contained no recognizable user identification')

            if user_type == 'system_admin':
                try:
                    user = Systemadmin.objects.get(id=user_id)
                    return user
                except Systemadmin.DoesNotExist:
                    raise InvalidToken('SystemAdmin user not found')
                    
            elif user_type == 'vendor':
                try:
                    user = Vendor.objects.get(id=user_id)
                    return user
                except Vendor.DoesNotExist:
                    raise InvalidToken('Vendor user not found')
                    
            elif user_type == 'customer':
                try:
                    user = Customer.objects.get(id=user_id)
                    return user
                except Customer.DoesNotExist:
                    raise InvalidToken('Customer user not found')
                    
            elif user_type == 'milkman':
                try:
                    user = Milkman.objects.get(id=user_id)
                    return user
                except Milkman.DoesNotExist:
                    raise InvalidToken('Milkman user not found')
            else:
                # Fallback to SystemAdmin if no user_type specified (backward compatibility)
                try:
                    user = Systemadmin.objects.get(id=user_id)
                    return user
                except Systemadmin.DoesNotExist:
                    raise InvalidToken('User type not specified or invalid in token.')
            
        except KeyError:
            raise InvalidToken('Token contained no recognizable user identification')
        except Exception as e:
            raise InvalidToken(f'Authentication failed: {str(e)}')
