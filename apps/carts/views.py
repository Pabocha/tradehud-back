from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import services
from .models import CartItem
from .serializers import CartItemSerializer


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            CartItem.objects.filter(user=self.request.user)
            .select_related("product", "variant", "variant__product")
            .prefetch_related("variant__attributes__attribute")
            .order_by("-id")
        )

    def perform_create(self, serializer):
        user = self.request.user
        variant = serializer.validated_data.get("variant")
        product = serializer.validated_data.get("product")
        quantity = serializer.validated_data["quantity"]

        if variant:
            unit_price = variant.get_unit_price(quantity)
            try:
                existing = CartItem.objects.get(user=user, variant=variant)
                existing.quantity += quantity
                existing.unit_price = unit_price
                existing.save()
                return
            except CartItem.DoesNotExist:
                serializer.save(user=user, unit_price=unit_price)
                return

        if product:
            unit_price = product.get_unit_price(quantity)
            try:
                existing = CartItem.objects.get(user=user, product=product)
                existing.quantity += quantity
                existing.unit_price = unit_price
                existing.save()
                return
            except CartItem.DoesNotExist:
                serializer.save(user=user, unit_price=unit_price)
                return

    @action(detail=True, methods=["patch"], url_path="change-quantity")
    def change_quantity(self, request, pk=None):
        try:
            cart_item = self.get_object()
            new_quantity = int(request.data.get("quantity", 1))
            if new_quantity < 1:
                return Response({"error": "Quantite invalide"}, status=400)

            if cart_item.variant:
                unit_price = cart_item.variant.get_unit_price(new_quantity)
            else:
                unit_price = cart_item.product.get_unit_price(new_quantity)

            cart_item.quantity = new_quantity
            cart_item.unit_price = unit_price
            cart_item.save()

            serializer = self.get_serializer(cart_item)
            return Response(serializer.data, status=200)
        except Exception as exc:
            return Response({"error": str(exc)}, status=500)

    @action(detail=False, methods=["delete"], url_path="clear")
    def clear_cart(self, request):
        deleted_count, _ = CartItem.objects.filter(user=request.user).delete()
        return Response(
            {"message": f"{deleted_count} produit(s) supprime(s) du panier."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["delete"], url_path="remove-product")
    def remove_product(self, request):
        user = request.user
        variant_id = request.data.get("variant_id")
        product_id = request.data.get("product_id")

        if not variant_id and not product_id:
            return Response({"error": "variant_id ou product_id est requis."}, status=400)

        item = None
        if variant_id:
            item = CartItem.objects.filter(user=user, variant__id=variant_id).first()
        if not item and product_id:
            item = CartItem.objects.filter(user=user, product__id=product_id).first()

        if not item:
            return Response({"error": "Produit introuvable dans le panier."}, status=404)

        item.delete()
        return Response({"message": "Produit supprime du panier."}, status=200)

    @action(detail=False, methods=["post"], url_path="preview-coupon")
    def preview_coupon(self, request):
        selected_ids = (
            request.data.get("cart_item_ids")
            or request.data.get("selected_cart_item_ids")
            or request.data.get("item_ids")
        )
        try:
            result = services.preview_coupon(
                cart_items=self.get_queryset(),
                user=request.user,
                coupon_code=request.data.get("coupon_code", ""),
                delivery_cost=request.data.get("delivery_cost", 0),
                selected_ids=selected_ids,
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
