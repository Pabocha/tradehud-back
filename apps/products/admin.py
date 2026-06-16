from django.contrib import admin
from .models import (Products, GalerieImages, Colors, 
                     ProductPriceTier, ProductPromotion, 
                     AttributeValue, ProductVariant, Attribute, RecentlyViewedProduct)

# Register your models here.
@admin.register(GalerieImages)
class GalerieImageAdmin(admin.ModelAdmin):
    list_display = ('product', 'type_image', 'alt_text', 'date_added', 'hash')
    list_filter = ('type_image', 'product', 'date_added')
@admin.register(Colors)
class ColorsAdmin(admin.ModelAdmin):
    list_display = ('name', 'code_hex')

@admin.register(Products)
class ColorsAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'country_origin', 'status', 'date_added')
    list_filter = ('status',)
    search_fields = ('name', 'shop', 'tags')

@admin.register(ProductPromotion)
class ProductPromotionAdmin(admin.ModelAdmin):
    list_display = ('product', 'promo_price', 'start_at', 'end_at', 'is_active')
    list_filter = ('is_active', 'start_at', 'end_at')
    search_fields = ('product__name',)

@admin.register(ProductPriceTier)
class ProductPriceTierAdmin(admin.ModelAdmin):
    list_display = ('product', 'min_quantity', 'max_quantity', 'price')
    list_filter = ('price',)
    search_fields = ('product__name',)

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('product', 'sku', 'price_override', 'stock_quantity')
    search_fields = ('product__name', 'sku')

@admin.register(RecentlyViewedProduct)
class RecentlyViewedProductAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'viewed_at')
    search_fields = ('user__email', 'product__name')

admin.site.register(Attribute)
admin.site.register(AttributeValue)
 