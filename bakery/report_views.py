# bakery/report_views.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, datetime

from django.db.models import (
    Sum,
    F,
    DecimalField,
    ExpressionWrapper,
    Value,
    Count,
)
from django.db.models.functions import TruncDate, Coalesce, TruncDay, TruncWeek, TruncMonth
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Sale, SaleItem, StockLedger, CogsEntry, PayrollEntry, PayrollPeriod


# ---------- helpers ----------

def money(value) -> str:
    if value is None:
        value = Decimal("0")
    return str(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def _dt_range(period: str):
    """
    Return (start_date, end_date, truncate_fn) based on ?range= parameter.
    period in {"7d","30d","90d","mtd","ytd"}; default "30d".
    """
    today = timezone.localdate()
    if period == "7d":
        start = today - timedelta(days=6)
        trunc = TruncDay
    elif period == "90d":
        start = today - timedelta(days=89)
        trunc = TruncDay
    elif period == "ytd":
        start = today.replace(month=1, day=1)
        trunc = TruncMonth
    elif period == "mtd":
        start = today.replace(day=1)
        trunc = TruncDay
    else:  # "30d"
        start = today - timedelta(days=29)
        trunc = TruncDay
    return start, today, trunc


# ---------- NEW: dashboard endpoints used by frontend ----------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_sales_trend(request):
    """Daily sales totals for last 30 days (or ?range=7d/30d/90d/mtd/ytd with auto granularity)."""
    period = request.query_params.get("range", "30d")
    start, end, trunc = _dt_range(period)

    qs = (
        Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=end)
        .annotate(bucket=trunc("billed_at"))
        .values("bucket")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("bucket")
    )

    data = [{"date": row["bucket"].date().isoformat(), "amount": float(row["total"] or 0)} for row in qs]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_products(request):
    """Top products by revenue for last 30 days."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    # revenue per line = qty * unit_price * (1 + tax_pct/100)
    line_revenue = ExpressionWrapper(
        F("qty") * F("unit_price") * (Value(Decimal("1.00")) + F("tax_pct") / Value(Decimal("100.00"))),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    qs = (
        SaleItem.objects.filter(sale__billed_at__date__gte=start, sale__billed_at__date__lte=today)
        .values("product_id", "product__name")
        .annotate(revenue=Coalesce(Sum(line_revenue), Decimal("0.00")))
        .order_by("-revenue")[:5]
    )

    data = [{"name": r["product__name"] or "Unknown", "value": float(r["revenue"] or 0)} for r in qs]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_outlets(request):
    """Top outlets by revenue for last 30 days."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    qs = (
        Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=today)
        .values("outlet__name")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("-total")[:5]
    )

    data = [{"name": r["outlet__name"] or "Unknown", "value": float(r["total"] or 0)} for r in qs]
    return Response(data)


