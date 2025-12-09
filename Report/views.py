from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from .models import Invoice
from .utils import generate_invoice_pdf
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from openpyxl import Workbook
import io
from OneWindowHomeSolution.responses import error_response, not_found_response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import logging

logger = logging.getLogger(__name__)

@swagger_auto_schema(
    method="get",
    operation_summary="Download Invoice PDF",
    operation_description="Generate and download a PDF invoice for the given invoice ID.",
    manual_parameters=[
        openapi.Parameter('pk', openapi.IN_PATH, description="Invoice ID", type=openapi.TYPE_INTEGER)
    ],
    responses={200: openapi.Response(description="PDF file for the invoice")}
)
@api_view(["GET"])
def invoice_pdf_view(request, pk):
    try:
        invoice = get_object_or_404(Invoice, pk=pk)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, "MilkyWay Invoice")

        # Customer Info
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 100, f"Customer: {invoice.customer.name}")
        c.drawString(50, height - 120, f"Address: {invoice.customer.address}")
        c.drawString(50, height - 140, f"Invoice No: {invoice.id}")
        c.drawString(50, height - 160, f"Date: {invoice.date}")

        # Table Headers
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, height - 200, "Product")
        c.drawString(250, height - 200, "Quantity")
        c.drawString(350, height - 200, "Price")
        c.drawString(450, height - 200, "Total")

        # Table Content
        y = height - 220
        c.setFont("Helvetica", 12)

        for item in invoice.items.all():  # adjust 'items' if it's a different related name
            total = item.quantity * item.price
            c.drawString(50, y, item.product_name)
            c.drawString(250, y, str(item.quantity))
            c.drawString(350, y, f"{item.price:.2f}")
            c.drawString(450, y, f"{total:.2f}")
            y -= 20

        # Total Amount
        c.setFont("Helvetica-Bold", 12)
        c.drawString(350, y - 20, "Total Amount:")
        c.drawString(450, y - 20, f"{invoice.total_amount:.2f}")

        c.showPage()
        c.save()

        buffer.seek(0)
        response = HttpResponse(
            buffer,
            content_type="application/pdf",
        )
        response['Content-Disposition'] = f'attachment; filename="invoice_{pk}.pdf"'
        return response
    except Invoice.DoesNotExist:
        return not_found_response("Invoice not found")
    except Exception as e:
        return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


@swagger_auto_schema(
    method="get",
    operation_summary="Download Invoice Excel",
    operation_description="Generate and download an Excel invoice for the given invoice ID.",
    manual_parameters=[
        openapi.Parameter('pk', openapi.IN_PATH, description="Invoice ID", type=openapi.TYPE_INTEGER)
    ],
    responses={200: openapi.Response(description="Excel file for the invoice")}
)
@api_view(["GET"])
def invoice_excel_view(request, pk):
    try:
        # Get the invoice instance
        invoice = get_object_or_404(Invoice, pk=pk)

        # Create a new Excel workbook and sheet
        wb = Workbook()
        ws = wb.active
        ws.title = f"Invoice_{pk}"

        # Invoice header
        ws.append(["MilkyWay Invoice"])
        ws.append([])
        ws.append(["Customer", invoice.customer.name])
        ws.append(["Address", invoice.customer.address])
        ws.append(["Invoice No", invoice.id])
        ws.append(
            [
                "Date",
                (
                    invoice.date
                    if isinstance(invoice.date, str)
                    else invoice.date.strftime("%Y-%m-%d")
                ),
            ]
        )

        ws.append([])

        # Table headers
        ws.append(["Product", "Quantity", "Price", "Total"])

        # Table rows
        for item in invoice.items.all():
            total = item.quantity * item.price
            ws.append(
                [item.product_name, item.quantity, float(item.price), float(total)]
            )

        # Total amount
        ws.append([])
        ws.append(["", "", "Total Amount", float(invoice.total_amount)])

        # Save the workbook to an in-memory buffer
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = f"attachment; filename=invoice_{pk}.xlsx"
        wb.save(response)
        return response
    except Invoice.DoesNotExist:
        return not_found_response("Invoice not found")
    except Exception as e:
        return error_response(f"An error occurred: {str(e)}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
