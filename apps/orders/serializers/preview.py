import logging

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from apps.accounts.models import Address
from apps.coupons.service import apply_coupon
from apps.products.models import ProductVariant, Products
from apps.shipping.services import calculate_shipping_cost

from ..models import Orders
from .orders import OrderLineCreateSerializer

logger = logging.getLogger(__name__)


class _PreviewLine:
    """Objet léger mimiquant une OrderLine pour le calcul coupon sans side-effect."""

    def __init__(self, variant=None, product=None, unit_price=Decimal("0"), quantity=1):
        self.variant = variant
        self.product = product
        self.unit_price = unit_price
        self.quantity = quantity

    @property
    def total_price(self):
        return Decimal(str(self.unit_price)) * self.quantity


class _ShippingLine:
    """Objet léger mimiquant une OrderLine pour le calcul shipping sans side-effect."""

    _counter = 0

    def __init__(self, variant=None, product=None, quantity=1):
        _ShippingLine._counter += 1
        self.id = _ShippingLine._counter
        self.variant = variant
        self.product = product
        self.quantity = quantity


class OrderPreviewSerializer(serializers.Serializer):
    order_lines = OrderLineCreateSerializer(many=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True, default="")
    discount = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, default=Decimal("0"))
    origin_address = serializers.PrimaryKeyRelatedField(queryset=Address.objects.all())
    shipping_method = serializers.ChoiceField(choices=Orders.CHOICES_SHIPPING_METHOD, default="standard")
    transport_mode = serializers.ChoiceField(choices=Orders.CHOICES_TRANSPORT_MODE, default="road")

    def validate_order_lines(self, value):
        if not value:
            raise serializers.ValidationError("Au moins une ligne de commande est requise.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user if request else None

        origin_address = attrs.get("origin_address")
        if origin_address and user and origin_address.customer_id != user.id:
            raise serializers.ValidationError({"origin_address": "Cette adresse ne vous appartient pas."})

        if origin_address and origin_address.address_type not in ("shipping", "both"):
            raise serializers.ValidationError({"origin_address": "Type d'adresse invalide pour la livraison."})

        discount = attrs.get("discount", Decimal("0"))
        coupon_code = (attrs.get("coupon_code") or "").strip()

        if discount and Decimal(str(discount)) < Decimal("0"):
            raise serializers.ValidationError({"discount": "La remise ne peut pas etre negative."})

        attrs["coupon_code"] = coupon_code
        return attrs

    def to_representation(self, validated_data):
        return validated_data

    def compute_preview(self):
        validated_data = self.validated_data
        request = self.context.get("request")
        user = request.user if request else None

        lines_data = validated_data["order_lines"]
        coupon_code = validated_data.get("coupon_code", "")
        requested_discount = Decimal(str(validated_data.get("discount", 0) or 0))
        shipping_method = validated_data.get("shipping_method", "standard")
        transport_mode = validated_data.get("transport_mode", "road")
        origin_address = validated_data["origin_address"]

        lines_preview = []
        shipping_lines = []
        total_price = Decimal("0.00")
        shop_ids = []

        for line in lines_data:
            quantity = line["quantity"]
            variant_id = line.get("variant")
            product_id = line.get("product")

            if variant_id:
                try:
                    variant = ProductVariant.objects.select_related("product").get(id=variant_id)
                except ProductVariant.DoesNotExist:
                    raise serializers.ValidationError(
                        {"variant": f"Variante avec l'ID {variant_id} introuvable."}
                    )

                if user and hasattr(variant.product, "shop") and variant.product.shop:
                    if getattr(variant.product.shop, "owner_id", None) == user.id:
                        raise serializers.ValidationError(
                            {"product": "Vous ne pouvez pas commander un produit de votre propre boutique."}
                        )

                unit_price_money = variant.get_unit_price(quantity)
                unit_price = unit_price_money.amount if hasattr(unit_price_money, "amount") else unit_price_money
                line_total = Decimal(str(unit_price)) * quantity
                total_price += line_total

                shop = variant.product.shop if hasattr(variant.product, "shop") else None
                if shop:
                    shop_ids.append(shop.id)

                lines_preview.append({
                    "variant": variant.id,
                    "product": None,
                    "product_name": variant.product.name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "shop_id": shop.id if shop else None,
                    "shop_name": shop.name if shop else None,
                })
                shipping_lines.append(_ShippingLine(variant=variant, quantity=quantity))
                continue

            if product_id:
                try:
                    product = Products.objects.get(id=product_id)
                except Products.DoesNotExist:
                    raise serializers.ValidationError(
                        {"product": f"Produit avec l'ID {product_id} introuvable."}
                    )

                if product.variants.exists():
                    raise serializers.ValidationError(
                        {"product": "Ce produit a des variantes. Veuillez selectionner une variante."}
                    )

                if user and hasattr(product, "shop") and product.shop:
                    if getattr(product.shop, "owner_id", None) == user.id:
                        raise serializers.ValidationError(
                            {"product": "Vous ne pouvez pas commander un produit de votre propre boutique."}
                        )

                unit_price_money = product.get_unit_price(quantity)
                unit_price = unit_price_money.amount if hasattr(unit_price_money, "amount") else unit_price_money
                line_total = Decimal(str(unit_price)) * quantity
                total_price += line_total

                shop = product.shop if hasattr(product, "shop") else None
                if shop:
                    shop_ids.append(shop.id)

                lines_preview.append({
                    "variant": None,
                    "product": product.id,
                    "product_name": product.name,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "shop_id": shop.id if shop else None,
                    "shop_name": shop.name if shop else None,
                })
                shipping_lines.append(_ShippingLine(product=product, quantity=quantity))

        shop_ids = list(set(shop_ids))

        total_discount = requested_discount
        coupon_info = None

        if coupon_code:
            preview_lines = [
                _PreviewLine(
                    variant=l.get("variant"),
                    product=l.get("product"),
                    unit_price=Decimal(str(l.get("unit_price", 0))),
                    quantity=l["quantity"],
                )
                for l in lines_preview
            ]
            # Résoudre les objets Product/Variant réels pour la validation coupon
            for pl in preview_lines:
                if pl.variant:
                    try:
                        pl.variant = ProductVariant.objects.select_related("product").get(id=pl.variant)
                    except ProductVariant.DoesNotExist:
                        pl.variant = None
                elif pl.product:
                    try:
                        pl.product = Products.objects.get(id=pl.product)
                    except Products.DoesNotExist:
                        pl.product = None

            try:
                coupon_result = apply_coupon(
                    user=user,
                    coupon_code=coupon_code,
                    order_lines=preview_lines,
                    subtotal=total_price,
                    delivery_cost=Decimal("0.00"),
                    lock_for_update=False,
                )
                total_discount = Decimal(str(coupon_result["total_discount"]))
                coupon_info = {
                    "code": coupon_code,
                    "discount_on_items": coupon_result["discount_on_items"],
                    "discount_on_shipping": coupon_result["discount_on_shipping"],
                    "total_discount": coupon_result["total_discount"],
                }
            except DjangoValidationError as exc:
                if hasattr(exc, "message_dict"):
                    raise serializers.ValidationError(exc.message_dict)
                message = exc.messages[0] if getattr(exc, "messages", None) else "Coupon invalide."
                raise serializers.ValidationError({"coupon_code": message})

        if total_discount < Decimal("0.00"):
            total_discount = Decimal("0.00")
        if total_discount > total_price:
            total_discount = total_price

        is_international = False
        try:
            shipping_result = calculate_shipping_cost(
                order_lines=shipping_lines,
                destination_address=origin_address,
                transport_mode=transport_mode,
            )
            delivery_cost = shipping_result["delivery_cost"]
            estimated_days = shipping_result.get("estimated_days", "Non disponible")
            is_international = shipping_result.get("is_international", False)
        except Exception:
            logger.error("Erreur calcul shipping pour preview: %s", exc_info=True)
            delivery_cost = Decimal("0.00")
            estimated_days = "Non disponible"

        total_amount = total_price - total_discount + delivery_cost
        if total_amount < Decimal("0.00"):
            total_amount = Decimal("0.00")

        effective_transport_mode = 'road' if not is_international else transport_mode

        return {
            "lines": lines_preview,
            "subtotal": total_price,
            "discount": total_discount,
            "delivery_cost": delivery_cost,
            "total_amount": total_amount,
            "shipping": {
                "method": shipping_method if not is_international else None,
                "transport_mode": effective_transport_mode,
                "delivery_cost": delivery_cost,
                "estimated_days": estimated_days,
                "is_international": is_international,
            },
            "coupon": coupon_info,
        }
