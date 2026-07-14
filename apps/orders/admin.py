from django.contrib import admin
from .models import Orders, OrderLine, ReturnRequest, ReturnItem, Refund

# Register your models here.

@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'status', 'order_date')
    list_filter = ('status',)
    search_fields = ('customer', 'order_number')

admin.site.register(OrderLine)


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = ('order_line', 'quantity', 'reason', 'description')


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'status', 'reason', 'created_at')
    list_filter = ('status', 'reason')
    search_fields = ('order__order_number',)
    inlines = [ReturnItemInline]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('id', 'return_request', 'order', 'amount', 'method', 'status', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('order__order_number', 'reference_number')