from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import ValidationError
from django.db.models import Sum, Avg
from django.utils.timezone import now
from apps.products.models import Products
from apps.products.serializers import ProductSerializer
from apps.accounts.models import SellerAccount
from ecommerce.permissions import IsSeller
from apps.categories.models import Categories
from apps.orders.models import Orders, OrderLine
from apps.comments.models import Ratings
from ..serializers import (
    ShopSerializer, ShopListSerializer, ShopPublicDetailSerializer,
    ShopUpdateSerializer, ShopStatisticsSerializer,
)
from ..models import Shops, ShopStatistics


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


def update_shop_statistics(shop, date=None):
    if date is None:
        date = now().date()

    order_items = OrderLine.objects.filter(
        shop=shop, order__order_date__date=date, order__status="delivered"
    )
    orders = Orders.objects.filter(
        order_date__date=date, status="delivered", order_lines__shop=shop
    ).distinct()

    total_orders = orders.count()
    total_revenue = orders.aggregate(s=Sum("total_amount"))["s"] or 0
    products_sold = order_items.aggregate(s=Sum("quantity"))["s"] or 0
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

    best_product_data = (
        order_items.values("product")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")
        .first()
    )
    best_product = None
    if best_product_data:
        best_product = Products.objects.get(id=best_product_data["product"])

    top_category_data = (
        order_items.values("product__category")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")
        .first()
    )
    top_category = None
    if top_category_data and top_category_data["product__category"]:
        top_category = Categories.objects.get(id=top_category_data["product__category"])

    shop_avg_rating, shop_number_of_reviews = compute_shop_rating(shop)

    all_products = Products.objects.filter(shop=shop)
    products_low_stock = all_products.filter(stock_quantity__gt=0, stock_quantity__lt=5).count()
    products_out_of_stock = all_products.filter(status='unavailable').count()
    total_stock = all_products.aggregate(s=Sum('stock_quantity'))['s'] or 0
    product_count = all_products.count()
    avg_product_stock = total_stock / product_count if product_count > 0 else 0

    current_datetime = now()
    active_sponsored = all_products.filter(
        is_sponsored=True, sponsored_start__lte=current_datetime, sponsored_end__gte=current_datetime
    ).count()

    total_views = all_products.aggregate(s=Sum('views_count'))['s'] or 0
    avg_views_per_product = total_views / product_count if product_count > 0 else 0
    inventory_turnover = products_sold / avg_product_stock if avg_product_stock > 0 else 0

    stats, _ = ShopStatistics.objects.update_or_create(
        shop=shop, date=date,
        defaults={
            "total_orders": total_orders, "total_revenue": total_revenue,
            "products_sold": products_sold, "average_order_value": avg_order_value,
            "best_selling_product": best_product, "top_category": top_category,
            "shop_average_rating": shop_avg_rating, "shop_number_of_reviews": shop_number_of_reviews,
            "products_low_stock": products_low_stock, "products_out_of_stock": products_out_of_stock,
            "average_product_stock": avg_product_stock, "active_sponsored_products": active_sponsored,
            "total_product_views": total_views, "average_views_per_product": avg_views_per_product,
            "inventory_turnover_ratio": inventory_turnover,
        }
    )
    sync_shop_public_metrics(shop)
    return stats


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
        queryset = self.get_queryset().filter(shop_id=shop_id).order_by('-date')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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
        last_stats = ShopStatistics.objects.filter(shop=shop).order_by('-date').first()
        serializer = self.get_serializer(last_stats)
        return Response({'success': True, 'message': f'Stats de {shop.name} recalculees sur {count} jours', 'days_updated': count, 'latest_stats': serializer.data})
