from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from .models import Orders, Quote, OrderLine
from apps.products.models import ProductVariant, Products


def is_quote_shop_owner(quote, user):
    return hasattr(user, 'seller_account') and quote.shop.owner_id == user.seller_account.id


def is_quote_participant(quote, user):
    return quote.user_id == user.id or is_quote_shop_owner(quote, user)


def is_quote_expired(quote):
    return quote.expires_at <= timezone.now()


def create_order_from_quote(
    user,
    quote,
    origin_address,
    delivery_cost,
    mark_paid=False,
    payment_first_name=None,
    payment_last_name=None,
    payment_phone_number=None,
):
    lines = list(quote.lines.select_related('product', 'variant', 'variant__product').all())
    if not lines:
        raise ValueError('Quote sans lignes.')

    with transaction.atomic():
        order = Orders.objects.create(
            customer=user,
            origin_address=origin_address,
            delivery_cost=delivery_cost,
            total_amount=Decimal('0.00'),
            payment_status='paid' if mark_paid else 'pending',
            payment_first_name=payment_first_name,
            payment_last_name=payment_last_name,
            payment_phone_number=payment_phone_number,
        )

        subtotal = Decimal('0.00')
        for line in lines:
            qty = int(line.quantity or 0)
            if qty <= 0:
                raise ValueError('Quantite invalide dans la quote.')

            product = line.product or (line.variant.product if line.variant_id else None)
            if product is None:
                raise ValueError('Ligne de quote sans produit/variante valide.')

            if line.variant_id:
                variant = ProductVariant.objects.select_for_update().get(id=line.variant_id)
                if variant.stock_quantity < qty:
                    raise ValueError(f"Stock insuffisant pour la variante {variant.id}.")
                variant.stock_quantity -= qty
                variant.save(update_fields=['stock_quantity'])
            else:
                variant = None
                product_locked = Products.objects.select_for_update().get(id=product.id)
                if product_locked.stock_quantity is None or product_locked.stock_quantity < qty:
                    raise ValueError(f"Stock insuffisant pour le produit {product_locked.id}.")
                product_locked.stock_quantity -= qty
                product_locked.save(update_fields=['stock_quantity'])

            unit_price = getattr(line.negotiated_price, 'amount', line.negotiated_price)
            line_total = Decimal(str(unit_price)) * qty
            subtotal += line_total

            OrderLine.objects.create(
                order=order,
                variant=variant,
                product=product if variant is None else None,
                shop=quote.shop,
                quantity=qty,
                unit_price=unit_price,
            )

        order.total_amount = subtotal + delivery_cost
        order.save(update_fields=['total_amount'])

        quote.status = 'converted'
        quote.converted_order = order
        quote.payment_link_token = None
        quote.payment_link_expires_at = None
        quote.save(update_fields=['status', 'converted_order', 'payment_link_token', 'payment_link_expires_at', 'updated_at'])

    return order
