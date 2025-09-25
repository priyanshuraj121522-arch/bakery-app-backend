from django.http import JsonResponse
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly

from .models import Outlet, Product, Batch, Sale
from .serializers import (
    OutletSerializer, ProductSerializer, BatchSerializer, SaleSerializer
)


class OutletViewSet(ModelViewSet):
    queryset = Outlet.objects.all().order_by("id")
    serializer_class = OutletSerializer
    # Public can read, only authenticated can write
    permission_classes = [IsAuthenticatedOrReadOnly]


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer
    # Public can read, only authenticated can write
    permission_classes = [IsAuthenticatedOrReadOnly]


class BatchViewSet(ModelViewSet):
    queryset = Batch.objects.all().order_by("-produced_on")
    serializer_class = BatchSerializer
    # Only authenticated users (staff) can access
    permission_classes = [IsAuthenticated]


class SaleViewSet(ModelViewSet):
    queryset = Sale.objects.all().order_by("-billed_at")
    serializer_class = SaleSerializer
    # Only authenticated users (cashier/manager/owner) can access
    permission_classes = [IsAuthenticated]


# ---- Health check (public, lightweight) ----
def health_check(request):
    return JsonResponse({"status": "ok"})
