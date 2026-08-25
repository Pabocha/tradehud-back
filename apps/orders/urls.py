from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.orders.views.buyer import BuyerOrderViewSet, BuyerQuoteViewSet, BuyerReturnRequestViewSet
from apps.orders.views.seller import SellerOrderViewSet, SellerQuoteViewSet, SellerReturnRequestViewSet

app_name = 'orders'

router = DefaultRouter()
router.register('quotes/client', BuyerQuoteViewSet, basename='client-quote')
router.register('returns', BuyerReturnRequestViewSet, basename='return-request')

seller_router = DefaultRouter()
seller_router.register('quotes/seller', SellerQuoteViewSet, basename='seller-quote')
seller_router.register('returns/staff', SellerReturnRequestViewSet, basename='staff-return-request')
seller_router.register('orders', SellerOrderViewSet, basename='seller-order')

urlpatterns = [
    path('create/', BuyerOrderViewSet.as_view({'post': 'create'}), name='order-create'),
    path('preview/', BuyerOrderViewSet.as_view({'post': 'preview'}), name='order-preview'),
    path('list/', SellerOrderViewSet.as_view({'get': 'list'}), name='order-list'),
    path('<int:pk>/', BuyerOrderViewSet.as_view({'get': 'retrieve'}), name='order-detail'),
    path('<int:pk>/update/', SellerOrderViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='order-update'),
    path('<int:pk>/delete/', SellerOrderViewSet.as_view({'delete': 'destroy'}), name='order-destroy'),
    path('<int:pk>/pay/', BuyerOrderViewSet.as_view({'post': 'pay'}), name='order-pay'),
    path('<int:pk>/payment-status/', SellerOrderViewSet.as_view({'patch': 'update_payment_status'}), name='order-payment-status'),
    path('shop-orders/', SellerOrderViewSet.as_view({'get': 'shop_orders'}), name='order-shop-orders'),
    path('my-orders/', BuyerOrderViewSet.as_view({'get': 'my_orders'}), name='order-my-orders'),
    path('returnable-items/', BuyerOrderViewSet.as_view({'get': 'returnable_items'}), name='order-returnable-items'),
    path('', include(router.urls)),
    path('seller/', include(seller_router.urls)),
]
