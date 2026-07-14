from decimal import Decimal
from rest_framework import permissions, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ShippingZone, ShippingRate
from .serializers import ShippingZoneSerializer, ShippingRateSerializer, ShippingEstimateSerializer
from .services import calculate_shipping_cost


class ShippingZoneViewSet(viewsets.ModelViewSet):
    queryset = ShippingZone.objects.all()
    serializer_class = ShippingZoneSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]


class ShippingRateViewSet(viewsets.ModelViewSet):
    queryset = ShippingRate.objects.select_related('zone', 'shop').all()
    serializer_class = ShippingRateSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAdminUser()]

    def get_queryset(self):
        qs = super().get_queryset()
        zone_id = self.request.query_params.get('zone')
        method = self.request.query_params.get('method')
        shop_id = self.request.query_params.get('shop')

        if zone_id:
            qs = qs.filter(zone_id=zone_id)
        if method:
            qs = qs.filter(method=method)
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        return qs


class ShippingEstimateView(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'], url_path='estimate')
    def estimate(self, request):
        serializer = ShippingEstimateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.accounts.models import Address
        from apps.orders.models import OrderLine

        address_id = serializer.validated_data['address_id']
        method = serializer.validated_data['shipping_method']
        subtotal = serializer.validated_data.get('subtotal')

        try:
            address = Address.objects.get(id=address_id)
        except Address.DoesNotExist:
            return Response({"error": "Adresse introuvable."}, status=status.HTTP_404_NOT_FOUND)

        country_code = str(address.country) if address.country else ''

        # On récupère les lignes de commande si un panier est fourni
        order_lines = OrderLine.objects.none()
        if request.user.is_authenticated:
            # On ne peut pas calculer sans order_lines — le front doit passer les shop_ids
            pass

        shop_ids = request.data.get('shop_ids', [])

        if not shop_ids:
            return Response(
                {"error": "Le champ 'shop_ids' est requis pour estimer les frais."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.products.models import ProductVariant, Products
        # Créer des OrderLine virtuelles pour le calcul
        lines_data = request.data.get('lines', [])
        if not lines_data:
            return Response(
                {"error": "Le champ 'lines' (liste de {shop_id, quantity, unit_price}) est requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculer le sous-total par boutique
        shop_totals = {}
        for line in lines_data:
            shop_id = line.get('shop_id')
            quantity = line.get('quantity', 1)
            unit_price = Decimal(str(line.get('unit_price', 0)))
            if shop_id not in shop_totals:
                shop_totals[shop_id] = {'quantity': 0, 'total': Decimal('0.00')}
            shop_totals[shop_id]['quantity'] += quantity
            shop_totals[shop_id]['total'] += unit_price * quantity

        shop_ids_list = list(shop_totals.keys())
        result = calculate_shipping_cost(
            order_lines=OrderLine.objects.none(),
            country_code=country_code,
            method=method,
            shop_ids=shop_ids_list,
            subtotal=subtotal,
        )

        # Enrichir avec les totaux par boutique
        result['shop_totals'] = {
            str(sid): {'quantity': data['quantity'], 'subtotal': str(data['total'])}
            for sid, data in shop_totals.items()
        }
        result['delivery_cost'] = str(result['delivery_cost'])

        return Response(result)
