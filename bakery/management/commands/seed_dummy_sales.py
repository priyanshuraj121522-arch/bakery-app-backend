import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from bakery.models import Outlet, Product, Sale, SaleItem

PRODUCTS = [
    ("BREAD-001", "Sourdough Bread", Decimal("120.00"), Decimal("5")),
    ("PASTRY-002", "Chocolate Croissant", Decimal("80.00"), Decimal("5")),
    ("CAKE-003", "Red Velvet Slice", Decimal("150.00"), Decimal("12")),
    ("COOKIE-004", "Oatmeal Cookie", Decimal("45.00"), Decimal("5")),
    ("MUFFIN-005", "Blueberry Muffin", Decimal("65.00"), Decimal("5")),
]

PAYMENT_MODES = ["CASH", "UPI", "CARD"]


class Command(BaseCommand):
    help = "Seed dummy outlets, products, and sales data for dashboards/exports."

    def handle(self, *args, **options):
        with transaction.atomic():
            outlet, _ = Outlet.objects.get_or_create(
                name="Downtown Bakery",
                defaults={"type": Outlet.OUTLET, "address": "123 Cake Lane"},
            )

            products = []
            for sku, name, mrp, tax_pct in PRODUCTS:
                product, _ = Product.objects.get_or_create(
                    sku=sku,
                    defaults={"name": name, "mrp": mrp, "tax_pct": tax_pct},
                )
                products.append(product)

            now = timezone.now()
            start = now - timedelta(days=30)

            # Clear existing seeded sales for deterministic results
            SaleItem.objects.filter(sale__billed_at__gte=start).delete()
            Sale.objects.filter(billed_at__gte=start).delete()

            total_sales = 0
            for day in range(30):
                day_start = (start + timedelta(days=day)).replace(hour=9, minute=0, second=0, microsecond=0)
                sale_count = random.randint(2, 6)
                for _ in range(sale_count):
                    billed_at = day_start + timedelta(minutes=random.randint(0, 9 * 60))
                    sale = Sale.objects.create(
                        outlet=outlet,
                        billed_at=billed_at,
                        subtotal=Decimal("0"),
                        tax=Decimal("0"),
                        discount=Decimal("0"),
                        total=Decimal("0"),
                        payment_mode=random.choice(PAYMENT_MODES),
                    )

                    item_count = random.randint(1, 3)
                    subtotal = Decimal("0")
                    tax_total = Decimal("0")
                    for _ in range(item_count):
                        product = random.choice(products)
                        qty = Decimal(random.randint(1, 4))
                        unit_price = product.mrp
                        line_subtotal = qty * unit_price
                        line_tax = line_subtotal * (product.tax_pct / Decimal("100"))

                        SaleItem.objects.create(
                            sale=sale,
                            product=product,
                            qty=float(qty),
                            unit_price=unit_price,
                            tax_pct=product.tax_pct,
                        )

                        subtotal += line_subtotal
                        tax_total += line_tax

                    sale.subtotal = subtotal.quantize(Decimal("0.01"))
                    sale.tax = tax_total.quantize(Decimal("0.01"))
                    sale.discount = Decimal("0")
                    sale.total = (sale.subtotal + sale.tax - sale.discount).quantize(Decimal("0.01"))
                    sale.save(update_fields=["subtotal", "tax", "discount", "total"])
                    total_sales += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Seeded {total_sales} dummy sales across 30 days."))
