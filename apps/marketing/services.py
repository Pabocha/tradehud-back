from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Exists, OuterRef
from django.utils import timezone

from apps.products.models import Products, ProductVariant


def select_flash_sale_products(min_discount=15, max_days=5):
    """Retourne les ids des produits éligibles à la vente flash.

    Critères : produit actif + status 'available' + promotion active
    (remise >= min_discount, fin dans <= max_days jours) + stock > 0.
    """
    now = timezone.now()
    min_discount = Decimal(str(min_discount))
    max_days = int(max_days)

    has_variant_stock = ProductVariant.objects.filter(
        product=OuterRef('pk'),
        stock_quantity__gt=0,
    )

    qs = (
        Products.objects
        .filter(
            is_active=True,
            status='available',
            promotions__is_active=True,
            promotions__start_at__lte=now,
            promotions__end_at__gte=now,
            promotions__end_at__lte=now + timedelta(days=max_days),
        )
        .filter(Q(stock_quantity__gt=0) | Exists(has_variant_stock))
        .prefetch_related('promotions')
        .distinct()
    )

    eligible = []
    for p in qs.iterator(chunk_size=200):
        base = p.base_price.amount
        if base <= 0:
            continue
        active = [
            pr for pr in p.promotions.all()
            if pr.is_active and pr.start_at <= now <= pr.end_at
            and pr.end_at <= now + timedelta(days=max_days)
        ]
        if not active:
            continue
        best = min(active, key=lambda pr: pr.promo_price.amount)
        discount_pct = (1 - best.promo_price.amount / base) * 100
        if discount_pct >= min_discount:
            eligible.append(p.id)
    return eligible


def sync_flash_sale_products(flash_sale, min_discount=15, max_days=5, limit=0):
    """Resync totale : remplace la sélection de la vente flash par les produits éligibles."""
    selected = select_flash_sale_products(min_discount, max_days)
    if limit and len(selected) > limit:
        selected = selected[:limit]
    flash_sale.target_type = 'product'
    flash_sale.target_products.set(selected)
    flash_sale.save(update_fields=['target_type', 'updated_at'])
    return selected
