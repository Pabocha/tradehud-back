from datetime import timedelta
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import ValidationError, NotFound
from django.core.cache import cache
from django.db.models import Sum, Avg, Count, F, Min, Q
from django.db.models.functions import Coalesce
from django.utils.timezone import now
from apps.products.models import Products, GalerieImages
from apps.products.serializers import ProductSerializer
from apps.accounts.models import SellerAccount, ShopFollow
from ecommerce.permissions import IsSeller
from apps.categories.models import Categories
from apps.orders.models import Orders, OrderLine
from apps.comments.models import Ratings
from ..analytics import (
    buffered_visits_map, buffered_views_map, buffered_views_product, get_shop_total_visits,
)
from ..serializers import (
    ShopSerializer, ShopListSerializer, ShopPublicDetailSerializer,
    ShopUpdateSerializer, ShopStatisticsSerializer,
)
from ..models import Shops, ShopStatistics

MAX_STATS_CACHE_TTL = 90
STATS_CACHE_PREFIX = 'th:stats:by_shop'
PERF_CACHE_PREFIX = 'th:perf:by_shop'


def compute_shop_rating(shop):
    qs = Ratings.objects.filter(product__shop=shop)
    average_rating = qs.aggregate(avg=Avg("rating"))["avg"] or 0
    return round(float(average_rating), 2), qs.count()


def recompute_shop_rating(shop):
    average_rating, number_of_reviews = compute_shop_rating(shop)
    Shops.objects.filter(pk=shop.pk).update(
        average_rating=average_rating,
        number_of_reviews=number_of_reviews,
    )
    return average_rating, number_of_reviews


def sync_shop_public_metrics(shop):
    delivered_orders = Orders.objects.filter(
        status="delivered", order_lines__shop=shop
    ).distinct()
    delivered_items = OrderLine.objects.filter(
        shop=shop, order__status="delivered"
    )
    total_orders = delivered_orders.count()
    number_sale = delivered_items.aggregate(s=Sum("quantity"))["s"] or 0
    average_rating, number_of_reviews = recompute_shop_rating(shop)
    Shops.objects.filter(pk=shop.pk).update(
        total_orders=total_orders,
        number_sale=number_sale,
        average_rating=average_rating,
        number_of_reviews=number_of_reviews,
    )


def _normalize_money(value):
    """djmoney renvoie un objet Money sur les agrégats : on ne garde que .amount."""
    return value.amount if hasattr(value, 'amount') else value


def compute_shop_current_metrics(shop):
    """Métriques « actuelles » de la boutique, indépendantes de la date.
    Calculées une seule fois puis copiées sur les lignes pour éviter la
    répétition de requêtes à chaque jour / chaque mise à jour."""
    all_products = Products.objects.filter(shop=shop)
    products_low_stock = all_products.filter(stock_quantity__gt=0, stock_quantity__lt=5).count()
    products_out_of_stock = all_products.filter(status='unavailable').count()
    total_stock = all_products.aggregate(s=Sum('stock_quantity'))['s'] or 0
    product_count = all_products.count()
    avg_product_stock = total_stock / product_count if product_count > 0 else 0

    active_sponsored = all_products.filter(
        is_sponsored=True, sponsored_start__lte=now(), sponsored_end__gte=now()
    ).count()

    total_views = all_products.aggregate(s=Sum('views_count'))['s'] or 0
    avg_views_per_product = total_views / product_count if product_count > 0 else 0
    shop_avg_rating, shop_number_of_reviews = compute_shop_rating(shop)

    return {
        'products_low_stock': products_low_stock,
        'products_out_of_stock': products_out_of_stock,
        'average_product_stock': avg_product_stock,
        'active_sponsored_products': active_sponsored,
        'total_product_views': total_views,
        'average_views_per_product': avg_views_per_product,
        'shop_average_rating': shop_avg_rating,
        'shop_number_of_reviews': shop_number_of_reviews,
    }


