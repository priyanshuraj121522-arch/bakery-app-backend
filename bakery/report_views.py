from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Sale, SaleItem, StockLedger


def money(value) -> str:
    if value is None:
        value = Decimal("0")
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@api_view(["GET"])
def owner_summary(request):
    today = timezone.localdate()
    window_start = today - timedelta(days=29)

    sales_all_time = Sale.objects.aggregate(total=Sum("total"))["total"] or Decimal("0")

    sales_30d_qs = Sale.objects.filter(
        billed_at__date__gte=window_start,
        billed_at__date__lte=today,
    )
    sales_30d_total = sales_30d_qs.aggregate(total=Sum("total"))["total"] or Decimal("0")
    orders_30d = sales_30d_qs.count()
    avg_ticket_30d = sales_30d_total / orders_30d if orders_30d else Decimal("0")

    sales_today_total = Sale.objects.filter(billed_at__date=today).aggregate(total=Sum("total"))["total"] or Decimal("0")

    sales_by_day_qs = (
        sales_30d_qs
        .annotate(day=TruncDate("billed_at"))
        .values("day")
        .annotate(total=Sum("total"))
        .order_by("day")
    )
    sales_by_day = [
        {"date": str(row["day"]), "total": money(row["total"])}
        for row in sales_by_day_qs
    ]

    revenue_expr = ExpressionWrapper(
        F("qty") * F("unit_price") * (
            Value(Decimal("1.00")) + F("tax_pct") / Value(Decimal("100.00"))
        ),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    top_products_qs = (
        SaleItem.objects.filter(
            sale__billed_at__date__gte=window_start,
            sale__billed_at__date__lte=today,
        )
        .values("product_id", "product__name")
        .annotate(
            qty=Sum("qty"),
            revenue=Sum(revenue_expr),
        )
        .order_by("-revenue")
    )[:5]

    top_products = [
        {
            "product_id": row["product_id"],
            "name": row["product__name"],
            "qty": float(row["qty"] or 0),
            "revenue": money(row["revenue"]),
        }
        for row in top_products_qs
    ]

    low_stock_qs = (
        StockLedger.objects.filter(batch__isnull=False)
        .values("batch_id", "batch__product__name")
        .annotate(qty_on_hand=Sum(F("qty_in") - F("qty_out")))
        .filter(qty_on_hand__lte=5)
        .order_by("qty_on_hand", "batch_id")
    )[:5]

    low_stock = [
        {
            "batch_id": row["batch_id"],
            "product": row["batch__product__name"],
            "batch_code": f"B{row['batch_id']:05d}",
            "qty": float(row["qty_on_hand"] or 0),
        }
        for row in low_stock_qs
    ]

    data = {
        "totals": {
            "sales_all_time": money(sales_all_time),
            "sales_30d": money(sales_30d_total),
            "orders_30d": orders_30d,
            "avg_ticket_30d": money(avg_ticket_30d),
            "sales_today": money(sales_today_total),
        },
        "sales_by_day_30d": sales_by_day,
        "top_products_30d": top_products,
        "low_stock": low_stock,
    }

    return Response(data)
