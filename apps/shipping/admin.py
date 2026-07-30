from django.contrib import admin
from .models import ShippingZone, Warehouse, PackageSize, ShippingPricing, ShippingRate


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'has_port', 'priority', 'is_active', 'created_at']
    list_filter = ['is_active', 'has_port']
    search_fields = ['name', 'description']
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Géographie', {
            'fields': ('countries', 'cities', 'has_port', 'priority'),
            'description': "countries: liste de codes ISO (ex: ['SN', 'ML']). cities: liste de villes (ex: ['Dakar', 'Thiès'])"
        }),
    )


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'zone', 'country', 'city', 'is_active']
    list_filter = ['is_active', 'country']
    search_fields = ['name', 'city']


@admin.register(PackageSize)
class PackageSizeAdmin(admin.ModelAdmin):
    list_display = [
        'display_name', 'name', 'max_weight_kg',
        'max_length_cm', 'max_width_cm', 'max_height_cm',
        'display_order',
    ]
    ordering = ['display_order']


@admin.register(ShippingPricing)
class ShippingPricingAdmin(admin.ModelAdmin):
    list_display = [
        'origin_zone', 'destination_zone', 'package_size',
        'transport_mode', 'base_price', 'price_per_kg',
        'estimated_days_min', 'estimated_days_max', 'is_active',
    ]
    list_filter = ['transport_mode', 'is_active', 'origin_zone', 'destination_zone']
    search_fields = ['origin_zone__name', 'destination_zone__name']
    raw_id_fields = ['origin_zone', 'destination_zone', 'package_size']


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ['zone', 'shop', 'method', 'base_price', 'free_shipping_threshold', 'is_active']
    list_filter = ['zone', 'method', 'is_active']
    search_fields = ['zone__name']
    def get_queryset(self, request):
        return super().get_queryset(request)
