# bakery/permissions.py
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOwner(BasePermission):
    """
    Full access only for users in 'owner' group.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="owner").exists()
        )


class IsManagerOrOwner(BasePermission):
    """
    Managers and Owners can access.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.groups.filter(name="owner").exists()
                or request.user.groups.filter(name="outlet_manager").exists()
            )
        )


class IsCashierOrAbove(BasePermission):
    """
    Cashiers, Managers, and Owners can access.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.groups.filter(name="owner").exists()
                or request.user.groups.filter(name="outlet_manager").exists()
                or request.user.groups.filter(name="cashier").exists()
            )
        )


class IsOwnerOrOutletUser(BasePermission):
    """
    Owners see everything.
    Managers/Cashiers restricted to their assigned outlet (via UserProfile).
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Owners bypass outlet restriction
        if request.user.groups.filter(name="owner").exists():
            return True

        # Non-owner: must have a UserProfile with an outlet
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.outlet:
            return False

        # If the object has an outlet field, enforce match
        if hasattr(obj, "outlet_id"):
            return obj.outlet_id == profile.outlet.id

        # Otherwise, only allow safe (read-only) access
        return request.method in SAFE_METHODS