def _best_product_and_category(shop, date):
    """Meilleur produit et catégorie la plus performante pour une journée."""
    delivered = OrderLine.objects.filter(shop=shop, order__status='delivered', order__order_date__date=date)
    best_data = (
        delivered.values('product')
        .annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    )
    best_product = None
    if best_data and best_data.get('product'):
        best_product = Products.objects.filter(id=best_data['product']).first()

    top_data = (
        delivered.values('product__category')
        .annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    )
    top_category = None
    if top_data and top_data.get('product__category'):
        top_category = Categories.objects.filter(id=top_data['product__category']).first()
    return best_product, top_category


def _customers_engagement(shop, date):
    """new_customers / repeat_customers d'une journée (commandes deliverées)."""
    customer_dates = list(
        Orders.objects.filter(
            order_date__date=date, status='delivered', order_lines__shop=shop
        ).values_list('order_date__date', 'customer_id').distinct()
    )
    if not customer_dates:
        return 0, 0
    customer_ids = {cid for _, cid in customer_dates}
    first_delivery = dict(
        Orders.objects.filter(
            customer_id__in=customer_ids, status='delivered', order_lines__shop=shop
        ).values('customer_id').annotate(first=Min('order_date__date')).values_list('customer_id', 'first')
    )
    new_customers = sum(1 for _, cid in customer_dates if first_delivery.get(cid) == date)
    repeat_customers = sum(
        1 for _, cid in customer_dates
        if first_delivery.get(cid) and first_delivery[cid] < date
    )
    return new_customers, repeat_customers


def _assemble_defaults(shop, date, day, metrics):
    """Assemble le dict `defaults` d'update_or_create. `metrics` contient les
    indicateurs quotidiens, `metrics` les indicateurs courants de la boutique.
    `visits` n'est JAMAIS inclus volontairement : le compteur est alimenté
    indépendamment (buffer Redis + flush) et ne doit pas être écrasé."""
    revenue = _normalize_money(day.get('revenue') or 0)
    products_sold = day.get('products_sold') or 0
    total_orders = day.get('total_orders') or 0
    avg_order_value = revenue / total_orders if total_orders > 0 else 0
    inventory_turnover = (
        products_sold / metrics['average_product_stock']
        if metrics['average_product_stock'] > 0 else 0
    )
    orders_created = day.get('orders_created') or 0
    visits = day.get('visits') or 0
    conversion_rate = (orders_created / visits * 100) if visits > 0 else 0
    return {
        'total_orders': total_orders,
        'total_revenue': round(revenue, 2),
        'products_sold': products_sold,
        'average_order_value': round(avg_order_value, 2),
        'best_selling_product': day.get('best_product'),
        'top_category': day.get('top_category'),
        'new_followers': day.get('new_followers') or 0,
        'new_customers': day.get('new_customers') or 0,
        'repeat_customers': day.get('repeat_customers') or 0,
        'conversion_rate': round(conversion_rate, 2),
        'cancelled_orders': day.get('cancelled_orders') or 0,
        'returned_products': day.get('returned_products') or 0,
        'inventory_turnover_ratio': round(inventory_turnover, 2),
        **metrics,
    }


