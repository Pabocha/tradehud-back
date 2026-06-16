from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.generics import ListAPIView
from .models import PayementMethod, Favorites, Coupon, Banner, Notifications
from .serializers import NotificationSerializer, PaymentMethodSerializer, FavoriteSerializer, CouponSerializer, BannerSerializer
from django.db import models
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status, viewsets
# Create your views here.

class CouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Coupon.objects.all().order_by('-id')

        return Coupon.objects.filter(
            models.Q(audience='public') |
            models.Q(audience='targeted', users=user) |
            models.Q(audience='single', users=user)
        ).distinct().order_by('-id')

    @action(detail=False, methods=['get'], url_path='my-coupons', permission_classes=[IsAuthenticated])
    def my_coupons(self, request):
        coupons = self.get_queryset()

        valid = []
        invalid = []

        for coupon in coupons:
            is_valid = coupon.is_valid_now()
            serialized = CouponSerializer(coupon, context={'request': request}).data
            serialized["valid"] = is_valid
            if is_valid:
                valid.append(serialized)
            else:
                invalid.append(serialized)

        return Response({
            "valid_coupons": valid,
            "invalid_coupons": invalid,
        })

class PaymentMethodView(ListAPIView):
    serializer_class = PaymentMethodSerializer
    queryset = PayementMethod.objects.all()
    pagination_class = None

class BannerView(ListAPIView):
    serializer_class = BannerSerializer
    queryset = Banner.objects.filter(is_active=True)

    def get_queryset(self):
        target = self.request.query_params.get('target')
        if target:
            return self.queryset.filter(target=target).order_by('-priority')
        return self.queryset.order_by('-priority')

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'delete', 'patch', 'post']

    def get_queryset(self):
        return Notifications.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['patch'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        serializer = self.get_serializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response(
            {'detail': 'Notifications marquees comme lues.', 'updated_count': updated},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path='bulk-delete')
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list):
            return Response(
                {'detail': 'Le champ ids doit etre une liste.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        valid_ids = []
        for value in ids:
            try:
                valid_ids.append(int(value))
            except (TypeError, ValueError):
                continue

        deleted_count, _ = self.get_queryset().filter(id__in=valid_ids).delete()
        return Response(
            {'detail': 'Notifications supprimees.', 'deleted_count': deleted_count},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['delete'], url_path='clear-all')
    def clear_all(self, request):
        deleted_count, _ = self.get_queryset().delete()
        return Response(
            {'detail': 'Toutes les notifications ont ete supprimees.', 'deleted_count': deleted_count},
            status=status.HTTP_200_OK,
        )


class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Favorites.objects.filter(user=self.request.user)
            .select_related('product', 'product__shop')
            .prefetch_related('product__promotions', 'product__price_tiers')
        )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def is_favorite(self, request):
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response({"error": "product_id manquant"}, status=400)
        exists = Favorites.objects.filter(user=request.user, product_id=product_id).exists()
        return Response({"favorited": exists})
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def toggle(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({"error": "product_id requis"}, status=status.HTTP_400_BAD_REQUEST)

        fav, created = Favorites.objects.get_or_create(user=request.user, product_id=product_id)

        if not created:
            fav.delete()
            return Response({"favorited": False}, status=status.HTTP_200_OK)
        else:
            return Response({"favorited": True}, status=status.HTTP_201_CREATED)
        
# def apply_coupon_to_order(order, coupon_code):
#     try:
#         coupon = Coupon.objects.get(code__iexact=coupon_code)
#     except Coupon.DoesNotExist:
#         raise ValidationError("Code promo invalide.")

#     if not coupon.is_valid():
#         raise ValidationError("Ce bon d'achat n'est plus valide.")

#     if coupon.min_order_amount and order.total < coupon.min_order_amount:
#         raise ValidationError("Le montant minimum pour utiliser ce bon n’est pas atteint.")

#     if coupon.discount_type == 'percent':
#         reduction = (order.total * coupon.discount_value) / 100
#     if coupon.target_products.exists():
#         return sum(item.total for item in order.items.filter(product__in=coupon.target_products.all()))
#     if coupon.target_categories.exists():
#         return sum(item.total for item in order.items.filter(product__category__in=coupon.target_categories.all()))
#     # return order.total
#     else:
#         reduction = coupon.discount_value

#     order.total -= min(reduction, order.total)  # on évite les totaux négatifs
#     coupon.uses += 1
#     coupon.save()
#     order.coupon = coupon
#     order.save()

 
