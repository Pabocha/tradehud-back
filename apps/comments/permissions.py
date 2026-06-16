from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsOwnerOrReadOnly(BasePermission):
    """Permet seulement au propriétaire d'un objet d'éditer ou supprimer.

    - Les requêtes en lecture sont accessibles à tous (GET, HEAD, OPTIONS).
    - Les requêtes non-sûres nécessitent d'être le propriétaire (obj.user == request.user).
    """

    def has_object_permission(self, request, view, obj):
        # lecture autorisée
        if request.method in SAFE_METHODS:
            return True

        # write/delete: nécessité d'être propriétaire
        user = getattr(request, 'user', None)
        return user and getattr(user, 'is_authenticated', False) and obj.user == user
