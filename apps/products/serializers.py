from rest_framework import serializers
from .models import *
from django.db.models import Avg, Count
from djmoney.contrib.django_rest_framework.fields import MoneyField
from apps.categories.models import Categories, CategoryAttribute
from apps.comments.models import Ratings
from django.utils import timezone
import json
from taggit.serializers import TagListSerializerField
from .documents import ProductDocument
from ecommerce.validators import validate_image_file


class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colors
        fields = ['id', 'name', 'code_hex']


class ProductPriceTierSerializer(serializers.ModelSerializer):
    """Serializer pour les paliers de prix (ProductPriceTier)"""
    price = MoneyField(max_digits=15, decimal_places=2)
    
    class Meta:
        model = ProductPriceTier
        fields = ['id', 'product', 'min_quantity', 'max_quantity', 'price']
        read_only_fields = ['id', 'product']  # Le produit est assigné automatiquement
    
    def create(self, validated_data):
        """Assigne le produit depuis le contexte"""
        product = self.context.get('product')
        if not product:
            raise serializers.ValidationError("Product context is required.")
        validated_data['product'] = product
        return super().create(validated_data)


class ProductPromotionSerializer(serializers.ModelSerializer):
    """Serializer pour les promotions de produit (ProductPromotion)."""
    promo_price = MoneyField(max_digits=15, decimal_places=2)

    class Meta:
        model = ProductPromotion
        fields = ['id', 'product', 'promo_price', 'start_at', 'end_at', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'product', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        product = self.context.get('product') or getattr(instance, 'product', None)
        start_at = attrs.get('start_at') or getattr(instance, 'start_at', None)
        end_at = attrs.get('end_at') or getattr(instance, 'end_at', None)
        promo_price = attrs.get('promo_price') or getattr(instance, 'promo_price', None)

        if not product:
            raise serializers.ValidationError("Product context is required.")

        if start_at and end_at and start_at >= end_at:
            raise serializers.ValidationError({"end_at": "end_at doit etre apres start_at."})

        if start_at and end_at and end_at <= timezone.now():
            raise serializers.ValidationError({"end_at": "end_at doit etre dans le futur."})

        if promo_price and product.base_price and promo_price >= product.base_price:
            raise serializers.ValidationError({"promo_price": "Le prix promo doit etre inferieur au prix de base."})

        return attrs

    def create(self, validated_data):
        product = self.context.get('product')
        if not product:
            raise serializers.ValidationError("Product context is required.")
        validated_data['product'] = product
        return super().create(validated_data)



class AttributeValueSerializer(serializers.ModelSerializer):
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    attribute_code = serializers.CharField(source="attribute.code", read_only=True)
    attribute_id = serializers.IntegerField(source="attribute.id", read_only=True)

    class Meta:
        model = AttributeValue
        fields = [
            "id",
            "attribute_id",
            "attribute_code",
            "attribute_name",
            "value",
            "code",
            "hex_color",
        ]


class ProductVariantSerializer(serializers.ModelSerializer):
    """Serializer pour ProductVariant (nested dans Product CRUD)."""
    attributes = AttributeValueSerializer(many=True, read_only=True)
    attribute_value_ids = serializers.PrimaryKeyRelatedField(
        queryset=AttributeValue.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    custom_attributes = serializers.JSONField(required=False)
    price_override = MoneyField(max_digits=15, decimal_places=2, required=False)

    class Meta: 
        model = ProductVariant
        fields = [
            'id',
            'sku',
            'weight',
            'price_override',
            'stock_quantity',
            'attributes',
            'attribute_value_ids',
            'custom_attributes',
        ]
        read_only_fields = ['id', 'sku']

    def create(self, validated_data):
        attrs = validated_data.pop('attributes', [])
        attr_ids = validated_data.pop('attribute_value_ids', [])
        if attr_ids:
            attrs = list(attr_ids)
        if not attrs:
            raise serializers.ValidationError("Chaque variante doit avoir au moins un attribut.")
        product = validated_data.pop('product', None)
        # product must be provided by parent serializer via context or passed data
        variant = ProductVariant.objects.create(**validated_data, product=product)
        if attrs:
            variant.attributes.set(attrs)
        return variant

    def update(self, instance, validated_data):
        attrs = validated_data.pop('attributes', None)
        attr_ids = validated_data.pop('attribute_value_ids', None)
        if attr_ids is not None:
            attrs = list(attr_ids)
        if attrs is not None and len(attrs) == 0:
            raise serializers.ValidationError("Chaque variante doit avoir au moins un attribut.")
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if attrs is not None:
            instance.attributes.set(attrs)
        return instance


class VariantTreeSerializer(serializers.Serializer):
    """
    Entrée dynamique imbriquée pour créer des variantes.
    Exemple:
    {
      "structure": ["color", "size"],
      "variants": [
        {"value": "Rouge", "children": [{"value": "M", "stock": 5}, {"value": "XL", "stock": 2}]}
      ]
    }
    """
    structure = serializers.ListField(child=serializers.JSONField(), required=True)
    variants = serializers.ListField(child=serializers.JSONField(), required=True)

    def _resolve_attribute(self, raw):
        if raw is None or raw == '':
            raise serializers.ValidationError("Attribut manquant.")
        if isinstance(raw, dict):
            if 'id' in raw:
                qs = Attribute.objects.filter(id=raw['id'])
            elif 'code' in raw:
                qs = Attribute.objects.filter(code__iexact=raw['code'])
            elif 'name' in raw:
                qs = Attribute.objects.filter(name__iexact=raw['name'])
            else:
                raise serializers.ValidationError("Format d'attribut invalide.")
        elif isinstance(raw, int):
            qs = Attribute.objects.filter(id=raw)
        elif isinstance(raw, str):
            qs = Attribute.objects.filter(code__iexact=raw)
            if not qs.exists():
                qs = Attribute.objects.filter(name__iexact=raw)
        else:
            raise serializers.ValidationError("Format d'attribut invalide.")

        attribute = qs.first()
        if not attribute:
            raise serializers.ValidationError("Attribut introuvable.")
        return attribute

    def _resolve_attribute_value(self, attribute, raw):
        if raw is None or raw == '':
            raise serializers.ValidationError("Valeur d'attribut manquante.")
        if isinstance(raw, dict):
            if 'id' in raw:
                qs = AttributeValue.objects.filter(id=raw['id'], attribute=attribute)
            elif 'code' in raw:
                qs = AttributeValue.objects.filter(code__iexact=raw['code'], attribute=attribute)
            elif 'value' in raw:
                qs = AttributeValue.objects.filter(value__iexact=raw['value'], attribute=attribute)
            else:
                raise serializers.ValidationError("Format de valeur d'attribut invalide.")
        elif isinstance(raw, int):
            qs = AttributeValue.objects.filter(id=raw, attribute=attribute)
        elif isinstance(raw, str):
            qs = AttributeValue.objects.filter(code__iexact=raw, attribute=attribute)
            if not qs.exists():
                qs = AttributeValue.objects.filter(value__iexact=raw, attribute=attribute)
        else:
            raise serializers.ValidationError("Format de valeur d'attribut invalide.")

        value = qs.first()
        if not value:
            raise serializers.ValidationError(
                f"Valeur d'attribut introuvable pour '{attribute.name}'."
            )
        return value

    def validate(self, attrs):
        product = self.context.get('product')
        if not product:
            raise serializers.ValidationError("Product context is required.")

        structure = attrs.get('structure') or []
        if not structure:
            raise serializers.ValidationError("La structure des variantes est requise.")

        attributes = [self._resolve_attribute(a) for a in structure]
        attr_ids = [a.id for a in attributes]
        if len(set(attr_ids)) != len(attr_ids):
            raise serializers.ValidationError("La structure contient des attributs en doublon.")

        if product.category:
            allowed = set(
                CategoryAttribute.objects.filter(category=product.category)
                .values_list('attribute_id', flat=True)
            )
            if allowed:
                for a in attributes:
                    if a.id not in allowed:
                        raise serializers.ValidationError(
                            f"L'attribut '{a.name}' n'est pas autorisé pour cette catégorie."
                        )

        variants = attrs.get('variants') or []
        if not variants:
            raise serializers.ValidationError("Les variantes sont requises.")

        combinations = []
        seen = set()

        def walk(nodes, depth, current_values):
            if not isinstance(nodes, list):
                raise serializers.ValidationError("Le champ 'variants' doit être une liste.")
            if depth >= len(attributes):
                raise serializers.ValidationError("Structure de variantes invalide.")

            attribute = attributes[depth]
            for node in nodes:
                if not isinstance(node, dict):
                    raise serializers.ValidationError("Format de variante invalide.")

                value_raw = node.get('value')
                value = self._resolve_attribute_value(attribute, value_raw)
                next_values = current_values + [value]

                children = node.get('children', [])
                is_leaf = depth == len(attributes) - 1

                if is_leaf:
                    if children:
                        raise serializers.ValidationError(
                            "Une feuille de variante ne doit pas contenir de sous-variantes."
                        )
                    stock = node.get('stock') if 'stock' in node else node.get('stock_quantity')
                    sku = node.get('sku')
                    weight = node.get('weight')
                    price_override = node.get('price_override')
                    custom_attributes = node.get('custom_attributes')

                    if stock is not None:
                        try:
                            stock = int(stock)
                        except (TypeError, ValueError):
                            raise serializers.ValidationError("Le stock doit être un entier.")
                        if stock < 0:
                            raise serializers.ValidationError("Le stock ne peut pas être négatif.")

                    key = tuple(v.id for v in next_values)
                    if key in seen:
                        raise serializers.ValidationError(
                            "Combinaison d'attributs en doublon dans la requête."
                        )
                    seen.add(key)

                    combinations.append({
                        'attribute_values': next_values,
                        'stock_quantity': stock,
                        'sku': sku,
                        'weight': weight,
                        'price_override': price_override,
                        'custom_attributes': custom_attributes,
                    })
                else:
                    if not children:
                        raise serializers.ValidationError(
                            "Chaque valeur doit avoir des sous-variantes."
                        )
                    walk(children, depth + 1, next_values)

        walk(variants, 0, [])

        attrs['resolved_attributes'] = attributes
        attrs['combinations'] = combinations
        return attrs


def compute_pricing_display(obj):
    """
    Synthétise la logique de prix pour le frontend.
    Priorité : promotion active > paliers > prix de base.
    """
    from django.utils.timezone import now

    base_price_amount = float(obj.base_price.amount)
    currency = str(obj.base_price.currency)

    # 1️⃣ Promotion active
    active_promo = obj.promotions.filter(
        is_active=True,
        start_at__lte=now(),
        end_at__gte=now()
    ).first()

    if active_promo:
        promo_price_amount = float(active_promo.promo_price.amount)
        return {
            'type': 'promo',
            'display_text': f'{int(round(promo_price_amount))} {currency}',
            'base_price': base_price_amount,
            'promo_price': promo_price_amount,
            'should_strike_base': True,
            'currency': currency,
            'promo_details': {
                'start_at': active_promo.start_at.isoformat(),
                'end_at': active_promo.end_at.isoformat()
            }
        }

    # 2️⃣ Paliers de prix
    price_tiers = obj.price_tiers.all().order_by('min_quantity')
    if price_tiers.exists():
        min_price = float(price_tiers.first().price.amount)
        max_price = float(price_tiers.last().price.amount)
        max_price = max(max_price, base_price_amount)

        return {
            'type': 'tiers',
            'display_text': f'{int(round(min_price))} - {int(round(max_price))} {currency}',
            'min_price': min_price,
            'max_price': max_price,
            'base_price': base_price_amount,
            'currency': currency,
            'tiers_count': price_tiers.count()
        }

    # 3️⃣ Prix de base
    return {
        'type': 'base',
        'display_text': f'{int(round(base_price_amount))} {currency}',
        'price': base_price_amount,
        'currency': currency
    }


class ProductSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_file])
    base_price = MoneyField(max_digits=15, decimal_places=2)
    country_origin = serializers.CharField(allow_blank=True, allow_null=True)
    tags = TagListSerializerField(required=False)
    category_name = serializers.CharField(source='category.name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    shop_is_verified = serializers.BooleanField(source='shop.is_verifted', read_only=True)
    category = serializers.PrimaryKeyRelatedField(
        queryset=Categories.objects.all(),
    )
    total_stock = serializers.IntegerField(read_only=True)
    attribute_display = serializers.SerializerMethodField()
    # ===== NOUVEAUX CHAMPS DE PRIX =====
    price_tiers = serializers.SerializerMethodField()
    active_promotions = serializers.SerializerMethodField()
    unit_price_for_quantity = serializers.SerializerMethodField()
    pricing_display = serializers.SerializerMethodField()
    # Variants read-only (créés via un endpoint dédié)
    variants = ProductVariantSerializer(many=True, read_only=True)

        
    def to_internal_value(self, data):

        # Nettoyage de data pour transformer les listes à un seul élément en simple valeur
        data = {
            key: value[0] if isinstance(value, list) and len(value) == 1 else value
            for key, value in data.items()
        }

        # Parser 'sizes' si c'est une chaîne JSON
        sizes = data.get('sizes')
        if sizes and isinstance(sizes, str):
            try:
                data['sizes'] = json.loads(sizes)
            except Exception:
                raise serializers.ValidationError({'sizes': 'Format JSON invalide.'})

        return super().to_internal_value(data)
    
    class Meta:
        model = Products
        fields = '__all__'
        # Exclude color_ids from being part of "__all__" output
        # extra_kwargs = {
        #     'color': {'read_only': True}
        # }

    def get_attribute_display(self, obj):
        raw = getattr(obj, 'attribute', None) or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        if not raw:
            return {}

        category = getattr(obj, 'category', None)
        fields_config = getattr(category, 'fields_config', None) or []
        if isinstance(fields_config, str):
            try:
                fields_config = json.loads(fields_config)
            except json.JSONDecodeError:
                fields_config = []

        name_to_label = {
            f['name']: f.get('label', f['name'])
            for f in fields_config
            if isinstance(f, dict) and 'name' in f
        }

        return {
            name_to_label.get(key, key): value
            for key, value in raw.items()
        }

    def get_price_tiers(self, obj):
        """Expose les paliers de prix disponibles pour le B2B"""
        tiers = obj.price_tiers.all().values('id', 'min_quantity', 'max_quantity', 'price')
        return [
            {   'id': tier['id'],
                'min_quantity': tier['min_quantity'],
                'max_quantity': tier['max_quantity'],
                'price': float(tier['price']) if tier['price'] else 0.0
            }
            for tier in tiers
        ]

    def get_active_promotions(self, obj):
        """Expose les promotions actives (valides à l'instant T)"""
        from django.utils.timezone import now
        promotions = obj.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now()
        ).values('promo_price', 'start_at', 'end_at')
        return [
            {
                'price': float(promo['promo_price']) if promo['promo_price'] else 0.0,
                'start_at': promo['start_at'].isoformat(),
                'end_at': promo['end_at'].isoformat()
            }
            for promo in promotions
        ]

    def get_unit_price_for_quantity(self, obj):
        """
        Retourne le prix unitaire pour une quantité donnée.
        Utilise le query param 'quantity' si disponible, sinon défaut 1.
        """
        request = self.context.get('request')
        quantity = 1
        if request and request.query_params.get('quantity'):
            try:
                quantity = int(request.query_params.get('quantity'))
            except (ValueError, TypeError):
                quantity = 1
        
        unit_price = obj.get_unit_price(quantity)
        return {
            'quantity': quantity,
            'unit_price': float(unit_price.amount),
            'currency': str(unit_price.currency)
        }

    def get_pricing_display(self, obj):
        """Synthétise la logique de prix pour le frontend (voir compute_pricing_display)."""
        return compute_pricing_display(obj)

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])

        instance = super().create(validated_data)
        if tags:
            # Si tags est une chaîne (string), on split, sinon on garde la liste
            if isinstance(tags, str):
                tag_list = [tag.strip() for tag in tags.split(',')]
            else:
                tag_list = tags
            instance.tags.set(tag_list)  # ✅ Bon
        return instance

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)

        instance = super().update(instance, validated_data)
        if tags is not None:
            if isinstance(tags, str):
                tag_list = [tag.strip() for tag in tags.split(',')]
            else:
                tag_list = tags
            instance.tags.set(tag_list)
        return instance


