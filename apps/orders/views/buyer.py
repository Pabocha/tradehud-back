from decimal import Decimal
from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from apps.accounts.models import Address
from apps.payments.models import PaymentMethod
from apps.notifications.notifications import create_notification_if_allowed
from apps.orders.models import Orders, Quote, OrderLine, ReturnRequest
from apps.orders.serializers import (
    OrderCreateSerializer, OrderSerializer, OrderPreviewSerializer,
    QuoteSerializer, ReturnRequestCreateSerializer, ReturnRequestSerializer,
)
from ..services import is_quote_expired, is_quote_participant, create_order_from_quote, update_quote_lines_if_provided
from apps.chat.services import notify_quote_event


class BuyerOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        user = self.request.user
        return Orders.objects.filter(customer=user)

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)

    @action(detail=False, methods=["get"], url_path="my-orders")
    def my_orders(self, request):
        queryset = Orders.objects.filter(customer=request.user).order_by("-order_date")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        order = self.get_object()
        if order.customer_id != request.user.id:
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)

        method_ids = request.data.get("payment_method")
        if not isinstance(method_ids, list) or not method_ids:
            return Response({"error": "Champ 'payment_method' requis (liste d'IDs)."}, status=status.HTTP_400_BAD_REQUEST)
        payment_first_name = (request.data.get("first_name") or "").strip()
        payment_last_name = (request.data.get("last_name") or "").strip()
        payment_phone_number = (request.data.get("phone_number") or "").strip()
        if not payment_first_name:
            return Response({"error": "Champ 'first_name' requis."}, status=status.HTTP_400_BAD_REQUEST)
        if not payment_last_name:
            return Response({"error": "Champ 'last_name' requis."}, status=status.HTTP_400_BAD_REQUEST)
        if not payment_phone_number:
            return Response({"error": "Champ 'phone_number' requis."}, status=status.HTTP_400_BAD_REQUEST)

        unique_method_ids = list(set(method_ids))
        methods = PaymentMethod.objects.filter(id__in=unique_method_ids)
        if methods.count() != len(unique_method_ids):
            return Response({"error": "Une ou plusieurs methodes de paiement sont invalides."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            order.payment_method.set(methods)
            order.payment_first_name = payment_first_name
            order.payment_last_name = payment_last_name
            order.payment_phone_number = payment_phone_number
            order.payment_status = "paid"
            order.save(update_fields=["payment_first_name", "payment_last_name", "payment_phone_number", "payment_status"])

        try:
            create_notification_if_allowed(user=order.customer, notification_type="order", title="Paiement confirme", message=f"Le paiement de la commande #{order.order_number} est confirme.")
        except Exception:
            pass

        return Response({"order_id": order.id, "payment_status": order.payment_status, "payment_method": list(order.payment_method.values_list("id", flat=True)), "payment_first_name": order.payment_first_name, "payment_last_name": order.payment_last_name, "payment_phone_number": order.payment_phone_number}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="returnable-items")
    def returnable_items(self, request):
        active_statuses = ("pending", "approved", "shipped_back")
        orders = Orders.objects.filter(customer=request.user, status="delivered").prefetch_related("order_lines__variant__product", "order_lines__product", "return_requests__items").order_by("-order_date")
        active_order_ids = set(ReturnRequest.objects.filter(order__in=orders, status__in=active_statuses).values_list("order_id", flat=True).distinct())
        cancelled_statuses = ("rejected", "cancelled")
        returned_qty_by_line = {}
        for rr in ReturnRequest.objects.filter(order__in=orders).exclude(status__in=cancelled_statuses):
            for item in rr.items.all():
                returned_qty_by_line[item.order_line_id] = returned_qty_by_line.get(item.order_line_id, 0) + item.quantity

        results = []
        for order in orders:
            if order.id in active_order_ids:
                continue
            for line in order.order_lines.all():
                product = line.variant.product if line.variant else line.product
                if not product:
                    continue
                remaining = line.quantity - returned_qty_by_line.get(line.id, 0)
                if remaining <= 0:
                    continue
                image_url = None
                if product.image and hasattr(product.image, "url"):
                    image_url = request.build_absolute_uri(product.image.url)
                results.append({"order_id": order.id, "order_number": order.order_number, "order_line_id": line.id, "product_id": product.id, "variant_id": line.variant_id, "product_name": product.name, "product_image": image_url, "variant_label": line.variant.sku if line.variant else None, "unit_price": float(line.unit_price), "quantity": line.quantity, "returnable_quantity": remaining})
        return Response(results)

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request):
        serializer = OrderPreviewSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        result = serializer.compute_preview()
        return Response(result)


class BuyerReturnRequestViewSet(viewsets.ModelViewSet):
    serializer_class = ReturnRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ReturnRequest.objects.filter(order__customer=self.request.user).select_related('order').prefetch_related('items__order_line__variant__product')

    def get_serializer_class(self):
        if self.action == 'create':
            return ReturnRequestCreateSerializer
        return ReturnRequestSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return_request = serializer.save()
        try:
            create_notification_if_allowed(user=request.user, notification_type="order", title="Demande de retour", message=f"Votre demande de retour pour la commande #{return_request.order.order_number} a ete enregistree.")
        except Exception:
            pass
        return Response(ReturnRequestSerializer(return_request).data, status=status.HTTP_201_CREATED)


class BuyerQuoteViewSet(viewsets.ModelViewSet):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Quote.objects.select_related('user', 'shop', 'converted_order').prefetch_related('lines__product', 'lines__variant__product').filter(user=self.request.user)

    def perform_create(self, serializer):
        shop = serializer.validated_data.get('shop')
        if hasattr(self.request.user, 'seller_account') and shop and shop.owner_id == self.request.user.seller_account.id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Vous ne pouvez pas creer une quote pour votre propre boutique.")
        quote = serializer.save(user=self.request.user, status='draft')
        try:
            notify_quote_event(quote, 'requested', self.request.user)
        except Exception:
            pass

    @action(detail=False, methods=['get'], url_path='my')
    def my_quotes(self, request):
        qs = self.get_queryset().filter(user=request.user).order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        quote = self.get_object()
        if quote.user_id != request.user.id:
            return Response({'error': 'Seul le client peut accepter la quote.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.status not in ('sent', 'countered'):
            return Response({'error': 'Statut invalide pour acceptation.'}, status=status.HTTP_400_BAD_REQUEST)
        if is_quote_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)
        quote.status = 'accepted'
        quote.accepted_at = __import__('django.utils.timezone', fromlist=['now']).now()
        quote.save(update_fields=['status', 'accepted_at', 'updated_at'])
        try:
            notify_quote_event(quote, 'accepted', request.user)
        except Exception:
            pass
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='counter')
    def counter(self, request, pk=None):
        quote = self.get_object()
        if not is_quote_participant(quote, request.user):
            return Response({'error': 'Non autorise.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.status not in ('draft', 'sent', 'countered'):
            return Response({'error': 'Statut invalide pour contre-proposition.'}, status=status.HTTP_400_BAD_REQUEST)
        if is_quote_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)
        update_quote_lines_if_provided(quote, request)
        quote.status = 'countered'
        quote.save(update_fields=['status', 'updated_at'])
        try:
            notify_quote_event(quote, 'countered', request.user)
        except Exception:
            pass
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        quote = self.get_object()
        if not is_quote_participant(quote, request.user):
            return Response({'error': 'Non autorise.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.status in ('converted', 'rejected'):
            return Response({'error': 'Action non autorisee pour ce statut.'}, status=status.HTTP_400_BAD_REQUEST)
        quote.status = 'rejected'
        quote.save(update_fields=['status', 'updated_at'])
        try:
            notify_quote_event(quote, 'rejected', request.user)
        except Exception:
            pass
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        quote = self.get_object()
        if quote.user_id != request.user.id:
            return Response({'error': 'Seul le client de la quote peut convertir en commande.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.status != 'accepted':
            return Response({'error': 'La quote doit etre acceptee avant checkout.'}, status=status.HTTP_400_BAD_REQUEST)
        if is_quote_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.converted_order_id:
            return Response({'detail': 'Quote deja convertie.', 'order_id': quote.converted_order_id}, status=status.HTTP_200_OK)

        address_id = request.data.get('origin_address')
        if not address_id:
            return Response({'error': "Champ 'origin_address' requis (ID de l'adresse)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            origin_address = Address.objects.get(id=address_id, customer=request.user)
        except (Address.DoesNotExist, ValueError):
            return Response({'error': "Adresse introuvable ou ne vous appartient pas."}, status=status.HTTP_400_BAD_REQUEST)
        if origin_address.address_type not in ('shipping', 'both'):
            return Response({'error': "Type d'adresse invalide pour la livraison."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.shipping.services import calculate_shipping_cost
            transport_mode = request.data.get('transport_mode', 'road')
            shipping_result = calculate_shipping_cost(order_lines=quote.lines.all(), destination_address=origin_address, transport_mode=transport_mode)
            delivery_cost = shipping_result['delivery_cost']
        except Exception:
            delivery_cost = Decimal('0')

        try:
            order = create_order_from_quote(user=request.user, quote=quote, origin_address=origin_address, delivery_cost=delivery_cost, mark_paid=False)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            notify_quote_event(quote, 'converted', request.user, order=order)
        except Exception:
            pass
        return Response({'quote_id': quote.id, 'order_id': order.id, 'status': quote.status, 'total_amount': float(order.total_amount.amount)}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path=r'pay/(?P<token>[^/.]+)/preview')
    def pay_preview(self, request, token=None):
        quote = Quote.objects.filter(payment_link_token=token).prefetch_related('lines__product', 'lines__variant__product').select_related('shop', 'user').first()
        if not quote:
            return Response({'error': 'Lien de paiement invalide.'}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id:
            return Response({'error': 'Ce lien ne vous appartient pas.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.converted_order_id:
            return Response({'error': 'Cette quote est deja convertie.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.payment_link_expires_at is None or quote.payment_link_expires_at <= __import__('django.utils.timezone', fromlist=['now']).now():
            return Response({'error': 'Lien de paiement expire.'}, status=status.HTTP_400_BAD_REQUEST)

        lines_payload = []
        subtotal = Decimal('0.00')
        for line in quote.lines.all():
            product = line.product or (line.variant.product if line.variant_id else None)
            unit_price = getattr(line.negotiated_price, 'amount', line.negotiated_price)
            line_total = Decimal(str(unit_price)) * int(line.quantity or 0)
            subtotal += line_total
            lines_payload.append({'line_id': line.id, 'product_id': product.id if product else None, 'product_name': product.name if product else None, 'variant_id': line.variant_id, 'quantity': line.quantity, 'negotiated_unit_price': unit_price, 'line_total': line_total})
        return Response({'quote_id': quote.id, 'shop': {'id': quote.shop_id, 'name': quote.shop.name}, 'expires_at': quote.expires_at, 'payment_link_expires_at': quote.payment_link_expires_at, 'lines': lines_payload, 'subtotal': subtotal}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path=r'pay/(?P<token>[^/.]+)')
    def pay_by_token(self, request, token=None):
        from django.utils import timezone as tz
        quote = Quote.objects.filter(payment_link_token=token).select_related('shop', 'user').first()
        if not quote:
            return Response({'error': 'Lien de paiement invalide.'}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id:
            return Response({'error': 'Ce lien ne vous appartient pas.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.converted_order_id:
            return Response({'detail': 'Quote deja convertie.', 'order_id': quote.converted_order_id}, status=status.HTTP_200_OK)
        if quote.payment_link_expires_at is None or quote.payment_link_expires_at <= tz.now():
            return Response({'error': 'Lien de paiement expire.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.status != 'accepted':
            return Response({'error': 'Statut de quote invalide pour paiement. Quote acceptee requise.'}, status=status.HTTP_400_BAD_REQUEST)

        address_id = request.data.get('origin_address')
        if not address_id:
            return Response({'error': "Champ 'origin_address' requis (ID de l'adresse)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            origin_address = Address.objects.get(id=address_id, customer=request.user)
        except (Address.DoesNotExist, ValueError):
            return Response({'error': "Adresse introuvable ou ne vous appartient pas."}, status=status.HTTP_400_BAD_REQUEST)
        if origin_address.address_type not in ('shipping', 'both'):
            return Response({'error': "Type d'adresse invalide pour la livraison."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.shipping.services import calculate_shipping_cost
            transport_mode = request.data.get('transport_mode', 'road')
            shipping_result = calculate_shipping_cost(order_lines=quote.lines.all(), destination_address=origin_address, transport_mode=transport_mode)
            delivery_cost = shipping_result['delivery_cost']
        except Exception:
            delivery_cost = Decimal('0')

        try:
            order = create_order_from_quote(user=request.user, quote=quote, origin_address=origin_address, delivery_cost=delivery_cost, mark_paid=True)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        try:
            notify_quote_event(quote, 'converted', request.user, order=order)
        except Exception:
            pass
        return Response({'quote_id': quote.id, 'order_id': order.id, 'status': quote.status, 'payment_status': order.payment_status, 'total_amount': float(order.total_amount.amount)}, status=status.HTTP_201_CREATED)
