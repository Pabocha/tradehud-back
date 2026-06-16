from rest_framework import serializers
from django.db.models import Avg, Count
from apps.categories.models import Categories
from apps.comments.models import ShopRatings
from apps.accounts.models import SellerAccount, ShopFollow
from apps.payments.models import PaymentMethod
from .models import Shops
from ecommerce.validators import validate_image_file
from apps.products.serializers import ProductSerializer
from apps.products.models import Products


class ShopSerializer(serializers.ModelSerializer):
    country_origin = serializers.SerializerMethodField() 
    categories = serializers.PrimaryKeyRelatedField(
        queryset=Categories.objects.all(),
        many=True,
    )

    def to_internal_value(self, data):
        # Convertir en dict normal (valeurs simples) au lieu de listes
        data = {key: value[0] if isinstance(value, list) and len(value) == 1 else value
                for key, value in data.items()}

        # Corriger le champ categories s’il est une string style "[8,10]"
        raw_categories = data.get('categories')
        if isinstance(raw_categories, str):
            try:
                # Nettoyer la chaîne pour obtenir une vraie liste d'entiers
                parsed = [int(x.strip()) for x in raw_categories.strip('[]').split(',') if x.strip().isdigit()]
                data['categories'] = parsed
            except Exception:
                raise serializers.ValidationError({
                    'categories': 'Format invalide. Utilise [1,2,3]'
                })

        return super().to_internal_value(data)


    class Meta:
        model = Shops
        fields = '__all__'
        read_only_fields = ['owner']

    def get_country_origin(self, obj):
        return str(obj.country_origin) 

# class ProductSerializer(serializers.ModelSerializer):
#     base_price = MoneyField(max_digits=15, decimal_places=2)
#     country_origin = serializers.SerializerMethodField()

#     def get_country_origin(self, obj):
#         return str(obj.country_origin) if obj.country_origin else None

#     class Meta:
#         model = Products
#         fields = '__all__'


class ShopListSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    country_origin = serializers.SerializerMethodField()

    def get_country_origin(self, obj):
        return str(obj.country_origin) if obj.country_origin else None

    class Meta:
        model = Shops
        fields = '__all__'

    def get_product(self, obj):
        request = self.context.get('request')
        raw_limit = request.query_params.get('products_per_shop', 5) if request else 5
        try:
            limit = max(1, min(int(raw_limit), 5))
        except (TypeError, ValueError):
            limit = 5
        products_qs = (
            Products.objects
            .with_total_stock()
            .filter(shop=obj)
            .select_related('shop', 'category')
            .prefetch_related('variants')[:limit]
        )
        return ProductSerializer(products_qs, many=True, context=self.context).data


class ShopUpdateSerializer(serializers.ModelSerializer):
    categories = serializers.PrimaryKeyRelatedField(
        queryset=Categories.objects.all(), many=True
    )
    logo = serializers.ImageField(required=False, validators=[validate_image_file])


    def to_internal_value(self, data):
        data = {key: value[0] if isinstance(value, list) and len(value) == 1 else value
                for key, value in data.items()}

        raw_categories = data.get('categories')
        if isinstance(raw_categories, str):
            try:
                parsed = [int(x.strip()) for x in raw_categories.strip('[]').split(',') if x.strip().isdigit()]
                data['categories'] = parsed
            except Exception:
                raise serializers.ValidationError({
                    'categories': 'Format invalide. Utilise [1,2,3]'
                })
        return super().to_internal_value(data)

    class Meta:
        model = Shops
        fields = [
            'id', 'name', 'email_contact', 'description', 'phone_number', 'address',
            'delivery_conditions', 'delivery_time_estimate', 'free_shipping',
            'return_policy', 'categories', 'payment_method', 'country_origin', 'logo'
        ]


class ShopOwnerPublicSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = SellerAccount
        fields = [
            'id',
            'company_name',
            'phone_number',
            'email_contact',
            'address',
            'status',
            'date_created',
            'user',
        ]

    def get_user(self, obj):
        if not obj.user:
            return None
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email,
        }


class ShopCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Categories
        fields = ['id', 'name', 'description', 'image', 'category_type']


class ShopPaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = ['id', 'name', 'value', 'image']


class ShopRatingPublicSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    order_id = serializers.IntegerField(source='order.id', read_only=True)

    class Meta:
        model = ShopRatings
        fields = [
            'id',
            'rating',
            'comment',
            'is_edited',
            'date_added',
            'date_updated',
            'order_id',
            'user',
        ]

    def get_user(self, obj):
        if not obj.user:
            return None
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
        }


class ShopPublicDetailSerializer(serializers.ModelSerializer):
    country_origin = serializers.SerializerMethodField()
    categories_details = ShopCategorySerializer(source='categories', many=True, read_only=True)
    reviews = serializers.SerializerMethodField()
    latest_statistics = serializers.SerializerMethodField()
    review_summary = serializers.SerializerMethodField()
    total_followers = serializers.SerializerMethodField()

    class Meta:
        model = Shops
        fields = [
            'id',
            'name',
            'email_contact',
            'description',
            'phone_number',
            'country_origin',
            'address',
            'logo',
            'date_created',
            'status',
            'delivery_conditions',
            'delivery_time_estimate',
            'free_shipping',
            'return_policy',
            'total_products',
            'total_orders',
            'average_rating',
            'number_of_reviews',
            'total_follow',
            'number_sale',
            'is_top_seller',
            'is_verifted',
            'verified_at',
            'categories_details',
            'total_followers',
            'review_summary',
            'reviews',
            'latest_statistics',
        ]

    def get_country_origin(self, obj):
        return str(obj.country_origin) if obj.country_origin else None

    def get_reviews(self, obj):
        request = self.context.get('request')
        raw_limit = request.query_params.get('reviews_limit', 10) if request else 10
        try:
            limit = max(1, min(int(raw_limit), 50))
        except (TypeError, ValueError):
            limit = 10

        queryset = (
            ShopRatings.objects.filter(shop=obj)
            .select_related('user', 'order')
            .order_by('-date_added')[:limit]
        )
        return ShopRatingPublicSerializer(queryset, many=True, context=self.context).data

    def get_latest_statistics(self, obj):
        stats = obj.statistics.order_by('-date').first()
        if not stats:
            return None
        return {
            'date': stats.date,
            'total_orders': stats.total_orders,
            'total_revenue': stats.total_revenue,
            'products_sold': stats.products_sold,
            'average_order_value': stats.average_order_value,
            'shop_average_rating': stats.shop_average_rating,
            'shop_number_of_reviews': stats.shop_number_of_reviews,
            'products_low_stock': stats.products_low_stock,
            'products_out_of_stock': stats.products_out_of_stock,
            'active_sponsored_products': stats.active_sponsored_products,
            'total_product_views': stats.total_product_views,
        }

    def get_review_summary(self, obj):
        qs = ShopRatings.objects.filter(shop=obj)
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

    def get_total_followers(self, obj):
        return ShopFollow.objects.filter(shop=obj).count()
