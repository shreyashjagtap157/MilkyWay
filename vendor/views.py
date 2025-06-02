from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Vendor, Society, FlatDetail, WorkerPayment
from .serializers import (
    VendorSerializer,
    SocietySerializer,
    FlatDetailSerializer,
    WorkerPaymentSerializer,
)


# Create your views here.
# ---------------- Vendor ViewSet ----------------
class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all()
    serializer_class = VendorSerializer

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
            {"message": "Vendor deleted"}, status=status.HTTP_204_NO_CONTENT
        )


# ---------------- Society ViewSet ----------------
class SocietyViewSet(viewsets.ModelViewSet):
    queryset = Society.objects.all()
    serializer_class = SocietySerializer

    def list(self, request):
        serializer = self.serializer_class(self.get_queryset(), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        society = self.get_object()
        serializer = self.serializer_class(society)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        society = self.get_object()
        serializer = self.serializer_class(society, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk=None):
        society = self.get_object()
        serializer = self.serializer_class(society, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        society = self.get_object()
        society.delete()
        return Response(
            {"message": "Society deleted"}, status=status.HTTP_204_NO_CONTENT
        )


# ---------------- FlatDetail ViewSet ----------------
class FlatDetailViewSet(viewsets.ModelViewSet):
    queryset = FlatDetail.objects.all()
    serializer_class = FlatDetailSerializer

    def list(self, request):
        serializer = self.serializer_class(self.get_queryset(), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        flat = self.get_object()
        serializer = self.serializer_class(flat)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        flat = self.get_object()
        serializer = self.serializer_class(flat, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk=None):
        flat = self.get_object()
        serializer = self.serializer_class(flat, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        flat = self.get_object()
        flat.delete()
        return Response({"message": "Flat deleted"}, status=status.HTTP_204_NO_CONTENT)


# ---------------- WorkerPayment ViewSet ----------------
class WorkerPaymentViewSet(viewsets.ModelViewSet):
    queryset = WorkerPayment.objects.all()
    serializer_class = WorkerPaymentSerializer

    def list(self, request):
        serializer = self.serializer_class(self.get_queryset(), many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        payment = self.get_object()
        serializer = self.serializer_class(payment)
        return Response(serializer.data)

    def create(self, request):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        payment = self.get_object()
        serializer = self.serializer_class(payment, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, pk=None):
        payment = self.get_object()
        serializer = self.serializer_class(payment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        payment = self.get_object()
        payment.delete()
        return Response(
            {"message": "Worker payment deleted"}, status=status.HTTP_204_NO_CONTENT
        )
