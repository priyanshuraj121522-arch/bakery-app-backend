# bakery/report_views.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Sale, Wastage

def money(x: Decimal) -> str:
    if x is None:
        x = Decimal("0")
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _parse_date(d: str):
    # expects 'YYYY-MM-DD'
    return datetime.strptime(d, "%Y-%m-%d").date()

@extend_schema(
    parameters=[
        OpenApiParameter(name="from", description="Start date (YYYY-MM-DD)", required=False, type=str),
        OpenApiParameter(name="to",   description="End date (YYYY-MM-DD)", required=False, type=str),
    ],
    responses={200: dict},
)
@api_view(["GET"])
def owner_summary(request):
    """
    Returns owner KPIs for a date or date range (inclusive).
    Defaults to 'today' in your local timezone.
    """
    tz = timezone.get_current_timezone()

    # --- Date range handling ---
    today_local = timezone.localdate()
    date_from_str = request.query_params.get("from")
    date_to_str   = request.query_params.get("to")

    if date_from_str and date_to_str:
        date_from = _parse_date(date_from_str)
        date_to   = _parse_date(date_to_str)
    elif date_from_str and not date_to_str:
        date_from = _parse_date(date_from_str)
        date_to   = date_from
    elif not date_from_str and date_to_str:
        date_to   = _parse_date(date_to_str)
        date_from = date_to
    else:
        # default: today
        date_from = today_local
        date_to   = today_local

    # --- Sales aggregates ---
    sales_qs = Sale.objects.filter(billed_at__date__gte=date_from,
                                   billed_at__date__lte=date_to)

    agg = sales_qs.aggregate(
        subtotal=Coalesce(Sum("subtotal"), Decimal("0.00")),
        tax=Coalesce(Sum("tax"), Decimal("0.00")),
        discount=Coalesce(Sum("discount"), Decimal("0.00")),
        total=Coalesce(Sum("total"), Decimal("0.00")),
        bills=Coalesce(Count("id"), 0),
    )

    bills = int(agg["bills"] or 0)
    avg_bill = (Decimal(agg["total"]) / bills) if bills else Decimal("0.00")

    # --- Outlet leaderboard (by total sales) ---
    by_outlet_qs = (sales_qs
        .values("outlet__name")
        .annotate(sales=Coalesce(Sum("total"), Decimal("0.00")))
        .order_by("-sales"))

    by_outlet = [
        {"outlet": row["outlet__name"], "sales": money(row["sales"])}
        for row in by_outlet_qs
    ]

    # --- Wastage (optional; returns totals if you use the Wastage model) ---
    try:
        wastage_qs = Wastage.objects.filter(noted_at__date__gte=date_from,
                                            noted_at__date__lte=date_to)
        wastage_qty = wastage_qs.aggregate(qty=Coalesce(Sum("qty"), 0.0))["qty"] or 0.0
    except Exception:
        wastage_qty = 0.0  # if Wastage model not present or no data yet

    data = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "subtotal": money(agg["subtotal"]),
        "tax": money(agg["tax"]),
        "discount": money(agg["discount"]),
        "total_sales": money(agg["total"]),
        "bills": bills,
        "avg_bill": money(avg_bill),
        "by_outlet": by_outlet,
        # You can later convert wastage to a % of production/sales when you track costs/qtys tightly.
        "wastage_qty": wastage_qty,
    }
    return Response(data)
