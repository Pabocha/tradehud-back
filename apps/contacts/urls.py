"""
URLs pour l'app client contacts (Formulaires de contact)
Inclus dans: ecommerce/urls.py -> /api/v1/client/support/
"""
from django.urls import include, path
from .routers import urlpatterns as router_urls

app_name = 'client_support'

urlpatterns = router_urls
