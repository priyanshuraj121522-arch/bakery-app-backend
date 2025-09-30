# bakery/views.py
from datetime import datetime

from django.db.models import Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .audit import write_audit
from .models import Outlet, Product, Batch, Sale
from .models_audit import AuditLog
from .permissions import IsOwner, IsManagerOrAbove, IsCashierOrAbove
from .serializers import (
    OutletSerializer,
    ProductSerializer,
    BatchSerializer,
    SaleSerializer,
    AuditLogSerializer,
)


class AuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = AuditLog.objects.select_related("actor").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        qs = super().get_queryset().order_by("-created_at")
        params = self.request.query_params

        action = params.get("action")
        if action:
            qs = qs.filter(action=action.lower())

        table = params.get("table")
        if table:
            qs = qs.filter(table__icontains=table.strip())

        q = params.get("q")
        if q:
            filters = Q(before__icontains=q) | Q(after__icontains=q) | Q(ua__icontains=q)
            if q.isdigit():
                filters |= Q(row_id=int(q))
            qs = qs.filter(filters)

        date_from = params.get("date_from")
        if date_from:
            try:
                start = datetime.strptime(date_from, "%Y-%m-%d").date()
                qs = qs.filter(created_at__date__gte=start)
            except ValueError:
                pass

        date_to = params.get("date_to")
        if date_to:
            try:
                end = datetime.strptime(date_to, "%Y-%m-%d").date()
                qs = qs.filter(created_at__date__lte=end)
            except ValueError:
                pass

        return qs


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


# --- Simple utility endpoints ---

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """Return the currently authenticated user with roles."""
    user = request.user
    roles = list(user.groups.values_list("name", flat=True))
    if user.is_superuser and "Owner" not in roles:
        roles.append("Owner")
    return Response({
        "id": user.id,
        "username": user.username,
        "roles": roles,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    """Simple health check"""
    return Response({"status": "ok"})
