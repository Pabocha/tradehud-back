from apps.products.serializers import *
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound, ValidationError
from django.db.models import Q as DQ, Case, When, IntegerField, F
from rest_framework.decorators import action, api_view
from drf_spectacular.utils import extend_schema, OpenApiExample
from django.utils.dateparse import parse_datetime
from apps.products.models import (
    Products, ProductVariant, ProductPromotion, GalerieImages,
    RecentlyViewedProduct, StockMovement, ProductComparison,
    AttributeValue, Attribute, Colors,
)
from apps.products.filters import ProductFilter
from apps.products.serializers import (
    ProductSerializer, ProductListSerializer, ProductDetailSerializer,
    ProductListWithCountrySerializer, ProductVariantSerializer,
    VariantTreeSerializer, ProductPriceTierSerializer, ProductPromotionSerializer,
    GalerieImageSerializer, ProductGalleryImageSerializer,
    RecentlyViewedProductSerializer, ProductComparisonSerializer,
    ProductPromotionListSerializer, StockMovementSerializer, StockAdjustmentSerializer,
    AttributeValueSerializer, build_variant_tree, compute_pricing_display,
)
from apps.categories.models import Categories


class TenPerPagePagination(PageNumberPagination):
    page_size = 10


@api_view(['GET'])
def countries_with_products(request):
    from django.db.models import Q
    countries_qs = (
        Products.objects.with_total_stock()
        .filter(is_active=True)
        .exclude(country_origin__isnull=True)
        .exclude(country_origin="")
        .filter(Q(total_stock__gt=0) | Q(total_stock__isnull=True, stock_quantity__gt=0))
        .values_list('country_origin', flat=True)
        .distinct()
    )
    countries = []
    seen = set()
    for raw in countries_qs:
        code = (raw or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        countries.append(code)
    countries.sort()
    return Response(["ALL", *countries])


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def filter_queryset(self, queryset):
        filterset = ProductFilter(data=self.request.query_params, queryset=queryset, request=self.request)
        if filterset.is_valid():
            return filterset.qs
        return queryset

    def get_serializer_class(self):
        if self.action in ['list', 'by_country', 'shop_products']:
            return ProductListSerializer
        if self.action in ['search_by_country']:
            return ProductListWithCountrySerializer
        if self.action in ['retrieve']:
            return ProductDetailSerializer
        return ProductSerializer

    def get_queryset(self):
        return (
            Products.objects
            .with_total_stock()
            .select_related("shop", "category")
            .prefetch_related("variants", "galerie_images")
        )

    def _paginate_with_page_size(self, queryset, request, page_size):
        paginator = PageNumberPagination()
        paginator.page_size = page_size
        page = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def _list_response(self, queryset, request, empty_on_invalid_page=False):
        try:
            page = self.paginate_queryset(queryset)
        except NotFound:
            if not empty_on_invalid_page:
                raise
            return Response({"count": queryset.count(), "next": None, "previous": None, "results": []}, status=status.HTTP_200_OK)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-country', permission_classes=[AllowAny])
    def by_country(self, request):
        raw_country = request.query_params.get('country', '')
        country = (raw_country or '').strip().upper()
        if not country or country == 'ALL':
            queryset = (
                self.get_queryset()
                .filter(is_active=True)
                .exclude(country_origin__isnull=True).exclude(country_origin="")
                .exclude(total_stock__isnull=False, total_stock__lte=0)
                .exclude(total_stock__isnull=True, stock_quantity__lte=0)
                .order_by('?')
            )
        else:
            queryset = (
                self.get_queryset()
                .filter(is_active=True, country_origin__iexact=country)
                .exclude(total_stock__isnull=False, total_stock__lte=0)
                .exclude(total_stock__isnull=True, stock_quantity__lte=0)
                .order_by('?')
            )
        return self._list_response(queryset, request)

    @action(detail=False, methods=['get'], url_path='search/by-country')
    def search_by_country(self, request):
        country = request.query_params.get('country', '').strip()
        if not country:
            return Response({'error': 'Query string "country" is required.'}, status=status.HTTP_400_BAD_REQUEST)
        query = request.query_params.get('q', '').strip()
        qs = self.get_queryset().filter(country_origin=country)
        if query:
            qs = qs.filter(DQ(name__icontains=query) | DQ(description__icontains=query) | DQ(tags__name__icontains=query)).distinct()
            score = (
                Case(When(name__icontains=query, then=3), default=0, output_field=IntegerField()) +
                Case(When(tags__name__icontains=query, then=2), default=0, output_field=IntegerField()) +
                Case(When(description__icontains=query, then=1), default=0, output_field=IntegerField())
            )
            qs = qs.annotate(search_score=score).order_by('-search_score', '-views_count', '-date_added')
        else:
            qs = qs.order_by('-views_count', '-date_added')
        serializer = ProductListWithCountrySerializer(qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='promotions/by-shop', permission_classes=[AllowAny])
    def promotions_by_shop(self, request):
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({"error": "Parameter 'shop_id' is required."}, status=status.HTTP_400_BAD_REQUEST)
        queryset = ProductPromotion.objects.filter(product__shop_id=shop_id).select_related('product').order_by('-created_at')
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            is_active_normalized = str(is_active).strip().lower()
            if is_active_normalized in ('true', '1', 'yes'):
                queryset = queryset.filter(is_active=True)
            elif is_active_normalized in ('false', '0', 'no'):
                queryset = queryset.filter(is_active=False)
            else:
                return Response({"error": "Parameter 'is_active' must be true or false."}, status=status.HTTP_400_BAD_REQUEST)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductPromotionSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ProductPromotionSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='shop/(?P<shop_id>[^/.]+)/all', permission_classes=[AllowAny])
    def shop_products(self, request, shop_id=None):
        queryset = self.get_queryset().filter(shop=shop_id)
        if not queryset.exists():
            return Response({'results': [], 'count': 0, 'next': None, 'previous': None})
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = ProductListSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='view', permission_classes=[AllowAny])
    def increment_view(self, request, pk=None):
        product = self.get_object()
        cooldown_seconds = 6 * 60 * 60
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        ip = request.META.get('HTTP_X_FORWARDED_FOR')
        if ip:
            ip = ip.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        key = f'product_view:{product.id}:{session_key}:{ip}'
        last_viewed = request.session.get(key)
        now_ts = timezone.now().timestamp()
        incremented = False
        if not last_viewed or (now_ts - float(last_viewed)) >= cooldown_seconds:
            Products.objects.filter(id=product.id).update(views_count=F('views_count') + 1)
            incremented = True
            request.session[key] = now_ts
            request.session.modified = True
        product.refresh_from_db(fields=['views_count'])
        return Response({'product_id': product.id, 'views_count': product.views_count, 'incremented': incremented}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='variants-list', permission_classes=[AllowAny])
    def variants_list(self, request, pk=None):
        product = self.get_object()
        tree = build_variant_tree(product)
        return Response(tree)

    @action(detail=True, methods=['get'], url_path='available-attributes', permission_classes=[AllowAny])
    def available_attributes(self, request, pk=None):
        product = self.get_object()
        from apps.categories.models import CategoryAttribute
        category = product.category
        if category:
            attr_ids = CategoryAttribute.objects.filter(category=category).values_list('attribute_id', flat=True)
            if attr_ids:
                attributes = Attribute.objects.filter(id__in=attr_ids)
            else:
                attributes = Attribute.objects.filter(is_variant=True)
        else:
            attributes = Attribute.objects.filter(is_variant=True)
        result = []
        for attr in attributes:
            values = AttributeValue.objects.filter(attribute=attr, is_active=True).values('id', 'value', 'code', 'hex_color')
            result.append({'id': attr.id, 'name': attr.name, 'code': attr.code, 'values': list(values)})
        return Response({'structure': product.variant_structure or [], 'attributes': result})


