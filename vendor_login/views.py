from django.contrib.auth import authenticate
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework import status
from .serializers import VendorLoginSerializer, MilkmanLoginSerializer


class VendorLoginView(APIView):
    def post(self, request):
        serializer = VendorLoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data["username"]
            password = serializer.validated_data["password"]
            user = authenticate(username=username, password=password)

            if user:
                token, _ = Token.objects.get_or_create(user=user)
                return Response(
                    {
                        "status": "success",
                        "code": status.HTTP_200_OK,
                        "message": "Login successful",
                        "token": token.key,
                        "userID": user.pk,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": "failed",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid credentials",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MilkmanLoginView(APIView):
    def post(self, request):
        serializer = MilkmanLoginSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data["username"]
            password = serializer.validated_data["password"]
            user = authenticate(username=username, password=password)

            if user:
                token, _ = Token.objects.get_or_create(user=user)
                return Response(
                    {
                        "status": "success",
                        "code": status.HTTP_200_OK,
                        "message": "Login successful",
                        "token": token.key,
                        "userID": user.pk,
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {
                    "status": "failed",
                    "code": status.HTTP_400_BAD_REQUEST,
                    "message": "Invalid credentials",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# from rest_framework.decorators import api_view
# from rest_framework.response import Response
# from rest_framework.authtoken.models import Token
# from rest_framework import status
# from django.contrib.auth import authenticate
# from drf_yasg.utils import swagger_auto_schema
# from .serializers import LoginSerializer


# @swagger_auto_schema(method="post", request_body=LoginSerializer)
# @api_view(["POST"])
# def login_view(request):
#     serializer = LoginSerializer(data=request.data)
#     if serializer.is_valid():
#         username = serializer.validated_data["username"]
#         password = serializer.validated_data["password"]
#         user = authenticate(username=username, password=password)
#         if user:
#             token, _ = Token.objects.get_or_create(user=user)
#             return Response(
#                 {
#                     "status": "success",
#                     "code": status.HTTP_200_OK,
#                     "message": "Login successful",
#                     "token": token.key,
#                     "userID": user.pk,
#                 },
#                 status=status.HTTP_200_OK,
#             )
#         return Response(
#             {
#                 "status": "failed",
#                 "code": status.HTTP_400_BAD_REQUEST,
#                 "message": "Invalid credentials",
#             },
#             status=status.HTTP_400_BAD_REQUEST,
#         )
#     return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
