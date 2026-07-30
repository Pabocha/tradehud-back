from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
import logging

logger = logging.getLogger(__name__)
from djmoney.contrib.django_rest_framework.fields import MoneyField
from apps.accounts.models import Address
from apps.coupons.models import CouponUsage
from apps.coupons.service import apply_coupon
from apps.notifications.notifications import create_notification_if_allowed
from apps.carts.models import CartItem
from apps.products.models import ProductVariant, Products
from apps.shipping.services import calculate_shipping_cost

from .models import OrderLine, Orders, Quote, QuoteLine, ReturnRequest, ReturnItem, Refund


class OrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    product_image = serializers.SerializerMethodField()
    variant_options = serializers.SerializerMethodField()

    class Meta:
        model = OrderLine
        fields = [
            'id',
            'variant',
            'product',
            'variant_sku',
            'variant_options',
            'product_name',
            'quantity',
            'unit_price',
            'total_price',
            'shop_name',
            'product_image',
            'shop',
        ]
        read_only_fields = ['shop']

    def _get_product(self, obj):
        if obj.variant:
            return obj.variant.product
        return obj.product

    def get_product_name(self, obj):
        product = self._get_product(obj)
        return product.name if product else None

    def get_product_image(self, obj):
        request = self.context.get('request')
        product = self._get_product(obj)
        if product and product.image and hasattr(product.image, 'url'):
            return request.build_absolute_uri(product.image.url)
        return None

    def get_variant_options(self, obj):
        if not obj.variant:
            return []
        return [
            {
                'attribute': av.attribute.name,
                'value': av.value,
                'hex_color': av.hex_color,
            }
            for av in obj.variant.attributes.select_related('attribute').all()
        ]


class OrderLineCreateSerializer(serializers.Serializer):
    variant = serializers.IntegerField(required=False)
    product = serializers.IntegerField(required=False)
    quantity = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        variant = attrs.get('variant')
        product = attrs.get('product')
        if not variant and not product:
            raise serializers.ValidationError("Vous devez fournir soit 'variant', soit 'product'.")
        if variant and product:
            raise serializers.ValidationError("Fournissez seulement 'variant' ou 'product', pas les deux.")
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    order_lines = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    delivery_cost = MoneyField(max_digits=10, decimal_places=2)
    is_discussed_order = serializers.SerializerMethodField()
    source_type = serializers.SerializerMethodField()
    source_quote_id = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source='customer.email', read_only=True)
    preview_image_url = serializers.SerializerMethodField()
    preview_product_name = serializers.SerializerMethodField()
    payment_method_name = serializers.SerializerMethodField()

    class Meta:
        model = Orders
        fields = [
            'id', 'order_number', 'customer', 'customer_name', 'order_date',
            'shipping_first_name', 'shipping_last_name', 'shipping_phone_number',
            'shipping_street_address', 'shipping_city', 'shipping_state_region',
            'shipping_postal_code', 'shipping_country',
            'shipping_method', 'transport_mode',
            'delivery_cost', 'discount', 'total_amount',
            'status', 'payment_method', 'payment_method_name', 'payment_status',
            'payment_first_name', 'payment_last_name', 'payment_phone_number',
            'applied_coupon_code', 'preview_image_url', 'preview_product_name',
            'is_discussed_order', 'source_type', 'source_quote_id',
            'order_lines'
        ]
        read_only_fields = ['customer', 'order_number', 'status', 'payment_status']

    def get_preview_image_url(self, obj):
        request = self.context.get("request")
        first_line = obj.order_lines.select_related("variant__product").first()

        if first_line:
            if first_line.variant and first_line.variant.product.image:
                return request.build_absolute_uri(first_line.variant.product.image.url)
            if first_line.product and first_line.product.image:
                return request.build_absolute_uri(first_line.product.image.url)
        return None

    def get_preview_product_name(self, obj):
        first_line = obj.order_lines.select_related("variant__product").first()
        if first_line:
            if first_line.variant:
                return first_line.variant.product.name
            if first_line.product:
                return first_line.product.name
        return None

    def get_payment_method_name(self, obj):
        return [pm.name for pm in obj.payment_method.all()]

    def _get_source_quote(self, obj):
        return obj.converted_quotes.only('id').order_by('-id').first()

    def get_is_discussed_order(self, obj):
        return self._get_source_quote(obj) is not None

    def get_source_type(self, obj):
        return 'quote' if self._get_source_quote(obj) is not None else 'standard'

    def get_source_quote_id(self, obj):
        quote = self._get_source_quote(obj)
        return quote.id if quote else None

    def _get_filtered_lignes(self, obj):
        shop_id = self.context.get('shop_id')
        shop_ids = self.context.get('shop_ids')
        lines = obj.order_lines.all()
        if shop_id:
            lines = lines.filter(shop_id=shop_id)
        elif shop_ids:
            lines = lines.filter(shop_id__in=shop_ids)
        return lines

    def get_total_amount(self, obj):
        # Pour le contexte vendeur (shop_id/shop_ids), retourner le montant des lignes filtrées.
        if self.context.get('shop_id') or self.context.get('shop_ids'):
            lines = self._get_filtered_lignes(obj)
            return sum((line.total_price for line in lines), Decimal('0.00'))
        return float(obj.total_amount.amount)

    def get_order_lines(self, obj):
        lines = self._get_filtered_lignes(obj)
        return OrderLineSerializer(lines, many=True, context=self.context).data


