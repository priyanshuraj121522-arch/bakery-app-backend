# bakery/views.py
from datetime import timedelta

from django.apps import apps
from django.db import connection
from django.db.models import Sum, F
from django.utils import timezone
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth

from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import write_audit
from .models import Outlet, Product, Batch, Sale
from .permissions import IsManagerOrAbove, IsCashierOrAbove
from .serializers import (
    OutletSerializer,
    ProductSerializer,
    BatchSerializer,
    SaleSerializer,
)


class BaseAuditedViewSet(viewsets.ModelViewSet):
    read_permission = IsCashierOrAbove
    write_permission = IsManagerOrAbove

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.action in ["list", "retrieve"]:
            permissions.append(self.read_permission())
        else:
            permissions.append(self.write_permission())
        return permissions

    def _serialize_instance(self, instance):
        serializer = self.get_serializer(instance)
        return serializer.data

    def perform_create(self, serializer):
        instance = serializer.save()
        after = self._serialize_instance(instance)
        write_audit(self.request, "create", instance, before=None, after=after)

    def perform_update(self, serializer):
        before = self._serialize_instance(serializer.instance)
        instance = serializer.save()
        after = self._serialize_instance(instance)
        write_audit(self.request, "update", instance, before=before, after=after)

    def perform_destroy(self, instance):
        before = self._serialize_instance(instance)
        write_audit(self.request, "delete", instance, before=before, after=None)
        instance.delete()


class OutletViewSet(BaseAuditedViewSet):
    queryset = Outlet.objects.all()
    serializer_class = OutletSerializer


class ProductViewSet(BaseAuditedViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class BatchViewSet(BaseAuditedViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer


class SaleViewSet(BaseAuditedViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    read_permission = IsCashierOrAbove
    write_permission = IsCashierOrAbove


# --- Simple utility endpoints -------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Return the currently authenticated user with roles and outlet context."""
    user = request.user
    roles = list(user.groups.values_list("name", flat=True))
    if user.is_superuser and "Owner" not in roles:
        roles.append("Owner")

    role_map = {"owner": "owner", "manager": "manager", "cashier": "cashier"}
    normalized_roles = sorted({role_map.get(role.lower(), role.lower()) for role in roles})

    profile = getattr(user, "profile", None)
    outlet_id = getattr(profile, "outlet_id", None)
    if profile and profile.outlet_id and getattr(profile, "outlet", None):
        outlets_data = [{"id": profile.outlet_id, "name": profile.outlet.name}]
    else:
        outlets_data = list(Outlet.objects.values("id", "name"))

    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email or "",
        "roles": normalized_roles,
        "outlet_id": outlet_id,
        "outlets": outlets_data,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Simple health check"""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health_db(request):
    """Verify database connectivity by executing a lightweight query."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        return Response({"ok": False, "error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return Response({"ok": True})


# --- Reports used by the dashboard -------------------------------------------

def _parse_range(request):
    """
    Accepts:
      from, to (ISO)  OR  days (int, default 30)
    Returns (start_dt, end_dt) tz-aware.
    """
    tz = timezone.get_current_timezone()
    q_from = request.query_params.get("from")
    q_to = request.query_params.get("to")
    q_days = request.query_params.get("days")

    if q_from and q_to:
        try:
            start_raw = timezone.datetime.fromisoformat(q_from)
            start = timezone.make_aware(start_raw) if start_raw.tzinfo is None else start_raw
        except Exception:
            start = timezone.now() - timedelta(days=30)
        try:
            end_raw = timezone.datetime.fromisoformat(q_to)
            end = timezone.make_aware(end_raw) if end_raw.tzinfo is None else end_raw
        except Exception:
            end = timezone.now()
    else:
        try:
            days = max(1, int(q_days or "30"))
        except Exception:
            days = 30
        end = timezone.now()
        start = end - timedelta(days=days)

    if start > end:
        start, end = end - timedelta(days=30), end
    return start, end


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_sales_trend(request):
    """
    GET /api/reports/sales-trend/?granularity=daily|weekly|monthly&from=...&to=...&days=30
    Returns: [{ "date": "YYYY-MM-DD", "amount": 1234.56 }, ...]
    """
    granularity = (request.query_params.get("granularity") or "daily").lower()
    start, end = _parse_range(request)

    if granularity == "weekly":
        trunc = TruncWeek("date")
    elif granularity == "monthly":
        trunc = TruncMonth("date")
    else:
        trunc = TruncDay("date")

    qs = (
        Sale.objects.filter(date__gte=start, date__lte=end)
        .annotate(bucket=trunc)
        .values("bucket")
        .annotate(amount=Sum("total"))
        .order_by("bucket")
    )

    data = [{"date": x["bucket"].date().isoformat(), "amount": float(x["amount"] or 0)} for x in qs]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_products(request):
    """
    GET /api/reports/top-products/?limit=5&from=...&to=...&days=30
    Returns: [{ "name": "<Product>", "value": <revenue> }, ...]
    """
    try:
        limit = max(1, int(request.query_params.get("limit", "5")))
    except Exception:
        limit = 5

    start, end = _parse_range(request)

    # Resolve SaleItem dynamically to avoid hard import errors
    SaleItem = apps.get_model("bakery", "SaleItem")
    if SaleItem is None:
        return Response([], status=200)

    amount_expr = F("line_total") if "line_total" in [f.name for f in SaleItem._meta.fields] else F("price") * F("quantity")

    qs = (
        SaleItem.objects.filter(sale__date__gte=start, sale__date__lte=end)
        .values("product__name")
        .annotate(value=Sum(amount_expr))
        .order_by("-value")[:limit]
    )
    data = [{"name": x["product__name"], "value": float(x["value"] or 0)} for x in qs]
    return Response(data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def reports_top_outlets(request):
    """
    GET /api/reports/top-outlets/?limit=5&from=...&to=...&days=30
    Returns: [{ "name": "<Outlet>", "value": <revenue> }, ...]
    """
    try:
        limit = max(1, int(request.query_params.get("limit", "5")))
    except Exception:
        limit = 5

    start, end = _parse_range(request)

    qs = (
        Sale.objects.filter(date__gte=start, date__lte=end)
        .values("outlet__name")
        .annotate(value=Sum("total"))
        .order_by("-value")[:limit]
    )
    data = [{"name": x["outlet__name"] or "Unknown", "value": float(x["value"] or 0)} for x in qs]
    return Response(data)