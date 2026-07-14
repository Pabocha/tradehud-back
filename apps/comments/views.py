from django.shortcuts import render
from rest_framework import permissions, viewsets, status
from .models import Ratings, ShopRatings
from .serializers import RatingSerializer, ShopRatingSerializer
from .permissions import IsOwnerOrReadOnly
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.orders.models import Orders

# Create your views here.

class RatingViewSet(viewsets.ModelViewSet):
    queryset = Ratings.objects.all()
    serializer_class = RatingSerializer
    # Lecture publique; création/édition/suppression réservées aux utilisateurs authentifiés
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        # Marquer comme édité et sauvegarder
        instance = serializer.save()
        if not instance.is_edited:
            instance.is_edited = True
            instance.save()

    def get_queryset(self):
        """
        Récupérer tous les commentaires d’un produit (avec pagination).
        Accessible sans authentification.
        """
        queryset = super().get_queryset().select_related('user')  # Optimisation
        product_id = self.request.query_params.get("product")
        if product_id:
            queryset = queryset.filter(product_id=product_id).order_by("-id")
        return queryset

    @action(detail=False, methods=["get"], url_path="by-products")
    def by_products(self, request):
        """
        Récupérer les commentaires de l’utilisateur connecté
        sur plusieurs produits à la fois (sans pagination).
        Exemple: /api/ratings/by-products/?ids=1,2,3
        Nécessite une authentification.
        """
        products = request.query_params.get("ids")
        if not products:
            return Response({"error": "Merci de fournir des IDs de produits"}, status=status.HTTP_400_BAD_REQUEST)
        product_ids = products.split(",")
        ratings = Ratings.objects.filter(
            product_id__in=product_ids,
            user=request.user   # 🔑 filtre sur l’utilisateur connecté
        ).order_by("-id")
        serializer = self.get_serializer(ratings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated], url_path="my-reviews")
    def my_reviews(self, request):
        qs = self.get_queryset().filter(user=request.user).select_related('product').order_by('-id')
        data = []
        for review in qs:
            item = self.get_serializer(review).data
            product = getattr(review, 'product', None)
            if product is not None:
                image_url = None
                try:
                    if getattr(product, 'image', None):
                        image_url = request.build_absolute_uri(product.image.url)
                except Exception:
                    image_url = None
                item['product_detail'] = {
                    'id': product.id,
                    'name': getattr(product, 'name', None),
                    'image': image_url,
                }
            data.append(item)
        return Response(data, status=status.HTTP_200_OK)


    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="order-review-status",
    )
    def order_review_status(self, request):
        """
        Retourne les produits et boutiques d'une commande avec statut d'avis.
        GET /api/ratings/products/order-review-status/?order=<id>
        """
        order_id = request.query_params.get("order")
        if not order_id:
            return Response(
                {"detail": "Paramètre 'order' requis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order = Orders.objects.filter(id=order_id, customer=request.user).first()
        if not order:
            return Response(
                {"detail": "Commande introuvable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        order_items = list(
            order.order_lines.select_related("product", "variant__product", "shop").all()
        )

        products_by_id = {}
        shops_by_id = {}

        for item in order_items:
            product = item.product or (item.variant.product if item.variant_id else None)
            if product:
                if product.id not in products_by_id:
                    products_by_id[product.id] = {
                        "product": {
                            "id": product.id,
                            "name": product.name,
                        },
                        "order_item_ids": [],
                    }
                products_by_id[product.id]["order_item_ids"].append(item.id)

            if item.shop_id and item.shop_id not in shops_by_id:
                shop_logo = item.shop.logo.url if getattr(item.shop, "logo", None) else None
                shops_by_id[item.shop_id] = {
                    "shop": {
                        "id": item.shop.id,
                        "name": item.shop.name,
                        "logo": request.build_absolute_uri(shop_logo) if shop_logo else None,
                    }
                }

        product_reviews = (
            Ratings.objects.filter(user=request.user, order_item__order=order)
            .select_related("product", "order_item", "user")
            .order_by("-id")
        )
        product_review_map = {}
        for review in product_reviews:
            if review.product_id not in product_review_map:
                product_review_map[review.product_id] = review

        shop_reviews = (
            ShopRatings.objects.filter(user=request.user, order=order)
            .select_related("shop", "order", "user")
            .order_by("-id")
        )
        shop_review_map = {}
        for review in shop_reviews:
            if review.shop_id not in shop_review_map:
                shop_review_map[review.shop_id] = review

        products_payload = []
        for product_id, info in products_by_id.items():
            review = product_review_map.get(product_id)
            products_payload.append(
                {
                    **info,
                    "has_review": review is not None,
                    "review": RatingSerializer(review, context={"request": request}).data if review else None,
                }
            )

        shops_payload = []
        for shop_id, info in shops_by_id.items():
            review = shop_review_map.get(shop_id)
            shops_payload.append(
                {
                    **info,
                    "has_review": review is not None,
                    "review": ShopRatingSerializer(review, context={"request": request}).data if review else None,
                }
            )

        return Response(
            {
                "order_id": order.id,
                "products": products_payload,
                "shops": shops_payload,
            },
            status=status.HTTP_200_OK,
        )


from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ShopRatings
from .serializers import ShopRatingSerializer
from .permissions import IsOwnerOrReadOnly


class ShopRatingViewSet(viewsets.ModelViewSet):
    """
    Gestion des avis des boutiques

    Cas couverts :
    1️⃣ Avis publics d'une boutique (tous les users)
    2️⃣ Avis des boutiques d'une commande (client connecté)
    3️⃣ Avis des boutiques du propriétaire
    4️⃣ Avis d'une boutique pour une commande précise
    """

    queryset = ShopRatings.objects.all()
    serializer_class = ShopRatingSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
        IsOwnerOrReadOnly
    ]

    def _paginated_response(self, queryset):
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # 🔹 Base queryset (NE CONTIENT AUCUNE LOGIQUE METIER)
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("user", "shop", "order")
        )

    # 🔹 Création
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # 🔹 Marquer l’avis comme modifié
    def perform_update(self, serializer):
        instance = serializer.save()
        if not instance.is_edited:
            instance.is_edited = True
            instance.save()

    # ==========================================================
    # 1️⃣ Avis publics d'une boutique (TOUS LES USERS)
    # GET /ratings/shops/by-shop/?shop=ID
    # ==========================================================
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.AllowAny],
        url_path="by-shop"
    )
    def by_shop(self, request):
        shop_id = request.query_params.get("shop")
        if not shop_id:
            return Response(
                {"detail": "Paramètre 'shop' requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = self.get_queryset().filter(shop_id=shop_id).order_by("-id")
        return self._paginated_response(qs)

    # ==========================================================
    # 2️⃣ Avis des boutiques d'une commande (CLIENT CONNECTÉ)
    # GET /ratings/shops/my-order-reviews/?order=ID
    # ==========================================================
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="my-order-reviews"
    )
    def my_order_reviews(self, request):
        order_id = request.query_params.get("order")
        if not order_id:
            return Response(
                {"detail": "Paramètre 'order' requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = self.get_queryset().filter(
            order_id=order_id,
            user=request.user
        ).order_by("-id")

        return self._paginated_response(qs)

    # ==========================================================
    # 3️⃣ Avis des boutiques du PROPRIÉTAIRE
    # GET /ratings/shops/my-shops-reviews/
    # ==========================================================
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="my-shops-reviews"
    )
    def my_shops_reviews(self, request):
        qs = self.get_queryset().filter(
            shop__owner=request.user
        ).order_by("-id")

        return self._paginated_response(qs)

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="my-reviews"
    )
    def my_reviews(self, request):
        qs = self.get_queryset().filter(user=request.user).select_related('shop').order_by('-id')
        data = []
        for review in qs:
            item = self.get_serializer(review).data
            shop = getattr(review, 'shop', None)
            if shop is not None:
                logo_url = None
                try:
                    if getattr(shop, 'logo', None):
                        logo_url = request.build_absolute_uri(shop.logo.url)
                except Exception:
                    logo_url = None
                item['shop_detail'] = {
                    'id': shop.id,
                    'name': getattr(shop, 'name', None),
                    'logo': logo_url,
                }
            data.append(item)
        return Response(data, status=status.HTTP_200_OK)


    # ==========================================================
    # 4️⃣ Avis d'une boutique pour une commande précise
    # GET /ratings/shops/by-shop-and-order/?shop=ID&order=ID
    # ==========================================================
    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="by-shop-and-order"
    )
    def by_shop_and_order(self, request):
        shop_id = request.query_params.get("shop")
        order_id = request.query_params.get("order")

        if not shop_id or not order_id:
            return Response(
                {"detail": "Paramètres 'shop' et 'order' requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        qs = self.get_queryset().filter(
            shop_id=shop_id,
            order_id=order_id
        ).order_by("-id")

        return self._paginated_response(qs)