def build_variant_tree(product):
    """Reconstruit un arbre de variantes à partir des variantes plates et de variant_structure."""
    structure = product.variant_structure or []
    if not structure:
        return None

    attr_codes = []
    for item in structure:
        if isinstance(item, dict):
            code = item.get('code')
            if code:
                attr_codes.append(code)
        elif isinstance(item, str):
            attr_codes.append(item)

    if not attr_codes:
        return None

    def pick_value(variant, code):
        for av in variant.attributes.all():
            if av.attribute.code == code:
                return av
        return None

    def add_to_tree(tree, values, leaf_payload):
        current = tree
        for idx, val in enumerate(values):
            if val is None:
                return
            key = val.value
            if idx == len(values) - 1:
                current.setdefault(key, []).append(leaf_payload)
            else:
                current = current.setdefault(key, {})

    tree = {}
    variants = product.variants.prefetch_related('attributes__attribute').all()
    for variant in variants:
        values = [pick_value(variant, code) for code in attr_codes]
        leaf_payload = {
            'id': variant.id,
            'sku': variant.sku,
            'stock': variant.stock_quantity,
            'weight': variant.weight,
            'price_override': (
                float(variant.price_override.amount) if variant.price_override else None
            ),
            'price_override_currency': (
                str(variant.price_override.currency) if variant.price_override else None
            ),
            'custom_attributes': variant.custom_attributes,
            'attributes': AttributeValueSerializer(variant.attributes.all(), many=True).data,
        }
        add_to_tree(tree, values, leaf_payload)

    def build_nodes(level, depth=0):
        nodes = []
        if depth >= len(attr_codes):
            return nodes
        for key, child in level.items():
            node = {'value': key}
            if depth == len(attr_codes) - 1:
                node['children'] = child
            else:
                node['children'] = build_nodes(child, depth + 1)
            nodes.append(node)
        return nodes

    return {
        'structure': attr_codes,
        'variants': build_nodes(tree, 0)
    }
