from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, QuoteViewSet

app_name = 'orders'

router = DefaultRouter()
router.register('quotes', QuoteViewSet, basename='quote')
router.register(r'', OrderViewSet, basename='orders')

urlpatterns = [
    path('', include(router.urls)),
]

