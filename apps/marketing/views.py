from rest_framework import viewsets, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from .serializers import AnnouncementSerializer, BannerSerializer, PublicBannerSerializer, CampaignSerializer, FlashSaleSerializer, FlashSaleListSerializer, FlashSaleWithProductsSerializer
from .models import Banner, Announcement, Campaign, FlashSale


class AnnouncementView(ListAPIView):
    serializer_class = AnnouncementSerializer
    queryset = Announcement.objects.filter(is_active=True)


class BannerView(ListAPIView):
    serializer_class = PublicBannerSerializer
    queryset = Banner.objects.filter(is_active=True)

    def get_queryset(self):
        qs = Banner.objects.filter(is_active=True)
        target = self.request.query_params.get('target')
        banner_type = self.request.query_params.get('type')
        if target:
            qs = qs.filter(target=target)
        if banner_type:
            qs = qs.filter(type=banner_type)
        return qs.order_by('-priority')


class CampaignViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Campaign.objects.all()
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CampaignSerializer
        return CampaignSerializer

    def get_queryset(self):
        qs = Campaign.objects.filter(is_active=True)
        now = self.request.query_params.get('active_only')
        if now == 'true':
            from django.utils import timezone
            t = timezone.now()
            qs = qs.filter(start_at__lte=t, end_at__gte=t)
        return qs

    @action(detail=False, methods=['get'], url_path='active')
    def active_campaigns(self, request):
        from django.utils import timezone
        t = timezone.now()
        qs = Campaign.objects.filter(is_active=True, start_at__lte=t, end_at__gte=t)
        serializer = CampaignSerializer(qs, many=True)
        return Response(serializer.data)


class FlashSaleViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == 'list':
            return FlashSaleListSerializer
        if self.action == 'products':
            return FlashSaleWithProductsSerializer
        return FlashSaleSerializer

    def get_queryset(self):
        from django.utils import timezone
        t = timezone.now()
        return FlashSale.objects.filter(
            is_active=True, start_at__lte=t, end_at__gte=t
        ).select_related('campaign')

    @action(detail=False, methods=['get'], url_path='products')
    def products(self, request):
        from django.utils import timezone
        t = timezone.now()
        qs = FlashSale.objects.filter(
            is_active=True, start_at__lte=t, end_at__gte=t
        ).select_related('campaign').prefetch_related(
            'target_products', 'target_categories', 'target_shops'
        )
        serializer = FlashSaleWithProductsSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='by-product/(?P<product_id>[^/.]+)')
    def by_product(self, request, product_id=None):
        from django.utils import timezone
        t = timezone.now()
        qs = FlashSale.objects.filter(
            is_active=True, start_at__lte=t, end_at__gte=t,
            target_type='all'
        ) | FlashSale.objects.filter(
            is_active=True, start_at__lte=t, end_at__gte=t,
            target_type='product', target_products__id=product_id
        )
        serializer = FlashSaleListSerializer(qs.distinct(), many=True)
        return Response(serializer.data)