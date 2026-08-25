from django.conf import settings
from django.db import models

from djmoney.models.fields import MoneyField


class SellerWallet(models.Model):
    shop = models.OneToOneField(
        'shops.Shops', on_delete=models.CASCADE, related_name='wallet'
    )
    balance = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF', default=0.00)
    total_earned = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF', default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Portefeuille {self.shop.name}"


class WalletTransaction(models.Model):
    TYPE_CHOICES = [('credit', 'Crédit'), ('debit', 'Débit')]
    SOURCE_CHOICES = [
        ('order_release', 'Vente livrée'),
        ('withdrawal', 'Retrait'),
        ('withdrawal_refund', 'Remboursement retrait'),
        ('adjustment', 'Ajustement'),
    ]

    wallet = models.ForeignKey(SellerWallet, on_delete=models.CASCADE, related_name='transactions')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    amount = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF')
    commission = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF', default=0.00)
    order = models.ForeignKey(
        'orders.Orders', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='wallet_transactions',
    )
    withdrawal = models.ForeignKey(
        'WithdrawalRequest', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='transactions',
    )
    label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'wallet'],
                condition=models.Q(source='order_release'),
                name='unique_order_release_per_wallet',
            ),
        ]


class WithdrawalRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('paid', 'Payée'),
        ('rejected', 'Rejetée'),
        ('cancelled', 'Annulée'),
    ]
    METHOD_CHOICES = [
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Virement bancaire'),
    ]

    wallet = models.ForeignKey(SellerWallet, on_delete=models.CASCADE, related_name='withdrawals')
    amount = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    destination = models.CharField(max_length=255)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    staff_note = models.CharField(max_length=255, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='processed_withdrawals',
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
