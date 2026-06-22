import django_filters
from django.db.models import Q, Subquery, OuterRef, Count, Sum, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from apps.orders.models import OrderLine
from apps.favorites.models import Favorites
from apps.carts.models import CartItem
from .models import Products


class ProductFilter(django_filters.FilterSet):
    tab = django_filters.CharFilter(method='filter_tab')
    search = django_filters.CharFilter(method='filter_search')
    country = django_filters.CharFilter(field_name='country_origin', lookup_expr='iexact')
    category = django_filters.NumberFilter(field_name='category_id')
    min_price = django_filters.NumberFilter(field_name='base_price__amount', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='base_price__amount', lookup_expr='lte')
    is_active = django_filters.BooleanFilter(field_name='is_active')
    is_sponsored = django_filters.BooleanFilter(field_name='is_sponsored')
    status = django_filters.CharFilter(field_name='status')
    date_added_after = django_filters.DateTimeFilter(field_name='date_added', lookup_expr='gte')
    date_added_before = django_filters.DateTimeFilter(field_name='date_added', lookup_expr='lte')

    class Meta:
        model = Products
        fields = [
            'tab', 'search', 'country', 'category',
            'min_price', 'max_price', 'is_active', 'is_sponsored',
            'status', 'date_added_after', 'date_added_before',
        ]

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value) |
            Q(tags__name__icontains=value)
        ).distinct()

    def filter_tab(self, queryset, name, value):
        if value == 'recent':
            one_week_ago = timezone.now() - timedelta(weeks=1)
            return queryset.filter(date_added__gte=one_week_ago).order_by('-date_added')
        elif value == 'popular':
            thirty_days_ago = timezone.now() - timedelta(days=30)


            recent_direct_qty = OrderLine.objects.filter(
                product=OuterRef('pk'),
                order__status='delivered',
                order__order_date__gte=thirty_days_ago,
            ).values('product').annotate(total=Sum('quantity')).values('total')[:1]

            recent_variant_qty = OrderLine.objects.filter(
                variant__product=OuterRef('pk'),
                order__status='delivered',
                order__order_date__gte=thirty_days_ago,
            ).values('variant__product').annotate(total=Sum('quantity')).values('total')[:1]

            fav_count = Favorites.objects.filter(
                product=OuterRef('pk'),
            ).values('product').annotate(count=Count('*')).values('count')[:1]

            cart_count = CartItem.objects.filter(
                product=OuterRef('pk'),
            ).values('product').annotate(count=Count('*')).values('count')[:1]

            cart_variant_count = CartItem.objects.filter(
                variant__product=OuterRef('pk'),
            ).values('variant__product').annotate(count=Count('*')).values('count')[:1]

            return queryset.annotate(
                popularity_score=(
                    Coalesce(Subquery(recent_direct_qty), 0) * 10
                    + Coalesce(Subquery(recent_variant_qty), 0) * 10
                    + Coalesce(Subquery(fav_count), 0) * 5
                    + (Coalesce(Subquery(cart_count), 0) + Coalesce(Subquery(cart_variant_count), 0)) * 3
                    + F('views_count')
                )
            ).order_by('-popularity_score')
        elif value == 'sponsored':
            now = timezone.now()
            return (
                queryset
                .filter(
                    is_sponsored=True,
                    sponsored_start__isnull=False,
                    sponsored_end__isnull=False,
                    sponsored_start__lte=now,
                    sponsored_end__gte=now,
                )
                .order_by('?')
            )
        return queryset