# ---------- EXISTING: owner / exec summaries & financials ----------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_summary(request):
    today = timezone.localdate()
    window_start = today - timedelta(days=29)

    sales_all_time = Sale.objects.aggregate(total=Sum("total"))["total"] or Decimal("0")

    sales_30d_qs = Sale.objects.filter(billed_at__date__gte=window_start, billed_at__date__lte=today)
    sales_30d_total = sales_30d_qs.aggregate(total=Sum("total"))["total"] or Decimal("0")
    orders_30d = sales_30d_qs.count()
    avg_ticket_30d = sales_30d_total / orders_30d if orders_30d else Decimal("0")

    sales_today_total = (
        Sale.objects.filter(billed_at__date=today).aggregate(total=Sum("total"))["total"] or Decimal("0")
    )

    sales_by_day_qs = (
        sales_30d_qs.annotate(day=TruncDate("billed_at"))
        .values("day")
        .annotate(total=Sum("total"))
        .order_by("day")
    )
    sales_by_day = [{"date": str(row["day"]), "total": money(row["total"])} for row in sales_by_day_qs]

    line_revenue = ExpressionWrapper(
        F("qty") * F("unit_price") * (Value(Decimal("1.00")) + F("tax_pct") / Value(Decimal("100.00"))),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    top_products_qs = (
        SaleItem.objects.filter(sale__billed_at__date__gte=window_start, sale__billed_at__date__lte=today)
        .values("product_id", "product__name")
        .annotate(qty=Sum("qty"), revenue=Sum(line_revenue))
        .order_by("-revenue")[:5]
    )
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cogs_report(request):
    params = request.query_params
    date_from = _parse_date(params.get("from"))
    date_to = _parse_date(params.get("to"))
    outlet_id = params.get("outlet_id")

    qs = CogsEntry.objects.select_related("sale_item", "sale_item__sale", "product", "outlet")
    if date_from:
        qs = qs.filter(sale_item__sale__billed_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(sale_item__sale__billed_at__date__lte=date_to)
    if outlet_id:
        qs = qs.filter(outlet_id=outlet_id)

    results = []
    for entry in qs.order_by("-computed_at"):
        sale = entry.sale_item.sale
        results.append(
            {
                "sale_id": sale.id,
                "sale_item_id": entry.sale_item_id,
                "product_id": entry.product_id,
                "product_name": entry.product.name,
                "outlet_id": entry.outlet_id,
                "outlet_name": entry.outlet.name if entry.outlet else "",
                "qty": float(entry.qty),
                "unit_cost": str(entry.unit_cost),
                "total_cost": str(entry.total_cost),
                "method": entry.method,
                "billed_at": sale.billed_at.isoformat(),
            }
        )

    return Response({"results": results})


def payroll_gross_cost(period_id: int):
    agg = PayrollEntry.objects.filter(period_id=period_id).aggregate(total=Sum("gross_pay"))
    return agg.get("total") or Decimal("0")


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def gross_costs_summary(request):
    period_id = request.query_params.get("period_id")
    payroll_total = Decimal("0")
    cogs_total = Decimal("0")

    period = None
    if period_id:
        try:
            period = PayrollPeriod.objects.get(pk=period_id)
        except PayrollPeriod.DoesNotExist:
            period = None
        payroll_total = payroll_gross_cost(period_id)

    qs = CogsEntry.objects.all()
    if period:
        qs = qs.filter(
            sale_item__sale__billed_at__date__gte=period.start_date,
            sale_item__sale__billed_at__date__lte=period.end_date,
        )
    cogs_agg = qs.aggregate(total=Sum("total_cost"))
    cogs_total = cogs_agg.get("total") or Decimal("0")

    return Response(
        {
            "payroll": str(payroll_total.quantize(Decimal("0.01"))),
            "cogs": str(cogs_total.quantize(Decimal("0.01"))),
            "total": str((payroll_total + cogs_total).quantize(Decimal("0.01"))),
        }
    )


@extend_schema(
    parameters=[
        OpenApiParameter(name="range", description="7d|30d|90d|mtd|ytd", required=False, type=str),
        OpenApiParameter(
            name="granularity", description="day|week|month (default auto from range)", required=False, type=str
        ),
        OpenApiParameter(name="limit", description="Top N for products/outlets (default 10)", required=False, type=int),
    ],
    responses={200: dict},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exec_summary(request):
    """
    Executive dashboard rollup:
      - timeseries of sales
      - top products / top outlets
      - revenue vs cogs (best-effort)
    """
    period = request.query_params.get("range", "30d")
    start, end, trunc_default = _dt_range(period)

    # choose truncate by granularity param
    gran = request.query_params.get("granularity")
    if gran == "week":
        trunc = TruncWeek
    elif gran == "month":
        trunc = TruncMonth
    else:
        trunc = trunc_default

    qs_sales = Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=end)

    # KPIs
    total_revenue = qs_sales.aggregate(v=Coalesce(Sum("total"), Decimal("0.00")))["v"] or Decimal("0.00")
    orders = qs_sales.aggregate(v=Coalesce(Count("id"), 0))["v"] or 0
    avg_ticket = (total_revenue / orders) if orders else Decimal("0.00")

    # Series
    timeseries_qs = (
        qs_sales.annotate(bucket=trunc("billed_at"))
        .values("bucket")
        .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("bucket")
    )
    series = [{"date": row["bucket"].date().isoformat(), "total": float(row["total"])} for row in timeseries_qs]

    # Top outlets
    top_outlets_qs = (
        qs_sales.values("outlet__name")
        .annotate(sales=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("-sales")[:10]
    )
    top_outlets = [{"name": r["outlet__name"] or "Unknown", "sales": float(r["sales"])} for r in top_outlets_qs]

    # Top products (revenue = qty*price*(1+tax))
    line_revenue = ExpressionWrapper(
        F("qty") * F("unit_price") * (Value(Decimal("1.00")) + F("tax_pct") / Value(Decimal("100.00"))),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    top_products_qs = (
        SaleItem.objects.filter(sale__in=qs_sales)
        .values("product__name")
        .annotate(sales=Coalesce(Sum(line_revenue), Decimal("0.00")))
        .order_by("-sales")[:10]
    )
    top_products = [{"name": r["product__name"] or "Unknown", "sales": float(r["sales"])} for r in top_products_qs]

    # Very rough COGS estimate (optional)
    cogs_estimate = None
    try:
        items = SaleItem.objects.filter(sale__in=qs_sales).select_related("product")
        total_cost = Decimal("0.00")
        for it in items:
            if hasattr(it.product, "approx_cost") and it.product.approx_cost is not None:
                unit_cost = Decimal(str(it.product.approx_cost))
            else:
                unit_cost = Decimal(str(it.unit_price)) * Decimal("0.60")  # heuristic
            total_cost += unit_cost * Decimal(str(it.qty))
        cogs_estimate = float(total_cost.quantize(Decimal("0.01")))
    except Exception:
        pass

    return Response(
        {
            "period": f"{start} → {end}",
            "kpis": {
                "revenue": float(total_revenue),
                "orders": int(orders),
                "avg_ticket": float(avg_ticket.quantize(Decimal('0.01'))),
            },
            "series": series,
            "top_outlets": top_outlets,
            "top_products": top_products,
            "revenue_vs_cogs": {
                "revenue": float(total_revenue),
                "cogs": cogs_estimate,
                "gross_margin": float(total_revenue) - (cogs_estimate or 0.0),
            },
        }
    )