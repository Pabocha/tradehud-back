from celery import shared_task
from django.db.models import Sum
from apps.notifications.notifications import create_notification_if_allowed


@shared_task
def verify_stock_consistency_task():
    """
    Tâche Celery pour vérifier la cohérence du stock.
    Compare stock_quantity (cache) vs somme des StockMovement (source de vérité).
    """
    from apps.products.models import Products, ProductVariant, StockMovement

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
            })

    if inconsistencies:
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            staff_users = User.objects.filter(is_staff=True)
            for user in staff_users:
                create_notification_if_allowed(
                    user=user,
                    notification_type='product',
                    title='Incohérence de stock détectée',
                    message=f'{len(inconsistencies)} produit(s)/variante(s) avec stock incohérent.',
                )
        except Exception:
            pass

    return {
        'checked_products': Products.objects.filter(is_active=True).count(),
        'checked_variants': ProductVariant.objects.filter(product__is_active=True).count(),
        'inconsistencies_count': len(inconsistencies),
        'inconsistencies': inconsistencies,
    }
