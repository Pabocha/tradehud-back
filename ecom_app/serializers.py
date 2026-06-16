from rest_framework import serializers 
from .models import PayementMethod, Favorites, Coupon, Banner, Notifications
from produits.models import Products
from djmoney.contrib.django_rest_framework.fields import MoneyField
from django.utils.timezone import now

class PaymentMethodSerializer(serializers.ModelSerializer):

    class Meta:
        model = PayementMethod
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    base_price = MoneyField(max_digits=15, decimal_places=2)
    seller_id = serializers.IntegerField(source='shop.owner_id', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    pricing_display = serializers.SerializerMethodField()

    class Meta:
        model = Products
        fields = [
            'id',
            'name',
            'base_price',
            'base_price_currency',
            'image',
            'stock_quantity',
            'status',
            'shop',
            'shop_name',
            'seller_id',
            'min_order_quantity',
            'pricing_display',
        ]

    def get_pricing_display(self, obj):
        base_price_amount = float(obj.base_price.amount)
        currency = str(obj.base_price.currency)

        active_promo = obj.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now(),
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
                    'end_at': active_promo.end_at.isoformat(),
                }
            }

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
                'tiers_count': price_tiers.count(),
            }

        return {
            'type': 'base',
            'display_text': f'{int(round(base_price_amount))} {currency}',
            'price': base_price_amount,
            'currency': currency,
        }

class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    class Meta:
        model = Favorites
        fields = ['id', 'added_at', 'product'] 

class CouponSerializer(serializers.ModelSerializer):
    users = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    target_categories = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    target_products = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    target_shops = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'description', 'discount_type', 'discount_value',
            'min_order_amount', 'start_date', 'end_date',
            'applicable_to_shipping', 'scope', 'audience', 'shipping_discount_type',
            'shipping_discount_value', 'shipping_discount_percent',
            'max_uses', 'uses',
            'users', 'target_categories', 'target_products', 'target_shops'
        ]

class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notifications
        fields = '__all__'
