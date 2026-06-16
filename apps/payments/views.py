from rest_framework.generics import ListAPIView
from .models import PayementMethod
from .serializers import PaymentMethodSerializer

# Create your views here.


class PaymentMethodView(ListAPIView):
    serializer_class = PaymentMethodSerializer
    queryset = PayementMethod.objects.all()
    pagination_class = None