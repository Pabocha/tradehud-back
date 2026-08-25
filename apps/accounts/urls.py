from rest_framework.routers import DefaultRouter
from django.urls import path, include
from apps.accounts.views.buyer import UserViewSet, AddressViewSet, ShopFollowViewSet
from apps.accounts.views.seller import SellerAccountViewSet
from apps.accounts.views.shared import (
    user_settings, update_user_settings, notification_settings,
    unread_counters, deactivate_account, request_delete_account,
    confirm_delete_account, ForgotPasswordView, VerifyOTPView, ResetPasswordView,
)

app_name = 'accounts'

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('addresses', AddressViewSet, basename='address')
router.register('shops', ShopFollowViewSet, basename='shop-follow')

# Vendeur
seller_router = DefaultRouter()
seller_router.register('sellers', SellerAccountViewSet, basename='seller-account')

urlpatterns = [
    path('', include(router.urls)),
    path('seller/', include(seller_router.urls)),

    # User Settings & Account Management
    path('user-settings/', user_settings, name='user-settings'),
    path('update-user-settings/', update_user_settings, name='update-user-settings'),
    path('notification-settings/', notification_settings, name='notification-settings'),
    path('unread-counters/', unread_counters, name='unread-counters'),

    # Account Actions
    path('account/deactivate/', deactivate_account, name='deactivate_account'),
    path('account/request-delete/', request_delete_account, name='request_delete_account'),
    path('account/confirm-delete/<uuid:token>/', confirm_delete_account, name='confirm_delete_account'),

    # OTP Password Reset
    path('password/forgot/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('password/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('password/reset/', ResetPasswordView.as_view(), name='reset-password'),
]
