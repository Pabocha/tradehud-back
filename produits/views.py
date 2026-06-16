import secrets
from decimal import Decimal
from .serializers import *
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
from .documents import ProductDocument
from elasticsearch_dsl import Q
from django.db.models import Q as DQ, Case, When, IntegerField, Sum, F
from django.db.models.functions import Coalesce
from rest_framework.decorators import action, api_view
from drf_spectacular.utils import extend_schema, OpenApiExample
from django.core.cache import cache
from django.utils.dateparse import parse_datetime
from datetime import datetime, timedelta
from .services.recommendations import RecommendationService, parse_recommendation_params
from commandes.models import Orders, LigneCommande


def _sponsored_queryset(base_qs):
    now = timezone.now()
    return base_qs.filter(
        is_sponsored=True,
        sponsored_start__isnull=False,
        sponsored_end__isnull=False,
        sponsored_start__lte=now,
        sponsored_end__gte=now,
    )

class TenPerPagePagination(PageNumberPagination):
    page_size = 10

@api_view(['GET'])
def countries_with_products(request):
    countries_qs = (
        Products.objects.with_total_stock()
        .filter(is_active=True)
        .exclude(country_origin__isnull=True)
        .exclude(country_origin="")
        .filter(
            DQ(total_stock__gt=0) |
            DQ(total_stock__isnull=True, stock_quantity__gt=0)
        )
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

    def get_serializer_class(self):
        if self.action in [
            'list',
            'by_country',
            'sponsored',
            'recent',
            'popular',
            'top_sold',
            'others',
            'combined',
            'recommendations',
            'search',
            'shop_products',
        ]:
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
            .prefetch_related("variants")
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
            return Response({
                "count": queryset.count(),
                "next": None,
                "previous": None,
                "results": [],
            }, status=status.HTTP_200_OK)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    def _home_combined_cache_key(self, request):
        if request.user.is_authenticated:
            return f"home:combined:ids:user:{request.user.id}"
        if not request.session.session_key:
            request.session.create()
        return f"home:combined:ids:session:{request.session.session_key}"

    @extend_schema(
        request=VariantTreeSerializer,
        examples=[
            OpenApiExample(
                "Dynamic Variant Tree",
                value={
                    "structure": ["color", "size"],
                    "variants": [
                        {
                            "value": "Rouge",
                            "children": [
                                {"value": "M", "stock": 13, "sku": "TS-RED-M"},
                                {"value": "XL", "stock": 12, "sku": "TS-RED-XL"},
                            ],
                        }
                    ],
                },
            )
        ],
    )
    @action(detail=True, methods=['post', 'put'], url_path='variants', permission_classes=[IsAuthenticatedOrReadOnly])
    def variants(self, request, pk=None):
        product = self.get_object()
        serializer = VariantTreeSerializer(data=request.data, context={'product': product})
        serializer.is_valid(raise_exception=True)
        combinations = serializer.validated_data['combinations']
        resolved_attributes = serializer.validated_data.get('resolved_attributes', [])

        incoming_codes = [a.code for a in resolved_attributes]
        existing_codes = []
        if product.variant_structure:
            for item in product.variant_structure:
                if isinstance(item, dict) and item.get('code'):
                    existing_codes.append(item['code'])
                elif isinstance(item, str):
                    existing_codes.append(item)

        if existing_codes and incoming_codes and existing_codes != incoming_codes:
            if product.variants.exists():
                return Response(
                    {
                        "detail": (
                            "Structure de variantes différente détectée. "
                            "Supprimez d'abord les variantes existantes avant de changer la structure."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        if request.method == 'PUT':
            product.variants.all().delete()
            if resolved_attributes:
                product.variant_structure = [
                    {'id': a.id, 'code': a.code, 'name': a.name} for a in resolved_attributes
                ]
                product.save(update_fields=['variant_structure'])
        else:
            existing_keys = set()
            for v in product.variants.prefetch_related('attributes').all():
                key = tuple(sorted(v.attributes.values_list('id', flat=True)))
                existing_keys.add(key)

            for combo in combinations:
                key = tuple(sorted([v.id for v in combo['attribute_values']]))
                if key in existing_keys:
                    return Response(
                        {"detail": "Combinaison d'attributs déjà existante."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            if resolved_attributes:
                product.variant_structure = [
                    {'id': a.id, 'code': a.code, 'name': a.name} for a in resolved_attributes
                ]
                product.save(update_fields=['variant_structure'])

        created = []
        for combo in combinations:
            create_kwargs = {'product': product}
            if combo.get('stock_quantity') is not None:
                create_kwargs['stock_quantity'] = combo['stock_quantity']
            if combo.get('sku'):
                create_kwargs['sku'] = combo['sku']
            if combo.get('weight') is not None:
                create_kwargs['weight'] = combo['weight']
            if combo.get('price_override') is not None:
                create_kwargs['price_override'] = combo['price_override']
            if combo.get('custom_attributes') is not None:
                create_kwargs['custom_attributes'] = combo['custom_attributes']

            variant = ProductVariant.objects.create(**create_kwargs)
            variant.attributes.set(combo['attribute_values'])
            created.append(variant)

        status_code = status.HTTP_201_CREATED if request.method == 'POST' else status.HTTP_200_OK
        all_variants = product.variants.prefetch_related('attributes').all()
        return Response(
            {
                "created": ProductVariantSerializer(created, many=True, context={'request': request}).data,
                "all": ProductVariantSerializer(all_variants, many=True, context={'request': request}).data,
            },
            status=status_code
        )

    @action(
        detail=True,
        methods=['patch', 'delete'],
        url_path=r'variants/(?P<variant_id>[^/.]+)',
        permission_classes=[IsAuthenticatedOrReadOnly],
    )
    def patch_variant(self, request, pk=None, variant_id=None):
        product = self.get_object()
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
        if request.method == 'DELETE':
            variant.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = ProductVariantSerializer(
            variant,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    

     # ACTION : filtrage par pays et popularitÃ©
    @action(detail=False, methods=['get'], url_path='by-country', permission_classes=[AllowAny])
    def by_country(self, request):
        raw_country = request.query_params.get('country', '')
        country = (raw_country or '').strip().upper()

        if not country or country == 'ALL':
            queryset = (
                self.get_queryset()
                .filter(is_active=True)
                .exclude(country_origin__isnull=True)
                .exclude(country_origin="")
                .exclude(total_stock__isnull=False, total_stock__lte=0)
                .exclude(total_stock__isnull=True, stock_quantity__lte=0)
                .order_by('?')
            )
        else:
            queryset = (
                self.get_queryset()
                .filter(is_active=True)
                .filter(country_origin__iexact=country)
                .exclude(total_stock__isnull=False, total_stock__lte=0)
                .exclude(total_stock__isnull=True, stock_quantity__lte=0)
                .order_by('?')
            )

        # Appliquer la pagination par defaut (settings)
        return self._list_response(queryset, request)

    @action(detail=True, methods=['post'], url_path='sponsor', permission_classes=[IsAuthenticatedOrReadOnly])
    def sponsor(self, request, pk=None):
        product = self.get_object()
        is_sponsored = request.data.get('is_sponsored')

        if is_sponsored is None:
            return Response({"detail": "Champ 'is_sponsored' requis."}, status=400)

        product.is_sponsored = str(is_sponsored).lower() == 'true'

        # Gestion des dates
        start = request.data.get('sponsored_start')
        end = request.data.get('sponsored_end')

        if product.is_sponsored:
            if not start or not end:
                return Response({"detail": "Les champs 'sponsored_start' et 'sponsored_end' sont requis."}, status=400)

            product.sponsored_start = parse_datetime(start)
            product.sponsored_end = parse_datetime(end)

            if not product.sponsored_start or not product.sponsored_end:
                return Response({"detail": "Les dates sont invalides (format ISO 8601 requis)."}, status=400)

            if product.sponsored_end <= product.sponsored_start:
                return Response({"detail": "La date de fin doit être postérieure à la date de début."}, status=400)

        else:
            product.sponsored_start = None
            product.sponsored_end = None

        product.save()

        return Response({
            "detail": f"Produit {'sponsorisé' if product.is_sponsored else 'désponsorisé'} avec succès.",
            "is_sponsored": product.is_sponsored,
            "sponsored_start": product.sponsored_start,
            "sponsored_end": product.sponsored_end
        })

    @action(detail=False, methods=['get'])
    def sponsored(self, request):
        """Produits sponsorisés (paginated)"""
        qs = _sponsored_queryset(self.get_queryset()).order_by('?')
        return self._list_response(qs, request, empty_on_invalid_page=True)

    @action(detail=False, methods=['get'])
    def recent(self, request):
        """Produits récents (paginated)"""
        one_week_ago = datetime.now() - timedelta(weeks=1)
        qs = self.get_queryset().filter(date_added__gte=one_week_ago).order_by('-date_added')
        return self._list_response(qs, request, empty_on_invalid_page=True)

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Produits populaires (paginated)"""
        qs = (
            self.get_queryset()
            .filter(
                DQ(variants__lignecommande__order__status='delivered') |
                DQ(lignecommande__order__status='delivered', lignecommande__variant__isnull=True)
            )
            .annotate(
                total_sold=Coalesce(
                    Sum('variants__lignecommande__quantity', filter=DQ(variants__lignecommande__order__status='delivered')),
                    0
                ) + Coalesce(
                    Sum('lignecommande__quantity', filter=DQ(lignecommande__order__status='delivered', lignecommande__variant__isnull=True)),
                    0
                )
            )
            .order_by('-total_sold', '-views_count')
        )
        return self._list_response(qs, request, empty_on_invalid_page=True)

    @action(detail=False, methods=['get'])
    def combined(self, request):
        """Retourne recent/sponsored/popular/others ensemble"""
        one_week_ago = datetime.now() - timedelta(weeks=1)
        sponsored_products = _sponsored_queryset(self.get_queryset()).order_by('?')[:10]
        recent_products = self.get_queryset().filter(date_added__gte=one_week_ago).order_by('-date_added')[:10]
        popular_products = (
           self.get_queryset()
            .filter(
                DQ(variants__lignecommande__order__status='delivered') |
                DQ(lignecommande__order__status='delivered', lignecommande__variant__isnull=True)
            )
            .annotate(
                total_sold=Coalesce(
                    Sum('variants__lignecommande__quantity', filter=DQ(variants__lignecommande__order__status='delivered')),
                    0
                ) + Coalesce(
                    Sum('lignecommande__quantity', filter=DQ(lignecommande__order__status='delivered', lignecommande__variant__isnull=True)),
                    0
                )
            )
            .order_by('-total_sold', '-views_count')[:10]
        )

        combined_ids = list({
            *[p.id for p in sponsored_products],
            *[p.id for p in recent_products],
            *[p.id for p in popular_products],
        })
        cache.set(self._home_combined_cache_key(request), combined_ids, timeout=60 * 30)

        return Response({
            "recent": ProductListSerializer(recent_products, many=True, context={'request': request}).data,
            "sponsored": ProductListSerializer(sponsored_products, many=True, context={'request': request}).data,
            "popular": ProductListSerializer(popular_products, many=True, context={'request': request}).data,
        })

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def recommendations(self, request):
        """
        Recommandations personnalisees.

        Query params:
        - limit (1..50)
        - context: home|product_detail|cart
        - exclude_ids: csv
        - seed_product_id: requis pour context=product_detail
        - refresh: true|false
        - debug: true|false (details du score)
        """
        params = parse_recommendation_params(request)
        if params["context"] == "home":
            already_shown_ids = cache.get(self._home_combined_cache_key(request), []) or []
            params["exclude_ids"].update(already_shown_ids)

        if params["context"] == "product_detail" and not params["seed_product_id"]:
            return Response(
                {"error": "seed_product_id est requis pour context=product_detail"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if params["seed_product_id"] and not Products.objects.filter(id=params["seed_product_id"]).exists():
            return Response({"error": "Produit seed introuvable"}, status=status.HTTP_404_NOT_FOUND)

        service = RecommendationService(request.user, params)
        payload = service.build()

        product_ids = [item["product_id"] for item in payload["items"]]
        products_map = {
            product.id: product
            for product in self.get_queryset().filter(id__in=product_ids)
        }

        items = []
        for item in payload["items"]:
            product_obj = products_map.get(item["product_id"])
            if product_obj is None:
                continue
            row = {
                "product_id": item["product_id"],
                "score": item["score"],
                "reason": item["reason"],
                "product": ProductListSerializer(product_obj, context={"request": request}).data,
            }
            if params["debug"] and "score_breakdown" in item:
                row["score_breakdown"] = item["score_breakdown"]
            items.append(row)

        return Response(
            {
                "count": len(items),
                "context": payload["context"],
                "generated_at": payload["generated_at"],
                "items": items,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Recherche via Elastic (proxy)"""
        query = request.query_params.get('q', '')
        if not query:
            return Response({'error': 'Query string "q" is required.'}, status=status.HTTP_400_BAD_REQUEST)
        search = ProductDocument.search().query(
            Q("bool", should=[
                Q("match", name={"query": query, "boost": 3, "fuzziness": "AUTO"}),
                Q("match_phrase", tags_text={"query": query, "boost": 10, "slop": 0}),
                Q("match_phrase", description={"query": query, "boost": 0.5}),
            ], minimum_should_match=1)
        ).sort('_score')
        results = search.execute()
        ids_in_order = [int(hit.meta.id) for hit in results]
        if not ids_in_order:
            return Response([])
        order = Case(
            *[When(id=pk, then=pos) for pos, pk in enumerate(ids_in_order)],
            output_field=IntegerField()
        )
        products_qs = Products.objects.filter(id__in=ids_in_order).order_by(order)
        serializer = self.get_serializer(products_qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='search/by-shop')
    def search_by_shop(self, request):
        """
        Recherche simple (ORM) qui retourne les boutiques matchÃ©es
        avec les produits correspondants.
        """
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'error': 'Query string "q" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        limit_per_shop = request.query_params.get('limit_per_shop', 10)
        try:
            limit_per_shop = int(limit_per_shop)
        except (TypeError, ValueError):
            limit_per_shop = 10

        qs = (
            self.get_queryset()
            .filter(
                DQ(name__icontains=query) |
                DQ(description__icontains=query) |
                DQ(tags__name__icontains=query)
            )
            .distinct()
        )

        score = (
            Case(When(name__icontains=query, then=3), default=0, output_field=IntegerField()) +
            Case(When(tags__name__icontains=query, then=2), default=0, output_field=IntegerField()) +
            Case(When(description__icontains=query, then=1), default=0, output_field=IntegerField())
        )

        qs = qs.annotate(search_score=score).order_by('-search_score', '-views_count', '-date_added')

        grouped = {}
        for product in qs:
            shop = product.shop
            if shop.id not in grouped:
                grouped[shop.id] = {
                    "shop": {
                        "id": shop.id,
                        "name": shop.name,
                        "logo": shop.logo.url if shop.logo else None,
                        "is_verified": shop.is_verifted,
                        'is_top_seller': shop.is_top_seller,
                        "country_origin": str(shop.country_origin) if shop.country_origin else None,
                        "average_rating": float(shop.average_rating or 0),
                        "date_created": shop.date_created.isoformat() if shop.date_created else None,
                    },
                    "products": [],
                }
            if limit_per_shop and len(grouped[shop.id]["products"]) >= limit_per_shop:
                continue
            grouped[shop.id]["products"].append(
                ProductListSerializer(product, context={'request': request}).data
            )

        results = list(grouped.values())
        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(results, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='search/by-country')
    def search_by_country(self, request):
        """
        Recherche simple (ORM) par pays du produit.
        """
        country = request.query_params.get('country', '').strip()
        if not country:
            return Response({'error': 'Query string "country" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        query = request.query_params.get('q', '').strip()

        qs = self.get_queryset().filter(country_origin=country)
        if query:
            qs = qs.filter(
                DQ(name__icontains=query) |
                DQ(description__icontains=query) |
                DQ(tags__name__icontains=query)
            ).distinct()

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

    @action(detail=False, methods=['get'], url_path='search/autocomplete')
    def autocomplete(self, request):
        prefix = request.query_params.get('q', '')
        if not prefix:
            return Response({'error': 'Query string "q" is required.'}, status=status.HTTP_400_BAD_REQUEST)
        search = ProductDocument.search()
        search = search.suggest('product-suggest', prefix, completion={
            "field": "name_suggest",
            "fuzzy": {"fuzziness": 1}
        })
        suggestions = search.execute().suggest
        options = suggestions['product-suggest'][0]['options']
        results = list(dict.fromkeys([opt['text'] for opt in options]))
        return Response(results)

    @action(detail=True, methods=['get', 'post'], url_path='images', parser_classes=[MultiPartParser, FormParser])
    def images(self, request, pk=None):
        """GET: liste les images de la galerie; POST: ajoute des images"""
        if request.method == 'GET':
            images = GalerieImages.objects.filter(product=pk)
            serializer = GalerieImageSerializer(images, many=True, context={'request': request}).data
            return Response(serializer)

        # POST
        product = get_object_or_404(Products, pk=pk)
        files = request.FILES.getlist('images')
        if not files:
            return Response({'error': 'Aucune image reÃ§ue.'}, status=400)
        errors = []
        created = []
        for file in files:
            data = {'product': product.id, 'image': file}
            serializer = GalerieImageSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                created.append(serializer.data)
            else:
                errors.append(serializer.errors)
        if errors:
            return Response({'message': 'Certaines images nâ€™ont pas pu Ãªtre enregistrÃ©es.', 'errors': errors}, status=400)
        return Response({'message': 'Images ajoutÃ©es avec succÃ¨s.', 'data': created}, status=201)

    @action(detail=True, methods=['delete'], url_path='delete-main-image')
    def delete_main_image(self, request, pk=None):
        product = get_object_or_404(Products, id=pk)
        if not product.image:
            return Response({"error": "Pas d'image principale Ã  supprimer"}, status=status.HTTP_400_BAD_REQUEST)
        product.image.delete(save=False)
        product.image = None
        product.save()
        # Remplacer par une image de la galerie si disponible
        galerie_image = product.galerie_images.order_by('date_added').first()
        if galerie_image:
            product.image = galerie_image.image
            product.save(update_fields=['image'])
            # DÃ©tacher l'image de la galerie sans supprimer le fichier
            galerie_image.image = None
            galerie_image.save(update_fields=['image'])
            galerie_image.delete()
        return Response({"message": "Image principale supprimÃ©e et remplacÃ©e" if galerie_image else "Image principale supprimÃ©e"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='delete-gallery-images')
    def delete_gallery_images(self, request):
        ids = request.data.get("image_ids", [])
        if not isinstance(ids, list):
            return Response({"error": "image_ids must be a list"}, status=400)
        qs = GalerieImages.objects.filter(id__in=ids)
        for img in qs:
            print("SUPPRESSION â†’", img.id, img.image.name)
        deleted_count, _ = qs.delete()
        return Response({"deleted": deleted_count}, status=200)

    @action(detail=True, methods=['get', 'post', 'patch', 'delete'], url_path='price-tiers', permission_classes=[IsAuthenticatedOrReadOnly])
    def price_tiers(self, request, pk=None):
        """
        GÃ¨re les paliers de prix d'un produit.
        
        GET /api/products/12/price-tiers/
        â†’ RÃ©cupÃ¨re tous les paliers du produit
        
        POST /api/products/12/price-tiers/
        â†’ CrÃ©e un nouveau palier
        Body: {"min_quantity": 10, "max_quantity": 50, "price": 12000}
        
        PATCH /api/products/12/price-tiers/?tier_id=5
        â†’ Modifie un palier existant
        
        DELETE /api/products/12/price-tiers/?tier_id=5
        â†’ Supprime un palier
        """
        product = self.get_object()
        
        # ðŸ”½ GET: RÃ©cupÃ©rer les paliers de ce produit
        if request.method == 'GET':
            tiers = product.price_tiers.all()
            serializer = ProductPriceTierSerializer(tiers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        elif request.method == 'POST':
            serializer = ProductPriceTierSerializer(
                data=request.data,
                context={'product': product}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'PATCH':
            tier_id = request.query_params.get('tier_id')
            if not tier_id:
                return Response({"error": "Parameter 'tier_id' is required."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                tier = product.price_tiers.get(id=tier_id)
            except ProductPriceTier.DoesNotExist:
                return Response({"error": "Price tier not found."}, status=status.HTTP_404_NOT_FOUND)
            
            serializer = ProductPriceTierSerializer(
                tier,
                data=request.data,
                partial=True,
                context={'product': product}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        elif request.method == 'DELETE':
            tier_id = request.query_params.get('tier_id')
            if not tier_id:
                return Response({"error": "Parameter 'tier_id' is required."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                tier = product.price_tiers.get(id=tier_id)
            except ProductPriceTier.DoesNotExist:
                return Response({"error": "Price tier not found."}, status=status.HTTP_404_NOT_FOUND)
            
            tier.delete()
            return Response({"message": "Price tier deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get', 'post', 'patch', 'delete'], url_path='promotions', permission_classes=[IsAuthenticatedOrReadOnly])
    def promotions(self, request, pk=None):
        """
        GÃ¨re les promotions d'un produit.

        GET /api/products/{id}/promotions/
        POST /api/products/{id}/promotions/
        PATCH /api/products/{id}/promotions/?promotion_id=5
        DELETE /api/products/{id}/promotions/?promotion_id=5
        """
        product = self.get_object()

        if request.method == 'GET':
            promotions = product.promotions.all().order_by('-created_at')
            serializer = ProductPromotionSerializer(promotions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        elif request.method == 'POST':
            serializer = ProductPromotionSerializer(
                data=request.data,
                context={'product': product}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'PATCH':
            promotion_id = request.query_params.get('promotion_id')
            if not promotion_id:
                return Response({"error": "Parameter 'promotion_id' is required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                promotion = product.promotions.get(id=promotion_id)
            except ProductPromotion.DoesNotExist:
                return Response({"error": "Promotion not found."}, status=status.HTTP_404_NOT_FOUND)

            serializer = ProductPromotionSerializer(
                promotion,
                data=request.data,
                partial=True,
                context={'product': product}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            promotion_id = request.query_params.get('promotion_id')
            if not promotion_id:
                return Response({"error": "Parameter 'promotion_id' is required."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                promotion = product.promotions.get(id=promotion_id)
            except ProductPromotion.DoesNotExist:
                return Response({"error": "Promotion not found."}, status=status.HTTP_404_NOT_FOUND)

            promotion.delete()
            return Response({"message": "Promotion deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='promotions/by-shop', permission_classes=[AllowAny])
    def promotions_by_shop(self, request):
        """
        Liste toutes les promotions des produits d'une boutique.

        GET /api/products/promotions/by-shop/?shop_id=<id>&is_active=true|false
        """
        shop_id = request.query_params.get('shop_id')
        if not shop_id:
            return Response({"error": "Parameter 'shop_id' is required."}, status=status.HTTP_400_BAD_REQUEST)

        queryset = ProductPromotion.objects.filter(
            product__shop_id=shop_id
        ).select_related('product').order_by('-created_at')

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            is_active_normalized = str(is_active).strip().lower()
            if is_active_normalized in ('true', '1', 'yes'):
                queryset = queryset.filter(is_active=True)
            elif is_active_normalized in ('false', '0', 'no'):
                queryset = queryset.filter(is_active=False)
            else:
                return Response(
                    {"error": "Parameter 'is_active' must be true or false."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductPromotionSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = ProductPromotionSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='shop/(?P<shop_id>[^/.]+)/all', permission_classes=[IsAuthenticated])
    def shop_products(self, request, shop_id=None):
        shop_product = self.get_queryset().filter(shop=shop_id)
        serializer = ProductListSerializer(shop_product, many=True, context={'request': request})
        if not shop_product.exists():
            return Response({'message': 'Aucune boutique trouvÃ©e pour ce vendeur.'}, status=404)
        return Response({'message': 'success', 'data': serializer.data})

    @action(detail=True, methods=['post'], url_path='view', permission_classes=[AllowAny])
    def increment_view(self, request, pk=None):
        """
        IncrÃ©mente les vues avec un cooldown par session/IP.
        """
        product = self.get_object()

        # Cooldown (en secondes) pour Ã©viter de compter trop souvent
        cooldown_seconds = 6 * 60 * 60  # 6 heures

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
        return Response(
            {
                'product_id': product.id,
                'views_count': product.views_count,
                'incremented': incremented,
            },
            status=status.HTTP_200_OK
        )
    
class QuoteViewSet(viewsets.ModelViewSet):
    queryset = (
        Quote.objects
        .select_related('user', 'shop', 'converted_order')
        .prefetch_related('lines__product', 'lines__variant__product')
    )
    serializer_class = QuoteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.is_staff or user.is_superuser:
            return qs

        if hasattr(user, 'seller_account'):
            return qs.filter(DQ(user=user) | DQ(shop__owner=user.seller_account)).distinct()

        return qs.filter(user=user)

    def perform_create(self, serializer):
        shop = serializer.validated_data.get('shop')
        if hasattr(self.request.user, 'seller_account') and shop and shop.owner_id == self.request.user.seller_account.id:
            raise ValidationError("Vous ne pouvez pas creer une quote pour votre propre boutique.")
        serializer.save(user=self.request.user, status='draft')

    def _is_shop_owner(self, quote, user):
        return hasattr(user, 'seller_account') and quote.shop.owner_id == user.seller_account.id

    def _is_quote_participant(self, quote, user):
        return quote.user_id == user.id or self._is_shop_owner(quote, user)

    def _is_expired(self, quote):
        return quote.expires_at <= timezone.now()

    def _create_order_from_quote(self, request, quote, delivery_address, delivery_cost, mark_paid=False):
        lines = list(quote.lines.select_related('product', 'variant', 'variant__product').all())
        if not lines:
            raise ValueError('Quote sans lignes.')

        with transaction.atomic():
            order = Orders.objects.create(
                customer=request.user,
                delivery_address=delivery_address,
                delivery_cost=delivery_cost,
                total_amount=Decimal('0.00'),
                payment_status='paid' if mark_paid else 'pending',
                payment_first_name=(request.data.get('first_name') or '').strip() or None,
                payment_last_name=(request.data.get('last_name') or '').strip() or None,
                payment_phone_number=(request.data.get('phone_number') or '').strip() or None,
            )

            subtotal = Decimal('0.00')
            for line in lines:
                qty = int(line.quantity or 0)
                if qty <= 0:
                    raise ValueError('Quantite invalide dans la quote.')

                product = line.product or (line.variant.product if line.variant_id else None)
                if product is None:
                    raise ValueError('Ligne de quote sans produit/variante valide.')

                if line.variant_id:
                    variant = ProductVariant.objects.select_for_update().get(id=line.variant_id)
                    if variant.stock_quantity < qty:
                        raise ValueError(f"Stock insuffisant pour la variante {variant.id}.")
                    variant.stock_quantity -= qty
                    variant.save(update_fields=['stock_quantity'])
                else:
                    variant = None
                    product_locked = Products.objects.select_for_update().get(id=product.id)
                    if product_locked.stock_quantity is None or product_locked.stock_quantity < qty:
                        raise ValueError(f"Stock insuffisant pour le produit {product_locked.id}.")
                    product_locked.stock_quantity -= qty
                    product_locked.save(update_fields=['stock_quantity'])

                unit_price = getattr(line.negotiated_price, 'amount', line.negotiated_price)
                line_total = Decimal(str(unit_price)) * qty
                subtotal += line_total

                LigneCommande.objects.create(
                    order=order,
                    variant=variant,
                    product=product if variant is None else None,
                    shop=quote.shop,
                    quantity=qty,
                    unit_price=unit_price,
                )

            order.total_amount = subtotal + delivery_cost
            order.save(update_fields=['total_amount'])

            quote.status = 'converted'
            quote.converted_order = order
            quote.payment_link_token = None
            quote.payment_link_expires_at = None
            quote.save(update_fields=['status', 'converted_order', 'payment_link_token', 'payment_link_expires_at', 'updated_at'])

        return order

    @action(detail=False, methods=['get'], url_path='my')
    def my_quotes(self, request):
        qs = self.get_queryset().filter(user=request.user).order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='shop')
    def shop_quotes(self, request):
        if not hasattr(request.user, 'seller_account'):
            return Response({'error': 'Acces reserve aux vendeurs.'}, status=status.HTTP_403_FORBIDDEN)

        qs = self.get_queryset().filter(shop__owner=request.user.seller_account)
        shop_id = request.query_params.get('shop_id')
        if shop_id:
            qs = qs.filter(shop_id=shop_id)

        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        qs = qs.order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='send')
    def send(self, request, pk=None):
        quote = self.get_object()

        if not self._is_shop_owner(quote, request.user):
            return Response({'error': 'Seul le vendeur peut envoyer la proposition.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status not in ('draft', 'countered'):
            return Response({'error': 'Statut invalide pour envoyer la quote.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'sent'
        quote.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='counter')
    def counter(self, request, pk=None):
        quote = self.get_object()

        if not self._is_quote_participant(quote, request.user):
            return Response({'error': 'Non autorise.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status not in ('sent', 'countered'):
            return Response({'error': 'Statut invalide pour contre-proposition.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'countered'
        quote.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        quote = self.get_object()

        if quote.user_id != request.user.id:
            return Response({'error': 'Seul le client peut accepter la quote.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status not in ('sent', 'countered'):
            return Response({'error': 'Statut invalide pour acceptation.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'accepted'
        quote.accepted_at = timezone.now()
        quote.save(update_fields=['status', 'accepted_at', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        quote = self.get_object()

        if not self._is_quote_participant(quote, request.user):
            return Response({'error': 'Non autorise.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status in ('converted', 'rejected'):
            return Response({'error': 'Action non autorisee pour ce statut.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'rejected'
        quote.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='payment-link')
    def payment_link(self, request, pk=None):
        quote = self.get_object()

        if not self._is_shop_owner(quote, request.user):
            return Response({'error': 'Seul le vendeur peut generer le lien de paiement.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status != 'accepted':
            return Response(
                {'error': 'La quote doit etre acceptee avant generation du lien.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            expires_in_minutes = int(request.data.get('expires_in_minutes', 1440))
        except (TypeError, ValueError):
            return Response({'error': "Champ 'expires_in_minutes' invalide."}, status=status.HTTP_400_BAD_REQUEST)

        expires_in_minutes = max(5, min(expires_in_minutes, 10080))
        token = secrets.token_urlsafe(32)
        link_expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)

        quote.payment_link_token = token
        quote.payment_link_expires_at = link_expires_at
        quote.payment_link_sent_at = timezone.now()
        quote.save(update_fields=['payment_link_token', 'payment_link_expires_at', 'payment_link_sent_at', 'updated_at'])

        preview_relative_url = f"/api/products/quotes/pay/{token}/preview/"
        pay_relative_url = f"/api/products/quotes/pay/{token}/"
        return Response(
            {
                'quote_id': quote.id,
                'token': token,
                'payment_link_expires_at': quote.payment_link_expires_at,
                'preview_url': request.build_absolute_uri(preview_relative_url),
                'pay_url': request.build_absolute_uri(pay_relative_url),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path=r'pay/(?P<token>[^/.]+)/preview')
    def pay_preview(self, request, token=None):
        quote = Quote.objects.filter(payment_link_token=token).prefetch_related(
            'lines__product', 'lines__variant__product'
        ).select_related('shop', 'user').first()

        if not quote:
            return Response({'error': 'Lien de paiement invalide.'}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id:
            return Response({'error': 'Ce lien ne vous appartient pas.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.converted_order_id:
            return Response({'error': 'Cette quote est deja convertie.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.payment_link_expires_at is None or quote.payment_link_expires_at <= timezone.now():
            return Response({'error': 'Lien de paiement expire.'}, status=status.HTTP_400_BAD_REQUEST)

        lines_payload = []
        subtotal = Decimal('0.00')
        for line in quote.lines.all():
            product = line.product or (line.variant.product if line.variant_id else None)
            unit_price = getattr(line.negotiated_price, 'amount', line.negotiated_price)
            line_total = Decimal(str(unit_price)) * int(line.quantity or 0)
            subtotal += line_total
            lines_payload.append({
                'line_id': line.id,
                'product_id': product.id if product else None,
                'product_name': product.name if product else None,
                'variant_id': line.variant_id,
                'quantity': line.quantity,
                'negotiated_unit_price': unit_price,
                'line_total': line_total,
            })

        return Response(
            {
                'quote_id': quote.id,
                'shop': {'id': quote.shop_id, 'name': quote.shop.name},
                'expires_at': quote.expires_at,
                'payment_link_expires_at': quote.payment_link_expires_at,
                'lines': lines_payload,
                'subtotal': subtotal,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path=r'pay/(?P<token>[^/.]+)')
    def pay_by_token(self, request, token=None):
        quote = Quote.objects.filter(payment_link_token=token).select_related('shop', 'user').first()

        if not quote:
            return Response({'error': 'Lien de paiement invalide.'}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id:
            return Response({'error': 'Ce lien ne vous appartient pas.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.converted_order_id:
            return Response(
                {'detail': 'Quote deja convertie.', 'order_id': quote.converted_order_id},
                status=status.HTTP_200_OK,
            )
        if quote.payment_link_expires_at is None or quote.payment_link_expires_at <= timezone.now():
            return Response({'error': 'Lien de paiement expire.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.status != 'accepted':
            return Response(
                {'error': 'Statut de quote invalide pour paiement. Quote acceptee requise.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_address = (request.data.get('delivery_address') or '').strip()
        if not delivery_address:
            return Response({'error': "Champ 'delivery_address' requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delivery_cost = Decimal(str(request.data.get('delivery_cost', 0) or 0))
        except Exception:
            return Response({'error': "Champ 'delivery_cost' invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = self._create_order_from_quote(
                request=request,
                quote=quote,
                delivery_address=delivery_address,
                delivery_cost=delivery_cost,
                mark_paid=True,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'quote_id': quote.id,
                'order_id': order.id,
                'status': quote.status,
                'payment_status': order.payment_status,
                'total_amount': order.total_amount,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        quote = self.get_object()

        if quote.user_id != request.user.id:
            return Response({'error': 'Seul le client de la quote peut convertir en commande.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status != 'accepted':
            return Response({'error': 'La quote doit etre acceptee avant checkout.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        if quote.converted_order_id:
            return Response(
                {
                    'detail': 'Quote deja convertie.',
                    'order_id': quote.converted_order_id,
                },
                status=status.HTTP_200_OK,
            )

        delivery_address = (request.data.get('delivery_address') or '').strip()
        if not delivery_address:
            return Response({'error': "Champ 'delivery_address' requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delivery_cost = Decimal(str(request.data.get('delivery_cost', 0) or 0))
        except Exception:
            return Response({'error': "Champ 'delivery_cost' invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = self._create_order_from_quote(
                request=request,
                quote=quote,
                delivery_address=delivery_address,
                delivery_cost=delivery_cost,
                mark_paid=False,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'quote_id': quote.id,
                'order_id': order.id,
                'status': quote.status,
                'total_amount': order.total_amount,
            },
            status=status.HTTP_201_CREATED,
        )

class ProductAttributeValuesView(ListAPIView):
    serializer_class = AttributeValueSerializer

    def get_queryset(self):
        raw_ids = self.request.query_params.getlist('attribute_ids')

        # Support: ?attribute_ids=1,2,3
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

        # Obtenir la catÃ©gorie + ses descendants
        descendant_ids = category.get_descendants(include_self=True).values_list('id', flat=True)

        return Products.objects.with_total_stock().filter(category_id__in=descendant_ids)

class RecentlyViewedProductViewSet(viewsets.ModelViewSet):
    queryset = RecentlyViewedProduct.objects.all()
    serializer_class = RecentlyViewedProductSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product')
        if not product_id:
            return Response(
                {"detail": "Le champ product est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = Products.objects.get(pk=product_id)
        except Products.DoesNotExist:
            return Response(
                {"detail": "Produit introuvable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            **lookup,
            defaults={
                'session_key': session_key,
                'ip_address': ip,
                'viewed_at': timezone.now()
            }
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
            Products.objects.filter(pk=product.pk).update(
                views_count=F('views_count') + 1
            )

        serializer = self.get_serializer(obj)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def get_queryset(self):
        user = self.request.user
        session_key = self.request.session.session_key
        if user.is_authenticated:
            return RecentlyViewedProduct.objects.filter(user=user).order_by('-viewed_at')
        return RecentlyViewedProduct.objects.filter(session_key=session_key).order_by('-viewed_at')

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None

        # GÃ©nÃ¨re une session manuellement si nÃ©cessaire (pour utilisateur anonyme)
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
            **lookup,
            defaults={
                'session_key': session_key,
                'ip_address': ip,
                'viewed_at': timezone.now()
            }
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
        """Retourne les produits les plus consultÃ©s par l'utilisateur"""
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

    
class ColorsView(ListAPIView):
    serializer_class = ColorSerializer
    queryset = Colors.objects.all()
    pagination_class = None




