from django.urls import path
from .views import invoice_pdf_view, invoice_excel_view

urlpatterns = [
    path("invoice/<int:pk>/pdf/", invoice_pdf_view, name="invoice-pdf"),
    path("invoice/<int:pk>/excel/", invoice_excel_view, name="invoice-excel"),
    # path("invoice/<int:invoice_id>/pdf/", invoice_pdf_view, name="invoice-pdf"),
]
