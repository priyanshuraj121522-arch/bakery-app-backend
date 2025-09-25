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


# --- helpers ---------------------------------------------------------------

def _user_is_owner(user) -> bool:
    return user.is_authenticated and user.groups.filter(name="owner").exists()

def _user_outlet(user):
    """Return Outlet assigned via UserProfile, or None."""
    try:
        return UserProfile.objects.select_related("outlet").get(user=user).outlet
    except UserProfile.DoesNotExist:
        return None


# --- ViewSets --------------------------------------------------------------

class OutletViewSet(ModelViewSet):
    """
    Owners: full access to all outlets.
    Managers/Cashiers: can only see their assigned outlet (read-only by default).
    """
    serializer_class = OutletSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]

    def get_queryset(self):
        qs = Outlet.objects.all().order_by("id")
        user = self.request.user
        if _user_is_owner(user):
            return qs
        outlet = _user_outlet(user)
        return qs.filter(id=outlet_id) if (outlet and (outlet_id := outlet.id)) else qs.none()

    # non-owners should not create/delete outlets through API
    def perform_create(self, serializer):
        if not _user_is_owner(self.request.user):
            raise PermissionDenied("Only owners can create outlets.")
        serializer.save()

    def perform_destroy(self, instance):
        if not _user_is_owner(self.request.user):
            raise PermissionDenied("Only owners can delete outlets.")
        return super().perform_destroy(instance)


class ProductViewSet(ModelViewSet):
    """
    Products are global (not per-outlet) in this backend.
    Require login; owners/managers typically edit; cashiers usually read.
    Adjust later if you want stricter rules.
    """
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated]


class BatchViewSet(ModelViewSet):
    """
    Batches are global for now. Require auth.
    """
    queryset = Batch.objects.all().order_by("-produced_on")
    serializer_class = BatchSerializer
    permission_classes = [IsAuthenticated]


class SaleViewSet(ModelViewSet):
    """
    Owners: all sales across outlets.
    Managers/Cashiers: only their outlet’s sales.
    On create/update by non-owners, the sale's outlet is forced to their assigned outlet.
    """
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]

    def get_queryset(self):
        qs = Sale.objects.all().order_by("-billed_at")
        user = self.request.user
        if _user_is_owner(user):
            return qs
        outlet = _user_outlet(user)
        return qs.filter(outlet_id=outlet.id) if outlet else qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        if _user_is_owner(user):
            # owner may post with any outlet in payload
            serializer.save()
            return
        outlet = _user_outlet(user)
        if not outlet:
            raise PermissionDenied("No outlet assigned to your profile.")
        # force outlet to the user’s outlet
        serializer.save(outlet=outlet)

    def perform_update(self, serializer):
        user = self.request.user
        if _user_is_owner(user):
            serializer.save()
            return
        outlet = _user_outlet(user)
        if not outlet:
            raise PermissionDenied("No outlet assigned to your profile.")
        # prevent cross-outlet changes
        instance_outlet_id = serializer.instance.outlet_id
        if instance_outlet_id != outlet.id:
            raise PermissionDenied("You cannot modify sales from another outlet.")
        # also force outlet to remain the same
        serializer.save(outlet=outlet)


# ---- Health check (public, lightweight) -----------------------------------

def health_check(request):
    # Public endpoint used by Railway/monitors
    return JsonResponse({"status": "ok"})
