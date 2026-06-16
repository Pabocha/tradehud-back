"""
URLs pour l'app vendor restaurant (Gestion des restaurants)
Inclus dans: ecommerce/urls.py -> /api/v1/vendor/restaurant/
"""
from django.urls import include, path
from .routers import urlpatterns as router_urls

app_name = 'vendor_restaurant'

urlpatterns = router_urls
