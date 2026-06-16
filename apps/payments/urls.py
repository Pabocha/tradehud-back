from rest_framework.routers import DefaultRouter
from .views import *
from django.urls import path, include

app_name = 'payments'


urlpatterns = [
    path('methods/', PaymentMethodView.as_view(), name='payment-methods'),
    
]