class GalerieImageSerializer(serializers.ModelSerializer):
    # Validate uploaded gallery image size/type
    image = serializers.ImageField(validators=[validate_image_file])

    class Meta:
        model = GalerieImages
        fields = '__all__'


class ProductGalleryImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = GalerieImages
        fields = ['image']


class ProductDetailSerializer(ProductSerializer):
    """Serializer pour le détail produit (lecture)."""
    variant_tree = serializers.SerializerMethodField()
    seller_id = serializers.IntegerField(source='shop.owner_id', read_only=True)
    galerie_images = ProductGalleryImageSerializer(many=True, read_only=True)
    review_summary = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = '__all__'

    def get_fields(self):
        fields = super().get_fields()
        fields.pop('variants', None)
        return fields

    def get_variant_tree(self, obj):
        return build_variant_tree(obj)

    def get_review_summary(self, obj):
        qs = Ratings.objects.filter(product=obj)
        aggregation = qs.aggregate(avg=Avg('rating'), total=Count('id'))
        total = aggregation['total'] or 0

        breakdown_rows = (
            qs.values('rating')
            .annotate(total=Count('id'))
            .order_by('rating')
        )
        breakdown = {int(row['rating']): row['total'] for row in breakdown_rows}

        return {
            'average_rating': round(float(aggregation['avg'] or 0), 2),
            'total_reviews': total,
            'ratings_breakdown': {
                '1': breakdown.get(1, 0),
                '2': breakdown.get(2, 0),
                '3': breakdown.get(3, 0),
                '4': breakdown.get(4, 0),
                '5': breakdown.get(5, 0),
            },
        }


class ProductListSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_file])
    base_price = MoneyField(max_digits=15, decimal_places=2)
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    shop_is_verified = serializers.BooleanField(source='shop.is_verifted', read_only=True)
    seller_id = serializers.IntegerField(source='shop.owner_id', read_only=True)
    has_variant = serializers.SerializerMethodField()
    pricing_display = serializers.SerializerMethodField()
    total_stock = serializers.IntegerField(read_only=True)
    country_origin = serializers.CharField(read_only=True)

    class Meta:
        model = Products
        fields = [
            'id',
            'name',
            'image',
            'base_price',
            'category',
            'category_name',
            'pricing_display',
            'total_stock',
            'stock_quantity',
            'min_order_quantity',
            'average_rating',
            'numbers_reviews',
            'is_sponsored',
            'has_variant',
            'shop',
            'shop_name',
            'shop_is_verified',
            'seller_id',
            'base_price_currency',
            'country_origin',
            'description',
        ]

    def get_pricing_display(self, obj):
        """Synthétise la logique de prix pour le frontend (voir compute_pricing_display)."""
        return compute_pricing_display(obj)

    def get_has_variant(self, obj):
        return obj.variants.exists()


class ProductListWithCountrySerializer(ProductListSerializer):
    country_origin = serializers.CharField(source='country_origin', read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ['country_origin']


class RecentlyViewedProductSerializer(serializers.ModelSerializer):
    product_detail = serializers.SerializerMethodField()

    class Meta:
        model = RecentlyViewedProduct
        fields = ['id', 'user', 'product', 'viewed_at', 'view_count', 'session_key', 'ip_address', 'product_detail']
        read_only_fields = ['user', 'viewed_at', 'view_count']

    def get_product_detail(self, obj):
        from apps.products.serializers import ProductSerializer
        return ProductSerializer(obj.product).data

class ProductPromotionListSerializer(ProductListSerializer):
    promotion_details = serializers.SerializerMethodField()
    remaining_time = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ['promotion_details', 'remaining_time']

    def get_promotion_details(self, obj):
        from django.utils.timezone import now
        promo = obj.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now()
        ).first()
        if not promo:
            return None
        return {
            'promo_price': float(promo.promo_price.amount),
            'start_at': promo.start_at.isoformat(),
            'end_at': promo.end_at.isoformat(),
        }

    def get_remaining_time(self, obj):
        from django.utils.timezone import now
        promo = obj.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now()
        ).first()
        if not promo:
            return None
        delta = promo.end_at - now()
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        return {
            'days': max(days, 0),
            'hours': max(hours, 0),
            'minutes': max(minutes, 0),
            'total_seconds': max(int(delta.total_seconds()), 0),
        }

class ColorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colors
        fields = '__all__'


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True, default=None)
    variant_sku = serializers.CharField(source='variant.sku', read_only=True, default=None)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'variant', 'product_name', 'variant_sku',
            'movement_type', 'quantity', 'previous_stock', 'new_stock',
            'reference_type', 'reference_id', 'note',
            'created_by', 'created_by_email', 'created_at',
        ]
        read_only_fields = ['id', 'previous_stock', 'new_stock', 'created_by', 'created_at']


class StockAdjustmentSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(help_text="Positif = entrée, négatif = sortie")
    movement_type = serializers.ChoiceField(
        choices=['restock', 'adjustment', 'return'],
        default='adjustment'
    )
    reference_id = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("La quantité ne peut pas être 0.")
        return value


class ProductComparisonSerializer(serializers.ModelSerializer):
    product_detail = serializers.SerializerMethodField()

    class Meta:
        model = ProductComparison
        fields = ['id', 'product', 'added_at', 'product_detail']
        read_only_fields = ['id', 'added_at']

    def get_product_detail(self, obj):
        return ProductListSerializer(obj.product, context=self.context).data

