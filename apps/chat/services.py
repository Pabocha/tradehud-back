def resolve_quote_room(quote):
    """Retrouve la room de chat liee a une quote (membres = acheteur + proprio de la boutique,
    produit epingle de la meme boutique)."""
    from .models import ChatRoom

    if not quote or not quote.shop_id or not quote.user_id:
        return None
    owner_user_id = None
    if quote.shop and quote.shop.owner:
        owner_user_id = quote.shop.owner.user_id
    if not owner_user_id:
        return None

    return (
        ChatRoom.objects
        .filter(pinned_product__shop_id=quote.shop_id)
        .filter(member=quote.user_id)
        .filter(member=owner_user_id)
        .distinct()
        .order_by("-last_updated")
        .first()
    )


def _format_amount(amount):
    try:
        return f"{int(round(float(amount))):,}".replace(",", " ") + " F"
    except (TypeError, ValueError):
        return None


def _quote_first_line(quote):
    return quote.lines.select_related("product", "variant__product").first()


def _quote_product_name(quote):
    line = _quote_first_line(quote)
    product = None
    if line:
        product = line.product or (line.variant.product if line.variant_id else None)
    return product.name if product else "ce produit"


def _quote_amount(quote):
    line = _quote_first_line(quote)
    if not line:
        return None
    return getattr(line.negotiated_price, "amount", line.negotiated_price)


def _quote_event_text(quote, event, actor_user=None, order=None):
    product_name = _quote_product_name(quote)
    amount = _quote_amount(quote)
    price_txt = _format_amount(amount)

    actor_name = ""
    if actor_user is not None:
        first = actor_user.first_name or ""
        last = actor_user.last_name or ""
        actor_name = f"{first} {last}".strip()

    if event == "requested":
        return (
            f"{actor_name or 'Le client'} a demande un devis pour {product_name}."
            + (f" Proposition : {price_txt}." if price_txt else "")
        )
    if event == "sent":
        return (
            f"Le vendeur propose {price_txt} pour {product_name}." if price_txt
            else f"Le vendeur a envoye sa proposition pour {product_name}."
        )
    if event == "countered":
        return (
            f"Nouvelle contre-proposition : {price_txt} pour {product_name}." if price_txt
            else f"Contre-proposition sur le devis de {product_name}."
        )
    if event == "accepted":
        return f"Le devis pour {product_name} a ete accepte."
    if event == "rejected":
        return f"Le devis pour {product_name} a ete refuse."
    if event == "payment_link":
        return "Un lien de paiement a ete genere pour ce devis."
    if event == "converted":
        order_number = order.order_number if order is not None else None
        if order_number:
            return f"Commande {order_number} creee depuis le devis."
        return "Une commande a ete creee depuis le devis."
    return None


def notify_quote_event(quote, event, actor_user=None, order=None):
    """Ecrit un message texte dans la room du devis et broadcast WS
    (action 'message' + action 'quote' pour mettre a jour le banner en temps reel)."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from .models import ChatMessage
    from .serializers import ChatMessageSerializer

    room = resolve_quote_room(quote)
    if not room:
        return

    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            room.roomId,
            {
                "type": "chat_message",
                "message": {
                    "action": "quote",
                    "roomId": room.roomId,
                    "quote_id": quote.id,
                    "quote_status": quote.status,
                },
            },
        )

    text = _quote_event_text(quote, event, actor_user, order)
    if not text:
        return

    chat_message = ChatMessage.objects.create(
        chat=room,
        user=actor_user,
        message=text[:255],
        message_type="text",
    )
    payload = ChatMessageSerializer(chat_message).data
    payload["action"] = "message"
    payload["roomId"] = room.roomId

    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            room.roomId,
            {
                "type": "chat_message",
                "message": payload,
            },
        )
