# bakery/views.py
from django.http import JsonResponse
from rest_framework.viewsets import ModelViewSet

from .models import Outlet, Product, Batch, Sale
from .serializers import (
    OutletSerializer, ProductSerializer, BatchSerializer, SaleSerializer
)


class OutletViewSet(ModelViewSet):
    queryset = Outlet.objects.all().order_by("id")
    serializer_class = OutletSerializer


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer


class BatchViewSet(ModelViewSet):
    queryset = Batch.objects.all().order_by("-produced_on")
    serializer_class = BatchSerializer


class SaleViewSet(ModelViewSet):
    queryset = Sale.objects.all().order_by("-billed_at")
    serializer_class = SaleSerializer


# ---- Health check (public, lightweight) ----
def health_check(request):
    return JsonResponse({"status": "ok"})
