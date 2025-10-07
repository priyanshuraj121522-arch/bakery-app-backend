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
from django.db.models.functions import TruncDate, Coalesce, TruncDay, TruncWeek, TruncMonth, Cast
from django.utils import timezone
# --- CACHE + RATE LIMIT START ---
from django.views.decorators.cache import cache_page
# --- CACHE + RATE LIMIT END ---
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Sale, SaleItem, StockLedger, CogsEntry, PayrollEntry, PayrollPeriod


# =========================
# Helpers
# =========================

def money(value) -> str:
    """Safely round money to 2 decimals as string (for endpoints that want strings)."""
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


# Common revenue expression: CAST(qty) * CAST(unit_price) * (1 + tax_pct/100)
def _line_revenue_expr():
    return ExpressionWrapper(
        Cast(F("qty"), DecimalField(max_digits=18, decimal_places=6))
        * Cast(F("unit_price"), DecimalField(max_digits=18, decimal_places=6))
        * (Value(Decimal("1")) + Cast(F("tax_pct"), DecimalField(max_digits=6, decimal_places=4)) / Value(Decimal("100"))),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


# =========================
# NEW: Dashboard endpoints used by frontend tiles/lists
# =========================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_sales_trend(request):
    """Daily sales totals (or auto granularity by range). Returns [{date, amount:number}]."""
    period = request.query_params.get("range", "30d")
    start, end, trunc = _dt_range(period)

    # --- PERF UPGRADE START ---
    sale_qs = Sale.objects.only("id", "billed_at", "total").filter(
        billed_at__date__gte=start, billed_at__date__lte=end
    )
    # --- PERF UPGRADE END ---
    qs = (
        sale_qs
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
    """Top products by revenue for the last 30 days. Returns [{name, value:number}]."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    line_revenue = _line_revenue_expr()

    qs = (
        SaleItem.objects.filter(sale__billed_at__date__gte=start, sale__billed_at__date__lte=today)
        .values("product_id", "product__name")
        .annotate(revenue=Coalesce(Sum(line_revenue), Decimal("0")))
        .order_by("-revenue")[:5]
    )
    data = [{"name": r["product__name"] or "Unknown", "value": float(r["revenue"] or 0)} for r in qs]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_outlets(request):
    """Top outlets by revenue for the last 30 days. Returns [{name, value:number}]."""
    today = timezone.localdate()
    start = today - timedelta(days=29)

    # --- PERF UPGRADE START ---
    sales_base = (
        Sale.objects.only("id", "billed_at", "total", "outlet_id")
        .select_related("outlet")
        .filter(billed_at__date__gte=start, billed_at__date__lte=today)
    )
    # --- PERF UPGRADE END ---
    qs = (
        sales_base
        .values("outlet__name")
        .annotate(total=Coalesce(Sum("total"), Decimal("0")))
        .order_by("-total")[:5]
    )
    data = [{"name": r["outlet__name"] or "Unknown", "value": float(r["total"] or 0)} for r in qs]
    return Response(data)


# =========================
# EXISTING: owner / exec & financial reports
# (kept intact to avoid breaking any existing screens)
# =========================

# --- CACHE + RATE LIMIT START ---
@cache_page(60)
# --- CACHE + RATE LIMIT END ---
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_summary(request):
    """
    Owner-style rollup used by older tiles: returns strings for currency fields
    (backward-compatible with any UI that expects strings).
    Implementation note: keep DB simple; do revenue math in Python to avoid
    aggregate/ExpressionWrapper edge-cases on some DBs.
    """
    today = timezone.localdate()
    window_start = today - timedelta(days=29)

    # KPI totals
    # --- PERF UPGRADE START ---
    sales_all_time = Sale.objects.only("total").aggregate(total=Sum("total"))["total"] or Decimal("0")
    # --- PERF UPGRADE END ---

    # --- PERF UPGRADE START ---
    sales_30d_qs = (
        Sale.objects.only("id", "billed_at", "total", "outlet_id")
        .filter(billed_at__date__gte=window_start, billed_at__date__lte=today)
    )
    # --- PERF UPGRADE END ---
    sales_30d_total = sales_30d_qs.aggregate(total=Sum("total"))["total"] or Decimal("0")
    orders_30d = sales_30d_qs.count()
    avg_ticket_30d = sales_30d_total / orders_30d if orders_30d else Decimal("0")

    # --- PERF UPGRADE START ---
    sales_today_total = (
        Sale.objects.only("total")
        .filter(billed_at__date=today)
        .aggregate(total=Sum("total"))["total"]
        or Decimal("0")
    )
    # --- PERF UPGRADE END ---

    sales_by_day_qs = (
        sales_30d_qs.annotate(day=TruncDate("billed_at"))
        .values("day")
        .annotate(total=Sum("total"))
        .order_by("day")
    )
    sales_by_day = [{"date": str(row["day"]), "total": money(row["total"])} for row in sales_by_day_qs]

    # Top products — compute revenue per item in Python
    per_product = {}
    items_qs = (
        SaleItem.objects.filter(
            sale__billed_at__date__gte=window_start,
            sale__billed_at__date__lte=today,
        )
        .select_related("product")
        .values("product_id", "product__name", "qty", "unit_price", "tax_pct")
    )

    for item in items_qs:
        pid = item["product_id"]
        name = item["product__name"] or "Unknown"
        qty = Decimal(str(item["qty"] or 0))
        price = Decimal(str(item["unit_price"] or 0))
        tax_pct = Decimal(str(item["tax_pct"] or 0))
        revenue = qty * price * (Decimal("1") + (tax_pct / Decimal("100")))
        bucket = per_product.setdefault(pid, {"name": name, "qty": Decimal("0"), "revenue": Decimal("0")})
        bucket["qty"] += qty
        bucket["revenue"] += revenue

    top_products = []
    for pid, data in sorted(per_product.items(), key=lambda entry: entry[1]["revenue"], reverse=True)[:5]:
        top_products.append(
            {
                "product_id": pid,
                "name": data["name"],
                "qty": float(data["qty"]),
                "revenue": money(data["revenue"]),
            }
        )

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
    """Detailed COGS rows (unchanged API shape, numeric strings kept)."""
    params = request.query_params
    date_from = _parse_date(params.get("from"))
    date_to = _parse_date(params.get("to"))
    outlet_id = params.get("outlet_id")

    qs = CogsEntry.objects.select_related("sale_item", "sale_item__sale", "product", "outlet")
    # --- PERF UPGRADE START ---
    qs = qs.only(
        "sale_item_id",
        "qty",
        "unit_cost",
        "total_cost",
        "method",
        "product__id",
        "product__name",
        "outlet__id",
        "outlet__name",
        "sale_item__sale__id",
        "sale_item__sale__billed_at",
    )
    # --- PERF UPGRADE END ---
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
    """Summarized payroll + cogs + total (strings kept for backward compatibility)."""
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


# =========================
# Executive summary (used by the new dashboard data flow)
# =========================

@extend_schema(
    parameters=[
        OpenApiParameter(name="range", description="7d|30d|90d|mtd|ytd", required=False, type=str),
        OpenApiParameter(name="granularity", description="day|week|month (auto if omitted)", required=False, type=str),
        OpenApiParameter(name="limit", description="Top N for products/outlets (default 5)", required=False, type=int),
    ],
    responses={200: dict},
)
# --- CACHE + RATE LIMIT START ---
@cache_page(60)
# --- CACHE + RATE LIMIT END ---
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exec_summary(request):
    """
    Executive dashboard rollup compatible with the new frontend:
      - timeseries (numbers)
      - top products & outlets (numbers)
      - KPIs & revenue vs cogs (numbers)
    All decimals -> float to avoid hydration mismatches.
    """
    period = request.query_params.get("range", "30d")
    start, end, trunc_default = _dt_range(period)

    gran = request.query_params.get("granularity")
    if gran == "week":
        trunc = TruncWeek
    elif gran == "month":
        trunc = TruncMonth
    else:
        trunc = trunc_default

    limit = int(request.query_params.get("limit", "5"))

    # --- PERF UPGRADE START ---
    qs_sales = (
        Sale.objects.only("id", "billed_at", "total", "outlet_id")
        .select_related("outlet")
        .filter(billed_at__date__gte=start, billed_at__date__lte=end)
    )
    sale_items_qs = (
        SaleItem.objects.filter(sale__in=qs_sales)
        .only("qty", "unit_price", "tax_pct", "sale", "product", "product__name")
    )
    # --- PERF UPGRADE END ---

    # KPIs
    total_revenue = qs_sales.aggregate(v=Coalesce(Sum("total"), Decimal("0")))["v"] or Decimal("0")
    orders = qs_sales.aggregate(v=Coalesce(Count("id"), 0))["v"] or 0
    avg_ticket = (total_revenue / orders) if orders else Decimal("0")

    # Series
    timeseries_qs = (
        qs_sales.annotate(bucket=trunc("billed_at"))
        .values("bucket")
        .annotate(total=Coalesce(Sum("total"), Decimal("0")))
        .order_by("bucket")
    )
    series = [{"date": row["bucket"].date().isoformat(), "total": float(row["total"])} for row in timeseries_qs]

    # Top outlets
    top_outlets_qs = (
        qs_sales.values("outlet__name")
        .annotate(sales=Coalesce(Sum("total"), Decimal("0")))
        .order_by("-sales")[:limit]
    )
    top_outlets = [{"name": r["outlet__name"] or "Unknown", "sales": float(r["sales"])} for r in top_outlets_qs]

    # Top products (revenue = qty*price*(1+tax))
    line_revenue = _line_revenue_expr()
    top_products_qs = (
        sale_items_qs
        .values("product__name")
        .annotate(sales=Coalesce(Sum(line_revenue), Decimal("0")))
        .order_by("-sales")[:limit]
    )
    top_products = [{"name": r["product__name"] or "Unknown", "sales": float(r["sales"])} for r in top_products_qs]

    # Very rough COGS estimate (optional)
    cogs_est = Decimal("0")
    try:
        # --- PERF UPGRADE START ---
        sale_items_for_cogs = sale_items_qs.select_related("product").only(
            "qty",
            "unit_price",
            "tax_pct",
            "product",
            "product__id",
            "product__mrp",
        )
        for it in sale_items_for_cogs:
            unit_cost = getattr(it.product, "approx_cost", None)
            if unit_cost is None:
                unit_cost = Decimal(str(it.unit_price)) * Decimal("0.60")  # heuristic
            cogs_est += Decimal(unit_cost) * Decimal(str(it.qty))
        # --- PERF UPGRADE END ---
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
            "series": series,  # [{date, total:number}]
            "top_outlets": top_outlets,  # [{name, sales:number}]
            "top_products": top_products,  # [{name, sales:number}]
            "revenue_vs_cogs": {
                "revenue": float(total_revenue),
                "cogs": float(cogs_est),
                "gross_margin": float(total_revenue - cogs_est),
            },
        }
    )
