from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, ClientQuoteViewSet, SellerQuoteViewSet, ReturnRequestViewSet

app_name = 'orders'

router = DefaultRouter()
router.register('quotes/client', ClientQuoteViewSet, basename='client-quote')
router.register('quotes/seller', SellerQuoteViewSet, basename='seller-quote')
router.register('returns', ReturnRequestViewSet, basename='return-request')

urlpatterns = [
    # Orders - custom explicit URLs
    path('create/', OrderViewSet.as_view({'post': 'create'}), name='order-create'),
    path('preview/', OrderViewSet.as_view({'post': 'preview'}), name='order-preview'),
    path('list/', OrderViewSet.as_view({'get': 'list'}), name='order-list'),
    path('<int:pk>/', OrderViewSet.as_view({'get': 'retrieve'}), name='order-detail'),
    path('<int:pk>/update/', OrderViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='order-update'),
    path('<int:pk>/delete/', OrderViewSet.as_view({'delete': 'destroy'}), name='order-destroy'),
    path('<int:pk>/pay/', OrderViewSet.as_view({'post': 'pay'}), name='order-pay'),
    path('<int:pk>/payment-status/', OrderViewSet.as_view({'patch': 'update_payment_status'}), name='order-payment-status'),
    path('shop-orders/', OrderViewSet.as_view({'get': 'shop_orders'}), name='order-shop-orders'),
    path('my-orders/', OrderViewSet.as_view({'get': 'my_orders'}), name='order-my-orders'),
    path('returnable-items/', OrderViewSet.as_view({'get': 'returnable_items'}), name='order-returnable-items'),
    # Quotes
    path('', include(router.urls)),
]

