from django_filters import rest_framework as filters

from .models import ShopStatistics

class ShopStatisticsFilter(filters.FilterSet):
    shop_id = filters.NumberFilter(field_name='shop__id')
    date = filters.DateFilter(field_name='date', lookup_expr='exact')
    date_from = filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = filters.DateFilter(field_name='date', lookup_expr='lte')
    
    class Meta:
        model = ShopStatistics
        fields = ['shop', 'date']
