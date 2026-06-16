from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

app_name = 'accounts'

router = DefaultRouter()

# ✨ Donne un préfixe explicite à tes utilisateurs (ex: 'users' ou 'me')
router.register('users', UserViewSet, basename='user')
router.register('sellers', SellerAccountViewSet, basename='seller-account')
router.register('shops', ShopFollowViewSet, basename='shop-follow')

urlpatterns = [
    path('', include(router.urls)),
    
    # ============================================
    # ⚙️ User Settings & Account Management
    # ============================================
    path('user-settings/', user_settings, name='user-settings'),
    path('update-user-settings/', update_user_settings, name='update-user-settings'),
    path('notification-settings/', notification_settings, name='notification-settings'),
    path('unread-counters/', unread_counters, name='unread-counters'),
    
    # Action d'état du compte (On pourrait les préfixer pour éviter des conflits futurs)
    path('account/deactivate/', deactivate_account, name='deactivate_account'),
    path('account/request-delete/', request_delete_account, name='request_delete_account'),
    path('account/confirm-delete/<uuid:token>/', confirm_delete_account, name='confirm_delete_account'),
    
    # ============================================
    # 🔐 OTP Password Reset Endpoints
    # ============================================
    path('password/forgot/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('password/verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('password/reset/', ResetPasswordView.as_view(), name='reset-password'),
]