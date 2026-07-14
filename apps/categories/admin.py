from django.contrib import admin
from django.db import models
from mptt.forms import TreeNodeChoiceField
from mptt.admin import DraggableMPTTAdmin
from .models import Categories, CategoryAttribute
from django import forms
from django_json_widget.widgets import JSONEditorWidget
# Register your models here.

class CategoriesAdminForm(forms.ModelForm):
    parent_category = TreeNodeChoiceField(queryset=Categories.objects.all(), required=False)

    class Meta:
        model = Categories
        fields = '__all__'

@admin.register(Categories)
class CategoriesAdmin(DraggableMPTTAdmin):
    form = CategoriesAdminForm  # 👈 Important pour le champ parent

    list_display = (
        'tree_actions',  # flèches de repli
        'indented_title',  # titre avec indentation automatique
        'category_type',
        'is_active',
    )
    formfield_overrides = {
        models.JSONField: {'widget': JSONEditorWidget},
    }
    list_display_links = ('indented_title',)
    list_filter = ('category_type', 'is_active')

# @admin.register(CategoryField)
# class CategoryFieldAdmin(admin.ModelAdmin):
#     list_display = ('category', 'label', 'field_type', 'required')
#     list_filter = ('required', 'field_type',)
#     search_fields = ('name', 'label',)

@admin.register(CategoryAttribute)
class CategoryAttributeAdmin(admin.ModelAdmin):
    list_display = ('category', 'attribute', 'required')
    list_filter = ('required',)
    search_fields = ('attribute__name', 'category__name',)