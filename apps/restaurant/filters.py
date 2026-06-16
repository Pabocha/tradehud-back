import django_filters
from .models import Restaurant, Meal, RestaurantOrder


class RestaurantFilter(django_filters.FilterSet):
    """Filtres avancés pour les restaurants"""
    name = django_filters.CharFilter(lookup_expr='icontains')
    city = django_filters.CharFilter(lookup_expr='icontains')
    min_rating = django_filters.NumberFilter(field_name='rating', lookup_expr='gte')
    max_delivery_fee = django_filters.NumberFilter(field_name='delivery_fee', lookup_expr='lte')
    is_open = django_filters.BooleanFilter()
    
    class Meta:
        model = Restaurant
        fields = ['name', 'city', 'category', 'is_open', 'is_active']


class MealFilter(django_filters.FilterSet):
    """Filtres avancés pour les plats"""
    name = django_filters.CharFilter(lookup_expr='icontains')
    min_price = django_filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price', lookup_expr='lte')
    restaurant = django_filters.NumberFilter(field_name='category__restaurant')
    category = django_filters.NumberFilter(field_name='category')
    
    class Meta:
        model = Meal
        fields = [
            'name', 'category', 'is_available',
            'is_vegetarian', 'is_vegan', 'is_gluten_free'
        ]


class RestaurantOrderFilter(django_filters.FilterSet):
    """Filtres pour les commandes"""
    created_after = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    min_amount = django_filters.NumberFilter(field_name='total_price', lookup_expr='gte')
    max_amount = django_filters.NumberFilter(field_name='total_price', lookup_expr='lte')
    
    class Meta:
        model = RestaurantOrder
        fields = ['status', 'restaurant', 'delivery_type', 'payment_method']