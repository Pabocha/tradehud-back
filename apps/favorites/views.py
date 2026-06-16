from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from .serializers import FavoriteSerializer
from .models import Favorites

# Create your views here.


class FavoriteViewSet(viewsets.ModelViewSet):
    serializer_class = FavoriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Favorites.objects.filter(user=self.request.user)
            .select_related('product', 'product__shop')
            .prefetch_related('product__promotions', 'product__price_tiers')
        )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def is_favorite(self, request):
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response({"error": "product_id manquant"}, status=400)
        exists = Favorites.objects.filter(user=request.user, product_id=product_id).exists()
        return Response({"favorited": exists})
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def toggle(self, request):
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({"error": "product_id requis"}, status=status.HTTP_400_BAD_REQUEST)

        fav, created = Favorites.objects.get_or_create(user=request.user, product_id=product_id)

        if not created:
            fav.delete()
            return Response({"favorited": False}, status=status.HTTP_200_OK)
        else:
            return Response({"favorited": True}, status=status.HTTP_201_CREATED)