class ProductAttributeValuesView(ListAPIView):
    serializer_class = AttributeValueSerializer
    def get_queryset(self):
        raw_ids = self.request.query_params.getlist('attribute_ids')
        if len(raw_ids) == 1 and ',' in raw_ids[0]:
            raw_ids = raw_ids[0].split(',')
        attribute_ids = [int(i) for i in raw_ids if i.isdigit()]
        queryset = AttributeValue.objects.all().select_related('attribute')
        if attribute_ids:
            queryset = queryset.filter(attribute_id__in=attribute_ids)
        return queryset


class ProductsByCategoryView(ListAPIView):
    serializer_class = ProductListSerializer
    pagination_class = TenPerPagePagination
    def get_queryset(self):
        category_id = self.kwargs.get('category_id')
        try:
            category = Categories.objects.get(id=category_id)
        except Categories.DoesNotExist:
            return Products.objects.none()
        descendant_ids = category.get_descendants(include_self=True).values_list('id', flat=True)
        return Products.objects.with_total_stock().filter(category_id__in=descendant_ids)


class RecentlyViewedProductViewSet(viewsets.ModelViewSet):
    queryset = RecentlyViewedProduct.objects.all()
    serializer_class = RecentlyViewedProductSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product')
        if not product_id:
            return Response({"detail": "Le champ product est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = Products.objects.get(pk=product_id)
        except Products.DoesNotExist:
            return Response({"detail": "Produit introuvable."}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user if request.user.is_authenticated else None
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        ip = self.get_client_ip()
        lookup = {'product': product}
        if user is not None:
            lookup['user'] = user
        else:
            lookup['user'] = None
            lookup['session_key'] = session_key
        obj, created = RecentlyViewedProduct.objects.get_or_create(
            **lookup, defaults={'session_key': session_key, 'ip_address': ip, 'viewed_at': timezone.now()}
        )
        if not created:
            obj.view_count += 1
            obj.viewed_at = timezone.now()
            if user is None and not obj.session_key:
                obj.session_key = session_key
            if ip and obj.ip_address != ip:
                obj.ip_address = ip
            obj.save()
        else:
            Products.objects.filter(pk=product.pk).update(views_count=F('views_count') + 1)
        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def get_queryset(self):
        user = self.request.user
        session_key = self.request.session.session_key
        if user.is_authenticated:
            return RecentlyViewedProduct.objects.filter(user=user).order_by('-viewed_at')
        return RecentlyViewedProduct.objects.filter(session_key=session_key).order_by('-viewed_at')

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        if not self.request.session.session_key:
            self.request.session.create()
        session_key = self.request.session.session_key
        ip = self.get_client_ip()
        product_id = self.request.data.get('product')
        lookup = {'product_id': product_id}
        if user is not None:
            lookup['user'] = user
        else:
            lookup['user'] = None
            lookup['session_key'] = session_key
        obj, created = RecentlyViewedProduct.objects.get_or_create(
            **lookup, defaults={'session_key': session_key, 'ip_address': ip, 'viewed_at': timezone.now()}
        )
        if not created:
            obj.view_count += 1
            obj.viewed_at = timezone.now()
            if user is None and not obj.session_key:
                obj.session_key = session_key
            if ip and obj.ip_address != ip:
                obj.ip_address = ip
            obj.save()
        serializer.instance = obj

    def get_client_ip(self):
        x_forwarded_for = self.request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return self.request.META.get('REMOTE_ADDR')

    @action(detail=False, methods=['get'])
    def most_viewed(self, request):
        user = request.user
        session_key = request.session.session_key
        qs = RecentlyViewedProduct.objects.all()
        if user.is_authenticated:
            qs = qs.filter(user=user)
        else:
            qs = qs.filter(session_key=session_key)
        top = qs.order_by('-view_count')[:10]
        serializer = self.get_serializer(top, many=True)
        return Response(serializer.data)


class ProductComparisonViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def _get_user_or_session(self, request):
        if request.user.is_authenticated:
            return {'user': request.user}
        if not request.session.session_key:
            request.session.create()
        return {'session_key': request.session.session_key}

    def list(self, request):
        lookup = self._get_user_or_session(request)
        comparisons = ProductComparison.objects.filter(**lookup).select_related('product')
        serializer = ProductComparisonSerializer(comparisons, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'product_id requis.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            product = Products.objects.get(id=product_id)
        except Products.DoesNotExist:
            return Response({'error': 'Produit introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        lookup = self._get_user_or_session(request)
        existing_count = ProductComparison.objects.filter(**lookup).count()
        if existing_count >= 4:
            return Response({'error': 'Maximum 4 produits en comparaison.'}, status=status.HTTP_400_BAD_REQUEST)
        obj, created = ProductComparison.objects.get_or_create(**lookup, product=product)
        if not created:
            return Response({'message': 'Déjà en comparaison.'}, status=status.HTTP_200_OK)
        return Response({'message': 'Ajouté à la comparaison.'}, status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        lookup = self._get_user_or_session(request)
        deleted, _ = ProductComparison.objects.filter(**lookup, product_id=pk).delete()
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'error': 'Non trouvé.'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['delete'], url_path='clear')
    def clear(self, request):
        lookup = self._get_user_or_session(request)
        ProductComparison.objects.filter(**lookup).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
