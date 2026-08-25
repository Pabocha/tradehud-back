from rest_framework.routers import DefaultRouter
from django.urls import path, include
from apps.shops.views.seller import SellerShopViewSet, SellerShopStatisticsViewSet
from apps.shops.views.shared import (
    PublicShopViewSet, ShopListViewSet, ProductsByShopViewSet,
    ShopFollowViewSet, PublicShopStatisticsViewSet,
)

app_name = 'shop'

router = DefaultRouter()
router.register('public', PublicShopViewSet, basename='public-shop')
router.register('list', ShopListViewSet, basename='shop-list')
router.register('products-by-shop', ProductsByShopViewSet, basename='products-by-shop')
router.register('follow', ShopFollowViewSet, basename='shop-follow')
router.register('statistics-public', PublicShopStatisticsViewSet, basename='shop-statistics-public')

seller_router = DefaultRouter()
seller_router.register('shops', SellerShopViewSet, basename='seller-shop')
seller_router.register('statistics', SellerShopStatisticsViewSet, basename='seller-shop-statistics')

urlpatterns = [
    path('', include(router.urls)),
    path('seller/', include(seller_router.urls)),
]
