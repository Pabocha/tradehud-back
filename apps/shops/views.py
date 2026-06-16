from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, filters, status
from django.utils.timezone import now
from apps.vendor.produits.models import Products
from comptes.models import SellerAccount
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Sum, Count, F, Avg
from commandes.models import Orders, LigneCommande
from comptes.models import ShopFollow
from .serializers import *
from .models import ShopStatistics
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from .statistics_serializers import ShopStatisticsSerializer
from apps.vendor.produits.serializers import ProductSerializer
from apps.vendor.categories.models import Categories


def sync_shop_public_metrics(shop):
    """
    Synchronise les KPI persistés dans la table Shops (vue publique/admin).
    Ces valeurs sont globales (toutes dates), pas limitées au jour recalculé.
    """
    delivered_orders = Orders.objects.filter(
        status="delivered",
        lignes_commande__shop=shop
    ).distinct()
    delivered_items = LigneCommande.objects.filter(
        shop=shop,
        order__status="delivered"
    )

    total_orders = delivered_orders.count()
    number_sale = delivered_items.aggregate(s=Sum("quantity"))["s"] or 0

    from apps.client.commentaires.models import ShopRatings
    reviews = ShopRatings.objects.filter(shop=shop)
    average_rating = reviews.aggregate(avg=Avg("rating"))["avg"] or 0
    number_of_reviews = reviews.count()

    Shops.objects.filter(pk=shop.pk).update(
        total_orders=total_orders,
        number_sale=number_sale,
        average_rating=average_rating,
        number_of_reviews=number_of_reviews,
    )


