from django.contrib import admin
from .models import Banner, Announcement, Campaign, FlashSale

# Register your models here.

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'type', 'target', 'is_active', 'priority', 'start_date', 'end_date')
    list_filter = ('is_active', 'type', 'target')
    search_fields = ('title',)

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'badge')
    search_fields = ('title',)

@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'start_at', 'end_at', 'created_at')
    list_filter = ('is_active', 'start_at', 'end_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(FlashSale)
class FlashSaleAdmin(admin.ModelAdmin):
    list_display = ('name', 'discount_type', 'discount_value', 'target_type', 'is_active', 'start_at', 'end_at', 'uses', 'max_uses')
    list_filter = ('is_active', 'discount_type', 'target_type', 'start_at')
    search_fields = ('name',)
    filter_horizontal = ('target_categories', 'target_shops', 'target_products')
