from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import ShopViewset, ProductsByShopViewSet, ShopStatisticsViewSet
# from .views import ShopListWithProductsView, ShopViewset

app_name = 'shop'

router = DefaultRouter()

router.register('statistics', ShopStatisticsViewSet, basename='shop-statistics')
router.register('products-by-shop', ProductsByShopViewSet, basename='products-by-shop')
router.register('', ShopViewset, basename='shop')

urlpatterns = [
    path('', include(router.urls)),
]