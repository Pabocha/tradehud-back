from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *

app_name = 'products'

router = DefaultRouter()
router.register('recently-viewed', RecentlyViewedProductViewSet, basename='recently-viewed')
router.register('quotes', QuoteViewSet, basename='quote')
router.register('', ProductViewSet, basename='product')
urlpatterns = [
    path('colors/', ColorsView.as_view(), name='color-product'),
    path('categories/<int:category_id>/', ProductsByCategoryView.as_view(), name='products-by-category'),
    path('countries_with_product/', countries_with_products, name="countries-with-product"),
    # path('attributes/', ProductAttributeViewSet.as_view({'get': 'list'}), name='product-attributes'),
    path('attributes-values/', ProductAttributeValuesView.as_view(), name='product-attribute-values'),
    path('', include(router.urls)),
    # Endpoints merged into ProductViewSet as actions:
    #  - /products/sponsored/
    #  - /products/recent/
    #  - /products/popular/
    #  - /products/others/
    #  - /products/combined/
    #  - /products/recommendations/?product_id=...
    #  - /products/search/?q=... and /products/search/autocomplete/?q=...
    #  - /products/{id}/images/ (GET/POST)
    #  - /products/{id}/delete-main-image/ (DELETE)
    #  - /products/delete-gallery-images/ (POST)
]