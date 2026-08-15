from rest_framework.generics import ListAPIView
from django.db.models import Q
from .models import PaymentMethod
from .serializers import PaymentMethodSerializer

# Create your views here.


class PaymentMethodView(ListAPIView):
    serializer_class = PaymentMethodSerializer
    pagination_class = None

    # AJOUT — Filtre par pays (query param ?country=SN).
    # Une méthode avec countries=[] est internationale et disponible partout.
    def get_queryset(self):
        queryset = PaymentMethod.objects.all()
        country = self.request.query_params.get('country')
        if country:
            country_code = country.strip().upper()
            queryset = queryset.filter(
                Q(countries__contains=[country_code]) | Q(countries=[])
            )
        return queryset
