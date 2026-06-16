from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, SerializerMethodField
from .models import Categories, CategoryField, CategoryAttribute
from ecom_app.validators import validate_image_file

class CategoryAttributeSerializer(ModelSerializer):
    attribute_name = serializers.CharField(source="attribute.name", read_only=True)
    attribute_code = serializers.CharField(source="attribute.code", read_only=True)
    
    class Meta:
        model = CategoryAttribute
        fields = '__all__'

class CategoriesSerializer(ModelSerializer):
    # Validate category image size/type
    image = serializers.ImageField(required=False, validators=[validate_image_file])

    class Meta:
        model = Categories
        fields = '__all__'

class CategoryHierarchySerializer(ModelSerializer):
    children = SerializerMethodField()

    class Meta:
        model = Categories
        fields = ['id', 'name', 'image', 'children']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        if children.exists():
            return CategorySerializer(children, many=True, context=self.context).data
        return []


class SubCategorySerializer(ModelSerializer):
    class Meta:
        model = Categories
        fields = ['id', 'name', 'image']

class CategorySerializer(ModelSerializer):
    children = SubCategorySerializer(many=True, read_only=True)

    class Meta:
        model = Categories
        fields = ['id', 'name', 'image', 'children']

class CategoryFieldSerializer(ModelSerializer):
    class Meta:
        model = CategoryField
        fields = ['id', 'name', 'label', 'field_type', 'required', 'choices']

