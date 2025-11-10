from rest_framework import permissions

class IsManagerOnly(permissions.BasePermission):
    message = "API access is restricted to managers only."

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        return bool(u and u.is_authenticated and u.is_active and getattr(u, "is_manager", False))


def is_top_manager(user) -> bool:
    return bool(getattr(user, "is_manager", False) and getattr(user, "manager", None) is None)