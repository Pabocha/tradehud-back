from decimal import Decimal
import logging
import math

from .models import ShippingZone, Warehouse, PackageSize, ShippingPricing

logger = logging.getLogger(__name__)


def get_zone_for_address(country_code, city=None):
    """
    Trouve la zone de livraison pour une adresse.
    Priorité: match par ville (priority) > match par pays.
    """
    country_code = (country_code or '').upper().strip()
    city = (city or '').strip()

    zones = ShippingZone.objects.filter(is_active=True)

    if city:
        for zone in zones.order_by('-priority'):
            if country_code in zone.countries and city in zone.cities:
                return zone

    for zone in zones.order_by('-priority'):
        if country_code in zone.countries:
            return zone

    return None


def get_port_zone_for_country(country_code):
    """Trouve la zone contenant un port/aéroport pour un pays donné."""
    country_code = (country_code or '').upper().strip()
    zones = ShippingZone.objects.filter(
        is_active=True, has_port=True, countries__contains=country_code
    ).order_by('-priority')
    return zones.first()


def get_warehouse_for_country(country_code):
    """Trouve l'entrepôt actif pour un pays donné."""
    country_code = (country_code or '').upper().strip()
    from django_countries.fields import Country
    return Warehouse.objects.filter(
        is_active=True, country=Country(country_code)
    ).first()


def get_default_warehouse():
    """Retourne l'entrepôt principal (premier actif). Utilisé pour l'envoi international."""
    return Warehouse.objects.filter(is_active=True).order_by('id').first()


def get_effective_dimensions(variant=None, product=None):
    """
    Récupère les dimensions effectives d'un produit/variante.
    La variante a priorité, sinon fallback sur le produit.
    Retourne (weight_kg, length_cm, width_cm, height_cm).
    """
    if variant:
        weight = variant.get_effective_weight()
        length = variant.get_effective_length()
        width = variant.get_effective_width()
        height = variant.get_effective_height()
    elif product:
        weight = product.weight
        length = product.length
        width = product.width
        height = product.height
    else:
        return None, None, None, None

    return weight, length, width, height


def determine_package_size(weight_kg=None, length_cm=None, width_cm=None, height_cm=None):
    """
    Détermine la taille du colis en fonction des dimensions.
    Un produit = un colis. On prend la première taille dont
    toutes les dimensions sont inférieures ou égales aux max.
    """
    sizes = PackageSize.objects.all().order_by('display_order')

    for size in sizes:
        fits = True
        if weight_kg is not None and weight_kg > size.max_weight_kg:
            fits = False
        if length_cm is not None and length_cm > size.max_length_cm:
            fits = False
        if width_cm is not None and width_cm > size.max_width_cm:
            fits = False
        if height_cm is not None and height_cm > size.max_height_cm:
            fits = False
        if fits:
            return size

    return sizes.last() if sizes.exists() else None


def _compute_cost_for_leg(origin_zone, destination_zone, package_size, transport_mode, weight_kg=None):
    """
    Calcule le coût pour un trajet entre deux zones.
    Retourne (cost, days_min, days_max) ou (None, 0, 0) si aucun tarif.
    """
    pricing = ShippingPricing.objects.filter(
        origin_zone=origin_zone,
        destination_zone=destination_zone,
        package_size=package_size,
        transport_mode=transport_mode,
        is_active=True,
    ).first()

    if not pricing:
        return None, 0, 0

    cost = pricing.compute_cost(weight_kg=weight_kg)
    return cost, pricing.estimated_days_min, pricing.estimated_days_max


