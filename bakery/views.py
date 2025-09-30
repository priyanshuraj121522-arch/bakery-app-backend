# bakery/views.py
from rest_framework import viewsets
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
