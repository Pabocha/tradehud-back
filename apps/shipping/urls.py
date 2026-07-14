from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ShippingZoneViewSet, ShippingRateViewSet, ShippingEstimateView

app_name = 'shipping'

router = DefaultRouter()
router.register('zones', ShippingZoneViewSet, basename='shipping-zone')
router.register('rates', ShippingRateViewSet, basename='shipping-rate')

urlpatterns = [
    path('estimate/', ShippingEstimateView.as_view({'post': 'estimate'}), name='shipping-estimate'),
    path('', include(router.urls)),
]
