from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class AuthenticationInfoView(APIView):
    """
    Provides information about available authentication methods
    """
    permission_classes = []  # Allow unauthenticated access
    
    @swagger_auto_schema(
        operation_summary="Authentication Information",
        operation_description="""
        Get information about available authentication methods in the API.
        
        ## Available Authentication Methods:
        
        ### 1. Admin Authentication
        - **Endpoint**: `/systemadmin/adminlogin/`
        - **Method**: POST
        - **Body**: `{"username": "admin_username", "password": "admin_password"}`
        - **Returns**: JWT tokens for system administrators
        - **Model**: SystemAdmin
        
        ### 2. Role-based Authentication
        - **Endpoint**: `/vendor-login/vendor_login/`
        - **Method**: POST  
        - **Body**: `{"contact": "phone_number", "password": "user_password"}`
        - **Returns**: JWT tokens for vendors, milkman, and customers
        - **Models**: VendorBusinessRegistration, Milkman, Customer
        
        ## Using JWT Tokens
        Once you receive a token from either endpoint, include it in subsequent requests:
        ```
        Authorization: Bearer <your_jwt_token>
        ```
        
        ## Token Refresh
        Use the refresh token at `/vendor-login/refresh/` to get new access tokens.
        """,
        responses={
            200: openapi.Response(
                description="Authentication information",
                examples={
                    "application/json": {
                        "message": "Authentication information retrieved successfully",
                        "authentication_methods": {
                            "admin_login": {
                                "endpoint": "/systemadmin/adminlogin/",
                                "method": "POST",
                                "description": "Login for system administrators",
                                "model": "SystemAdmin"
                            },
                            "role_based_login": {
                                "endpoint": "/vendor-login/vendor_login/", 
                                "method": "POST",
                                "description": "Login for vendors, milkman, and customers",
                                "models": ["VendorBusinessRegistration", "Milkman", "Customer"]
                            }
                        }
                    }
                }
            )
        },
        tags=['Authentication Info']
    )
    def get(self, request):
        auth_info = {
            "message": "Authentication information retrieved successfully",
            "authentication_methods": {
                "admin_login": {
                    "endpoint": "/systemadmin/adminlogin/",
                    "method": "POST",
                    "description": "Login for system administrators using username and password",
                    "model": "SystemAdmin",
                    "sample_request": {
                        "username": "admin_username",
                        "password": "admin_password"
                    }
                },
                "role_based_login": {
                    "endpoint": "/vendor-login/vendor_login/",
                    "method": "POST", 
                    "description": "Login for vendors, milkman, and customers using contact and password",
                    "models": ["VendorBusinessRegistration", "Milkman", "Customer"],
                    "sample_request": {
                        "contact": "phone_number",
                        "password": "user_password"
                    }
                }
            },
            "token_usage": {
                "description": "Include JWT token in Authorization header",
                "format": "Authorization: Bearer <your_jwt_token>",
                "refresh_endpoint": "/vendor-login/refresh/"
            }
        }
        
        return Response(auth_info, status=status.HTTP_200_OK)
