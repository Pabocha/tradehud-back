from rest_framework import serializers
from apps.products.serializers import ProductSerializer
from .models import Favorites


class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    class Meta:
        model = Favorites
        fields = ['id', 'added_at', 'product'] 