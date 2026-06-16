from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import CartItemViewSet

app_name = 'cart'

router = DefaultRouter()
router.register('', CartItemViewSet, basename='cart')

urlpatterns = [
    path('', include(router.urls)),
]
