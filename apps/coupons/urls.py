from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

app_name = 'coupons'

router = DefaultRouter()
router.register('', CouponViewSet, basename='coupons')

urlpatterns = [
    path('', include(router.urls)),
    
]