def update_shop_statistics(shop, date=None):
    """Recalcule (et crée si besoin) la statistique d'une boutique pour une journée."""
    if date is None:
        date = now().date()

    delivered = OrderLine.objects.filter(
        shop=shop, order__status='delivered', order__order_date__date=date
    )
    sales = delivered.aggregate(
        revenue=Sum(F('unit_price') * F('quantity')),
        products_sold=Sum('quantity'),
    )

    day_orders = Orders.objects.filter(order_date__date=date, order_lines__shop=shop).distinct()
    status_counts = {
        r['status']: r['n']
        for r in day_orders.values('status').annotate(n=Count('id', distinct=True))
    }

    best_product, top_category = (None, None)
    if (sales['products_sold'] or 0) > 0:
        best_product, top_category = _best_product_and_category(shop, date)

    new_customers, repeat_customers = _customers_engagement(shop, date)

    day_metrics = {
        'revenue': sales['revenue'] or 0,
        'products_sold': sales['products_sold'] or 0,
        'total_orders': status_counts.get('delivered', 0),
        'cancelled_orders': status_counts.get('cancelled', 0),
        'returned_products': (
            OrderLine.objects.filter(
                shop=shop,
                order__status__in=['returned', 'partially_returned'],
                order__order_date__date=date,
            ).aggregate(s=Sum('quantity'))['s'] or 0
        ),
        'orders_created': day_orders.count(),
        'new_customers': new_customers,
        'repeat_customers': repeat_customers,
        'new_followers': ShopFollow.objects.filter(shop=shop, followed_at__date=date).count(),
        'visits': get_shop_total_visits(shop.id, date),
        'best_product': best_product,
        'top_category': top_category,
    }

    stats, _ = ShopStatistics.objects.update_or_create(
        shop=shop,
        date=date,
        defaults=_assemble_defaults(shop, date, day_metrics, compute_shop_current_metrics(shop)),
    )
    sync_shop_public_metrics(shop)
    return stats


def _backfill_shop_statistics(shop, dates):
    """Crée les lignes manquantes d'une fenêtre de dates en une seule passe
    d'agrégats groupés (pas une boucle jour-par-jour)."""
    if not dates:
        return
    dates = sorted(set(dates))

    line_rows = {
        r['order__order_date__date']: r
        for r in OrderLine.objects.filter(
            shop=shop, order__status='delivered', order__order_date__date__in=dates
        ).values('order__order_date__date').annotate(
            products_sold=Sum('quantity'),
            revenue=Sum(F('unit_price') * F('quantity')),
        )
    }

    status_rows = dict()
    for r in Orders.objects.filter(
        order_date__date__in=dates, order_lines__shop=shop
    ).values('order_date__date', 'status').annotate(n=Count('id', distinct=True)):
        status_rows.setdefault(r['order_date__date'], {})[r['status']] = r['n']

    customers_per_day = list(
        Orders.objects.filter(
            order_date__date__in=dates, status='delivered', order_lines__shop=shop
        ).values_list('order_date__date', 'customer_id').distinct()
    )
    customer_ids = {cid for _, cid in customers_per_day}
    first_delivery = dict(
        Orders.objects.filter(
            customer_id__in=customer_ids, status='delivered', order_lines__shop=shop
        ).values('customer_id').annotate(first=Min('order_date__date')).values_list('customer_id', 'first')
    )

    follow_rows = dict(
        ShopFollow.objects.filter(shop=shop, followed_at__date__in=dates)
        .values('followed_at__date').annotate(n=Count('id')).values_list('followed_at__date', 'n')
    )

    for date in dates:
        d = date.isoformat()
        line = line_rows.get(date, {})
        status_map = status_rows.get(date, {})
        sold = line.get('products_sold') or 0
        new_customers = sum(1 for day, cid in customers_per_day if day == date and first_delivery.get(cid) == date)
        repeat_customers = sum(
            1 for day, cid in customers_per_day
            if day == date and first_delivery.get(cid) and first_delivery[cid] < date
        )
        best_product, top_category = (None, None)
        if sold > 0:
            best_product, top_category = _best_product_and_category(shop, date)

        day_metrics = {
            'revenue': line.get('revenue') or 0,
            'products_sold': sold,
            'total_orders': status_map.get('delivered', 0),
            'cancelled_orders': status_map.get('cancelled', 0),
            'returned_products': (
                OrderLine.objects.filter(
                    shop=shop,
                    order__status__in=['returned', 'partially_returned'],
                    order__order_date__date=date,
                ).aggregate(s=Sum('quantity'))['s'] or 0
            ),
            'orders_created': sum(status_map.values()),
            'new_customers': new_customers,
            'repeat_customers': repeat_customers,
            'new_followers': follow_rows.get(date, 0),
            'visits': get_shop_total_visits(shop.id, date),
            'best_product': best_product,
            'top_category': top_category,
        }
        try:
            ShopStatistics.objects.update_or_create(
                shop=shop,
                date=date,
                defaults=_assemble_defaults(shop, date, day_metrics, compute_shop_current_metrics(shop)),
            )
        except Exception:
            # Le backfill ne doit jamais faire planter une lecture du dashboard.
            continue


