# bakery/views.py
from django.http import JsonResponse
from django.contrib.auth.models import Group

from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Outlet, Product, Batch, Sale, UserProfile
from .serializers import (
    OutletSerializer, ProductSerializer, BatchSerializer, SaleSerializer
)
from .permissions import IsOwnerOrOutletUser


# -------------------- helpers --------------------

def _user_is_owner(user) -> bool:
    return user.is_authenticated and user.groups.filter(name="owner").exists()


def _user_outlet(user):
    """
    Return the Outlet assigned to the user via UserProfile, or None.
    """
    try:
        return UserProfile.objects.select_related("outlet").get(user=user).outlet
    except UserProfile.DoesNotExist:
        return None


# -------------------- ViewSets --------------------

class OutletViewSet(ModelViewSet):
    """
    Owners see all outlets. Non-owners only see their own outlet.
    """
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]
    queryset = Outlet.objects.all().order_by("id")
    serializer_class = OutletSerializer

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return self.queryset
        outlet = _user_outlet(user)
        return self.queryset.filter(id=outlet.id) if outlet else self.queryset.none()


class ProductViewSet(ModelViewSet):
    """
    Products are global (not tied to outlet). Any authenticated user can access.
    """
    permission_classes = [IsAuthenticated]
    queryset = Product.objects.all().order_by("id")
    serializer_class = ProductSerializer


class BatchViewSet(ModelViewSet):
    """
    Owners see all batches. Non-owners only see batches for their outlet.
    """
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]
    queryset = Batch.objects.select_related("outlet").all().order_by("-produced_on")
    serializer_class = BatchSerializer

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return self.queryset
        outlet = _user_outlet(user)
        return self.queryset.filter(outlet=outlet) if outlet else self.queryset.none()


class SaleViewSet(ModelViewSet):
    """
    Owners see all sales. Non-owners only see / create / edit sales for their outlet.
    """
    permission_classes = [IsAuthenticated, IsOwnerOrOutletUser]
    queryset = Sale.objects.select_related("outlet").all().order_by("-billed_at")
    serializer_class = SaleSerializer

    def get_queryset(self):
        user = self.request.user
        if _user_is_owner(user):
            return self.queryset
        outlet = _user_outlet(user)
        return self.queryset.filter(outlet=outlet) if outlet else self.queryset.none()

    def perform_create(self, serializer):
        outlet = _user_outlet(self.request.user)
        if not outlet:
            raise PermissionDenied("No outlet assigned to your profile.")
        serializer.save(outlet=outlet)

    def perform_update(self, serializer):
        outlet = _user_outlet(self.request.user)
        if not outlet:
            raise PermissionDenied("No outlet assigned to your profile.")

        instance = serializer.instance
        if instance.outlet_id != outlet.id:
            raise PermissionDenied("You can only modify sales for your own outlet.")

        # Prevent changing outlet on update
        new_outlet = serializer.validated_data.get("outlet")
        if new_outlet and new_outlet.id != outlet.id:
            raise PermissionDenied("Cannot change sale to another outlet.")

        serializer.save()


# -------------------- simple endpoints --------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Returns basic info about the current user and their assigned outlet.
    """
    user = request.user
    outlet = _user_outlet(user)
    groups = list(user.groups.values_list("name", flat=True))
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.get_full_name(),
        "groups": groups,
        "outlet": outlet.name if outlet else None,
        "outlet_id": outlet.id if outlet else None,
        "is_owner": "owner" in groups,
    })


def health_check(request):
    return JsonResponse({"status": "ok"})
