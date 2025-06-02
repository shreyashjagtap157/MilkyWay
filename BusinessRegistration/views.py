from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import VendorBusinessRegistration
from .serializers import VendorBusinessRegistrationSerializer


# Create your views here.
# ---------------- Vendor Business Registration ViewSet ----------------
class VendorBusinessRegistrationViewSet(viewsets.ModelViewSet):
    queryset = VendorBusinessRegistration.objects.all()
    serializer_class = VendorBusinessRegistrationSerializer

    def list(self, request):
        serializer = self.serializer_class(self.get_queryset(), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        vendor = self.get_object()
        serializer = self.serializer_class(vendor)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        vendor = self.get_object()
        serializer = self.serializer_class(vendor, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk=None):
        vendor = self.get_object()
        serializer = self.serializer_class(vendor, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        vendor = self.get_object()
        vendor.delete()
        return Response(
            {"message": "Vendor Business Registration deleted"},
            status=status.HTTP_204_NO_CONTENT,
        )
