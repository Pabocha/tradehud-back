from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import CartItemViewSet

app_name = 'cart'

router = DefaultRouter()
router.register('', CartItemViewSet, basename='cart')

cart_add = CartItemViewSet.as_view({'post': 'create'})

urlpatterns = [
    path('add/', cart_add, name='cart-add'),
    path('', include(router.urls)),
]
