from decimal import Decimal
from typing import Dict, Any, List

from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import StockLedger, Product, Ingredient, Outlet


def f(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _sum_qty(qs):
    agg = qs.aggregate(
        tin=Sum("qty_in"),
        tout=Sum("qty_out"),
    )
    tin = Decimal(str(agg.get("tin") or 0))
    tout = Decimal(str(agg.get("tout") or 0))
    return tin - tout


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def inventory_overview(request):
    ITEM_ING = getattr(StockLedger, "INGREDIENT", "ingredient")
    ITEM_PROD = getattr(StockLedger, "PRODUCT", "product")

    # Kitchen raw (ingredients, outlet null)
    kitchen_raw: List[Dict[str, Any]] = []
    for ing in Ingredient.objects.all().values("id", "name"):
        qty = _sum_qty(
            StockLedger.objects.filter(
                item_type=ITEM_ING,
                item_id=ing["id"],
                outlet__isnull=True,
            )
        )
        if qty != 0:
            kitchen_raw.append({
                "id": ing["id"],
                "name": ing["name"],
                "qty_on_hand": f(qty),
            })

    # Kitchen finished (products, outlet null)
    kitchen_finished: List[Dict[str, Any]] = []
    for p in Product.objects.all().values("id", "name"):
        qty = _sum_qty(
            StockLedger.objects.filter(
                item_type=ITEM_PROD,
                item_id=p["id"],
                outlet__isnull=True,
            )
        )
        if qty != 0:
            kitchen_finished.append({
                "id": p["id"],
                "name": p["name"],
                "qty_on_hand": f(qty),
            })

    # Outlets (products per outlet)
    outlets_payload: List[Dict[str, Any]] = []
    for outlet in Outlet.objects.all().values("id", "name"):
        stock_rows: List[Dict[str, Any]] = []
        for p in Product.objects.all().values("id", "name"):
            qty = _sum_qty(
                StockLedger.objects.filter(
                    item_type=ITEM_PROD,
                    item_id=p["id"],
                    outlet_id=outlet["id"],
                )
            )
            if qty != 0:
                stock_rows.append({
                    "product_id": p["id"],
                    "product_name": p["name"],
                    "qty_on_hand": f(qty),
                })
        outlets_payload.append({
            "id": outlet["id"],
            "name": outlet["name"],
            "stock": stock_rows,
        })

    return Response({
        "kitchen_raw": kitchen_raw,
        "kitchen_finished": kitchen_finished,
        "outlets": outlets_payload,
    })
