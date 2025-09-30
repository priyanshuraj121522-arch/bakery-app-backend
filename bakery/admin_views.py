from datetime import datetime, timedelta
import logging

from django.db import models
from django.db.models import Sum, Count, F, Value
from django.db.models.functions import TruncDate, Coalesce
from django.utils import timezone
from django.utils.timezone import make_aware
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import AuditLog, Product, Outlet, StockLedger, Sale, SaleItem
from .serializers import AuditLogSerializer, StockAlertRow

log = logging.getLogger(__name__)


class IsOwnerOrManager(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return user.groups.filter(name__in=["Owner", "Manager"]).exists()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor").all().order_by("-created_at")
    serializer_class = AuditLogSerializer
    permission_classes = [IsOwnerOrManager]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["action", "table"]
    search_fields = ["row_id", "actor__email", "actor__username"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        action = params.get("action")
        if action:
            qs = qs.filter(action=action)
        table = params.get("table")
        if table:
            qs = qs.filter(table__icontains=table)
        date_from = params.get("from")
        if date_from:
            try:
                qs = qs.filter(created_at__gte=make_aware(datetime.fromisoformat(date_from)))
            except ValueError:
                pass
        date_to = params.get("to")
        if date_to:
            try:
                qs = qs.filter(created_at__lte=make_aware(datetime.fromisoformat(date_to)))
            except ValueError:
                pass
        search = params.get("search")
        if search:
            qs = qs.filter(
                models.Q(row_id__icontains=search)
                | models.Q(actor__email__icontains=search)
                | models.Q(actor__username__icontains=search)
            )
        return qs


def current_stock_by_product_outlet():
    rows = (
        StockLedger.objects.values("item_type", "item_id", "outlet_id")
        .annotate(qty=models.Sum("qty_in") - models.Sum("qty_out"))
    )
    stock = {}
    for row in rows:
        if row["item_type"] != StockLedger.PRODUCT:
            continue
        key = (row["item_id"], row["outlet_id"])
        stock[key] = float(row["qty"] or 0.0)
    return stock


@api_view(["POST"])
@permission_classes([IsOwnerOrManager])
def stock_check_now(request):
    stock = current_stock_by_product_outlet()
    outlets = {o.id: o for o in Outlet.objects.all()}
    data = []
    for product in Product.objects.all():
        threshold = float(product.reorder_threshold or 0)
        if threshold <= 0:
            continue
        product_rows = [((pid, oid), qty) for (pid, oid), qty in stock.items() if pid == product.id]
        matched = False
        for (product_id, outlet_id), qty in product_rows:
            if qty < threshold:
                matched = True
                outlet = outlets.get(outlet_id)
                data.append(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "outlet_id": outlet_id,
                        "outlet_name": outlet.name if outlet else "",
                        "qty_on_hand": qty,
                        "threshold": threshold,
                    }
                )
        if not matched and not product_rows and threshold > 0:
            data.append(
                {
                    "product_id": product.id,
                    "product_name": product.name,
                    "outlet_id": None,
                    "outlet_name": "",
                    "qty_on_hand": 0.0,
                    "threshold": threshold,
                }
            )
    serializer = StockAlertRow(data=data, many=True)
    serializer.is_valid(raise_exception=True)
    return Response({"results": serializer.data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_summary(request):
    try:
        now = timezone.now()
        start = now - timedelta(days=30)

        sale_date = Coalesce(F("billed_at"), F("created_at"))
        orders_qs = Sale.objects.annotate(s_date=sale_date).filter(
            s_date__gte=start,
            s_date__lte=now,
        )

        totals = orders_qs.aggregate(
            orders_30d=Coalesce(Count("id"), Value(0)),
            sales_30d=Coalesce(Sum("total"), Value(0)),
        )

        orders_30d = totals.get("orders_30d") or 0
        sales_30d = float(totals.get("sales_30d") or 0)
        avg_ticket_30d = float(sales_30d / orders_30d) if orders_30d else 0.0

        by_day = (
            orders_qs.annotate(day=TruncDate("s_date"))
            .values("day")
            .annotate(total=Coalesce(Sum("total"), Value(0)))
            .order_by("day")
        )

        sales_by_day_30d = [
            {
                "date": row["day"].isoformat() if row.get("day") else "",
                "total": float(row.get("total") or 0),
            }
            for row in by_day
        ]

        items_qs = SaleItem.objects.filter(sale__in=orders_qs)

        top_products = (
            items_qs.values("product_id", "product__name")
            .annotate(
                qty=Coalesce(Sum("qty"), Value(0)),
                total=Coalesce(Sum(F("qty") * F("unit_price")), Value(0)),
            )
            .order_by("-qty")[:10]
        )

        top_products_30d = [
            {
                "product_id": row.get("product_id"),
                "name": row.get("product__name") or "",
                "qty": float(row.get("qty") or 0),
                "total": float(row.get("total") or 0),
            }
            for row in top_products
        ]

        return Response(
            {
                "sales_30d": sales_30d,
                "orders_30d": orders_30d,
                "avg_ticket_30d": avg_ticket_30d,
                "sales_by_day_30d": sales_by_day_30d,
                "top_products_30d": top_products_30d,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as exc:  # pragma: no cover - defensive
        log.exception("admin_summary failed")
        return Response(
            {"error": "summary_failed", "detail": str(exc)},
            status=status.HTTP_200_OK,
        )
