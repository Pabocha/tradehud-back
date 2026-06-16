from rest_framework import serializers
from .models import CartItem
from produits.models import ProductVariant
from djmoney.money import Money


class CartItemSerializer(serializers.ModelSerializer):
    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    variant_attributes = serializers.SerializerMethodField()
    product_name = serializers.SerializerMethodField()
    product_base_price = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
    product_brand = serializers.SerializerMethodField()
    product_status = serializers.SerializerMethodField()
    product_description = serializers.SerializerMethodField()
    product_currency = serializers.SerializerMethodField()
    product_min_order_quantity = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()
    price_tiers = serializers.SerializerMethodField()
    active_promotions = serializers.SerializerMethodField()
    is_variant_item = serializers.SerializerMethodField()
    available_stock = serializers.SerializerMethodField()
    is_out_of_stock = serializers.SerializerMethodField()
    can_fulfill_requested_quantity = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id',
            'user',
            'variant',
            'product',
            'variant_sku',
            'variant_attributes',
            'product_name',
            'quantity',
            'product_base_price',
            'unit_price',
            'product_image',
            'product_brand',
            'product_status',
            'product_min_order_quantity',
            'product_description',
            'product_currency',
            'line_total',
            'price_tiers',
            'active_promotions',
            'is_variant_item',
            'available_stock',
            'is_out_of_stock',
            'can_fulfill_requested_quantity',
        ]
        read_only_fields = ['user', 'unit_price']
        extra_kwargs = {
            'variant': {'required': False, 'allow_null': True},
            'product': {'required': False, 'allow_null': True},
        }

    def validate(self, attrs):
        variant = attrs.get('variant')
        product = attrs.get('product')
        request = self.context.get('request')
        user = request.user if request else None

        if not variant and not product:
            raise serializers.ValidationError("Vous devez fournir soit 'variant', soit 'product'.")
        if variant and product:
            raise serializers.ValidationError("Fournissez seulement 'variant' ou 'product', pas les deux.")

        if user and user.is_authenticated:
            if variant and variant.product and variant.product.shop:
                if getattr(variant.product.shop, 'owner_id', None) == user.id:
                    raise serializers.ValidationError(
                        "Vous ne pouvez pas ajouter votre propre produit au panier."
                    )
            if product and product.shop:
                if getattr(product.shop, 'owner_id', None) == user.id:
                    raise serializers.ValidationError(
                        "Vous ne pouvez pas ajouter votre propre produit au panier."
                    )

        if product and product.variants.exists():
            raise serializers.ValidationError(
                "Ce produit a des variantes. Veuillez sélectionner une variante."
            )
        return attrs

    def _get_product(self, obj):
        if obj.variant:
            return obj.variant.product
        return obj.product

    def get_product_name(self, obj):
        product = self._get_product(obj)
        return product.name if product else None
    
    def get_product_min_order_quantity(self, obj):
        product = self._get_product(obj)
        return product.min_order_quantity if product else 1

    def get_product_base_price(self, obj):
        """Retourne le prix de base du produit"""
        try:
            product = self._get_product(obj)
            return float(product.base_price.amount) if product else 0.0
        except:
            return 0.0

    def get_unit_price(self, obj):
        """Retourne le prix unitaire FIGÉ du panier (ou calcule si absent)"""
        if obj.unit_price:
            return float(obj.unit_price.amount)
        # Fallback: calculer à partir du variant
        current = obj.get_current_price()
        if hasattr(current, 'amount'):
            return float(current.amount)
        try:
            return float(current)
        except Exception:
            return 0.0

    def get_product_currency(self, obj):
        """Retourne la devise"""
        try:
            product = self._get_product(obj)
            return str(product.base_price.currency) if product else "XOF"
        except:
            return "XOF"

    def get_line_total(self, obj):
        """Calcule le total de la ligne: unit_price * quantity"""
        try:
            if obj.unit_price:
                unit_price = float(obj.unit_price.amount)
            else:
                current = obj.get_current_price()
                unit_price = float(current.amount) if hasattr(current, 'amount') else float(current)
            return unit_price * obj.quantity
        except:
            return 0.0

    def get_price_tiers(self, obj):
        """Expose les paliers de prix disponibles du variant"""
        product = self._get_product(obj)
        if not product:
            return []
        tiers = product.price_tiers.all().values('min_quantity', 'max_quantity', 'price')
        return [
            {
                'min_quantity': tier['min_quantity'],
                'max_quantity': tier['max_quantity'],
                'price': float(tier['price']) if tier['price'] else 0.0
            }
            for tier in tiers
        ]

    def get_active_promotions(self, obj):
        """Expose les promotions actives du variant"""
        from django.utils.timezone import now
        product = self._get_product(obj)
        if not product:
            return []
        promotions = product.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now()
        ).values('promo_price', 'start_at', 'end_at')
        return [
            {
                'price': float(promo['promo_price']) if promo['promo_price'] else 0.0,
                'start_at': promo['start_at'],
                'end_at': promo['end_at']
            }
            for promo in promotions
        ]

    def get_variant_attributes(self, obj):
        if not obj.variant:
            return []
        attrs = obj.variant.attributes.all()
        return [
            {'id': a.id, 'attribute': a.attribute.name, 'value': a.value}
            for a in attrs
        ]

    def get_product_image(self, obj):
        product = self._get_product(obj)
        if not product or not product.image:
            return None
        try:
            request = self.context.get('request')
            url = product.image.url
            if request:
                return request.build_absolute_uri(url)
            return url
        except Exception:
            return None

    def get_product_brand(self, obj):
        product = self._get_product(obj)
        return product.brand if product else None

    def get_product_status(self, obj):
        product = self._get_product(obj)
        return product.status if product else None

    def get_product_description(self, obj):
        product = self._get_product(obj)
        return product.description if product else None

    def get_is_variant_item(self, obj):
        return obj.variant is not None

    def _resolve_available_stock(self, obj):
        """
        Retourne le stock disponible pertinent pour l'item du panier.
        - Si variante: stock de la variante.
        - Si produit simple: stock du produit.
        """
        if obj.variant:
            return int(obj.variant.stock_quantity or 0)
        if obj.product:
            return int(obj.product.stock_quantity or 0)
        return 0

    def get_available_stock(self, obj):
        return self._resolve_available_stock(obj)

    def get_is_out_of_stock(self, obj):
        return self._resolve_available_stock(obj) <= 0

    def get_can_fulfill_requested_quantity(self, obj):
        return self._resolve_available_stock(obj) >= int(obj.quantity or 0)
