from django.contrib import admin
from .models import PayementMethod, Notifications, Favorites, Coupon, CouponUsage, Banner


@admin.register(Notifications)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'type', 'title', 'is_read', 'created_at')
    list_filter = ('type', 'is_read', 'created_at')

@admin.register(Favorites)
class FavoritesAdmin(admin.ModelAdmin):
    list_display = ('user', 'product',  'added_at')

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('code', 'users__email')


@admin.register(CouponUsage)
class CouponUsageAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'user', 'order', 'discount_amount', 'used_at')
    search_fields = ('coupon__code', 'user__email', 'order__order_number')
    list_filter = ('used_at',)

@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'target', 'type', 'is_active', 'priority')
    list_filter = ('target', 'type', 'is_active')
    search_fields = ('title',)


admin.site.register(PayementMethod)

