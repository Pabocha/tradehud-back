from django.contrib import admin
from django.utils import timezone

from .models import SellerWallet, WalletTransaction, WithdrawalRequest
from .services import get_or_create_wallet, cancel_withdrawal, mark_withdrawal_paid


@admin.register(SellerWallet)
class SellerWalletAdmin(admin.ModelAdmin):
    list_display = ['id', 'shop', 'balance', 'total_earned', 'updated_at']
    list_select_related = ['shop']
    search_fields = ['shop__name']


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet', 'type', 'source', 'amount', 'commission', 'order', 'created_at']
    list_select_related = ['wallet', 'order']
    list_filter = ['type', 'source']
    search_fields = ['label', 'order__order_number']
    date_hierarchy = 'created_at'


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet', 'amount', 'method', 'destination', 'status', 'created_at', 'processed_at']
    list_select_related = ['wallet', 'processed_by']
    list_filter = ['status', 'method']
    search_fields = ['destination', 'wallet__shop__name']
    readonly_fields = ['wallet', 'amount', 'method', 'destination', 'created_at']

    def mark_paid(self, request, queryset):
        count = 0
        for req in queryset.filter(status='pending'):
            try:
                mark_withdrawal_paid(req, request.user)
                count += 1
            except Exception as exc:
                self.message_user(request, f"Erreur retrait #{req.id}: {exc}", level='error')
        self.message_user(request, f"{count} retrait(s) marqué(s) payé(s).")
    mark_paid.short_description = "Marquer comme payé"

    def reject_and_refund(self, request, queryset):
        count = 0
        for req in queryset.filter(status='pending'):
            try:
                cancel_withdrawal(req, note="Rejeté par le staff", by_staff=True)
                count += 1
            except Exception as exc:
                self.message_user(request, f"Erreur retrait #{req.id}: {exc}", level='error')
        self.message_user(request, f"{count} retrait(s) rejeté(s) et remboursé(s).")
    reject_and_refund.short_description = "Rejeter et rembourser"

    actions = ['mark_paid', 'reject_and_refund']
