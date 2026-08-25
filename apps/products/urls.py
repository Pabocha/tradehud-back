from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views.shared import (
    ProductViewSet, ProductComparisonViewSet, RecentlyViewedProductViewSet,
    ProductAttributeValuesView, ProductsByCategoryView, countries_with_products,
)
from .views.seller import (
    SellerProductViewSet, SellerProductGalleryViewSet,
)
from .api_views import (
    ProductSearchView, ProductSearchByShopView, ProductSearchAutocompleteView,
    RecommendationsView, PromotionsView, ProductsByCategorySlugView,
)

app_name = 'products'

# --- Routes partagées (public / buyer / seller) ---
shared_router = DefaultRouter()
shared_router.register('recently-viewed', RecentlyViewedProductViewSet, basename='recently-viewed')
shared_router.register('comparison', ProductComparisonViewSet, basename='product-comparison')
shared_router.register('', ProductViewSet, basename='product')

# --- Routes vendeur ---
seller_router = DefaultRouter()
seller_router.register('', SellerProductViewSet, basename='seller-product')

seller_gallery_list = SellerProductGalleryViewSet.as_view({'get': 'list', 'post': 'create'})
seller_gallery_bulk_delete = SellerProductGalleryViewSet.as_view({'delete': 'bulk_delete'})
seller_gallery_reorder = SellerProductGalleryViewSet.as_view({'post': 'reorder'})
seller_gallery_delete_main = SellerProductGalleryViewSet.as_view({'delete': 'delete_main_image'})

urlpatterns = [
    # --- Partagé / Public ---
    path('search/', ProductSearchView.as_view(), name='product-search'),
    path('search/by-shop/', ProductSearchByShopView.as_view(), name='product-search-by-shop'),
    path('search/autocomplete/', ProductSearchAutocompleteView.as_view(), name='product-search-autocomplete'),
    path('recommendations/', RecommendationsView.as_view(), name='product-recommendations'),
    path('promotions/', PromotionsView.as_view(), name='product-promotions'),
    path('categories/<int:category_id>/', ProductsByCategoryView.as_view(), name='products-by-category'),
    path('by-category-slug/<slug:slug>/', ProductsByCategorySlugView.as_view(), name='products-by-category-slug'),
    path('countries_with_product/', countries_with_products, name="countries-with-product"),
    path('attributes-values/', ProductAttributeValuesView.as_view(), name='product-attribute-values'),
    path('', include(shared_router.urls)),

    # --- Vendeur : Galerie ---
    path('<int:product_pk>/gallery/', seller_gallery_list, name='seller-product-gallery'),
    path('<int:product_pk>/gallery/bulk-delete/', seller_gallery_bulk_delete, name='seller-product-gallery-bulk-delete'),
    path('<int:product_pk>/gallery/reorder/', seller_gallery_reorder, name='seller-product-gallery-reorder'),
    path('<int:product_pk>/gallery/delete-main-image/', seller_gallery_delete_main, name='seller-product-gallery-delete-main-image'),
]

# Les actions vendeur (variants, sponsor, price-tiers, promotions) sont sur
# le SellerProductViewSet inclus via seller_router. On les expose séparément
# sous le préfixe seller/ dans api_v1.py.
urlpatterns += [
    path('seller/', include(seller_router.urls)),
]
