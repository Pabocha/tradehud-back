from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import BannerView, CampaignViewSet, FlashSaleViewSet

app_name = 'marketing'

router = DefaultRouter()
router.register('campaigns', CampaignViewSet, basename='campaign')
router.register('flash-sales', FlashSaleViewSet, basename='flash-sale')

urlpatterns = [
    path('banners/', BannerView.as_view(), name='banners'),
    path('', include(router.urls)),
]
