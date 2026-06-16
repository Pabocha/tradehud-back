from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

app_name = 'favorites'

router = DefaultRouter()
router.register('', FavoriteViewSet, basename='favorites')

urlpatterns = [
    path('', include(router.urls)),
    
]