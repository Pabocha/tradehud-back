# ecommerce/api_v1.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView
from apps.accounts.views import CustomTokenObtainPairView, LogoutView

app_name = 'api_v1'

urlpatterns = [
    # ---- Authentication Tokens ----
    path('auth/token/', CustomTokenObtainPairView.as_view(), name='auth-token'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='auth-token-refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='auth-token-verify'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),

    # ---- Core & Users ----
    path('accounts/', include('apps.accounts.urls')),
    path('notifications/', include('apps.notifications.urls')),

    # ---- Client ----
    path('cart/', include('apps.carts.urls')),
    path('comments/', include('apps.comments.urls')),
    # path('contacts/', include('apps.contacts.urls')),

    # ---- Vendor ----
    path('products/', include('apps.products.urls')),
    path('shop/', include('apps.shops.urls')),
    path('categories/', include('apps.categories.urls')),
    path('restaurant/', include('apps.restaurant.urls')),

    # ---- Orders ----
    path('orders/', include('apps.orders.urls')),

    # ---- Messaging (Tout est centralisé dans l'app) ----
    path('messaging/', include('apps.chat.urls')), 
]