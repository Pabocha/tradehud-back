from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()

# router.register('chat', MessagesViewSet, basename='chat')

urlpatterns = router.urls