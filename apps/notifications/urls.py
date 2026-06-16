from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

app_name = 'notifications'

router = DefaultRouter()
router.register('', NotificationViewSet, basename='notifications')

urlpatterns = [
    path('', include(router.urls)),
    
]