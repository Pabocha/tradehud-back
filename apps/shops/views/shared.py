from django.shortcuts import get_object_or_404
from rest_framework import viewsets, permissions, filters, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Sum, Avg
from apps.products.models import Products
from apps.products.serializers import ProductSerializer
from apps.accounts.models import ShopFollow
from apps.categories.models import Categories
from django_filters.rest_framework import DjangoFilterBackend
from ..serializers import ShopSerializer, ShopListSerializer, ShopPublicDetailSerializer, ShopStatisticsSerializer
from ..models import Shops, ShopStatistics


class PublicShopViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ShopPublicDetailSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Shops.objects.filter(is_deleted=False).select_related('owner', 'owner__user').prefetch_related('categories', 'payment_method')

    def retrieve(self, request, pk=None):
        shop = get_object_or_404(
            Shops.objects.select_related('owner', 'owner__user').prefetch_related('categories', 'payment_method'),
            pk=pk, is_deleted=False
        )
        serializer = ShopPublicDetailSerializer(shop, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class ShopListViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = ShopListSerializer

    def get_queryset(self):
        return Shops.objects.filter(is_deleted=False).order_by('-id')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        category_id = request.query_params.get('category_id')
        if category_id:
            try:
                category = Categories.objects.get(pk=int(category_id))
            except (ValueError, Categories.DoesNotExist):
                return Response({'detail': 'category_id invalide.'}, status=status.HTTP_400_BAD_REQUEST)
            category_ids = category.get_descendants(include_self=True).values_list('id', flat=True)
            queryset = queryset.filter(categories__id__in=category_ids).distinct()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ShopListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ShopListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)


class ProductsByShopViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shop_id = self.request.query_params.get('shop_id')
        if shop_id is not None:
            return Products.objects.filter(shop=shop_id)
        return Products.objects.none()


class ShopFollowViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = None

    @action(detail=True, methods=['get'], url_path='is-followed')
    def is_followed(self, request, pk=None):
        try:
            shop = Shops.objects.get(pk=pk)
        except Shops.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)
        is_following = ShopFollow.objects.filter(user=request.user, shop=shop).exists()
        total_follow = ShopFollow.objects.filter(shop=shop).count()
        return Response({"followed": is_following, "total_follow": total_follow}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='follow')
    def follow(self, request, pk=None):
        try:
            shop = Shops.objects.get(pk=pk)
        except Shops.DoesNotExist:
            return Response({"detail": "Boutique introuvable."}, status=status.HTTP_404_NOT_FOUND)
        follow_obj, created = ShopFollow.objects.get_or_create(user=request.user, shop=shop)
        if not created:
            follow_obj.delete()
            return Response({"followed": False, "detail": "Boutique desabonnee."}, status=status.HTTP_200_OK)
        return Response({"followed": True, "detail": "Boutique suivie."}, status=status.HTTP_201_CREATED)


class PublicShopStatisticsViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ShopStatistics.objects.select_related('shop', 'best_selling_product', 'top_category')
    serializer_class = ShopStatisticsSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['shop', 'date']
    ordering = ['-date']

    def get_queryset(self):
        qs = super().get_queryset()
        shop_id = self.request.query_params.get('shop_id')
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        date_from = self.request.query_params.get('date_from')
        date_to = self.request.query_params.get('date_to')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    @action(detail=False, methods=['get'], url_path='by-shop/(?P<shop_id>[^/.]+)')
    def by_shop(self, request, shop_id=None):
        queryset = self.get_queryset().filter(shop_id=shop_id).order_by('-date')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
