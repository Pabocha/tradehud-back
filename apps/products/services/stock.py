from django.db import transaction
from django.db.models import Sum
from django.conf import settings
from apps.notifications.notifications import create_notification_if_allowed


LOW_STOCK_THRESHOLD = 5


def record_stock_movement(
    product=None,
    variant=None,
    movement_type='adjustment',
    quantity=0,
    reference_type=None,
    reference_id=None,
    note=None,
    created_by=None,
):
    """
    Enregistre un mouvement de stock (event sourcing).
    Met à jour le cache stock_quantity atomiquement.
    """
    from apps.products.models import StockMovement

    if not product and not variant:
        raise ValueError("product ou variant requis")

    target = variant or product
    previous_stock = target.stock_quantity or 0
    new_stock = previous_stock + quantity

    if new_stock < 0:
        raise ValueError(
            f"Stock insuffisant pour {target}: "
            f"actuel={previous_stock}, mouvement={quantity}, résultat={new_stock}"
        )

    with transaction.atomic():
        target.stock_quantity = new_stock
        target.save(update_fields=['stock_quantity'])

        movement = StockMovement.objects.create(
            product=product,
            variant=variant,
            movement_type=movement_type,
            quantity=quantity,
            previous_stock=previous_stock,
            new_stock=new_stock,
            reference_type=reference_type,
            reference_id=reference_id,
            note=note,
            created_by=created_by,
        )

    if new_stock <= LOW_STOCK_THRESHOLD:
        _send_low_stock_alert(target, new_stock)

    return movement


def _send_low_stock_alert(target, current_stock):
    """Envoie une alerte de stock bas au propriétaire de la boutique."""
    try:
        if hasattr(target, 'shop') and target.shop:
            owner = target.shop.owner.user if hasattr(target.shop, 'owner') else None
            if owner:
                create_notification_if_allowed(
                    user=owner,
                    notification_type='product',
                    title='Stock bas',
                    message=f'Le produit "{target}" a un stock de {current_stock} unités.',
                )
    except Exception:
        pass


def verify_stock_consistency():
    """
    Vérifie la cohérence entre stock_quantity et la somme des mouvements.
    Retourne les incohérences trouvées.
    """
    from apps.products.models import Products, ProductVariant

    inconsistencies = []

    for product in Products.objects.filter(is_active=True).iterator():
        if product.variants.exists():
            continue
        if product.stock_quantity is None:
            continue

        total_from_movements = (
            StockMovement.objects
            .filter(product=product)
            .aggregate(total=Sum('quantity'))['total'] or 0
        )

        if total_from_movements != product.stock_quantity:
            inconsistencies.append({
                'type': 'product',
                'id': product.id,
                'name': str(product),
                'cached_stock': product.stock_quantity,
                'movement_stock': total_from_movements,
                'difference': product.stock_quantity - total_from_movements,
            })

    for variant in ProductVariant.objects.select_related('product').filter(
        product__is_active=True
    ).iterator():
        total_from_movements = (
            StockMovement.objects
            .filter(variant=variant)
            .aggregate(total=Sum('quantity'))['total'] or 0
        )

        if total_from_movements != variant.stock_quantity:
            inconsistencies.append({
                'type': 'variant',
                'id': variant.id,
                'name': f"{variant.product.name} [{variant.sku}]",
                'cached_stock': variant.stock_quantity,
                'movement_stock': total_from_movements,
                'difference': variant.stock_quantity - total_from_movements,
            })

    return inconsistencies
