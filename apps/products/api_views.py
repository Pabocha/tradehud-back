from datetime import timedelta

from django.db.models import Q as DQ, Sum, Case, When, IntegerField
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from elasticsearch_dsl import Q as ESQ

from .documents import ProductDocument
from .models import Products, ProductPromotion
from .serializers import ProductListSerializer, ProductPromotionSerializer
from .services.recommendations import RecommendationService, parse_recommendation_params


def _base_product_queryset():
    return (
        Products.objects
        .with_total_stock()
        .select_related("shop", "category")
        .prefetch_related("variants")
    )


def _active_promotion_product_ids():
    """Produits avec une promo active se terminant dans plus de 5 jours (à exclure des vues)."""
    now = timezone.now()
    five_days_from_now = now + timedelta(days=5)
    return set(
        ProductPromotion.objects.filter(
            is_active=True,
            start_at__lte=now,
            end_at__gte=now,
            end_at__gt=five_days_from_now,
        ).values_list('product_id', flat=True).distinct()
    )


def _active_promotions_queryset():
    now = timezone.now()
    five_days_from_now = now + timedelta(days=5)
    return (
        _base_product_queryset()
        .filter(
            promotions__is_active=True,
            promotions__start_at__lte=now,
            promotions__end_at__gte=now,
            promotions__end_at__lte=five_days_from_now,
        )
        .distinct()
    )


def _promotion_remaining_time(promo):
    delta = promo.end_at - timezone.now()
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return {
        'days': max(days, 0),
        'hours': max(hours, 0),
        'minutes': max(minutes, 0),
        'total_seconds': max(int(delta.total_seconds()), 0),
    }


class PromotionsView(APIView):
    def get(self, request):
        products = _active_promotions_queryset()
        serializer = ProductPromotionSerializer(products, many=True, context={'request': request})
        return Response(serializer.data)


class ProductSearchView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '')
        if not query:
            return Response({'error': 'Query string "q" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        search = ProductDocument.search().query(
            ESQ("bool", should=[
                ESQ("match", name={"query": query, "boost": 3, "fuzziness": "AUTO"}),
                ESQ("match_phrase", tags_text={"query": query, "boost": 10, "slop": 0}),
                ESQ("match_phrase", description={"query": query, "boost": 0.5}),
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
        serializer = ProductListSerializer(products_qs, many=True, context={'request': request})
        return Response(serializer.data)


class ProductSearchByShopView(APIView):
    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'error': 'Query string "q" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        limit_per_shop = request.query_params.get('limit_per_shop', 10)
        try:
            limit_per_shop = int(limit_per_shop)
        except (TypeError, ValueError):
            limit_per_shop = 10

        score = (
            Case(When(name__icontains=query, then=3), default=0, output_field=IntegerField()) +
            Case(When(tags__name__icontains=query, then=2), default=0, output_field=IntegerField()) +
            Case(When(description__icontains=query, then=1), default=0, output_field=IntegerField())
        )
        qs = (
            _base_product_queryset()
            .filter(
                DQ(name__icontains=query) |
                DQ(description__icontains=query) |
                DQ(tags__name__icontains=query)
            )
            .distinct()
            .annotate(search_score=score)
            .order_by('-search_score', '-views_count', '-date_added')
        )

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
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(results, request)
        if page is not None:
            return paginator.get_paginated_response(page) 

        return Response(results, status=status.HTTP_200_OK)


class ProductSearchAutocompleteView(APIView):
    def get(self, request):
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


class RecommendationsView(APIView):
    def get(self, request):
        params = parse_recommendation_params(request)

        promoted_ids = _active_promotion_product_ids()
        params["exclude_ids"].update(promoted_ids)

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
            for product in _base_product_queryset().filter(id__in=product_ids)
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
