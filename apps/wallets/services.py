import logging

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from djmoney.money import Money

from apps.orders.models import Orders
from apps.shops.models import Shops

from .models import SellerWallet, WalletTransaction, WithdrawalRequest

logger = logging.getLogger(__name__)


def _decimal_val(value):
    if hasattr(value, 'amount'):
        return value.amount
    return Decimal(str(value or 0))


def _money(val, currency='XOF'):
    if hasattr(val, 'amount'):
        return val
    return Money(Decimal(str(val)), currency)


def get_platform_commission_percent():
    return Decimal(str(getattr(settings, 'PLATFORM_COMMISSION_PERCENT', 0)))


def get_min_withdrawal_amount():
    return Decimal(str(getattr(settings, 'WITHDRAWAL_MIN_AMOUNT', 0)))


def get_or_create_wallet(shop):
    wallet, _ = SellerWallet.objects.get_or_create(shop=shop)
    return wallet


def _shop_gross_for_order(order, shop_id):
    lines = order.order_lines.filter(shop_id=shop_id)
    return sum((line.total_price for line in lines), Decimal('0.00'))


def release_order_funds(order):
    """Crédite chaque boutique de sa part nette (après commission).
    Idempotent : un seul crédit par (commande, boutique)."""
    if order.payment_status != 'paid':
        return []
    commission_pct = get_platform_commission_percent()
    shop_ids = list(
        order.order_lines
        .exclude(shop=None)
        .values_list('shop_id', flat=True)
        .distinct()
    )
    released = []
    with transaction.atomic():
        for shop_id in shop_ids:
            try:
                shop = Shops.objects.get(id=shop_id)
            except Shops.DoesNotExist:
                logger.error("Boutique %s introuvable pour crédit commande %s", shop_id, order.order_number)
                continue
            wallet = SellerWallet.objects.select_for_update().get_or_create(shop=shop)[0]
            exists = WalletTransaction.objects.filter(
                wallet=wallet, order=order, source='order_release'
            ).exists()
            if exists:
                continue
            gross = _shop_gross_for_order(order, shop_id)
            if gross <= Decimal('0.00'):
                continue
            commission = (gross * commission_pct / Decimal('100')).quantize(Decimal('0.01'))
            net = gross - commission
            wallet.balance = wallet.balance + _money(net)
            wallet.total_earned = wallet.total_earned + _money(net)
            wallet.save(update_fields=['balance', 'total_earned'])
            WalletTransaction.objects.create(
                wallet=wallet,
                type='credit',
                source='order_release',
                amount=net,
                commission=commission,
                order=order,
                label=f"Commande #{order.order_number}",
            )
            released.append({'shop_id': shop_id, 'net': net, 'commission': commission})
            logger.info(
                "Crédit boutique %s : net=%s commission=%s (commande %s)",
                shop_id, net, commission, order.order_number,
            )
    return released


def request_withdrawal(wallet, amount, method, destination):
    try:
        amount_dec = Decimal(str(amount)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError):
        raise ValidationError("Montant invalide.")
    if amount_dec <= Decimal('0.00'):
        raise ValidationError("Le montant doit être supérieur à 0.")
    min_amount = get_min_withdrawal_amount()
    if amount_dec < min_amount:
        raise ValidationError(f"Le montant minimum de retrait est de {min_amount} XOF.")
    if method not in ('mobile_money', 'bank_transfer'):
        raise ValidationError("Méthode de retrait invalide.")
    if not destination or not destination.strip():
        raise ValidationError("Le numéro/compte de destination est requis.")
    with transaction.atomic():
        wallet_locked = SellerWallet.objects.select_for_update().get(id=wallet.id)
        current = Decimal(str(wallet_locked.balance.amount))
        if amount_dec > current:
            raise ValidationError("Solde insuffisant.")
        wallet_locked.balance = wallet_locked.balance - _money(amount_dec)
        wallet_locked.save(update_fields=['balance'])
        req = WithdrawalRequest.objects.create(
            wallet=wallet_locked,
            amount=amount_dec,
            method=method,
            destination=destination.strip(),
        )
        WalletTransaction.objects.create(
            wallet=wallet_locked,
            type='debit',
            source='withdrawal',
            amount=amount_dec,
            withdrawal=req,
            label=f"Retrait → {destination.strip()} ({req.get_method_display()})",
        )
    return req


def cancel_withdrawal(req, note='', by_staff=False):
    if req.status != 'pending':
        raise ValidationError("Seules les demandes en attente peuvent être annulées.")
    with transaction.atomic():
        wallet_locked = SellerWallet.objects.select_for_update().get(id=req.wallet_id)
        wallet_locked.balance = wallet_locked.balance + _money(req.amount)
        wallet_locked.save(update_fields=['balance'])
        WalletTransaction.objects.create(
            wallet=wallet_locked,
            type='credit',
            source='withdrawal_refund',
            amount=req.amount,
            withdrawal=req,
            label="Remboursement rejeté" if by_staff else "Remboursement annulé",
        )
        req.status = 'rejected' if by_staff else 'cancelled'
        if note:
            req.staff_note = note
        if by_staff:
            req.processed_at = timezone.now()
        req.save(update_fields=['status', 'staff_note', 'processed_at'])
    return req


def mark_withdrawal_paid(req, staff_user):
    if req.status != 'pending':
        raise ValidationError(f"Statut invalide : {req.get_status_display()}.")
    req.status = 'paid'
    req.processed_by = staff_user
    req.processed_at = timezone.now()
    req.save(update_fields=['status', 'processed_by', 'processed_at'])
    return req
