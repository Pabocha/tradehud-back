from rest_framework.permissions import BasePermission


class IsSupportOrAdmin(BasePermission):
    """Accès réservé aux rôles support/admin (plateforme dédiée)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.type_user in ('support', 'admin'))
