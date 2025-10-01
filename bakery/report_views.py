from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, datetime

from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

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
