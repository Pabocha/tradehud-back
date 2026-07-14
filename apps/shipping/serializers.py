from rest_framework import serializers
from .models import ShippingZone, ShippingRate


class ShippingZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingZone
        fields = ['id', 'name', 'description', 'countries', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class ShippingRateSerializer(serializers.ModelSerializer):
    zone_name = serializers.CharField(source='zone.name', read_only=True)
    shop_name = serializers.CharField(source='shop.name', read_only=True, default=None)

    class Meta:
        model = ShippingRate
        fields = [
            'id', 'zone', 'zone_name', 'shop', 'shop_name', 'method',
            'base_price', 'price_per_kg', 'free_shipping_threshold',
            'min_delivery_days', 'max_delivery_days', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class ShippingEstimateSerializer(serializers.Serializer):
    address_id = serializers.IntegerField()
    shipping_method = serializers.ChoiceField(choices=['standard', 'express', 'pickup'], default='standard')
    subtotal = serializers.DecimalField(max_digits=15, decimal_places=2, required=False)
