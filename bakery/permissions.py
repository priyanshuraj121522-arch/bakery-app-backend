# bakery/permissions.py
from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsOwner(BasePermission):
    """
    Allows access only to users in 'owner' group.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="owner").exists()
        )


class IsManagerOrOwner(BasePermission):
    """
    Allows access to managers and owners.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.groups.filter(name="owner").exists() or
                request.user.groups.filter(name="outlet_manager").exists()
            )
        )


class IsCashierOrAbove(BasePermission):
    """
    Allows access to cashier, manager, and owner.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (
                request.user.groups.filter(name="owner").exists() or
                request.user.groups.filter(name="outlet_manager").exists() or
                request.user.groups.filter(name="cashier").exists()
            )
        )
