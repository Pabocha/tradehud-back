from rest_framework import viewsets, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from apps.products.models import (
    Products, ProductVariant, ProductPromotion, GalerieImages,
    StockMovement, ProductPriceTier,
)
from apps.products.serializers import (
    ProductSerializer, ProductListSerializer, ProductDetailSerializer,
    ProductVariantSerializer, VariantTreeSerializer,
    ProductPriceTierSerializer, ProductPromotionSerializer,
    GalerieImageSerializer, StockMovementSerializer, StockAdjustmentSerializer,
    build_variant_tree,
)
from apps.products.filters import ProductFilter
from ecommerce.permissions import IsSeller, IsSellerOfProduct
from django.utils.dateparse import parse_datetime


class SellerProductViewSet(viewsets.ModelViewSet):
    """CRUD Produits — réservé au vendeur propriétaire de la boutique."""
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsSeller]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return (
            Products.objects
            .with_total_stock()
            .select_related("shop", "category")
            .prefetch_related("variants", "galerie_images")
            .filter(shop__owner=self.request.user.seller_account)
        )

    def get_serializer_class(self):
        if self.action in ['list']:
            return ProductListSerializer
        if self.action in ['retrieve']:
            return ProductDetailSerializer
        return ProductSerializer

    def filter_queryset(self, queryset):
        filterset = ProductFilter(data=self.request.query_params, queryset=queryset, request=self.request)
        if filterset.is_valid():
            return filterset.qs
        return queryset

    def perform_create(self, serializer):
        serializer.save(shop=self.request.user.seller_account.shops.first())

    def check_product_ownership(self, request, pk=None):
        product = self.get_object()
        self.check_object_permissions(request, product)
        return product

    @action(detail=True, methods=['post', 'put'], url_path='variants')
    def variants(self, request, pk=None):
        product = self.check_product_ownership(request, pk)
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
                return Response({"detail": "Structure de variantes différente détectée. Supprimez d'abord les variantes existantes avant de changer la structure."}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'PUT':
            product.variants.all().delete()
            if resolved_attributes:
                product.variant_structure = [{'id': a.id, 'code': a.code, 'name': a.name} for a in resolved_attributes]
                product.save(update_fields=['variant_structure'])
        else:
            existing_keys = set()
            for v in product.variants.prefetch_related('attributes').all():
                key = tuple(sorted(v.attributes.values_list('id', flat=True)))
                existing_keys.add(key)
            for combo in combinations:
                key = tuple(sorted([v.id for v in combo['attribute_values']]))
                if key in existing_keys:
                    return Response({"detail": "Combinaison d'attributs déjà existante."}, status=status.HTTP_400_BAD_REQUEST)
            if resolved_attributes:
                product.variant_structure = [{'id': a.id, 'code': a.code, 'name': a.name} for a in resolved_attributes]
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
        return Response({
            "created": ProductVariantSerializer(created, many=True, context={'request': request}).data,
            "all": ProductVariantSerializer(all_variants, many=True, context={'request': request}).data,
        }, status=status_code)

    @action(detail=True, methods=['patch', 'delete'], url_path=r'variants/(?P<variant_id>[^/.]+)')
    def patch_variant(self, request, pk=None, variant_id=None):
        product = self.check_product_ownership(request, pk)
        variant = get_object_or_404(ProductVariant, id=variant_id, product=product)
        if request.method == 'DELETE':
            variant.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        serializer = ProductVariantSerializer(variant, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='sponsor')
    def sponsor(self, request, pk=None):
        product = self.check_product_ownership(request, pk)
        is_sponsored = request.data.get('is_sponsored')
        if is_sponsored is None:
            return Response({"detail": "Champ 'is_sponsored' requis."}, status=400)
        product.is_sponsored = str(is_sponsored).lower() == 'true'
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
            "sponsored_end": product.sponsored_end,
        })

    @action(detail=True, methods=['get', 'post', 'patch', 'delete'], url_path='price-tiers')
    def price_tiers(self, request, pk=None):
        product = self.check_product_ownership(request, pk)
        if request.method == 'GET':
            tiers = product.price_tiers.all()
            serializer = ProductPriceTierSerializer(tiers, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        elif request.method == 'POST':
            serializer = ProductPriceTierSerializer(data=request.data, context={'product': product})
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
            serializer = ProductPriceTierSerializer(tier, data=request.data, partial=True, context={'product': product})
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

    @action(detail=True, methods=['get', 'post', 'patch', 'delete'], url_path='promotions')
    def promotions(self, request, pk=None):
        product = self.check_product_ownership(request, pk)
        if request.method == 'GET':
            promotions = product.promotions.all().order_by('-created_at')
            serializer = ProductPromotionSerializer(promotions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        elif request.method == 'POST':
            serializer = ProductPromotionSerializer(data=request.data, context={'product': product})
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
            serializer = ProductPromotionSerializer(promotion, data=request.data, partial=True, context={'product': product})
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

    @action(detail=True, methods=['get', 'post'], url_path='stock-movements')
    def stock_movements(self, request, pk=None):
        product = self.check_product_ownership(request, pk)
        if request.method == 'GET':
            variant_id = request.query_params.get('variant_id')
            movements = StockMovement.objects.filter(product=product)
            if variant_id:
                movements = movements.filter(variant_id=variant_id)
            movements = movements.select_related('variant', 'created_by')[:50]
            serializer = StockMovementSerializer(movements, many=True)
            return Response(serializer.data)

        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.products.services.stock import record_stock_movement
        try:
            movement = record_stock_movement(
                product=product,
                movement_type=data['movement_type'],
                quantity=data['quantity'],
                reference_type='manual',
                reference_id=data.get('reference_id'),
                note=data.get('note'),
                created_by=request.user,
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class SellerProductGalleryViewSet(viewsets.ViewSet):
    """Gestion de la galerie images — réservé au vendeur propriétaire."""
    permission_classes = [IsAuthenticated, IsSeller]
    parser_classes = [MultiPartParser, FormParser]

    def _get_product(self, product_pk):
        product = get_object_or_404(Products, pk=product_pk)
        self.check_object_permissions(self.request, product)
        return product

    def list(self, request, product_pk=None):
        product = self._get_product(product_pk)
        images = GalerieImages.objects.filter(product=product)
        from apps.products.serializers import GalerieImageSerializer
        serializer = GalerieImageSerializer(images, many=True, context={'request': request})
        return Response(serializer.data)

    def create(self, request, product_pk=None):
        product = self._get_product(product_pk)
        files = request.FILES.getlist('images')
        if not files:
            return Response({'error': 'Aucune image reçue.'}, status=400)
        errors = []
        created = []
        from apps.products.serializers import GalerieImageSerializer
        for file in files:
            data = {'product': product.id, 'image': file}
            serializer = GalerieImageSerializer(data=data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                created.append(serializer.data)
            else:
                errors.append(serializer.errors)
        if errors:
            return Response({'message': 'Certaines images n\'ont pas pu être enregistrées.', 'errors': errors}, status=400)
        return Response({'message': 'Images ajoutées avec succès.', 'data': created}, status=201)

    @action(detail=False, methods=['delete'], url_path='bulk-delete')
    def bulk_delete(self, request, product_pk=None):
        product = self._get_product(product_pk)
        ids = request.data.get("image_ids", [])
        if not isinstance(ids, list):
            return Response({"error": "image_ids must be a list"}, status=400)
        qs = GalerieImages.objects.filter(id__in=ids, product=product)
        deleted_count, _ = qs.delete()
        return Response({"deleted": deleted_count}, status=200)

    @action(detail=False, methods=['post'], url_path='reorder')
    def reorder(self, request, product_pk=None):
        product = self._get_product(product_pk)
        ids = request.data.get("ids", [])
        if not isinstance(ids, list) or not ids:
            return Response({"error": "ids must be a non-empty list"}, status=400)
        images = GalerieImages.objects.filter(id__in=ids, product=product)
        images_by_id = {img.id: img for img in images}
        for pos, img_id in enumerate(ids):
            if img_id in images_by_id:
                images_by_id[img_id].position = pos
                images_by_id[img_id].save(update_fields=['position'])
        return Response({"message": "Ordre mis à jour"}, status=200)

    @action(detail=False, methods=['delete'], url_path='delete-main-image')
    def delete_main_image(self, request, product_pk=None):
        product = self._get_product(product_pk)
        if not product.image:
            return Response({"error": "Pas d'image principale à supprimer"}, status=status.HTTP_400_BAD_REQUEST)
        product.image.delete(save=False)
        product.image = None
        product.save()
        galerie_image = product.galerie_images.order_by('date_added').first()
        if galerie_image:
            product.image = galerie_image.image
            product.save(update_fields=['image'])
            galerie_image.image = None
            galerie_image.save(update_fields=['image'])
            galerie_image.delete()
        return Response(
            {"message": "Image principale supprimée et remplacée" if galerie_image else "Image principale supprimée"},
            status=status.HTTP_200_OK,
        )



