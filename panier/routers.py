from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import CartItemViewSet

router = DefaultRouter()
router.register('', CartItemViewSet, basename='cart')

urlpatterns = [
    # autres urls...
    path('', include(router.urls)),
]
