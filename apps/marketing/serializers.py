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
            'id', 'name', 'description', 'discount_type', 'discount_value',
            'start_at', 'end_at', 'is_active', 'is_currently_active',
            'target_type', 'target_categories', 'target_shops', 'target_products',
            'max_uses', 'uses', 'campaign', 'campaign_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'uses', 'created_at', 'updated_at']

    def validate(self, attrs):
        discount_type = attrs.get('discount_type')
        discount_value = attrs.get('discount_value')
        if discount_type == 'percent' and discount_value and discount_value > 100:
            raise serializers.ValidationError({"discount_value": "Le pourcentage ne peut pas dépasser 100%."})
        return attrs


class FlashSaleListSerializer(serializers.ModelSerializer):
    """Serializer allégé pour la liste publique des flash sales."""
    is_currently_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = FlashSale
        fields = [
            'id', 'name', 'description', 'discount_type', 'discount_value',
            'start_at', 'end_at', 'is_currently_active', 'target_type',
            'max_uses', 'uses',
        ]