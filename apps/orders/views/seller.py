import secrets
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Q as DQ
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from ..models import Orders, Quote, OrderLine, ReturnRequest, Refund
from ..serializers import OrderSerializer, QuoteSerializer, ReturnRequestSerializer, RefundSerializer
from ..services import is_quote_shop_owner, is_quote_participant, is_quote_expired, update_quote_lines_if_provided
from apps.notifications.notifications import create_notification_if_allowed
from apps.chat.services import notify_quote_event
from apps.wallets.services import release_order_funds


class SellerOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Orders.objects.all()
        if hasattr(user, 'seller_account'):
            shop_ids = list(user.seller_account.shops.values_list("id", flat=True))
            if shop_ids:
                return Orders.objects.filter(order_lines__shop_id__in=shop_ids).distinct()
        return Orders.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated and not (user.is_staff or user.is_superuser) and hasattr(user, 'seller_account'):
            shop_ids = list(user.seller_account.shops.values_list("id", flat=True))
            if shop_ids:
                context["shop_ids"] = shop_ids
        return context

    @action(detail=False, methods=["get"], url_path="shop-orders")
    def shop_orders(self, request):
        user = request.user
        shop_id = request.query_params.get("shop_id")
        context = self.get_serializer_context()

        if user.is_staff or user.is_superuser:
            queryset = Orders.objects.all()
            if shop_id:
                try:
                    shop_id_int = int(shop_id)
                except (TypeError, ValueError):
                    return Response({"error": "shop_id invalide."}, status=status.HTTP_400_BAD_REQUEST)
                queryset = queryset.filter(order_lines__shop_id=shop_id_int).distinct()
                context["shop_id"] = shop_id_int
        else:
            if not hasattr(user, "seller_account"):
                return Response({"error": "Acces reserve aux proprietaires de boutiques."}, status=status.HTTP_403_FORBIDDEN)

            owned_shop_ids = list(user.seller_account.shops.values_list("id", flat=True))
            if not owned_shop_ids:
                queryset = Orders.objects.none()
            elif shop_id:
                try:
                    shop_id_int = int(shop_id)
                except (TypeError, ValueError):
                    return Response({"error": "shop_id invalide."}, status=status.HTTP_400_BAD_REQUEST)
                if shop_id_int not in owned_shop_ids:
                    return Response({"error": "Vous ne pouvez voir que les commandes de vos propres boutiques."}, status=status.HTTP_403_FORBIDDEN)
                queryset = Orders.objects.filter(order_lines__shop_id=shop_id_int).distinct()
                context["shop_id"] = shop_id_int
            else:
                queryset = Orders.objects.filter(order_lines__shop_id__in=owned_shop_ids).distinct()
                context["shop_ids"] = owned_shop_ids

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        payment_status_param = request.query_params.get("payment_status")
        if payment_status_param:
            queryset = queryset.filter(payment_status=payment_status_param)

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                DQ(order_number__icontains=search)
                | DQ(shipping_first_name__icontains=search)
                | DQ(shipping_last_name__icontains=search)
                | DQ(shipping_phone_number__icontains=search)
                | DQ(customer__email__icontains=search)
            )

        queryset = queryset.select_related("customer").prefetch_related("order_lines").order_by("-order_date")

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, context=context)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, context=context)
        return Response(serializer.data)

    @action(detail=True, methods=["patch", "post"], url_path="set-status")
    def set_status(self, request, pk=None):
        order = self.get_object()
        user = request.user

        new_status = request.data.get("status")
        if not new_status:
            return Response({"error": "Champ 'status' requis."}, status=status.HTTP_400_BAD_REQUEST)

        current = order.status

        if user.is_staff or user.is_superuser:
            allowed_transitions = {
                "pending": {"processing", "deposited", "cancelled"},
                "processing": {"deposited", "shipped", "cancelled"},
                "deposited": {"shipped", "in_transit", "delivered", "cancelled"},
                "shipped": {"in_transit", "delivered"},
                "in_transit": {"delivered"},
            }
            allowed = allowed_transitions.get(current, set())
        else:
            if not hasattr(user, "seller_account"):
                return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)
            owned_shop_ids = list(user.seller_account.shops.values_list("id", flat=True))
            if not order.order_lines.filter(shop_id__in=owned_shop_ids).exists():
                return Response(
                    {"error": "Vous ne pouvez modifier que les commandes de vos propres boutiques."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # Le vendeur prepare la commande puis la depose a l'entrepot ;
            # la suite du cycle (expedition, livraison) est geree par la plateforme.
            seller_transitions = {
                "pending": {"deposited", "cancelled"},
                "processing": {"deposited", "cancelled"},
            }
            allowed = seller_transitions.get(current, set())

        if new_status == current:
            return Response({"status": current}, status=status.HTTP_200_OK)
        if new_status not in allowed:
            return Response(
                {"error": "Transition de statut non autorisee.", "from": current, "to": new_status},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.status = new_status
        update_fields = ["status"]
        if new_status == "shipped" and not order.shipping_date:
            order.shipping_date = timezone.now()
            update_fields.append("shipping_date")

        with transaction.atomic():
            order.save(update_fields=update_fields)
            if new_status == "delivered" and order.payment_status == "paid":
                release_order_funds(order)

        status_label = dict(Orders.CHOICES_STATUS).get(new_status, new_status)
        try:
            create_notification_if_allowed(
                user=order.customer,
                notification_type="order",
                title="Mise a jour commande",
                message=f"Le statut de votre commande #{order.order_number} est passe a '{status_label}'.",
            )
        except Exception:
            pass
        return Response({"status": order.status}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path="payment-status")
    def update_payment_status(self, request, pk=None):
        order = self.get_object()
        user = request.user
        if not (user.is_staff or user.is_superuser or order.customer_id == user.id):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)
        new_status = request.data.get("payment_status")
        if not new_status:
            return Response({"error": "Champ 'payment_status' requis."}, status=status.HTTP_400_BAD_REQUEST)
        allowed_transitions = {"pending": {"paid", "failed"}, "paid": {"refunded"}, "failed": {"pending"}, "refunded": set()}
        current = order.payment_status
        if new_status == current:
            return Response({"payment_status": current}, status=status.HTTP_200_OK)
        if new_status not in allowed_transitions.get(current, set()):
            return Response({"error": "Transition de statut non autorisee.", "from": current, "to": new_status}, status=status.HTTP_400_BAD_REQUEST)
        order.payment_status = new_status
        order.save(update_fields=["payment_status"])
        try:
            create_notification_if_allowed(user=order.customer, notification_type="order", title="Mise a jour paiement", message=f"Le statut de paiement de la commande #{order.order_number} est passe a '{new_status}'.")
        except Exception:
            pass
        return Response({"payment_status": order.payment_status}, status=status.HTTP_200_OK)


class SellerQuoteViewSet(viewsets.ModelViewSet):
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Quote.objects.select_related('user', 'shop', 'converted_order').prefetch_related('lines__product', 'lines__variant__product')
        if hasattr(user, 'seller_account'):
            return Quote.objects.filter(shop__owner=user.seller_account).select_related('user', 'shop', 'converted_order').prefetch_related('lines__product', 'lines__variant__product')
        return Quote.objects.none()

    def create(self, request, *args, **kwargs):
        return Response({'error': 'Les vendeurs ne peuvent pas creer de quotes.'}, status=status.HTTP_403_FORBIDDEN)

    def update(self, request, *args, **kwargs):
        return Response({'error': 'Action non autorisee.'}, status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, *args, **kwargs):
        return Response({'error': 'Action non autorisee.'}, status=status.HTTP_403_FORBIDDEN)

    def destroy(self, request, *args, **kwargs):
        return Response({'error': 'Action non autorisee.'}, status=status.HTTP_403_FORBIDDEN)

    @action(detail=False, methods=['get'], url_path='list')
    def shop_quotes(self, request):
        if not hasattr(request.user, 'seller_account'):
            return Response({'error': 'Acces reserve aux vendeurs.'}, status=status.HTTP_403_FORBIDDEN)
        qs = self.get_queryset().filter(shop__owner=request.user.seller_account)
        shop_id = request.query_params.get('shop_id')
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        qs = qs.order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='send')
    def send(self, request, pk=None):
        quote = self.get_object()
        if not is_quote_shop_owner(quote, request.user):
            return Response({'error': 'Seul le vendeur peut envoyer la proposition.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.status not in ('draft', 'countered'):
            return Response({'error': 'Statut invalide pour envoyer la quote.'}, status=status.HTTP_400_BAD_REQUEST)
        if is_quote_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)
        update_quote_lines_if_provided(quote, request)
        quote.status = 'sent'
        quote.save(update_fields=['status', 'updated_at'])
        try:
            notify_quote_event(quote, 'sent', request.user)
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

    @action(detail=True, methods=['post'], url_path='payment-link')
    def payment_link(self, request, pk=None):
        quote = self.get_object()
        if not is_quote_shop_owner(quote, request.user):
            return Response({'error': 'Seul le vendeur peut generer le lien de paiement.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.status != 'accepted':
            return Response({'error': 'La quote doit etre acceptee avant generation du lien.'}, status=status.HTTP_400_BAD_REQUEST)
        if is_quote_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            expires_in_minutes = int(request.data.get('expires_in_minutes', 1440))
        except (TypeError, ValueError):
            return Response({'error': "Champ 'expires_in_minutes' invalide."}, status=status.HTTP_400_BAD_REQUEST)
        expires_in_minutes = max(5, min(expires_in_minutes, 10080))
        token = secrets.token_urlsafe(32)
        link_expires_at = timezone.now() + timedelta(minutes=expires_in_minutes)
        quote.payment_link_token = token
        quote.payment_link_expires_at = link_expires_at
        quote.payment_link_sent_at = timezone.now()
        quote.save(update_fields=['payment_link_token', 'payment_link_expires_at', 'payment_link_sent_at', 'updated_at'])
        preview_relative_url = f"/api/v1/orders/quotes/client/pay/{token}/preview/"
        pay_relative_url = f"/api/v1/orders/quotes/client/pay/{token}/"
        try:
            notify_quote_event(quote, 'payment_link', request.user)
        except Exception:
            pass
        return Response({'quote_id': quote.id, 'token': token, 'payment_link_expires_at': quote.payment_link_expires_at, 'preview_url': request.build_absolute_uri(preview_relative_url), 'pay_url': request.build_absolute_uri(pay_relative_url)}, status=status.HTTP_200_OK)


class SellerReturnRequestViewSet(viewsets.ModelViewSet):
    serializer_class = ReturnRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return ReturnRequest.objects.select_related('order').prefetch_related('items__order_line__variant__product')
        return ReturnRequest.objects.none()

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        return_request = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)
        if return_request.status != 'pending':
            return Response({"error": f"Statut invalide. Statut actuel : {return_request.status}"}, status=status.HTTP_400_BAD_REQUEST)
        return_request.status = 'approved'
        return_request.staff_note = request.data.get('staff_note', '')
        return_request.save(update_fields=['status', 'staff_note', 'updated_at'])
        try:
            create_notification_if_allowed(user=return_request.order.customer, notification_type="order", title="Retour approuve", message=f"Votre retour pour la commande #{return_request.order.order_number} a ete approuve.")
        except Exception:
            pass
        return Response(ReturnRequestSerializer(return_request).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        return_request = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)
        if return_request.status != 'pending':
            return Response({"error": f"Statut invalide. Statut actuel : {return_request.status}"}, status=status.HTTP_400_BAD_REQUEST)
        return_request.status = 'rejected'
        return_request.staff_note = request.data.get('staff_note', '')
        return_request.save(update_fields=['status', 'staff_note', 'updated_at'])
        try:
            create_notification_if_allowed(user=return_request.order.customer, notification_type="order", title="Retour rejete", message=f"Votre retour pour la commande #{return_request.order.order_number} a ete rejete.")
        except Exception:
            pass
        return Response(ReturnRequestSerializer(return_request).data)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete(self, request, pk=None):
        return_request = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)
        if return_request.status not in ('approved', 'shipped_back', 'received'):
            return Response({"error": f"Statut invalide. Statut actuel : {return_request.status}"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            for item in return_request.items.select_related('order_line__variant', 'order_line__product').all():
                if item.order_line.variant:
                    item.order_line.variant.stock_quantity += item.quantity
                    item.order_line.variant.save(update_fields=['stock_quantity'])
                    try:
                        from apps.products.services.stock import record_stock_movement
                        record_stock_movement(variant=item.order_line.variant, quantity=item.quantity, movement_type='return', reason=f"Retour #{return_request.id} approuve", reference_number=f"RETURN-{return_request.id}", performed_by=request.user)
                    except Exception:
                        pass
            return_request.status = 'completed'
            return_request.save(update_fields=['status', 'updated_at'])
            order = return_request.order
            all_items_returned = all(ri.quantity >= ri.order_line.quantity for ri in return_request.items.all())
            if all_items_returned:
                order.status = 'returned'
            else:
                order.status = 'partially_returned'
            order.save(update_fields=['status'])

        try:
            create_notification_if_allowed(user=order.customer, notification_type="order", title="Retour termine", message=f"Votre retour pour la commande #{order.order_number} a ete finalise. Le stock a ete reintegre.")
        except Exception:
            pass
        return Response(ReturnRequestSerializer(return_request).data)

    @action(detail=True, methods=['post'], url_path='refund')
    def refund(self, request, pk=None):
        return_request = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)
        if return_request.status != 'completed':
            return Response({"error": "Le retour doit etre finalise avant de creer un remboursement."}, status=status.HTTP_400_BAD_REQUEST)
        amount = request.data.get('amount')
        method = request.data.get('method', 'original')
        if not amount:
            return Response({"error": "Champ 'amount' requis."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = Decimal(str(amount))
        except Exception:
            return Response({"error": "Montant invalide."}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({"error": "Le montant doit etre superieur a 0."}, status=status.HTTP_400_BAD_REQUEST)

        total_refundable = return_request.total_refund_amount
        already_refunded = sum(r.amount for r in return_request.refunds.filter(status='completed'))
        remaining = total_refundable - already_refunded
        if amount > remaining:
            return Response({"error": f"Montant superieur au remboursement restant ({remaining})."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            refund = Refund.objects.create(return_request=return_request, order=return_request.order, amount=amount, method=method, status='processing', processed_by=request.user)
            order = return_request.order
            if already_refunded + amount >= total_refundable:
                order.payment_status = 'refunded'
            else:
                order.payment_status = 'partially_refunded'
            order.save(update_fields=['payment_status'])

        try:
            create_notification_if_allowed(user=order.customer, notification_type="order", title="Remboursement initie", message=f"Un remboursement de {amount} a ete initie pour la commande #{order.order_number}.")
        except Exception:
            pass
        return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)
