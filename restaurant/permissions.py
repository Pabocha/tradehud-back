from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission personnalisée : lecture pour tous, modification uniquement pour le propriétaire
    """
    def has_object_permission(self, request, view, obj):
        # Lecture autorisée pour tout le monde
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture uniquement pour le propriétaire
        return obj.owner == request.user


class IsRestaurantOwner(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est propriétaire du restaurant
    """
    def has_object_permission(self, request, view, obj):
        # Pour les objets Restaurant
        if hasattr(obj, 'owner'):
            return obj.owner == request.user or request.user.is_staff
        
        # Pour les objets liés à un restaurant (Meal, MenuCategory, etc.)
        if hasattr(obj, 'restaurant'):
            return obj.restaurant.owner == request.user or request.user.is_staff
        
        # Pour les catégories de menu
        if hasattr(obj, 'category') and hasattr(obj.category, 'restaurant'):
            return obj.category.restaurant.owner == request.user or request.user.is_staff
        
        return False


class IsCustomerOrRestaurantOwner(permissions.BasePermission):
    """
    Permission pour les commandes : accessible par le client ou le propriétaire du restaurant
    """
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Staff a tous les droits
        if user.is_staff:
            return True
        
        # Le client peut voir ses commandes
        if hasattr(obj, 'customer') and obj.customer == user:
            return True
        
        # Le propriétaire du restaurant peut voir les commandes de son restaurant
        if hasattr(obj, 'restaurant') and obj.restaurant.owner == user:
            return True
        
        return False


class CanReviewRestaurant(permissions.BasePermission):
    """
    Permission pour laisser un avis : l'utilisateur doit avoir commandé dans ce restaurant
    """
    def has_permission(self, request, view):
        # Lecture autorisée pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture uniquement pour les utilisateurs authentifiés
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Lecture autorisée
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # L'utilisateur ne peut modifier/supprimer que ses propres avis
        return obj.user == request.user