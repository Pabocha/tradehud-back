from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

router = DefaultRouter()

router.register('products', RatingViewSet, basename='product-ratings')
router.register('shops', ShopRatingViewSet, basename='shop-ratings')

# custom_urls = [
#     path('by-products/', RatingViewSet.as_view({'get': 'by_products'}), name='ratings-by-products'),
# ]

urlpatterns = [
    path('', include(router.urls)),
    # path('', include(custom_urls)),  # Inclure les URLs personnalisées
]