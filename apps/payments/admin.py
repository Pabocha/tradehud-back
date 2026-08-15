from django.contrib import admin
from .models import PaymentMethod

# Register your models here.


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('id', 'value', 'name', 'type', 'requires_phone', 'countries')
    list_editable = ('name', 'type', 'requires_phone')
    search_fields = ('name', 'value')
