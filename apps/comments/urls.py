from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

app_name = 'client_reviews'

router = DefaultRouter()

router.register('products', RatingViewSet, basename='product-ratings')
router.register('shops', ShopRatingViewSet, basename='shop-ratings')

urlpatterns = [
    path('', include(router.urls)),
]