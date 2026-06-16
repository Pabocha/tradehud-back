from django.contrib import admin
from .models import *

# Register your models here.

@admin.register(Orders)
class OrdersAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'status', 'order_date')
    list_filter = ('status',)
    search_fields = ('customer', 'order_number')

admin.site.register(OrderLine)