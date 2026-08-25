import logging

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from rest_framework import serializers

from djmoney.contrib.django_rest_framework.fields import MoneyField

from apps.accounts.models import Address
from apps.coupons.models import CouponUsage
from apps.coupons.service import apply_coupon
from apps.notifications.notifications import create_notification_if_allowed
from apps.carts.models import CartItem
from apps.products.models import ProductVariant, Products
from apps.shipping.services import calculate_shipping_cost

from ..models import OrderLine, Orders
from .returns import ReturnRequestSerializer

logger = logging.getLogger(__name__)


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
    return_requests = serializers.SerializerMethodField()

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
            'customer_note', 'carrier_name', 'tracking_number', 'tracking_url',
            'shipping_date', 'estimated_delivery_date', 'delivery_notes',
            'order_lines', 'return_requests'
        ]
        read_only_fields = [
            'customer', 'order_number', 'status', 'payment_status',
            'customer_note', 'carrier_name', 'tracking_number', 'tracking_url',
            'shipping_date', 'estimated_delivery_date', 'delivery_notes',
        ]

    # Mémoïse les lignes filtrées par boutique sur l'instance (clé par contexte) :
    # une seule requête par commande au lieu d'une par champ calculé.
    def _get_filtered_lignes(self, obj):
        shop_id = self.context.get('shop_id')
        shop_ids = tuple(sorted(self.context.get('shop_ids') or ()))
        cache = getattr(obj, '_filtered_lignes_cache', None)
        if cache is None:
            cache = {}
            obj._filtered_lignes_cache = cache
        key = (shop_id, shop_ids)
        if key not in cache:
            lines = obj.order_lines.all()
            if shop_id:
                lines = lines.filter(shop_id=shop_id)
            elif shop_ids:
                lines = lines.filter(shop_id__in=shop_ids)
            cache[key] = list(lines.select_related("variant__product"))
        return cache[key]

    def _get_preview_line(self, obj):
        lines = self._get_filtered_lignes(obj)
        return lines[0] if lines else None

    def get_preview_image_url(self, obj):
        request = self.context.get("request")
        first_line = self._get_preview_line(obj)

        if first_line:
            if first_line.variant and first_line.variant.product.image:
                return request.build_absolute_uri(first_line.variant.product.image.url)
            if first_line.product and first_line.product.image:
                return request.build_absolute_uri(first_line.product.image.url)
        return None

    def get_preview_product_name(self, obj):
        first_line = self._get_preview_line(obj)
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

    def get_total_amount(self, obj):
        # Pour le contexte vendeur (shop_id/shop_ids), retourner le montant des lignes filtrées.
        if self.context.get('shop_id') or self.context.get('shop_ids'):
            lines = self._get_filtered_lignes(obj)
            return sum((line.total_price for line in lines), Decimal('0.00'))
        return float(obj.total_amount.amount)

    def get_order_lines(self, obj):
        return OrderLineSerializer(
            self._get_filtered_lignes(obj), many=True, context=self.context
        ).data

    def get_return_requests(self, obj):
        requests = obj.return_requests.select_related('order').prefetch_related(
            'items__order_line__variant__product', 'items__order_line__product'
        )
        return ReturnRequestSerializer(requests, many=True, context=self.context).data


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