class ShopViewset(viewsets.ModelViewSet):
    queryset = Shops.objects.all()
    serializer_class = ShopSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly] 
    parser_classes = [MultiPartParser, FormParser, JSONParser]


    def perform_create(self, serializer):
        try:
            seller_account = self.request.user.seller_account
        except SellerAccount.DoesNotExist:
            raise ValidationError({'owner': 'Aucun compte vendeur lié à cet utilisateur.'})

        serializer.save(owner=seller_account)

    def _get_seller_account(self):
        user = self.request.user
        if not user.is_authenticated:
            return None
        try:
            return user.seller_account
        except SellerAccount.DoesNotExist:
            return None

    def get_queryset(self):
        seller_account = self._get_seller_account()
        if seller_account is None:
            raise ValidationError({'owner': 'Aucun compte vendeur lie a cet utilisateur.'})
        return Shops.objects.filter(owner=seller_account)
    
    def retrieve(self, request, pk=None):
        seller_account = self._get_seller_account()
        if seller_account is None:
            raise ValidationError({'owner': 'Aucun compte vendeur lie a cet utilisateur.'})
        shop = get_object_or_404(Shops, pk=pk, owner=seller_account)
        serializer = ShopSerializer(shop, context={'request': request})
        return Response(serializer.data)

    
    @action(detail=False, methods=['get'], url_path='shop-list')
    def shop_list(self, request):
        queryset = Shops.objects.all().order_by('-id')
        category_id = request.query_params.get('category_id')
        if category_id:
            try:
                category = Categories.objects.get(pk=int(category_id))
            except (ValueError, Categories.DoesNotExist):
                return Response(
                    {'detail': 'category_id invalide.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            category_ids = category.get_descendants(include_self=True).values_list('id', flat=True)
            queryset = queryset.filter(categories__id__in=category_ids).distinct()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ShopListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ShopListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(
        detail=True,
        methods=['get'],
        permission_classes=[permissions.AllowAny],
        url_path='public-detail'
    )
    def public_detail(self, request, pk=None):
        shop = get_object_or_404(
            Shops.objects.select_related('owner', 'owner__user').prefetch_related('categories', 'payment_method'),
            pk=pk,
            is_deleted=False
        )
        serializer = ShopPublicDetailSerializer(shop, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    # 🔸 PATCH /api/shop/<id>/update-fields/
    @action(detail=True, methods=['patch'], url_path='update-fields')
    def update_fields(self, request, pk=None):
        try:
            shop = self.get_object()
        except Shops.DoesNotExist:
            return Response({'detail': 'Boutique introuvable.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = ShopUpdateSerializer(shop, data=request.data, partial=True, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({'detail': 'Boutique mise à jour avec succès.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='is-followed')
    def is_followed(self, request, pk=None):
        try:
            shop = Shops.objects.get(pk=pk)
        except Shops.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)

        # Vérifie si l'utilisateur suit cette boutique
        is_following = ShopFollow.objects.filter(user=request.user, shop=shop).exists()

        # Compte le nombre total de followers
        total_follow = ShopFollow.objects.filter(shop=shop).count()

        return Response({
            "followed": is_following,
            "total_follow": total_follow,
        }, status=status.HTTP_200_OK)

class ProductsByShopViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shop_id = self.request.query_params.get('shop_id')
        if shop_id is not None:
            return Products.objects.filter(shop=shop_id)
        return Products.objects.none()
    

def update_shop_statistics(shop, date=None):
    """
    Met à jour les statistiques complètes d'une boutique pour une date donnée
    
    Structure correcte des modèles :
    - Orders : customer, order_date, status, lignes_commande (relation)
    - LigneCommande : order, product, shop, quantity, unit_price
    - Products : shop, stock_quantity, status, views_count, is_sponsored, sponsored_start, sponsored_end
    - Categories : name
    - ShopRatings : shop, rating
    """
    if date is None:
        date = now().date()

    # ===== RÉCUPÉRER LES COMMANDES VIA LIGNES COMMANDE =====
    # Les lignes de commande du shop pour ce jour
    order_items = LigneCommande.objects.filter(
        shop=shop, 
        order__order_date__date=date,
        order__status="delivered"
    )
    
    # Les commandes uniques associées à ces lignes
    orders = Orders.objects.filter(
        order_date__date=date,
        status="delivered",
        lignes_commande__shop=shop
    ).distinct()

    # ===== MÉTRIQUES DE VENTES =====
    total_orders = orders.count()
    total_revenue = orders.aggregate(s=Sum("total_amount"))["s"] or 0
    products_sold = order_items.aggregate(s=Sum("quantity"))["s"] or 0
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

    # ===== MEILLEUR PRODUIT =====
    best_product_data = (
        order_items.values("product")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")
        .first()
    )
    best_product = None
    if best_product_data:
        best_product = Products.objects.get(id=best_product_data["product"])

    # ===== MEILLEURE CATÉGORIE =====
    top_category_data = (
        order_items.values("product__category")
        .annotate(total_qty=Sum("quantity"))
        .order_by("-total_qty")
        .first()
    )
    top_category = None
    if top_category_data and top_category_data["product__category"]:
        top_category = Categories.objects.get(id=top_category_data["product__category"])

    # ===== SATISFACTION & RÉPUTATION =====
    from apps.client.commentaires.models import ShopRatings
    shop_reviews = ShopRatings.objects.filter(shop=shop)
    shop_avg_rating = shop_reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    shop_number_of_reviews = shop_reviews.count()

    # ===== INVENTAIRE =====
    all_products = Products.objects.filter(shop=shop)
    products_low_stock = all_products.filter(stock_quantity__gt=0, stock_quantity__lt=5).count()
    products_out_of_stock = all_products.filter(status='unavailable').count()
    
    total_stock = all_products.aggregate(s=Sum('stock_quantity'))['s'] or 0
    product_count = all_products.count()
    avg_product_stock = total_stock / product_count if product_count > 0 else 0

    # ===== SPONSORING ACTIF =====
    current_datetime = now()
    active_sponsored = all_products.filter(
        is_sponsored=True,
        sponsored_start__lte=current_datetime,
        sponsored_end__gte=current_datetime
    ).count()

    # ===== TRAFIC PRODUITS =====
    total_views = all_products.aggregate(s=Sum('views_count'))['s'] or 0
    avg_views_per_product = total_views / product_count if product_count > 0 else 0

    # ===== INVENTORY TURNOVER RATIO =====
    inventory_turnover = products_sold / avg_product_stock if avg_product_stock > 0 else 0

    # ===== CRÉER OU METTRE À JOUR LES STATS =====
    stats, created = ShopStatistics.objects.update_or_create(
        shop=shop, 
        date=date,
        defaults={
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "products_sold": products_sold,
            "average_order_value": avg_order_value,
            "best_selling_product": best_product,
            "top_category": top_category,
            "shop_average_rating": shop_avg_rating,
            "shop_number_of_reviews": shop_number_of_reviews,
            "products_low_stock": products_low_stock,
            "products_out_of_stock": products_out_of_stock,
            "average_product_stock": avg_product_stock,
            "active_sponsored_products": active_sponsored,
            "total_product_views": total_views,
            "average_views_per_product": avg_views_per_product,
            "inventory_turnover_ratio": inventory_turnover,
        }
    )
    # Maintenir les champs agrégés de la table Shops synchronisés.
    sync_shop_public_metrics(shop)
    return stats
    

class ShopStatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet pour consulter les statistiques des boutiques.
    
    Endpoints:
    - GET /api/shop/shop-statistics/ → liste toutes les stats
    - GET /api/shop/shop-statistics/?shop_id=<id> → stats d'une boutique
    - GET /api/shop/shop-statistics/?shop_id=<id>&date_from=<date>&date_to=<date> → stats sur une période
    - GET /api/shop/shop-statistics/<id>/ → détail d'une stat
    - GET /api/shop/shop-statistics/by-shop/<shop_id>/ → stats d'une boutique (alternative)
    """
    queryset = ShopStatistics.objects.select_related('shop', 'best_selling_product', 'top_category')
    serializer_class = ShopStatisticsSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['shop', 'date']
    ordering = ['-date']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        shop_id = self.request.query_params.get('shop_id')
        if shop_id:
            queryset = queryset.filter(shop_id=shop_id)
        
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        
        # DEBUG
        print(f"Queryset count: {queryset.count()}")
        print(f"Dates in queryset: {list(queryset.values_list('date', flat=True))}")
        print(f"Shop in queryset: {queryset}")
        
        return queryset

    @action(detail=False, methods=['get'], url_path='by-shop/(?P<shop_id>[^/.]+)')
    def by_shop(self, request, shop_id=None):
        """Récupère les stats d'une boutique avec pagination."""
        queryset = self.get_queryset().filter(shop_id=shop_id).order_by('-date')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'], url_path='recalculate-today')
    def recalculate_today(self, request):
        """
        Endpoint pour forcer le recalcul des stats d'aujourd'hui.
        
        POST /api/shop/shop-statistics/recalculate-today/?shop_id=<id>
        
        Params:
        - shop_id (requis): ID de la boutique
        
        Returns:
        - stats recalculées
        """
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response(
                {'error': 'shop_id est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            shop = Shops.objects.get(id=shop_id)
        except Shops.DoesNotExist:
            return Response(
                {'error': f'Boutique {shop_id} non trouvée'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Vérifier que l'utilisateur est le propriétaire (optionnel, pour la sécurité)
        if request.user.is_authenticated and hasattr(request.user, 'seller_account'):
            if shop.owner != request.user.seller_account:
                return Response(
                    {'error': 'Vous ne pouvez recalculer que vos propres boutiques'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        try:
            # Recalculer les stats pour aujourd'hui
            today = now().date()
            stats = update_shop_statistics(shop, today)
            serializer = self.get_serializer(stats)
            return Response({
                'success': True,
                'message': f'Stats de {shop.name} recalculées pour {today}',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': f'Erreur recalcul: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='recalculate-range')
    def recalculate_range(self, request):
        """
        Endpoint pour recalculer les stats sur une plage de jours.
        
        POST /api/shop/shop-statistics/recalculate-range/?shop_id=<id>&days=<days>
        
        Params:
        - shop_id (requis): ID de la boutique
        - days (optionnel, défaut 7): Nombre de jours à recalculer
        
        Returns:
        - Nombre de jours recalculés + dernière stat
        """
        from datetime import timedelta
        
        shop_id = request.query_params.get('shop_id')
        days = int(request.query_params.get('days', 7))
        
        if not shop_id:
            return Response(
                {'error': 'shop_id est requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            shop = Shops.objects.get(id=shop_id)
        except Shops.DoesNotExist:
            return Response(
                {'error': f'Boutique {shop_id} non trouvée'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Vérifier que l'utilisateur est le propriétaire
        if request.user.is_authenticated and hasattr(request.user, 'seller_account'):
            if shop.owner != request.user.seller_account:
                return Response(
                    {'error': 'Vous ne pouvez recalculer que vos propres boutiques'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        try:
            today = now().date()
            count = 0
            current_date = today - timedelta(days=days-1)
            
            while current_date <= today:
                update_shop_statistics(shop, current_date)
                count += 1
                current_date += timedelta(days=1)
            
            # Retourner la dernière stat
            last_stats = ShopStatistics.objects.filter(shop=shop).order_by('-date').first()
            serializer = self.get_serializer(last_stats)
            
            return Response({
                'success': True,
                'message': f'Stats de {shop.name} recalculées sur {count} jours',
                'days_updated': count,
                'latest_stats': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': f'Erreur recalcul: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    

# class ShopListWithProductsView(ListAPIView):
#     queryset = Shops.objects.all()
#     serializer_class = ShopListSerializer
#     permission_classes = [AllowAny]

#     def get_serializer_context(self):
#         context = super().get_serializer_context()
#         context['request'] = self.request  # pour accéder à `request.query_params`
#         return context



# class ShopViewset(viewsets.ModelViewSet):
#     queryset = Shops.objects.all()
#     serializer_class = ShopSerializer
#     permission_classes = [IsAuthenticated]

#     def create(self, request, *args, **kwargs):
#         print("=== Données reçues du front ===")
#         print(request.data)

#         # Optionnel : aussi voir les fichiers reçus
#         print("=== Fichiers reçus ===")
#         print(request.FILES)

#         return super().create(request, *args, **kwargs)


# class ShopCreateView(CreateAPIView):
#     queryset = Shops.objects.all()
#     serializer_class = ShopSerializer
