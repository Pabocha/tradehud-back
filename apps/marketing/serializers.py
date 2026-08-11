from rest_framework import serializers
from .models import Banner, Announcement, Campaign, FlashSale


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['id', 'title', 'description', 'badge', 'badge_color']


class BannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = '__all__'


class PublicBannerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ['id', 'image', 'title', 'description', 'tag', 'cta', 'badge', 'badge_color', 'link', 'type', 'priority']


class CampaignSerializer(serializers.ModelSerializer):
    is_currently_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'slug', 'description', 'badge', 'badge_color',
            'banner_image', 'start_at', 'end_at', 'is_active',
            'is_currently_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class FlashSaleSerializer(serializers.ModelSerializer):
    is_currently_active = serializers.BooleanField(read_only=True)
    campaign_name = serializers.CharField(source='campaign.name', read_only=True, default=None)

    class Meta:
        model = FlashSale
        fields = [
            'id', 'name', 'description',
            'start_at', 'end_at', 'is_active', 'is_currently_active',
            'target_type', 'target_categories', 'target_shops', 'target_products',
            'max_uses', 'uses', 'campaign', 'campaign_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'uses', 'created_at', 'updated_at']


class FlashSaleListSerializer(serializers.ModelSerializer):
    """Serializer allégé pour la liste publique des flash sales."""
    is_currently_active = serializers.BooleanField(read_only=True)
    remaining_time = serializers.SerializerMethodField()

    class Meta:
        model = FlashSale
        fields = [
            'id', 'name', 'description',
            'start_at', 'end_at', 'is_currently_active', 'target_type',
            'max_uses', 'uses', 'remaining_time',
        ]

    def get_remaining_time(self, obj):
        from django.utils.timezone import now
        delta = obj.end_at - now()
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        return {
            'days': max(days, 0),
            'hours': max(hours, 0),
            'minutes': max(minutes, 0),
            'total_seconds': max(int(delta.total_seconds()), 0),
        }


class FlashSaleWithProductsSerializer(FlashSaleListSerializer):
    """Flash sale active avec ses produits (prix calculés via pricing_display)."""
    products = serializers.SerializerMethodField()

    class Meta(FlashSaleListSerializer.Meta):
        fields = FlashSaleListSerializer.Meta.fields + ['products']

    def get_products(self, obj):
        from datetime import timedelta
        from django.utils.timezone import now
        from apps.products.models import Products
        from apps.products.serializers import ProductListSerializer
        request = self.context.get('request')
        limit = 20
        if request:
            try:
                limit = int(request.query_params.get('limit', 20))
            except (TypeError, ValueError):
                limit = 20
        t = now()
        qs = Products.objects.select_related('shop', 'category').filter(
            is_active=True,
            promotions__is_active=True,
            promotions__start_at__lte=t,
            promotions__end_at__gte=t,
            promotions__end_at__lte=t + timedelta(days=5),
        )
        if obj.target_type == 'category':
            qs = qs.filter(category__in=obj.target_categories.all())
        elif obj.target_type == 'shop':
            qs = qs.filter(shop__in=obj.target_shops.all())
        elif obj.target_type == 'product':
            qs = qs.filter(id__in=obj.target_products.all())
        qs = qs.distinct()[:limit]
        serializer = ProductListSerializer(qs, many=True, context=self.context)
        return serializer.data