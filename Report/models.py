from django.db import models


class Customer(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name or "Unnamed Customer"


class Invoice(models.Model):
    invoice_number = models.CharField(
        max_length=100,
        unique=True,
        db_index=True
    )
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    date = models.DateField(
        auto_now_add=True,
        null=True,
        blank=True,
        db_index=True
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        db_index=True
    )


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name="items", on_delete=models.CASCADE)
    product_name = models.CharField(max_length=100, blank=True, null=True)
    quantity = models.PositiveIntegerField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    @property
    def total(self):
        return self.quantity * self.price

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
