# bakery/views.py
from django.http import JsonResponse
from django.contrib.auth.models import Group
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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


# --- replace ONLY the SaleViewSet class in bakery/views.py with this ---
class SaleViewSet(ModelViewSet):
    """
    Owners: full access.
    Managers/Cashiers: limited to their own outlet; outlet & cashier are enforced.
    """
    serializer_class = SaleSerializer

    def get_queryset(self):
        qs = Sale.objects.select_related("outlet", "cashier").order_by("-billed_at")
        user = self.request.user
        if _user_is_owner(user):
            return qs
        outlet = _user_outlet(user)
        if outlet is None:
            return Sale.objects.none()
        return qs.filter(outlet=outlet)

    def perform_create(self, serializer):
        user = self.request.user
        # Owners can create anywhere
        if _user_is_owner(user):
            serializer.save()
            return

        outlet = _user_outlet(user)
        if outlet is None:
            raise PermissionDenied("You are not assigned to an outlet.")

        # If client provided an outlet, it must match their outlet
        provided = serializer.validated_data.get("outlet")
        if provided and provided.id != outlet.id:
            raise PermissionDenied("You can only create sales for your own outlet.")

        # Enforce outlet & cashier
        serializer.save(outlet=outlet, cashier=user)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        if _user_is_owner(user):
            serializer.save()
            return

        outlet = _user_outlet(user)
        if outlet is None:
            raise PermissionDenied("You are not assigned to an outlet.")

        if instance.outlet_id != outlet.id:
            raise PermissionDenied("You can only modify sales for your own outlet.")

        # Prevent switching to a different outlet in updates
        new_outlet = serializer.validated_data.get("outlet")
        if new_outlet and new_outlet.id != outlet.id:
            raise PermissionDenied("Cannot change sale to another outlet.")

        serializer.save()



# ---- Health check (public, lightweight) ----
def health_check(request):
    return JsonResponse({"status": "ok"})


# ---- Me (authenticated) ----
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Return basic info about the current user, their groups, and assigned outlet (via UserProfile).
    """
    groups = list(request.user.groups.values_list("name", flat=True))
    profile = UserProfile.objects.select_related("outlet").filter(user=request.user).first()
    outlet = None
    if profile and profile.outlet:
        outlet = {
            "id": profile.outlet.id,
            "name": profile.outlet.name,
        }

    return Response({
        "id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "groups": groups,
        "outlet": outlet,
    })