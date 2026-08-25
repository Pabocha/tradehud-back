from rest_framework.permissions import BasePermission


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
