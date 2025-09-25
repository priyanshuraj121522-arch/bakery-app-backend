from django.http import JsonResponse
from rest_framework.viewsets import ModelViewSet

from .models import Outlet, Product, Batch, Sale
from .serializers import (
    OutletSerializer, ProductSerializer, BatchSerializer, SaleSerializer
)
from .permissions import IsOwner, IsManagerOrOwner, IsCashierOrAbove
from rest_framework.permissions import IsAuthenticatedOrReadOnly


class OutletViewSet(ModelViewSet):
    queryset = Outlet.objects.all().order_by("id")
    serializer_class = OutletSerializer
    # Only Owners can manage outlets; public can read
    permission_classes = [IsAuthenticatedOrReadOnly | IsOwner]


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer
    # Public can read; only Owner can add/update/delete products
    permission_classes = [IsAuthenticatedOrReadOnly | IsOwner]


class BatchViewSet(ModelViewSet):
    queryset = Batch.objects.all().order_by("-produced_on")
    serializer_class = BatchSerializer
    # Managers and Owners can manage batches
    permission_classes = [IsManagerOrOwner]


class SaleViewSet(ModelViewSet):
    queryset = Sale.objects.all().order_by("-billed_at")
    serializer_class = SaleSerializer
    # Cashiers, Managers, and Owners can manage sales
    permission_classes = [IsCashierOrAbove]


# ---- Health check (public, lightweight) ----
def health_check(request):
    return JsonResponse({"status": "ok"})
