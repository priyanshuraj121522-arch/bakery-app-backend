import random
from datetime import timedelta, datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from bakery.models import Outlet, Product, Sale, SaleItem

# Try to import CogsEntry if exists
try:
    from bakery.models import CogsEntry  # type: ignore
    HAS_COGS = True
except Exception:
    HAS_COGS = False


PRODUCTS = [
    ("BREAD-001", "Sourdough Bread", Decimal("120.00"), Decimal("5")),
    ("PASTRY-002", "Chocolate Croissant", Decimal("80.00"), Decimal("5")),
    ("CAKE-003", "Red Velvet Slice", Decimal("150.00"), Decimal("12")),
    ("COOKIE-004", "Oatmeal Cookie", Decimal("45.00"), Decimal("5")),
    ("MUFFIN-005", "Blueberry Muffin", Decimal("65.00"), Decimal("5")),
]

PAYMENT_MODES = ["CASH", "UPI", "CARD"]

DEFAULT_OUTLETS = [
    "Downtown Bakery",
    "Uptown Bakery",
    "Riverside Bakery",
]


class Command(BaseCommand):
    help = (
        "Seed dummy outlets, products, and sales data for dashboards/exports.\n"
        "Default: 30 days, 1 outlet. Use flags for richer data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="How many days to seed (default 30).")
        parser.add_argument("--avg-orders", type=int, default=5, help="Approx avg orders per day (default 5).")
        parser.add_argument(
            "--outlets",
            type=int,
            default=1,
            help="How many outlets to create (default 1).",
        )
        parser.add_argument("--start", type=str, default="", help="Optional start date (YYYY-MM-DD).")
        parser.add_argument("--flush", action="store_true", help="Delete existing seeded sales first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        days: int = max(1, opts["days"])
        avg_orders: int = max(1, opts["avg_orders"])
        outlets_count: int = max(1, opts["outlets"])
        start_iso: str = opts["start"]
        flush: bool = opts["flush"]

        rng = random.Random(42)
        today = timezone.localdate()
        start_date = (
            datetime.fromisoformat(start_iso).date()
            if start_iso
            else (today - timedelta(days=days - 1))
        )
        end_date = today

        self.stdout.write(
            self.style.NOTICE(
                f"📊 Seeding {days} days ({start_date} → {end_date}) with ~{avg_orders} orders/day × {outlets_count} outlet(s)"
            )
        )

        # ----- Outlets -----
        outlet_names = DEFAULT_OUTLETS[:outlets_count]
        outlets = []
        for name in outlet_names:
            outlet, _ = Outlet.objects.get_or_create(
                name=name,
                defaults={"type": Outlet.OUTLET, "address": f"{rng.randint(10,999)} Baker Street"},
            )
            outlets.append(outlet)

        # ----- Products -----
        products = []
        for sku, name, mrp, tax_pct in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                sku=sku,
                defaults={"name": name, "mrp": mrp, "tax_pct": tax_pct},
            )
            products.append(product)

        # ----- Optional flush -----
        if flush:
            self.stdout.write("🧹 Flushing existing dummy data in recent range…")
            SaleItem.objects.filter(sale__billed_at__gte=start_date).delete()
            Sale.objects.filter(billed_at__gte=start_date).delete()

        total_sales = 0
        total_revenue = Decimal("0.00")

        for day in range(days):
            day_date = start_date + timedelta(days=day)
            for outlet in outlets:
                sale_count = rng.randint(max(2, avg_orders - 2), avg_orders + 3)
                for _ in range(sale_count):
                    billed_at = timezone.make_aware(
                        datetime.combine(day_date, datetime.min.time())
                    ) + timedelta(hours=rng.randint(8, 19), minutes=rng.randint(0, 59))

                    sale = Sale.objects.create(
                        outlet=outlet,
                        billed_at=billed_at,
                        subtotal=Decimal("0"),
                        tax=Decimal("0"),
                        discount=Decimal("0"),
                        total=Decimal("0"),
                        payment_mode=rng.choice(PAYMENT_MODES),
                    )

                    subtotal = Decimal("0")
                    tax_total = Decimal("0")
                    item_count = rng.randint(1, 4)
                    for _ in range(item_count):
                        product = rng.choice(products)
                        qty = Decimal(rng.randint(1, 3))
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

                    total_revenue += sale.total
                    total_sales += 1

                    # Optional COGS
                    if HAS_COGS:
                        try:
                            CogsEntry.objects.create(
                                sale=sale,
                                outlet=outlet,
                                cost=(sale.total * Decimal("0.6")).quantize(Decimal("0.01")),
                            )
                        except Exception:
                            pass

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Seeded {total_sales} sales ({len(outlets)} outlets) totalling ₹{total_revenue}."
            )
        )