# ecommerce/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from .media_views import serve_media_with_cache # Ajuste l'import selon ton projet

urlpatterns = [
    # ============ ADMIN ============
    path('admin/', admin.site.urls),

    # ============ THIRD PARTY AUTH (S'ils servent pour des templates/OAuth) ============
    path('auth/', include('dj_rest_auth.urls')),
    path('auth/social/', include('allauth.socialaccount.urls')),

    # ============ API V1 (CENTRALISÉE) ============
    path('api/v1/', include('ecommerce.api_v1', namespace='api-v1')),

    # ============ API DOCUMENTATION ============
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# Serve media files in DEBUG mode
if settings.DEBUG:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve_media_with_cache),
    ]