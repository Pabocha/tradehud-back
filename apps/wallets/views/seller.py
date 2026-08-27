from django.db.models import Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, NotFound
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.shops.models import Shops
from apps.wallets.models import SellerWallet, WithdrawalRequest
from apps.wallets.serializers import (
    WalletSerializer,
    WalletTransactionSerializer,
    WithdrawalRequestSerializer,
    WithdrawalCreateSerializer,
)
from apps.wallets.services import (
    get_or_create_wallet,
    cancel_withdrawal as cancel_withdrawal_service,
    request_withdrawal,
)


class SellerWalletViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_owned_shop(self, request):
        user = request.user
        if not hasattr(user, 'seller_account'):
            raise PermissionDenied("Accès réservé aux vendeurs.")
        shop_id = request.query_params.get('shop_id') or request.data.get('shop_id')
        qs = Shops.objects.filter(
            owner=user.seller_account, is_deleted=False
        )
        if shop_id:
            shop = qs.filter(id=shop_id).first()
            if not shop:
                raise NotFound("Boutique introuvable ou accès non autorisé.")
        else:
            shop = qs.order_by('id').first()
        if not shop:
            raise NotFound("Aucune boutique trouvée.")
        return shop

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        shop = self._get_owned_shop(request)
        wallet = get_or_create_wallet(shop)
        return Response(WalletSerializer(wallet).data)

    @action(detail=False, methods=['get'], url_path='transactions')
    def transactions(self, request):
        shop = self._get_owned_shop(request)
        wallet = get_or_create_wallet(shop)
        qs = wallet.transactions.select_related('order')
        type_filter = request.query_params.get('type')
        if type_filter in ('credit', 'debit'):
            qs = qs.filter(type=type_filter)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = WalletTransactionSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = WalletTransactionSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get', 'post'], url_path='withdrawals')
    def withdrawals(self, request):
        shop = self._get_owned_shop(request)
        wallet = get_or_create_wallet(shop)
        if request.method == 'GET':
            qs = wallet.withdrawals.all()
            page = self.paginate_queryset(qs)
            if page is not None:
                serializer = WithdrawalRequestSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = WithdrawalRequestSerializer(qs, many=True)
            return Response(serializer.data)
        # POST
        ser = WithdrawalCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            req = request_withdrawal(
                wallet=wallet,
                amount=ser.validated_data['amount'],
                method=ser.validated_data['method'],
                destination=ser.validated_data['destination'],
            )
        except DjangoValidationError as exc:
            message = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WithdrawalRequestSerializer(req).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path=r'withdrawals/(?P<pk>\d+)/cancel')
    def cancel_withdrawal(self, request, pk=None):
        shop = self._get_owned_shop(request)
        wallet = get_or_create_wallet(shop)
        req = WithdrawalRequest.objects.filter(id=pk, wallet=wallet).first()
        if not req:
            raise NotFound("Demande introuvable.")
        try:
            cancel_withdrawal_service(req, note=request.data.get('note', ''))
        except DjangoValidationError as exc:
            message = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(WithdrawalRequestSerializer(req).data)
