from rest_framework.permissions import BasePermission


class IsSeller(BasePermission):
    """L'utilisateur est un vendeur (ou les deux rôles)."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.type_user in ('vendeur', 'deux')
        )


class IsBuyer(BasePermission):
    """L'utilisateur est un acheteur (ou les deux rôles)."""
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.type_user in ('acheteur', 'deux')
        )


class IsSellerOfProduct(BasePermission):
    """Le vendeur est bien le propriétaire du produit via sa boutique."""
    def has_object_permission(self, request, view, obj):
        product = obj if hasattr(obj, 'shop') else obj.product
        return (
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'seller_account')
            and product.shop.owner == request.user.seller_account
        )


class IsSellerOfShop(BasePermission):
    """Le vendeur est bien le propriétaire de la boutique."""
    def has_object_permission(self, request, view, obj):
        shop = obj if hasattr(obj, 'owner') else obj.shop
        return (
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, 'seller_account')
            and shop.owner == request.user.seller_account
        )


class IsChatRoomMember(BasePermission):
    """L'utilisateur est membre de la salle de chat."""
    def has_object_permission(self, request, view, obj):
        room = obj if hasattr(obj, 'member') else obj.chat
        return room.member.filter(id=request.user.id).exists()


class IsOrderParticipant(BasePermission):
    """L'utilisateur est soit l'acheteur, soit un vendeur concerné par la commande."""
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user.is_authenticated:
            return False

        order = obj if hasattr(obj, 'customer') else obj.order

        # Le client propriétaire de la commande
        if order.customer_id == user.id:
            return True

        # Un vendeur dont la boutique figure dans les lignes de commande
        if hasattr(user, 'seller_account'):
            shop_ids = order.order_lines.values_list('shop_id', flat=True)
            from apps.shops.models import Shops
            return Shops.objects.filter(
                id__in=shop_ids,
                owner=user.seller_account
            ).exists()

        return False
