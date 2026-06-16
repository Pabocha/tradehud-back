from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from .views import (
    RestaurantViewSet,
    RestaurantCategoryViewSet,
    RestaurantStatisticsViewSet,
    MenuCategoryViewSet,
    MealViewSet,
    RestaurantReviewViewSet,
    MealReviewViewSet,
    RestaurantOrderViewSet,
    OrderItemViewSet,
    PaymentViewSet,
)

# 🔹 Routeur principal
router = routers.DefaultRouter()
router.register(r'restaurants', RestaurantViewSet, basename='restaurant')
router.register(r'restaurants-categories', RestaurantCategoryViewSet, basename='restaurant-category')
router.register(r'menu-categories', MenuCategoryViewSet, basename='menu-category')
router.register(r'meals', MealViewSet, basename='meal')
router.register(r'restaurant-reviews', RestaurantReviewViewSet, basename='restaurant-review')
router.register(r'meal-reviews', MealReviewViewSet, basename='meal-review')
router.register(r'restaurants-orders', RestaurantOrderViewSet, basename='restaurant-order')
router.register(r'order-items', OrderItemViewSet, basename='order-item')
router.register(r'payments', PaymentViewSet, basename='payment')

# 🔹 Sous-route imbriquée : statistiques d’un restaurant
# statistics_router = routers.NestedSimpleRouter(router, r'restaurants', lookup='restaurant')
router.register(r'statistics', RestaurantStatisticsViewSet, basename='restaurant-statistics')

# 🔹 Inclusion dans urlpatterns
urlpatterns = [
    path('', include(router.urls)),
    # path('', include(statistics_router.urls)),
]
