from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.core.exceptions import ValidationError as DjangoValidationError

from apps.coupons.service import apply_coupon


def preview_coupon(cart_items, user, coupon_code, delivery_cost, selected_ids=None):
    coupon_code = (coupon_code or "").strip()

    try:
        delivery_cost = Decimal(str(delivery_cost or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("delivery_cost invalide.")

    if selected_ids is not None:
        if not isinstance(selected_ids, list):
            raise ValueError("cart_item_ids doit etre une liste d'identifiants.")
        parsed_ids = []
        for raw_id in selected_ids:
            try:
                parsed_ids.append(int(raw_id))
            except (TypeError, ValueError):
                raise ValueError("Tous les cart_item_ids doivent etre des entiers.")
        cart_items = cart_items.filter(id__in=parsed_ids)

    if not cart_items.exists():
        raise ValueError("Votre panier est vide.")

    order_lines = []
    subtotal = Decimal("0.00")

    for item in cart_items:
        if item.unit_price is not None and hasattr(item.unit_price, "amount"):
            unit_price_amount = Decimal(str(item.unit_price.amount))
        else:
            current_price = item.get_current_price()
            unit_price_amount = Decimal(
                str(getattr(current_price, "amount", current_price))
            )

        line_total = unit_price_amount * Decimal(str(item.quantity))
        subtotal += line_total

        order_lines.append(
            SimpleNamespace(
                variant=item.variant,
                product=item.product,
                total_price=line_total,
            )
        )

    try:
        coupon_result = apply_coupon(
            user=user,
            coupon_code=coupon_code,
            order_lines=order_lines,
            subtotal=subtotal,
            delivery_cost=delivery_cost,
            lock_for_update=False,
        )
    except DjangoValidationError as exc:
        if hasattr(exc, "message_dict"):
            raise ValueError(exc.message_dict)
        message = exc.messages[0] if getattr(exc, "messages", None) else "Coupon invalide."
        raise ValueError(message)

    total_discount = Decimal(str(coupon_result["total_discount"]))
    total_after_discount = subtotal - total_discount + delivery_cost
    if total_after_discount < Decimal("0.00"):
        total_after_discount = Decimal("0.00")

    coupon = coupon_result.get("coupon")

    return {
        "coupon_valid": coupon is not None,
        "coupon_code": coupon.code if coupon else None,
        "coupon_id": coupon.id if coupon else None,
        "scope": coupon.scope if coupon else None,
        "discount_type": coupon.discount_type if coupon else None,
        "discount_value": float(coupon.discount_value) if coupon else None,
        "subtotal": subtotal,
        "delivery_cost": delivery_cost,
        "eligible_subtotal": coupon_result["eligible_subtotal"],
        "discount_on_items": coupon_result["discount_on_items"],
        "discount_on_shipping": coupon_result["discount_on_shipping"],
        "total_discount": total_discount,
        "total_after_discount": total_after_discount,
        "selected_items_count": len(order_lines),
    }