def _build_totals(serializer_rows, shop_id=None):
    total_revenue = round(sum(float(r['total_revenue'] or 0) for r in serializer_rows), 2)
    total_orders = sum(r.get('total_orders') or 0 for r in serializer_rows)
    products_sold = sum(r.get('products_sold') or 0 for r in serializer_rows)
    visits = sum(r.get('visits') or 0 for r in serializer_rows)
    last = serializer_rows[-1] if serializer_rows else None

    extra_visits = 0
    extra_product_views = 0
    if shop_id:
        extra_visits = sum(buffered_visits_map(shop_id, [now().date()]).values())
        extra_product_views = sum(buffered_views_map(shop_id).values())

    return {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'products_sold': products_sold,
        'average_order_value': round(total_revenue / total_orders, 2) if total_orders else 0,
        'visits': visits + extra_visits,
        'conversion_rate': round(total_orders / (visits + extra_visits) * 100, 2) if (visits + extra_visits) else 0,
        'cancelled_orders': sum(r.get('cancelled_orders') or 0 for r in serializer_rows),
        'returned_products': sum(r.get('returned_products') or 0 for r in serializer_rows),
        'new_customers': sum(r.get('new_customers') or 0 for r in serializer_rows),
        'repeat_customers': sum(r.get('repeat_customers') or 0 for r in serializer_rows),
        'new_followers': sum(r.get('new_followers') or 0 for r in serializer_rows),
        'total_product_views': (last.get('total_product_views', 0) if last else 0) + extra_product_views,
        'average_views_per_product': last.get('average_views_per_product', 0) if last else 0,
        'products_low_stock': last.get('products_low_stock', 0) if last else 0,
        'products_out_of_stock': last.get('products_out_of_stock', 0) if last else 0,
        'average_product_stock': last.get('average_product_stock', 0) if last else 0,
        'active_sponsored_products': last.get('active_sponsored_products', 0) if last else 0,
        'inventory_turnover_ratio': last.get('inventory_turnover_ratio', 0) if last else 0,
        'shop_average_rating': last.get('shop_average_rating', 0) if last else 0,
        'shop_number_of_reviews': last.get('shop_number_of_reviews', 0) if last else 0,
        'best_selling_product_name': last.get('best_selling_product_name') if last else None,
        'top_category_name': last.get('top_category_name') if last else None,
    }


def _period_best_product_and_category(shop, start_date, end_date):
    """Meilleur produit et catégorie phare de TOUTE la fenêtre (les lignes sont
    souvent liées à un variant : on groupe via Coalesce(variant__product, product))."""
    delivered = OrderLine.objects.filter(
        shop=shop, order__status='delivered',
        order__order_date__date__range=(start_date, end_date),
    )
    best_name = None
    best_row = (
        delivered
        .annotate(pid=Coalesce('variant__product', 'product'))
        .values('pid').filter(pid__isnull=False)
        .annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    )
    if best_row and best_row.get('pid'):
        p = Products.objects.filter(id=best_row['pid']).only('name').first()
        best_name = p.name if p else None

    top_name = None
    top_row = (
        delivered
        .annotate(cat=Coalesce('variant__product__category', 'product__category'))
        .values('cat').filter(cat__isnull=False)
        .annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    )
    if top_row and top_row.get('cat'):
        c = Categories.objects.filter(id=top_row['cat']).only('name').first()
        top_name = c.name if c else None
    return best_name, top_name