class OrderCreateSerializer(serializers.ModelSerializer):
    order_lines = OrderLineCreateSerializer(many=True, write_only=True)
    coupon_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    origin_address = serializers.PrimaryKeyRelatedField(queryset=Address.objects.all())
    transport_mode = serializers.ChoiceField(
        choices=Orders.CHOICES_TRANSPORT_MODE, default='road', write_only=True
    )

    class Meta:
        model = Orders
        fields = [
            'origin_address', 'shipping_method', 'transport_mode',
            'discount', 'coupon_code', 'order_lines'
        ]

    def validate_order_lines(self, value):
        if not value:
            raise serializers.ValidationError("Au moins une ligne de commande est requise.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None

        origin_address = attrs.get('origin_address')
        if origin_address and user and origin_address.customer_id != user.id:
            raise serializers.ValidationError({"origin_address": "Cette adresse ne vous appartient pas."})

        if origin_address and origin_address.address_type not in ('shipping', 'both'):
            raise serializers.ValidationError({"origin_address": "Type d'adresse invalide pour la livraison."})

        discount = attrs.get("discount")
        coupon_code = (attrs.get("coupon_code") or "").strip()

        if discount is not None and Decimal(str(discount)) < Decimal("0"):
            raise serializers.ValidationError({"discount": "La remise ne peut pas etre negative."})

        return attrs

    def to_representation(self, instance):
        return {
            'id': instance.id,
            'order_number': instance.order_number,
            'origin_address': instance.origin_address_id,
            'shipping_method': instance.shipping_method,
            'transport_mode': instance.transport_mode,
            'discount': str(instance.discount),
            'delivery_cost': str(instance.delivery_cost),
            'total_amount': str(instance.total_amount),
            'status': instance.status,
        }

    def create(self, validated_data):
        lines_data = validated_data.pop('order_lines')
        coupon_code = (validated_data.pop('coupon_code', '') or '').strip()
        requested_discount = Decimal(str(validated_data.pop('discount', 0) or 0))
        shipping_method = validated_data.pop('shipping_method', 'standard')
        transport_mode = validated_data.pop('transport_mode', 'road')
        request = self.context.get('request')
        user = request.user if request else None

        with transaction.atomic():
            order = Orders.objects.create(
                total_amount=Decimal('0.00'),
                discount=Decimal('0.00'),
                delivery_cost=Decimal('0.00'),
                shipping_method=shipping_method,
                transport_mode=transport_mode,
                **validated_data
            )

            total_price = Decimal('0.00')

            for line in lines_data:
                quantity = line['quantity']
                variant_id = line.get('variant')
                product_id = line.get('product')

                if variant_id:
                    try:
                        variant = ProductVariant.objects.select_for_update().get(id=variant_id)
                    except ProductVariant.DoesNotExist:
                        raise serializers.ValidationError(
                            {"variant": f"Variante avec l'ID {variant_id} introuvable."}
                        )

                    if variant.stock_quantity < quantity:
                        raise serializers.ValidationError(
                            {"stock": f"Stock insuffisant pour la variante {variant.sku} "
                                      f"(disponible: {variant.stock_quantity}, demande: {quantity})"}
                        )

                    if user and hasattr(variant.product, 'shop') and variant.product.shop:
                        if getattr(variant.product.shop, 'owner_id', None) == user.id:
                            raise serializers.ValidationError(
                                {"product": "Vous ne pouvez pas commander un produit de votre propre boutique."}
                            )

                    unit_price_money = variant.get_unit_price(quantity)
                    unit_price = unit_price_money.amount if hasattr(unit_price_money, 'amount') else unit_price_money

                    variant.stock_quantity -= quantity
                    variant.save(update_fields=["stock_quantity"])

                    OrderLine.objects.create(
                        order=order,
                        variant=variant,
                        shop=variant.product.shop if hasattr(variant.product, 'shop') else None,
                        quantity=quantity,
                        unit_price=unit_price
                    )
                    total_price += Decimal(str(unit_price)) * quantity
                    if user and user.is_authenticated:
                        CartItem.objects.filter(user=user, variant=variant).delete()
                    continue

                if product_id:
                    try:
                        product = Products.objects.select_for_update().get(id=product_id)
                    except Products.DoesNotExist:
                        raise serializers.ValidationError(
                            {"product": f"Produit avec l'ID {product_id} introuvable."}
                        )

                    if product.variants.exists():
                        raise serializers.ValidationError(
                            {"product": "Ce produit a des variantes. Veuillez selectionner une variante."}
                        )

                    if product.stock_quantity is None:
                        raise serializers.ValidationError(
                            {"stock": "Stock indisponible pour ce produit."}
                        )

                    if product.stock_quantity < quantity:
                        raise serializers.ValidationError(
                            {"stock": f"Stock insuffisant pour le produit {product.name} "
                                      f"(disponible: {product.stock_quantity}, demande: {quantity})"}
                        )

                    if user and hasattr(product, 'shop') and product.shop:
                        if getattr(product.shop, 'owner_id', None) == user.id:
                            raise serializers.ValidationError(
                                {"product": "Vous ne pouvez pas commander un produit de votre propre boutique."}
                            )

                    unit_price_money = product.get_unit_price(quantity)
                    unit_price = unit_price_money.amount if hasattr(unit_price_money, 'amount') else unit_price_money

                    product.stock_quantity -= quantity
                    product.save(update_fields=["stock_quantity"])

                    OrderLine.objects.create(
                        order=order,
                        product=product,
                        shop=product.shop if hasattr(product, 'shop') else None,
                        quantity=quantity,
                        unit_price=unit_price
                    )
                    total_price += Decimal(str(unit_price)) * quantity
                    if user and user.is_authenticated:
                        CartItem.objects.filter(user=user, product=product).delete()

            coupon = None
            total_discount = requested_discount
            if coupon_code:
                try:
                    coupon_result = apply_coupon(
                        user=user,
                        coupon_code=coupon_code,
                        order_lines=order.order_lines.select_related("variant__product", "product").all(),
                        subtotal=total_price,
                        delivery_cost=Decimal('0.00'),
                    )
                except DjangoValidationError as exc:
                    if hasattr(exc, "message_dict"):
                        raise serializers.ValidationError(exc.message_dict)
                    message = exc.messages[0] if getattr(exc, "messages", None) else "Coupon invalide."
                    raise serializers.ValidationError({"coupon_code": message})

                coupon = coupon_result["coupon"]
                total_discount = Decimal(str(coupon_result["total_discount"]))

            if total_discount < Decimal("0.00"):
                total_discount = Decimal("0.00")
            if total_discount > total_price:
                total_discount = total_price

            try:
                from apps.shipping.services import calculate_shipping_cost
                shipping_result = calculate_shipping_cost(
                    order_lines=order.order_lines.all(),
                    destination_address=order.origin_address,
                    transport_mode=transport_mode,
                )
                delivery_cost = shipping_result['delivery_cost']
                is_international = shipping_result.get('is_international', False)
            except Exception:
                logger.error("Erreur calcul shipping pour commande %s: %s", order.order_number, exc_info=True)
                delivery_cost = Decimal('0.00')
                is_international = False

            if not is_international:
                transport_mode = 'road'
                shipping_method = shipping_method
            else:
                shipping_method = None

            total_amount = total_price - total_discount + delivery_cost
            if total_amount < Decimal("0.00"):
                total_amount = Decimal("0.00")

            order.delivery_cost = delivery_cost
            order.discount = total_discount
            order.total_amount = total_amount
            order.applied_coupon = coupon
            order.applied_coupon_code = coupon.code if coupon else None
            order.transport_mode = transport_mode
            order.shipping_method = shipping_method
            order.save(update_fields=[
                "delivery_cost", "discount", "total_amount",
                "applied_coupon", "applied_coupon_code",
                "transport_mode", "shipping_method",
            ])

            if coupon:
                coupon.uses += 1
                coupon.save(update_fields=["uses"])
                CouponUsage.objects.create(
                    coupon=coupon,
                    user=user,
                    order=order,
                    discount_amount=total_discount
                )

        try:
            create_notification_if_allowed(
                user=user,
                notification_type="order",
                title="Commande creee",
                message=f"Votre commande #{order.order_number} a ete enregistree.",
            )
        except Exception:
            # La creation de commande ne doit jamais etre bloquee par la notification.
            pass

        return order


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


class QuoteLineSerializer(serializers.ModelSerializer):
    negotiated_price = MoneyField(max_digits=15, decimal_places=2)
    product_name = serializers.SerializerMethodField()
    variant_sku = serializers.CharField(source='variant.sku', read_only=True)

    class Meta:
        model = QuoteLine
        fields = [
            'id',
            'product',
            'product_name',
            'variant',
            'variant_sku',
            'quantity',
            'negotiated_price',
            'remarks',
        ]

    def get_product_name(self, obj):
        if obj.product:
            return obj.product.name
        if obj.variant and obj.variant.product:
            return obj.variant.product.name
        return None

    def validate(self, attrs):
        product = attrs.get('product') or getattr(self.instance, 'product', None)
        variant = attrs.get('variant') or getattr(self.instance, 'variant', None)
        if bool(product) == bool(variant):
            raise serializers.ValidationError("Fournissez soit 'product', soit 'variant'.")
        return attrs


class QuoteSerializer(serializers.ModelSerializer):
    lines = QuoteLineSerializer(many=True)

    class Meta:
        model = Quote
        fields = [
            'id',
            'user',
            'shop',
            'status',
            'expires_at',
            'accepted_at',
            'payment_link_token',
            'payment_link_expires_at',
            'payment_link_sent_at',
            'converted_order',
            'created_at',
            'updated_at',
            'lines',
        ]
        read_only_fields = [
            'user',
            'status',
            'accepted_at',
            'payment_link_token',
            'payment_link_expires_at',
            'payment_link_sent_at',
            'converted_order',
            'created_at',
            'updated_at',
        ]

    def validate_expires_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("expires_at doit etre dans le futur.")
        return value

    def validate(self, attrs):
        shop = attrs.get('shop') or getattr(self.instance, 'shop', None)
        lines = attrs.get('lines')
        if self.instance is not None and 'shop' in attrs and attrs['shop'].id != self.instance.shop_id:
            raise serializers.ValidationError({"shop": "La boutique d'une quote ne peut pas etre modifiee."})
        if lines is None and self.instance is not None:
            return attrs
        if not lines:
            raise serializers.ValidationError({"lines": "Au moins une ligne est requise."})

        for line in lines:
            product = line.get('product')
            variant = line.get('variant')
            if bool(product) == bool(variant):
                raise serializers.ValidationError(
                    {"lines": "Chaque ligne doit contenir soit 'product', soit 'variant'."}
                )

            product_obj = product or (variant.product if variant else None)
            if shop and product_obj and product_obj.shop_id != shop.id:
                raise serializers.ValidationError(
                    {"lines": "Toutes les lignes doivent appartenir a la boutique selectionnee."}
                )

            quantity = line.get('quantity') or 0
            if quantity <= 0:
                raise serializers.ValidationError(
                    {"lines": "La quantite doit etre strictement superieure a 0."}
                )
        return attrs

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        quote = Quote.objects.create(**validated_data)
        for line_data in lines_data:
            QuoteLine.objects.create(quote=quote, **line_data)
        return quote

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                QuoteLine.objects.create(quote=instance, **line_data)
        return instance


class ReturnItemCreateSerializer(serializers.Serializer):
    order_line_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)


class ReturnRequestCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=ReturnRequest.REASON_CHOICES)
    description = serializers.CharField(required=False, allow_blank=True)
    items = ReturnItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Au moins un article est requis.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None

        try:
            order = Orders.objects.get(id=attrs['order_id'])
        except Orders.DoesNotExist:
            raise serializers.ValidationError({"order_id": "Commande introuvable."})

        if order.customer_id != user.id:
            raise serializers.ValidationError({"order_id": "Cette commande ne vous appartient pas."})

        if order.status not in ('delivered', 'in_transit'):
            raise serializers.ValidationError({"order_id": "Seules les commandes livrées ou en transit peuvent faire l'objet d'un retour."})

        if ReturnRequest.objects.filter(order=order, status__in=('pending', 'approved', 'shipped_back')).exists():
            raise serializers.ValidationError({"order_id": "Un retour est déjà en cours pour cette commande."})

        attrs['order'] = order

        for item in attrs['items']:
            try:
                order_line = OrderLine.objects.get(id=item['order_line_id'], order=order)
            except OrderLine.DoesNotExist:
                raise serializers.ValidationError(
                    {"items": f"Ligne de commande {item['order_line_id']} introuvable."}
                )
            if item['quantity'] > order_line.quantity:
                raise serializers.ValidationError(
                    {"items": f"Quantité demandée ({item['quantity']}) supérieure à la quantité commandée ({order_line.quantity})."}
                )
            item['order_line'] = order_line

        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = validated_data.pop('order')

        with transaction.atomic():
            return_request = ReturnRequest.objects.create(
                order=order,
                reason=validated_data['reason'],
                description=validated_data.get('description', ''),
            )

            for item in items_data:
                ReturnItem.objects.create(
                    return_request=return_request,
                    order_line=item['order_line'],
                    quantity=item['quantity'],
                    reason=item.get('reason', ''),
                    description=item.get('description', ''),
                )

        return return_request


class ReturnItemSerializer(serializers.ModelSerializer):
    refund_amount = serializers.ReadOnlyField()
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = ReturnItem
        fields = ['id', 'order_line', 'product_name', 'quantity', 'reason', 'description', 'refund_amount']

    def get_product_name(self, obj):
        if obj.order_line.variant:
            return obj.order_line.variant.product.name
        if obj.order_line.product:
            return obj.order_line.product.name
        return None


class ReturnRequestSerializer(serializers.ModelSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)
    total_refund_amount = serializers.ReadOnlyField()
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = ReturnRequest
        fields = [
            'id', 'order', 'order_number', 'status', 'reason', 'description',
            'staff_note', 'items', 'total_refund_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'staff_note']


class RefundSerializer(serializers.ModelSerializer):
    processed_by_name = serializers.CharField(source='processed_by.email', read_only=True, default=None)

    class Meta:
        model = Refund
        fields = [
            'id', 'return_request', 'order', 'amount', 'method',
            'status', 'reference_number', 'processed_by', 'processed_by_name',
            'created_at', 'processed_at',
        ]
        read_only_fields = ['status', 'reference_number', 'processed_by', 'processed_at']
