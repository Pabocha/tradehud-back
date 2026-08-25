from decimal import Decimal

from rest_framework import serializers

from djmoney.contrib.django_rest_framework.fields import MoneyField

from .models import SellerWallet, WalletTransaction, WithdrawalRequest


class WalletSerializer(serializers.ModelSerializer):
    shop_name = serializers.CharField(source='shop.name', read_only=True)
    pending_withdrawal_total = MoneyField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = SellerWallet
        fields = [
            'id', 'shop', 'shop_name',
            'balance', 'total_earned', 'pending_withdrawal_total',
            'updated_at',
        ]

    def get_pending_withdrawal_total(self, obj):
        total = obj.withdrawals.filter(status='pending').aggregate(t=serializers.models.Sum('amount'))['t']
        return total if total else 0


class WalletTransactionSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', default=None, read_only=True)

    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'type', 'source', 'label',
            'amount', 'commission', 'order', 'order_number',
            'created_at',
        ]


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            'id', 'amount', 'method', 'destination',
            'status', 'staff_note',
            'created_at', 'processed_at',
        ]
        read_only_fields = ['status', 'staff_note', 'processed_at']


class WithdrawalCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    method = serializers.ChoiceField(choices=WithdrawalRequest.METHOD_CHOICES)
    destination = serializers.CharField(max_length=255, trim_whitespace=True)
