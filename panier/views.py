from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ecom_app.services.coupons import apply_coupon

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

    @action(detail=True, methods=["patch"], url_path="change_quantity")
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

    @action(detail=False, methods=["delete"], url_path="remove_product")
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
        """
        Previsualise la reduction d'un coupon sur le panier courant.
        Aucun impact persistant: n'incremente pas coupon.uses.
        """
        coupon_code = (request.data.get("coupon_code") or "").strip()
        raw_delivery_cost = request.data.get("delivery_cost", 0)
        selected_ids_raw = (
            request.data.get("cart_item_ids")
            or request.data.get("selected_cart_item_ids")
            or request.data.get("item_ids")
        )

        try:
            delivery_cost = Decimal(str(raw_delivery_cost or 0))
        except (InvalidOperation, TypeError, ValueError):
            return Response({"error": "delivery_cost invalide."}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = self.get_queryset()

        if selected_ids_raw is not None:
            if not isinstance(selected_ids_raw, list):
                return Response(
                    {"error": "cart_item_ids doit etre une liste d'identifiants."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            selected_ids = []
            for raw_id in selected_ids_raw:
                try:
                    selected_ids.append(int(raw_id))
                except (TypeError, ValueError):
                    return Response(
                        {"error": "Tous les cart_item_ids doivent etre des entiers."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            cart_items = cart_items.filter(id__in=selected_ids)

        if not cart_items.exists():
            return Response({"error": "Votre panier est vide."}, status=status.HTTP_400_BAD_REQUEST)

        order_lines = []
        subtotal = Decimal("0.00")

        for item in cart_items:
            if item.unit_price is not None and hasattr(item.unit_price, "amount"):
                unit_price_amount = Decimal(str(item.unit_price.amount))
            else:
                current_price = item.get_current_price()
                unit_price_amount = Decimal(str(getattr(current_price, "amount", current_price)))

            line_total = unit_price_amount * Decimal(str(item.quantity))
            subtotal += line_total

            order_lines.append(
                SimpleNamespace(
                    variant=item.variant,
                    product=item.product,
                    total_price=line_total,
                )
            )

        try:
            coupon_result = apply_coupon(
                user=request.user,
                coupon_code=coupon_code,
                order_lines=order_lines,
                subtotal=subtotal,
                delivery_cost=delivery_cost,
                lock_for_update=False,
            )
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            message = exc.messages[0] if getattr(exc, "messages", None) else "Coupon invalide."
            return Response({"coupon_code": message}, status=status.HTTP_400_BAD_REQUEST)

        total_discount = Decimal(str(coupon_result["total_discount"]))
        total_after_discount = subtotal - total_discount + delivery_cost
        if total_after_discount < Decimal("0.00"):
            total_after_discount = Decimal("0.00")

        coupon = coupon_result.get("coupon")
        return Response(
            {
                "coupon_valid": coupon is not None,
                "coupon_code": coupon.code if coupon else None,
                "coupon_id": coupon.id if coupon else None,
                "scope": coupon.scope if coupon else None,
                "discount_type": coupon.discount_type if coupon else None,
                "subtotal": subtotal,
                "delivery_cost": delivery_cost,
                "eligible_subtotal": coupon_result["eligible_subtotal"],
                "discount_on_items": coupon_result["discount_on_items"],
                "discount_on_shipping": coupon_result["discount_on_shipping"],
                "total_discount": total_discount,
                "total_after_discount": total_after_discount,
                "selected_items_count": len(order_lines),
            },
            status=status.HTTP_200_OK,
        )
