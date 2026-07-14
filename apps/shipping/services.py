from decimal import Decimal
from django.db.models import Q
from .models import ShippingRate


def get_zone_for_country(country_code):
    """Trouve la zone de livraison pour un code pays donné."""
    from .models import ShippingZone
    country_code = (country_code or '').upper().strip()

    zones = ShippingZone.objects.filter(is_active=True)
    for zone in zones:
        if country_code in zone.countries:
            return zone
    return None


def calculate_shipping_cost(order_lines, country_code, method='standard', shop_ids=None, subtotal=None):
    """
    Calcule le coût de livraison total pour une commande.

    Args:
        order_lines: queryset de OrderLine (pour calculer le poids total)
        country_code: code pays ISO de livraison
        method: 'standard', 'express', ou 'pickup'
        shop_ids: liste des IDs de boutiques impliquées (si None, on déduit des order_lines)
        subtotal: sous-total de la commande (pour vérifier le free_shipping_threshold)

    Returns:
        dict: {
            'delivery_cost': Decimal,
            'estimated_days': str,
            'rate_details': list  # détail par boutique
        }
    """
    if shop_ids is None:
        shop_ids = list(order_lines.values_list('shop_id', flat=True).distinct())

    zone = get_zone_for_country(country_code)
    if not zone:
        return {
            'delivery_cost': Decimal('0.00'),
            'estimated_days': 'Non disponible',
            'rate_details': [],
            'error': f"Aucune zone de livraison pour le pays {country_code}",
        }

    total_cost = Decimal('0.00')
    rate_details = []
    min_days = 0
    max_days = 0

    for shop_id in shop_ids:
        shop_subtotal = None
        if subtotal and len(shop_ids) > 1:
            # Répartir le sous-total proportionnellement par boutique
            shop_lines_total = sum(
                line.total_price for line in order_lines.filter(shop_id=shop_id)
            )
            total_all = sum(
                line.total_price for line in order_lines
            )
            if total_all > 0:
                shop_subtotal = subtotal * (shop_lines_total / total_all)

        rate = (
            ShippingRate.objects.filter(
                zone=zone, method=method, is_active=True
            ).filter(
                Q(shop_id=shop_id) | Q(shop__isnull=True)
            ).order_by(
                'shop__isnull'
            ).first()
        )

        if not rate:
            rate_details.append({
                'shop_id': shop_id,
                'rate_id': None,
                'cost': Decimal('0.00'),
                'note': 'Aucun tarif trouvé',
            })
            continue

        effective_subtotal = shop_subtotal or subtotal

        if rate.free_shipping_threshold and effective_subtotal:
            if Decimal(str(effective_subtotal)) >= rate.free_shipping_threshold:
                rate_details.append({
                    'shop_id': shop_id,
                    'rate_id': rate.id,
                    'cost': Decimal('0.00'),
                    'note': 'Livraison gratuite (seuil atteint)',
                })
                continue

        cost = rate.base_price

        rate_details.append({
            'shop_id': shop_id,
            'rate_id': rate.id,
            'cost': cost,
        })
        total_cost += cost

        if min_days == 0 or rate.min_delivery_days < min_days:
            min_days = rate.min_delivery_days
        if rate.max_delivery_days > max_days:
            max_days = rate.max_delivery_days

    estimated_days = f"{min_days}-{max_days} jours" if max_days > 0 else "Non disponible"

    return {
        'delivery_cost': total_cost,
        'estimated_days': estimated_days,
        'rate_details': rate_details,
    }
