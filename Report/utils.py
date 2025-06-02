from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from io import BytesIO
from django.http import FileResponse


def generate_invoice_pdf(invoice):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "MilkWay Invoice")

    # Customer Info
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 100, f"Customer: {invoice.customer.name}")
    c.drawString(50, height - 120, f"Address: {invoice.customer.address}")
    c.drawString(50, height - 140, f"Invoice No: {invoice}")
    c.drawString(50, height - 160, f"Date: {invoice.date}")

    # Table Headers
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 200, "Product")
    c.drawString(250, height - 200, "Quantity")
    c.drawString(350, height - 200, "Price")
    c.drawString(450, height - 200, "Total")

    y = height - 220
    c.setFont("Helvetica", 12)

    for item in invoice.items.all():
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
    return FileResponse(buffer, as_attachment=True, filename=f"Invoice_{invoice}.pdf")