def _assemble_window(shop, start_date, end_date):
    """Sérialise les lignes + totaux d'une fenêtre [start_date, end_date] incluse.
    Backfill lazy des journées manquantes, fusion du buffer de visites Redis."""
    days_count = (end_date - start_date).days + 1
    all_dates = [start_date + timedelta(days=i) for i in range(days_count)]
    shop_id = shop.id

    existing_dates = set(
        ShopStatistics.objects.filter(shop_id=shop_id, date__in=all_dates).values_list('date', flat=True)
    )
    missing = [d for d in all_dates if d not in existing_dates]
    if missing:
        _backfill_shop_statistics(shop, missing)

    rows = list(
        ShopStatistics.objects.filter(shop_id=shop_id, date__in=all_dates).select_related(
            'best_selling_product', 'top_category'
        ).order_by('date')
    )

    buffered = buffered_visits_map(shop_id, all_dates)
    for row in rows:
        row.visits += buffered.get(row.date.isoformat(), 0)

    serialized = ShopStatisticsSerializer(rows, many=True).data
    totals = _build_totals(serialized, shop_id=shop_id)
    return serialized, totals


def invalidate_shop_stats_cache(shop_id):
    for prefix in (STATS_CACHE_PREFIX, PERF_CACHE_PREFIX):
        try:
            cache.delete_pattern(f'{prefix}:{shop_id}:*')
        except Exception:
            pass


