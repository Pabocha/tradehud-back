from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *
from .api_views import (
    ProductSearchView,
    ProductSearchByShopView,
    ProductSearchAutocompleteView,
    RecommendationsView,
    PromotionsView,
)

app_name = 'products'

router = DefaultRouter()
router.register('recently-viewed', RecentlyViewedProductViewSet, basename='recently-viewed')
router.register('', ProductViewSet, basename='product')
urlpatterns = [
    path('search/', ProductSearchView.as_view(), name='product-search'),
    path('search/by-shop/', ProductSearchByShopView.as_view(), name='product-search-by-shop'),
    path('search/autocomplete/', ProductSearchAutocompleteView.as_view(), name='product-search-autocomplete'),
    path('recommendations/', RecommendationsView.as_view(), name='product-recommendations'),
    path('promotions/', PromotionsView.as_view(), name='product-promotions'),
    # path('colors/', ColorsView.as_view(), name='color-product'),
    path('categories/<int:category_id>/', ProductsByCategoryView.as_view(), name='products-by-category'),
    path('countries_with_product/', countries_with_products, name="countries-with-product"),
    path('attributes-values/', ProductAttributeValuesView.as_view(), name='product-attribute-values'),
    path('', include(router.urls)),
]