from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from apps.accounts.serializers import SellerAccountSerializer
from apps.accounts.models import SellerAccount
from django.db import IntegrityError
from ecommerce.permissions import IsSeller


class SellerAccountViewSet(viewsets.ModelViewSet):
    serializer_class = SellerAccountSerializer
    permission_classes = [IsAuthenticated, IsSeller]

    def get_queryset(self):
        return SellerAccount.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError({'detail': 'Un compte vendeur existe deja pour cet utilisateur.'})

    @action(detail=False, methods=['post'], url_path='create-seller-account')
    def create_seller_account(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            try:
                serializer.save(user=request.user)
                return Response(serializer.data, status=201)
            except IntegrityError:
                return Response({'detail': 'Un compte vendeur existe deja pour cet utilisateur.'}, status=status.HTTP_409_CONFLICT)
        return Response(serializer.errors, status=400)

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        try:
            seller = request.user.seller_account
            serializer = self.get_serializer(seller)
            return Response(serializer.data)
        except SellerAccount.DoesNotExist:
            return Response({'detail': 'Aucun compte vendeur.'}, status=status.HTTP_404_NOT_FOUND)
