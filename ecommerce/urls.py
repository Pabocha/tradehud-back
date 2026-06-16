"""ecommerce URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from rest_framework_simplejwt.views import (
    # TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from comptes.views import CustomTokenObtainPairView, LogoutView
from django.conf import settings
from chat import views
from django.contrib.auth import views as auth_views
from ecommerce.media_views import serve_media_with_cache


urlpatterns = [

    # Authentification 
    path('auth/', include('dj_rest_auth.urls')),  # Auth de base
    path('auth/social/', include('allauth.socialaccount.urls')),  # OAuth via providers
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/token/logout/', LogoutView.as_view(), name='token_logout'),
    path('admin/', admin.site.urls),
    # Api marketpalce 
    path('api/compte/', include('comptes.routers')),
    path('api/products/', include('produits.routers')),
    path('api/others/', include('ecom_app.routers')),
    path('api/orders/', include('commandes.routers')),
    path('api/message/', include('chat.routers')),
    path('api/shop/', include('boutique.routers')),
    path('api/ratings/', include('commentaires.routers')),
    path('api/categories/', include('categories.routers')),
    path('api/carts/', include('panier.routers')),
    path('api/chat/<str:room_name>/', views.room, name='chat_room'),
    path('api/chats/<str:roomId>/messages', views.MessagesView.as_view(), name='messageList'),
    path('api/chats/<str:roomId>/messages/upload', views.ChatMessageCreateView.as_view(), name='messageCreate'),
    path('api/chats/<str:roomId>/messages/read', views.ChatMessageReadView.as_view(), name='messageRead'),
	path('api/users/chats', views.ChatRoomView.as_view(), name='chatRoomList'),
	path('api/users/support-chat/start', views.SupportChatStartView.as_view(), name='supportChatStart'),
	    path('api/users/conversations', views.ChatUserConversationsView.as_view(), name='chatUserConversations'),
    # Restauration 
    path('api/', include('restaurant.routers')),
    # Swagger / OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
 
if settings.DEBUG:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve_media_with_cache),
    ]
