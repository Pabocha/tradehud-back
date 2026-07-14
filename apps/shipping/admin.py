from django.contrib import admin
from .models import ShippingZone, ShippingRate


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'description']


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ['zone', 'shop', 'method', 'base_price', 'free_shipping_threshold', 'is_active']
    list_filter = ['zone', 'method', 'is_active']
    search_fields = ['zone__name']
