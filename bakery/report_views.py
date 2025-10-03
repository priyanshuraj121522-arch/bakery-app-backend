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


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


@api_view(["GET"])
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
        results.append({
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
        })

    return Response({"results": results})


def payroll_gross_cost(period_id: int):
    agg = PayrollEntry.objects.filter(period_id=period_id).aggregate(total=Sum("gross_pay"))
    return agg.get("total") or Decimal("0")


@api_view(["GET"])
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

    return Response({
        "payroll": str(payroll_total.quantize(Decimal("0.01"))),
        "cogs": str(cogs_total.quantize(Decimal("0.01"))),
        "total": str((payroll_total + cogs_total).quantize(Decimal("0.01"))),
    })


def _dt_range(period: str):
    """
    Return (start_date, end_date, truncate_fn) based on ?range= parameter.
    period in {"7d","30d","90d","mtd","ytd"}; default "30d".
    """
    now = timezone.now()
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


def _safe_decimal(x):
    from decimal import Decimal

    return Decimal(str(x or "0"))


@extend_schema(
    parameters=[
        OpenApiParameter(name="range", description="7d|30d|90d|mtd|ytd", required=False, type=str),
        OpenApiParameter(name="granularity", description="day|week|month (default auto from range)", required=False, type=str),
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
      - revenue vs cogs (if data present)
      - simple stock-out predictions (days_to_zero) using StockLedger, last 7d avg
    Defensive: if models/fields are missing or empty, returns sensible defaults.
    """
    from decimal import Decimal

    period = request.query_params.get("range", "30d")
    limit = int(request.query_params.get("limit", "10"))
    gran = request.query_params.get("granularity")  # optional

    try:
        start, end, trunc_default = _dt_range(period)
    except Exception:
        start, end, trunc_default = _dt_range("30d")

    # choose truncate by granularity param
    if gran == "week":
        trunc = TruncWeek
    elif gran == "month":
        trunc = TruncMonth
    elif gran == "day" or gran is None:
        trunc = trunc_default
    else:
        trunc = trunc_default

    # --- Sales timeseries + totals ---
    try:
        qs_sales = Sale.objects.filter(billed_at__date__gte=start, billed_at__date__lte=end)
        timeseries_qs = (
            qs_sales.annotate(bucket=trunc("billed_at"))
            .values("bucket")
            .annotate(total=Coalesce(Sum("total"), Decimal("0.00")))
            .order_by("bucket")
        )
        series = [{"date": row["bucket"].date().isoformat(), "total": float(row["total"])} for row in timeseries_qs]
        total_revenue = float(qs_sales.aggregate(v=Coalesce(Sum("total"), Decimal("0.00")))["v"])
        orders = int(qs_sales.aggregate(v=Coalesce(Count("id"), 0))["v"])
        avg_ticket = float(round(Decimal(str(total_revenue)) / orders, 2)) if orders else 0.0
    except Exception:
        series = []
        total_revenue = 0.0
        orders = 0
        avg_ticket = 0.0

    # --- Top products ---
    try:
        top_products_qs = (
            qs_sales.values("items__product__name")  # SaleItem reverse name "items"
            .annotate(sales=Coalesce(Sum("total"), Decimal("0.00")))
            .order_by("-sales")[:limit]
        )
        top_products = [
            {"name": row["items__product__name"] or "Unknown", "sales": float(row["sales"])}
            for row in top_products_qs
        ]
    except Exception:
        top_products = []

    # --- Top outlets ---
    try:
        top_outlets_qs = (
            qs_sales.values("outlet__name")
            .annotate(sales=Coalesce(Sum("total"), Decimal("0.00")))
            .order_by("-sales")[:limit]
        )
        top_outlets = [
            {"name": row["outlet__name"] or "Unknown", "sales": float(row["sales"])}
            for row in top_outlets_qs
        ]
    except Exception:
        top_outlets = []

    # --- Revenue vs COGS (best-effort) ---
    # If you have StockLedger with reasons "purchase" (qty_in * cost) and "sale" (qty_out),
    # estimate COGS for this window as sum of qty_out * last known unit_cost per product.
    revenue_vs_cogs = {"revenue": total_revenue, "cogs": None, "gross_margin": None}
    try:
        cogs = None

        # Example heuristic: if SaleItem has unit_price but not unit_cost, try using Product.approx_cost if present
        if SaleItem.objects.exists():
            items = SaleItem.objects.filter(sale__in=qs_sales).select_related("product")
            from decimal import Decimal

            cogs_total = Decimal("0.00")
            for it in items:
                unit_cost = None
                # Prefer product.approx_cost if exists; else 60% of unit_price as guess
                if hasattr(it.product, "approx_cost") and it.product.approx_cost is not None:
                    unit_cost = Decimal(str(it.product.approx_cost))
                else:
                    unit_cost = Decimal(str(it.unit_price)) * Decimal("0.60")
                cogs_total += unit_cost * Decimal(str(it.qty))
            cogs = float(cogs_total.quantize(Decimal("0.01")))
        if cogs is not None:
            revenue_vs_cogs["cogs"] = cogs
            revenue_vs_cogs["gross_margin"] = round(total_revenue - cogs, 2)
    except Exception:
        pass

    # --- Stock-out predictions (simple) ---
    # For each product: days_to_zero = current_stock / avg_daily_sales_7d
    stockouts = []
    try:
        window7 = timezone.localdate() - timedelta(days=6)
        # avg daily sales
        sales7 = (
            SaleItem.objects.filter(sale__billed_at__date__gte=window7)
            .values("product__id", "product__name")
            .annotate(qty=Coalesce(Sum("qty"), 0.0))
        )
        avg_per_day = {row["product__id"]: (float(row["qty"]) / 7.0) for row in sales7}

        # current stock from StockLedger: sum(qty_in - qty_out) per product
        if "StockLedger" in globals():
            stock = (
                StockLedger.objects.filter(item_type=StockLedger.PRODUCT)
                .values("item_id")
                .annotate(qty=Coalesce(Sum(F("qty_in") - F("qty_out")), 0.0))
            )
            for s in stock:
                pid = s["item_id"]
                rate = avg_per_day.get(pid, 0.0)
                days = None
                if rate > 0:
                    days = round(float(s["qty"]) / rate, 1)
                name = next((r["product__name"] for r in sales7 if r["product__id"] == pid), None)
                stockouts.append({"product_id": pid, "name": name or f"Product {pid}", "days_to_zero": days})
    except Exception:
        stockouts = []

    return Response({
        "period": period,
        "series": series,  # [{date, total}]
        "kpis": {
            "revenue": total_revenue,
            "orders": orders,
            "avg_ticket": avg_ticket,
        },
        "top_products": top_products,  # [{name, sales}]
        "top_outlets": top_outlets,  # [{name, sales}]
        "revenue_vs_cogs": revenue_vs_cogs,  # {revenue, cogs?, gross_margin?}
        "stockouts": stockouts,  # [{product_id, name, days_to_zero?}]
    })
