from datetime import datetime, timedelta

from django.db import models
from django.db.models import Sum, Count, F, Value, DecimalField, FloatField
from django.db.models.functions import TruncDate, Coalesce, Cast
from django.utils import timezone
from django.utils.timezone import make_aware
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditLog, Product, Outlet, StockLedger, Sale, SaleItem
from .serializers import AuditLogSerializer, StockAlertRow


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


class DashboardSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        since = now - timedelta(days=30)

        sale_date = Coalesce(F("billed_at"), F("created_at"))
        sales_qs = Sale.objects.annotate(s_date=sale_date).filter(s_date__gte=since)

        orders_30d = sales_qs.count()
        sales_sum = sales_qs.aggregate(
            total=Coalesce(
                Sum(
                    Cast("total", output_field=DecimalField(max_digits=12, decimal_places=2))
                ),
                Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )["total"] or 0
        sales_30d = float(sales_sum)
        avg_ticket_30d = float(sales_30d / orders_30d) if orders_30d else 0.0

        by_day = (
            sales_qs.annotate(day=TruncDate("s_date"))
            .values("day")
            .annotate(
                total=Coalesce(
                    Sum(
                        Cast("total", output_field=DecimalField(max_digits=12, decimal_places=2))
                    ),
                    Value(0, output_field=DecimalField(max_digits=12, decimal_places=2)),
                )
            )
            .order_by("day")
        )
        sales_by_day_30d = [
            {"date": r["day"].isoformat(), "total": float(r["total"] or 0)}
            for r in by_day
            if r.get("day")
        ]

        items_qs = SaleItem.objects.annotate(
            s_date=Coalesce(F("sale__billed_at"), F("sale__created_at"))
        ).filter(s_date__gte=since)

        items_qs = items_qs.annotate(
            line_revenue=Coalesce(
                Cast(F("qty"), FloatField()) * Cast(F("unit_price"), FloatField()),
                Value(0.0, output_field=FloatField()),
            )
        )

        top = (
            items_qs.values("product__name")
            .annotate(
                revenue=Coalesce(Sum("line_revenue"), Value(0.0, output_field=FloatField())),
                qty=Coalesce(Sum(Cast("qty", FloatField())), Value(0.0, output_field=FloatField())),
            )
            .order_by("-revenue")[:10]
        )

        top_products_30d = [
            {
                "name": r.get("product__name") or "Unnamed",
                "revenue": float(r.get("revenue") or 0),
                "qty": float(r.get("qty") or 0),
            }
            for r in top
        ]

        return Response(
            {
                "kpis": {
                    "sales_30d": sales_30d,
                    "orders_30d": orders_30d,
                    "avg_ticket_30d": avg_ticket_30d,
                },
                "sales_by_day_30d": sales_by_day_30d,
                "top_products_30d": top_products_30d,
            }
        )
