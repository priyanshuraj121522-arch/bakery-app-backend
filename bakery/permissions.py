from rest_framework.permissions import BasePermission, SAFE_METHODS


OWNER_GROUP = "Owner"
MANAGER_GROUP = "Manager"
CASHIER_GROUP = "Cashier"


def _has_group(user, name: str) -> bool:
    return user.groups.filter(name=name).exists()


class IsOwner(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or _has_group(user, OWNER_GROUP))
        )


class IsManagerOrAbove(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or _has_group(user, OWNER_GROUP):
            return True
        return _has_group(user, MANAGER_GROUP)


class IsCashierOrAbove(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or _has_group(user, OWNER_GROUP) or _has_group(user, MANAGER_GROUP):
            return True
        return _has_group(user, CASHIER_GROUP)


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
