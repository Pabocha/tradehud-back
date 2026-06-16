from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError

from .models import Coupon, CouponUsage

TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _line_product(line):
    if line.variant:
        return line.variant.product
    return line.product


def _is_line_eligible(coupon, line):
    product = _line_product(line)
    if not product:
        return False

    if coupon.scope == "cart":
        return True
    if coupon.scope == "product":
        return coupon.target_products.filter(id=product.id).exists()
    if coupon.scope == "category":
        if not product.category_id:
            return False
        return coupon.target_categories.filter(id=product.category_id).exists()
    if coupon.scope == "shop":
        return coupon.target_shops.filter(id=product.shop_id).exists()
    return False


def apply_coupon(user, coupon_code, order_lines, subtotal, delivery_cost, lock_for_update=True):
    empty_result = {
        "coupon": None,
        "eligible_subtotal": _money(subtotal),
        "discount_on_items": Decimal("0.00"),
        "discount_on_shipping": Decimal("0.00"),
        "total_discount": Decimal("0.00"),
    }

    if not coupon_code:
        return empty_result

    if not user or not getattr(user, "is_authenticated", False):
        raise ValidationError({"coupon_code": "Authentification requise pour appliquer un coupon."})

    try:
        coupon_queryset = Coupon.objects
        if lock_for_update:
            coupon_queryset = coupon_queryset.select_for_update()
        coupon = coupon_queryset.get(code__iexact=coupon_code.strip())
    except Coupon.DoesNotExist:
        raise ValidationError({"coupon_code": "Code promo invalide."})

    if not coupon.is_valid_now():
        raise ValidationError({"coupon_code": "Coupon inactif, expire ou quota atteint."})

    if coupon.audience in ("targeted", "single") and not coupon.users.filter(id=user.id).exists():
        raise ValidationError({"coupon_code": "Vous n'etes pas eligible a ce coupon."})

    if coupon.audience == "single" and CouponUsage.objects.filter(coupon=coupon, user=user).exists():
        raise ValidationError({"coupon_code": "Ce coupon utilisateur unique a deja ete utilise."})

    eligible_subtotal = Decimal("0.00")
    lines = list(order_lines)
    if coupon.scope != "shipping":
        for line in lines:
            if _is_line_eligible(coupon, line):
                eligible_subtotal += _money(line.total_price)

    eligible_subtotal = _money(eligible_subtotal)

    discount_on_items = Decimal("0.00")
    discount_on_shipping = Decimal("0.00")

    if coupon.scope == "shipping":
        shipping_base = _money(delivery_cost)
        if shipping_base <= Decimal("0.00"):
            raise ValidationError({"coupon_code": "Ce coupon s'applique uniquement aux frais de livraison."})

        if coupon.shipping_discount_type == "percent":
            percent = _money(coupon.shipping_discount_percent or 0)
            if percent <= Decimal("0.00") or percent > Decimal("100.00"):
                raise ValidationError({"coupon_code": "Pourcentage de livraison invalide."})
            discount_on_shipping = _money(shipping_base * percent / Decimal("100"))
        elif coupon.shipping_discount_type == "fixed":
            fixed = _money(coupon.shipping_discount_value or 0)
            if fixed <= Decimal("0.00"):
                raise ValidationError({"coupon_code": "Montant fixe de livraison invalide."})
            discount_on_shipping = fixed
        else:
            raise ValidationError({"coupon_code": "Type de reduction livraison invalide."})

        discount_on_shipping = min(discount_on_shipping, shipping_base)
    else:
        if eligible_subtotal <= Decimal("0.00"):
            raise ValidationError({"coupon_code": "Aucun article eligible dans ce panier."})

        if coupon.min_order_amount and eligible_subtotal < _money(coupon.min_order_amount):
            raise ValidationError({"coupon_code": "Le montant minimum requis n'est pas atteint."})

        if coupon.discount_type == "percent":
            discount_on_items = _money(eligible_subtotal * _money(coupon.discount_value) / Decimal("100"))
        elif coupon.discount_type == "fixed":
            discount_on_items = _money(coupon.discount_value)
        else:
            raise ValidationError({"coupon_code": "Type de reduction invalide pour ce coupon."})

        discount_on_items = min(discount_on_items, eligible_subtotal)

    total_discount = _money(discount_on_items + discount_on_shipping)

    return {
        "coupon": coupon,
        "eligible_subtotal": eligible_subtotal,
        "discount_on_items": discount_on_items,
        "discount_on_shipping": discount_on_shipping,
        "total_discount": total_discount,
    }
