# ecommerce/api_v1.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenVerifyView
from apps.accounts.auth_views import (
    CustomTokenObtainPairView,
    CookieTokenRefreshView,
    CheckAuthView,
    LogoutView,
)

app_name = 'api_v1'

urlpatterns = [
    # ---- Authentication Tokens ----
    path('auth/token/', CustomTokenObtainPairView.as_view(), name='auth-token'),
    path('auth/token/refresh/', CookieTokenRefreshView.as_view(), name='auth-token-refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='auth-token-verify'),
    path('auth/check/', CheckAuthView.as_view(), name='auth-check'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),

    # ---- Core & Users ----
    path('accounts/', include('apps.accounts.urls')),
    path('notifications/', include('apps.notifications.urls')),

    # ---- Products (public + buyer + seller routes inside app) ----
    path('products/', include('apps.products.urls')),

    # ---- Shops (public + seller routes inside app) ----
    path('shop/', include('apps.shops.urls')),

    # ---- Categories ----
    path('categories/', include('apps.categories.urls')),
    path('restaurant/', include('apps.restaurant.urls')),

    # ---- Client ----
    path('cart/', include('apps.carts.urls')),
    path('comments/', include('apps.comments.urls')),
    path('favorites/', include('apps.favorites.urls')),

    # ---- Orders (buyer + seller routes inside app) ----
    path('orders/', include('apps.orders.urls')),

    # ---- Messaging ----
    path('messaging/', include('apps.chat.urls')),

    # ---- Support (tickets) ----
    path('support/', include('apps.support.urls')),

    # ---- Marketing ----
    path('marketing/', include('apps.marketing.urls')),

    # ---- Shipping ----
    path('shipping/', include('apps.shipping.urls')),

    # ---- Payments ----
    path('payments/', include('apps.payments.urls')),

    # ---- Portefeuille vendeur ----
    path('wallets/', include('apps.wallets.urls')),
]
