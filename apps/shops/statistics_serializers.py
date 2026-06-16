from rest_framework import serializers
from .models import ShopStatistics, Shops


class ShopStatisticsSerializer(serializers.ModelSerializer):
    """Serializer complet pour les statistiques de boutique avec tous les indicateurs clés."""
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    best_selling_product_name = serializers.CharField(source='best_selling_product.name', read_only=True)
    top_category_name = serializers.CharField(source='top_category.name', read_only=True)

    class Meta:
        model = ShopStatistics
        fields = [
            'id',
            'shop',
            'shop_name',
            'date',
            # Ventes
            'total_orders',
            'total_revenue',
            'products_sold',
            'average_order_value',
            # Engagement
            'new_followers',
            'new_customers',
            'repeat_customers',
            # Trafic
            'visits',
            'conversion_rate',
            'total_product_views',
            'average_views_per_product',
            # Retours
            'cancelled_orders',
            'returned_products',
            # Produits vedettes
            'best_selling_product',
            'best_selling_product_name',
            'top_category',
            'top_category_name',
            # Satisfaction
            'shop_average_rating',
            'shop_number_of_reviews',
            # Inventaire
            'products_low_stock',
            'products_out_of_stock',
            'average_product_stock',
            # Promotion
            'active_sponsored_products',
            # Efficacité
            'inventory_turnover_ratio',
        ]
        read_only_fields = fields
