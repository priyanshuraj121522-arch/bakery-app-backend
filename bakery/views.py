# bakery/views.py
from django.http import JsonResponse
from django.contrib.auth.models import Group
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied

from .models import Outlet, Product, Batch, Sale, UserProfile
from .serializers import (
    OutletSerializer, ProductSerializer, BatchSerializer, SaleSerializer
)
from .permissions import IsOwnerOrOutletUser


# ---------------- helpers ----------------

def _user_is_owner(user) -> bool:
    return user.is_authenticated and user.groups.filter(name="owner").exists()

def _user_outlet(user):
    """
    Return Outlet assigned via UserProfile, or None.
    """
    try:
        return UserProfile.objects.select_related("outlet").get(user=user).outlet
    except UserProfile.DoesNotExist:
        return None


# ---------------- ViewSets ----------------

class OutletViewSet(ModelViewSet):
    # Base queryset is REQUIRED so DRF router can infer the basename
    queryset = Outlet.objects.all()
    serializer_class = OutletSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return Outlet.objects.all().order_by("id")

        outlet = _user_outlet(user)
        if not outlet:
            return Outlet.objects.none()
        return Outlet.objects.filter(id=outlet.id).order_by("id")


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return Product.objects.all().order_by("id")

        outlet = _user_outlet(user)
        if not outlet:
            return Product.objects.none()
        # If products are global, keep all; if they’re outlet-scoped, filter here.
        return Product.objects.all().order_by("id")


class BatchViewSet(ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return Batch.objects.all().order_by("-produced_on")

        outlet = _user_outlet(user)
        if not outlet:
            return Batch.objects.none()
        return Batch.objects.filter(recipe__product__outlet=outlet).order_by("-produced_on")


class SaleViewSet(ModelViewSet):
    queryset = Sale.objects.all()
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return Sale.objects.all().order_by("-billed_at")

        outlet = _user_outlet(user)
        if not outlet:
            return Sale.objects.none()
        return Sale.objects.filter(outlet=outlet).order_by("-billed_at")


# ---- Health check (public, lightweight) ----
def health_check(request):
    return JsonResponse({"status": "ok"})
