from django.contrib import admin
from .models import CustomUser, SellerAccount, ShopFollow, UserSettings, UserProfile, Address
from django.contrib.auth.admin import UserAdmin
from .forms import UserCreationForm, UserChangeForm

# Register your models here.

class UserAdmin(UserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    list_display = ('email', 'phone_number', 'first_name', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    readonly_fields = ('date_joined',)
    fieldsets = (
        (None, {'fields': ('password', 'email',  'type_user')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone_number', 'full_address', 'gender', 'country', 'date_of_birth')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser',  'groups', 'user_permissions')}),
        ('Seller account', {'fields': ('has_seller_account',)}),
        ('Important date', {'fields': ('last_login','date_joined' )})
    )
    add_fieldsets = (
        (None, {'fields': ('first_name', 'phone_number', 'email', 'password_1', 'password_2')}),
    )
    search_fields = ('email', 'first_name', 'phone_number')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions')

@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'language', 'country', 'currency')
    search_fields = ('country', 'currency')

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('customer', 'street_address', 'city', 'state_region', 'postal_code', 'country')
    search_fields = ('city', 'state_region', 'country')

admin.site.register(CustomUser, UserAdmin)
admin.site.register(SellerAccount)
admin.site.register(ShopFollow)
admin.site.register(UserProfile)