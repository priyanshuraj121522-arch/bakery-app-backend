# bakery/report_views.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, datetime

from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Value, Count
from django.db.models.functions import TruncDate, Coalesce, TruncDay, TruncWeek, TruncMonth
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Sale, SaleItem, StockLedger, CogsEntry, PayrollEntry, PayrollPeriod


def money(value) -> str:
    if value is None:
        value = Decimal("0")
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------
# Dashboard Data Endpoints
# ---------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_sales_trend(request):
    """Return daily sales totals for TradingView-style chart."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    qs = (
        Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=today)
        .annotate(day=TruncDate("billed_at"))
        .values("day")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("day")
    )

    data = [
        {"date": row["day"].isoformat(), "total": float(row["total"] or 0)}
        for row in qs
    ]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_products(request):
    """Return top 5 products by revenue (last 30 days)."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    revenue_expr = ExpressionWrapper(
        F("qty") * F("unit_price") * (
            Value(Decimal("1.00")) + F("tax_pct") / Value(Decimal("100.00"))
        ),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    qs = (
        SaleItem.objects.filter(
            sale__billed_at__date__gte=start,
            sale__billed_at__date__lte=today,
        )
        .values("product_id", "product__name")
        .annotate(revenue=Sum(revenue_expr))
        .order_by("-revenue")[:5]
    )

    data = [
        {"name": row["product__name"], "revenue": float(row["revenue"] or 0)}
        for row in qs
    ]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_outlets(request):
    """Return top outlets by total revenue (last 30 days)."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    qs = (
        Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=today)
        .values("outlet__name")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("-total")[:5]
    )

    data = [
        {"name": row["outlet__name"] or "Unknown", "revenue": float(row["total"] or 0)}
        for row in qs
    ]
    return Response(data)


# ---------------------------------------------
# Original owner_summary + exec_summary
# ---------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_summary(request):
    """Owner-level KPIs for revenue, orders, avg ticket, and top products."""
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


@extend_schema(
    parameters=[
        OpenApiParameter(name="range", description="7d|30d|90d|mtd|ytd", required=False, type=str),
        OpenApiParameter(name="granularity", description="day|week|month", required=False, type=str),
        OpenApiParameter(name="limit", description="Top N for products/outlets (default 10)", required=False, type=int),
    ],
    responses={200: dict},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exec_summary(request):
    """Executive dashboard: revenue trend, top products/outlets, and COGS."""
    period = request.query_params.get("range", "30d")
    try:
        start = timezone.localdate() - timedelta(days=int(period.replace("d", "")) - 1)
    except Exception:
        start = timezone.localdate() - timedelta(days=29)
    end = timezone.localdate()

    qs = Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=end)

    total_revenue = qs.aggregate(v=Coalesce(Sum("total"), Decimal("0.00")))["v"]
    orders = qs.aggregate(c=Count("id"))["c"]
    avg_ticket = (total_revenue / orders) if orders else Decimal("0")

    sales_series = (
        qs.annotate(day=TruncDate("billed_at"))
        .values("day")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("day")
    )
    series = [{"date": str(r["day"]), "total": float(r["total"])} for r in sales_series]

    top_outlets = (
        qs.values("outlet__name")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("-total")[:5]
    )
    top_outlets_data = [
        {"name": r["outlet__name"] or "Unknown", "sales": float(r["total"])} for r in top_outlets
    ]

    top_products = (
        SaleItem.objects.filter(sale__in=qs)
        .values("product__name")
        .annotate(revenue=Coalesce(Sum("qty" * F("unit_price")), Decimal("0.00")))
        .order_by("-revenue")[:5]
    )
    top_products_data = [
        {"name": r["product__name"], "sales": float(r["revenue"])} for r in top_products
    ]

    return Response({
        "period": f"{start} → {end}",
        "revenue": float(total_revenue or 0),
        "orders": orders,
        "avg_ticket": float(avg_ticket),
        "series": series,
        "top_outlets": top_outlets_data,
        "top_products": top_products_data,
    })