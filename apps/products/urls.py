from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *
from .api_views import (
    ProductSearchView,
    ProductSearchByShopView,
    ProductSearchAutocompleteView,
    RecommendationsView,
    PromotionsView,
    ProductsByCategorySlugView,
)

app_name = 'products'

router = DefaultRouter()
router.register('recently-viewed', RecentlyViewedProductViewSet, basename='recently-viewed')
router.register('comparison', ProductComparisonViewSet, basename='product-comparison')
router.register('', ProductViewSet, basename='product')

product_gallery_list = ProductGalleryViewSet.as_view({'get': 'list', 'post': 'create',})
product_gallery_bulk_delete = ProductGalleryViewSet.as_view({'delete': 'bulk_delete',})
product_gallery_reorder = ProductGalleryViewSet.as_view({'post': 'reorder',})
product_gallery_delete_main = ProductGalleryViewSet.as_view({'delete': 'delete_main_image',})

urlpatterns = [
    path('search/', ProductSearchView.as_view(), name='product-search'),
    path('search/by-shop/', ProductSearchByShopView.as_view(), name='product-search-by-shop'),
    path('search/autocomplete/', ProductSearchAutocompleteView.as_view(), name='product-search-autocomplete'),
    path('recommendations/', RecommendationsView.as_view(), name='product-recommendations'),
    path('promotions/', PromotionsView.as_view(), name='product-promotions'),
    # path('colors/', ColorsView.as_view(), name='color-product'),
    path('categories/<int:category_id>/', ProductsByCategoryView.as_view(), name='products-by-category'),
    path('by-category-slug/<slug:slug>/', ProductsByCategorySlugView.as_view(), name='products-by-category-slug'),
    path('countries_with_product/', countries_with_products, name="countries-with-product"),
    path('attributes-values/', ProductAttributeValuesView.as_view(), name='product-attribute-values'),
    path('<int:product_pk>/gallery/', product_gallery_list, name='product-gallery'),
    path('<int:product_pk>/gallery/bulk-delete/', product_gallery_bulk_delete, name='product-gallery-bulk-delete'),
    path('<int:product_pk>/gallery/reorder/', product_gallery_reorder, name='product-gallery-reorder'),
    path('<int:product_pk>/gallery/delete-main-image/', product_gallery_delete_main, name='product-gallery-delete-main-image'),
    path('', include(router.urls)),
]