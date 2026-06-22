from rest_framework.generics import ListAPIView
from .serializers import BannerSerializer
from .models import Banner, Announcement

# Create your views here.


class BannerView(ListAPIView):
    serializer_class = BannerSerializer
    queryset = Banner.objects.filter(is_active=True)

    def get_queryset(self):
        target = self.request.query_params.get('target')
        if target:
            return self.queryset.filter(target=target).order_by('-priority')
        return self.queryset.order_by('-priority')