def calculate_shipping_cost(order_lines, destination_address, transport_mode='road'):
    """
    Calcule le coût de livraison total pour une commande.

    Logique (groupée par taille de colis):
    1. Zone de destination = adresse client
    2. Entrepôt d'origine = premier entrepôt actif du pays destination
       Si aucun → premier entrepôt actif (principal) → international
    3. Pour CHAQUE OrderLine, résoudre dimensions + PackageSize
    4. Regrouper les articles par PackageSize
    5. Pour chaque groupe:
       a. weight_total = somme(poids × quantité)
       b. volume_total = somme(longueur × largeur × hauteur × quantité)
       c. n_colis = max(ceil(weight_total / max_weight), ceil(volume_total / max_volume))
       d. Coût = n_colis × cost_per_colis(route)
    6. Total = somme des coûts de tous les groupes
    7. Estimated days = le plus long des groupes

    Args:
        order_lines: queryset d'OrderLine
        destination_address: objet Address ou dict avec country, city
        transport_mode: 'road', 'sea', ou 'air' (pour fret international)

    Returns:
        dict: {
            'delivery_cost': Decimal,
            'estimated_days': str,
            'is_international': bool,
            'colis_details': list,
        }
    """
    if hasattr(destination_address, 'country'):
        dest_country = str(destination_address.country).upper().strip()
        dest_city = getattr(destination_address, 'city', '') or ''
    else:
        dest_country = (destination_address.get('country', '') or '').upper().strip()
        dest_city = destination_address.get('city', '') or ''

    dest_zone = get_zone_for_address(dest_country, dest_city)
    if not dest_zone:
        return {
            'delivery_cost': Decimal('0.00'),
            'estimated_days': 'Non disponible',
            'is_international': False,
            'colis_details': [],
            'error': f"Aucune zone de livraison pour {dest_country}",
        }

    warehouse = get_warehouse_for_country(dest_country)
    if not warehouse:
        warehouse = get_default_warehouse()
    if not warehouse:
        return {
            'delivery_cost': Decimal('0.00'),
            'estimated_days': 'Non disponible',
            'is_international': False,
            'colis_details': [],
            'error': f"Aucun entrepôt actif",
        }

    origin_zone = warehouse.zone
    origin_country = str(warehouse.country).upper().strip()
    is_international = (origin_country != dest_country)

    # --- Phase 1 : résoudre les dimensions et regrouper par taille de colis ---
    groups = {}  # { package_size_id: { 'size': PackageSize, 'items': [...], 'total_weight': Decimal, 'total_volume': Decimal } }

    for line in order_lines:
        variant = line.variant
        product = line.product
        quantity = line.quantity or 1

        weight_kg, length_cm, width_cm, height_cm = get_effective_dimensions(
            variant=variant, product=product
        )

        package_size = determine_package_size(weight_kg, length_cm, width_cm, height_cm)
        if not package_size:
            logger.warning("Aucune taille de colis trouvée pour order_line %s", line.id)
            continue

        w = Decimal(str(weight_kg)) if weight_kg else Decimal('0')
        item_volume = Decimal('0')
        if length_cm and width_cm and height_cm:
            item_volume = Decimal(str(length_cm)) * Decimal(str(width_cm)) * Decimal(str(height_cm))

        product_name = ''
        if variant and variant.product:
            product_name = variant.product.name
        elif product:
            product_name = product.name

        gid = package_size.id
        if gid not in groups:
            groups[gid] = {
                'size': package_size,
                'total_weight': Decimal('0'),
                'total_volume': Decimal('0'),
                'items': [],
            }
        groups[gid]['total_weight'] += w * quantity
        groups[gid]['total_volume'] += item_volume * quantity
        groups[gid]['items'].append({
            'product_name': product_name,
            'quantity': quantity,
            'weight_kg': weight_kg,
            'dimensions': {'length': length_cm, 'width': width_cm, 'height': height_cm},
        })

    # --- Phase 2 : calculer le coût par groupe ---
    total_cost = Decimal('0.00')
    max_days_min = 0
    max_days_max = 0
    colis_details = []

    for gid, group in groups.items():
        pkg = group['size']
        total_weight = group['total_weight']
        total_volume = group['total_volume']

        max_weight = pkg.max_weight_kg or Decimal('999')
        max_volume = Decimal('0')
        if pkg.max_length_cm and pkg.max_width_cm and pkg.max_height_cm:
            max_volume = Decimal(str(pkg.max_length_cm)) * Decimal(str(pkg.max_width_cm)) * Decimal(str(pkg.max_height_cm))

        n_by_weight = math.ceil(total_weight / max_weight) if max_weight > 0 and total_weight > 0 else 1
        n_by_volume = math.ceil(total_volume / max_volume) if max_volume > 0 and total_volume > 0 else 1
        n_colis = max(n_by_weight, n_by_volume)

        # Coût unitaire pour une taille de colis donnée sur cette route
        colis_unit_cost = Decimal('0.00')
        days_min = 0
        days_max = 0

        if not is_international:
            cost, d_min, d_max = _compute_cost_for_leg(
                origin_zone, dest_zone, pkg, 'road', total_weight
            )
            if cost is not None:
                colis_unit_cost = cost
                days_min = d_min
                days_max = d_max
            else:
                logger.warning(
                    "Aucun tarif road: %s → %s, taille %s",
                    origin_zone.name, dest_zone.name, pkg.name
                )
        else:
            port_origin = get_port_zone_for_country(origin_country)
            port_dest = get_port_zone_for_country(dest_country)

            if not port_origin or not port_dest:
                logger.warning(
                    "Port manquant pour international %s → %s",
                    origin_country, dest_country
                )
                continue

            cost1, d1_min, d1_max = _compute_cost_for_leg(
                origin_zone, port_origin, pkg, 'road', total_weight
            )
            cost2, d2_min, d2_max = _compute_cost_for_leg(
                port_origin, port_dest, pkg, transport_mode, total_weight
            )
            cost3, d3_min, d3_max = _compute_cost_for_leg(
                port_dest, dest_zone, pkg, 'road', total_weight
            )

            if cost1 is None:
                logger.warning("Leg1 manquant: %s → %s", origin_zone.name, port_origin.name)
            if cost2 is None:
                logger.warning("Leg2 manquant: %s → %s (%s)", port_origin.name, port_dest.name, transport_mode)
            if cost3 is None:
                logger.warning("Leg3 manquant: %s → %s", port_dest.name, dest_zone.name)

            colis_unit_cost = (cost1 or Decimal('0')) + (cost2 or Decimal('0')) + (cost3 or Decimal('0'))
            days_min = d1_min + d2_min + d3_min
            days_max = d1_max + d2_max + d3_max

        group_total_cost = colis_unit_cost * n_colis
        total_cost += group_total_cost

        if days_max > max_days_max:
            max_days_max = days_max
        if days_min > max_days_min:
            max_days_min = days_min

        colis_details.append({
            'package_size': pkg.display_name,
            'n_colis': n_colis,
            'total_weight_kg': float(total_weight),
            'colis_unit_cost': float(colis_unit_cost),
            'group_total_cost': float(group_total_cost),
            'items': group['items'],
        })

    estimated_days = (
        f"{max_days_min}-{max_days_max} jours"
        if max_days_max > 0
        else "Non disponible"
    )

    return {
        'delivery_cost': total_cost,
        'estimated_days': estimated_days,
        'is_international': is_international,
        'colis_details': colis_details,
    }
