from rest_framework import serializers
from .models import Coupon

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