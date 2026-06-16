from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import NotificationViewSet, PaymentMethodView, FavoriteViewSet, CouponViewSet, BannerView

router = DefaultRouter()

router.register('favorites', FavoriteViewSet, basename='favorites')
router.register('coupons', CouponViewSet, basename='coupons')
router.register('notifications', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('', include(router.urls)),
    path('payment-method/', PaymentMethodView.as_view(), name='payment-method'),
    path('banners/', BannerView.as_view(), name='banners'),
]
