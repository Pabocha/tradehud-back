from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views.seller import SellerWalletViewSet

router = DefaultRouter()
router.register(r'seller', SellerWalletViewSet, basename='wallets-seller')

urlpatterns = [
    path('', include(router.urls)),
]