class SellerShopViewSet(viewsets.ModelViewSet):
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticated, IsSeller]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def perform_create(self, serializer):
        try:
            seller_account = self.request.user.seller_account
        except SellerAccount.DoesNotExist:
            raise ValidationError({'owner': 'Aucun compte vendeur lie a cet utilisateur.'})
        serializer.save(owner=seller_account)

    def _get_seller_account(self):
        try:
            return self.request.user.seller_account
        except (AttributeError, SellerAccount.DoesNotExist):
            return None

    def get_queryset(self):
        seller_account = self._get_seller_account()
        if seller_account is None:
            return Shops.objects.none()
        return Shops.objects.filter(owner=seller_account)

    def retrieve(self, request, pk=None):
        seller_account = self._get_seller_account()
        if seller_account is None:
            raise ValidationError({'owner': 'Aucun compte vendeur lie a cet utilisateur.'})
        shop = get_object_or_404(Shops, pk=pk, owner=seller_account)
        serializer = ShopSerializer(shop, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_path='update-fields')
    def update_fields(self, request, pk=None):
        try:
            shop = self.get_object()
        except Shops.DoesNotExist:
            return Response({'detail': 'Boutique introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ShopUpdateSerializer(shop, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({'detail': 'Boutique mise a jour avec succes.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SellerShopStatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    """ Vue pour gérer les statistiques des boutiques du vendeur. Fournit des endpoints pour 
    récupérer les statistiques par boutique et recalculer les statistiques pour aujourd'hui ou 
    une plage de dates.
    """
    queryset = ShopStatistics.objects.select_related('shop', 'best_selling_product', 'top_category')
    serializer_class = ShopStatisticsSerializer
    permission_classes = [permissions.IsAuthenticated, IsSeller]

    def get_queryset(self):
        seller = getattr(self.request.user, 'seller_account', None)
        if seller is None:
            return ShopStatistics.objects.none()
        return ShopStatistics.objects.filter(
            shop__owner=seller
        ).select_related('shop', 'best_selling_product', 'top_category')

    @action(detail=False, methods=['get'], url_path='by-shop/(?P<shop_id>[^/.]+)')
    def by_shop(self, request, shop_id=None):
        days = 30
        try:
            days = max(1, min(int(request.query_params.get('days', 30)), 366))
        except (TypeError, ValueError):
            days = 30

        today = now().date()
        start = today - timedelta(days=days - 1)

        cache_key = f'{STATS_CACHE_PREFIX}:{shop_id}:{days}:{today.isoformat()}'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            shop = Shops.objects.get(id=shop_id)
        except Shops.DoesNotExist:
            raise NotFound({'detail': f'Boutique {shop_id} inexistante.'})

        serialized, totals = _assemble_window(shop, start, today)

        # Meilleur produit / catégorie phare de TOUTE la fenêtre (le dernier jour
        # est souvent vide → le champ serait à null sinon).
        best_name, top_name = _period_best_product_and_category(shop, start, today)
        if best_name:
            totals['best_selling_product_name'] = best_name
        if top_name:
            totals['top_category_name'] = top_name

        # Fenêtre précédente de même durée pour les évolutions.
        prev_start = start - timedelta(days=days)
        prev_end = start - timedelta(days=1)
        _, previous_totals = _assemble_window(shop, prev_start, prev_end)

        payload = {'results': serialized, 'totals': totals, 'previous': previous_totals}
        cache.set(cache_key, payload, MAX_STATS_CACHE_TTL)
        return Response(payload)

    @action(detail=False, methods=['get'], url_path='by-shop/(?P<shop_id>[^/.]+)/performance')
    def performance(self, request, shop_id=None):
        days = 30
        try:
            days = max(1, min(int(request.query_params.get('days', 30)), 366))
        except (TypeError, ValueError):
            days = 30
        today = now().date()
        start = today - timedelta(days=days - 1)

        cache_key = f'{PERF_CACHE_PREFIX}:{shop_id}:{days}:{today.isoformat()}'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            shop = Shops.objects.get(id=shop_id)
        except Shops.DoesNotExist:
            raise NotFound({'detail': f'Boutique {shop_id} inexistante.'})

        # --- Répartition des commandes par statut (fenêtre) ---
        status_breakdown = {
            r['status']: r['n']
            for r in Orders.objects.filter(
                order_date__date__range=(start, today), order_lines__shop=shop
            ).values('status').annotate(n=Count('id', distinct=True))
        }

        # --- Top produits par CA (livrées) ---
        delivered = OrderLine.objects.filter(
            shop=shop, order__status='delivered', order__order_date__date__range=(start, today),
        )
        top_products = []
        product_ids = []
        for r in delivered.annotate(pid=Coalesce('variant__product', 'product')).values('pid').filter(
            pid__isnull=False
        ).annotate(
            qty=Sum('quantity'), revenue=Sum(F('unit_price') * F('quantity'))
        ).order_by('-revenue')[:5]:
            product_ids.append(r['pid'])
            top_products.append({
                'id': r['pid'],
                'qty': r['qty'] or 0,
                'revenue': round(float(_normalize_money(r['revenue']) or 0), 2),
            })
        if product_ids:
            names = dict(Products.objects.filter(id__in=product_ids).values_list('id', 'name'))
            principal = {
                g.product_id: g.image.url
                for g in GalerieImages.objects.filter(product_id__in=product_ids, type_image='principale')
            }
            for item in top_products:
                item['name'] = names.get(item['id'], '—')
                item['image'] = principal.get(item['id'])

        # --- Top vues ---
        top_views = [
            {
                'id': p.id, 'name': p.name,
                'views': (p.views_count or 0) + buffered_views_product(p.id),
            }
            for p in Products.objects.filter(shop=shop).order_by('-views_count')[:5]
            .only('id', 'name', 'views_count')
        ]

        # --- Alertes stock ---
        low_stock = [
            {'id': p.id, 'name': p.name, 'stock': p.stock_quantity}
            for p in Products.objects.filter(shop=shop, stock_quantity__gt=0, stock_quantity__lt=5)
            .order_by('stock_quantity')[:8].only('id', 'name', 'stock_quantity')
        ]
        out_of_stock = [
            {'id': p.id, 'name': p.name}
            for p in Products.objects.filter(shop=shop, status='unavailable')[:8].only('id', 'name')
        ]

        # --- Promotions / sponsors ---
        sponsored_qs = Products.objects.filter(
            shop=shop, is_sponsored=True, sponsored_start__lte=now(), sponsored_end__gte=now()
        )
        active_sponsored = sponsored_qs.count()
        expiring_soon = [
            {'id': p.id, 'name': p.name}
            for p in sponsored_qs.filter(sponsored_end__lte=now() + timedelta(days=7))[:8].only('id', 'name')
        ]

        # --- Fidélité (clients livrés sur la fenêtre) ---
        customers = list(
            Orders.objects.filter(
                order_date__date__range=(start, today), status='delivered', order_lines__shop=shop
            ).values_list('order_date__date', 'customer_id').distinct()
        )
        customer_ids = {cid for _, cid in customers}
        first_delivery = dict(
            Orders.objects.filter(
                customer_id__in=customer_ids, status='delivered', order_lines__shop=shop
            ).values('customer_id').annotate(first=Min('order_date__date')).values_list('customer_id', 'first')
        )
        repeat_customers = sum(
            1 for _, cid in customers
            if first_delivery.get(cid) and first_delivery[cid] < start
        )
        new_customers = len(customer_ids) - repeat_customers
        loyalty_rate = round(
            repeat_customers / (repeat_customers + new_customers) * 100, 2
        ) if (repeat_customers + new_customers) else 0

        payload = {
            'status_breakdown': status_breakdown,
            'top_products': top_products,
            'top_views': top_views,
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'active_sponsored': active_sponsored,
            'expiring_soon': expiring_soon,
            'loyalty_rate': loyalty_rate,
        }
        cache.set(cache_key, payload, MAX_STATS_CACHE_TTL)
        return Response(payload)

    @action(detail=False, methods=['post'], url_path='recalculate-today')
    def recalculate_today(self, request):
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({'error': 'shop_id est requis'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            shop = Shops.objects.get(id=shop_id)
        except Shops.DoesNotExist:
            return Response({'error': f'Boutique {shop_id} non trouvee'}, status=status.HTTP_404_NOT_FOUND)
        seller = getattr(request.user, 'seller_account', None)
        if seller and shop.owner != seller:
            return Response({'error': 'Vous ne pouvez recalculer que vos propres boutiques'}, status=status.HTTP_403_FORBIDDEN)
        stats = update_shop_statistics(shop, now().date())
        invalidate_shop_stats_cache(shop.id)
        serializer = self.get_serializer(stats)
        return Response({'success': True, 'message': f'Stats de {shop.name} recalculees', 'data': serializer.data})

    @action(detail=False, methods=['post'], url_path='recalculate-range')
    def recalculate_range(self, request):
        from datetime import timedelta
        shop_id = request.query_params.get('shop_id')
        days = int(request.query_params.get('days', 7))
        if not shop_id:
            return Response({'error': 'shop_id est requis'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            shop = Shops.objects.get(id=shop_id)
        except Shops.DoesNotExist:
            return Response({'error': f'Boutique {shop_id} non trouvee'}, status=status.HTTP_404_NOT_FOUND)
        seller = getattr(request.user, 'seller_account', None)
        if seller and shop.owner != seller:
            return Response({'error': 'Vous ne pouvez recalculer que vos propres boutiques'}, status=status.HTTP_403_FORBIDDEN)
        today = now().date()
        current_date = today - timedelta(days=days - 1)
        count = 0
        while current_date <= today:
            update_shop_statistics(shop, current_date)
            count += 1
            current_date += timedelta(days=1)
        invalidate_shop_stats_cache(shop.id)
        last_stats = ShopStatistics.objects.filter(shop=shop).order_by('-date').first()
        serializer = self.get_serializer(last_stats)
        return Response({'success': True, 'message': f'Stats de {shop.name} recalculees sur {count} jours', 'days_updated': count, 'latest_stats': serializer.data})
