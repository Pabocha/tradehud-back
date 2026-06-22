from django.utils import timezone
from django.db.models import Q as DQ
from django.db import transaction
from decimal import Decimal
from rest_framework import decorators, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from apps.payments.models import PaymentMethod
from .models import Orders, Quote, OrderLine
from apps.products.models import ProductVariant, Products
from apps.notifications.notifications import create_notification_if_allowed
from .serializers import OrderCreateSerializer, OrderSerializer, QuoteSerializer


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Orders.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        return OrderSerializer

    def _get_user_owned_shop_ids(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, "seller_account"):
            return []
        return list(user.seller_account.shops.values_list("id", flat=True))

    def get_queryset(self):
        """
        - Admin/staff: toutes les commandes
        - Proprietaire de boutique: commandes qui contiennent ses boutiques
        - Client:
          - acces detail (retrieve/pay/payment-status) a ses propres commandes
          - aucun acces via /orders/ (utiliser /orders/my-orders/)
        """
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return Orders.objects.all()

        owned_shop_ids = self._get_user_owned_shop_ids()
        if self.action in ["retrieve", "pay", "update_payment_status"]:
            query = DQ(customer=user)
            if owned_shop_ids:
                query |= DQ(order_lines__shop_id__in=owned_shop_ids)
            return Orders.objects.filter(query).distinct()

        if owned_shop_ids:
            return Orders.objects.filter(
                order_lines__shop_id__in=owned_shop_ids
            ).distinct()

        return Orders.objects.none()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        if (
            self.action in ["list", "retrieve", "shop_orders"]
            and user.is_authenticated
            and not (user.is_staff or user.is_superuser)
        ):
            owned_shop_ids = self._get_user_owned_shop_ids()
            if owned_shop_ids:
                context["shop_ids"] = owned_shop_ids
        return context

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)

    def _can_update_payment_status(self, order):
        user = self.request.user
        return user.is_staff or user.is_superuser or order.customer_id == user.id

    @decorators.action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        """
        POST /orders/{id}/pay/
        Permet un paiement en confirmation immediate:
        - assigne la/les methode(s) de paiement
        - passe payment_status a "paid"
        """
        order = self.get_object()
        if not self._can_update_payment_status(order):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)

        method_ids = request.data.get("payment_method")
        if not isinstance(method_ids, list) or not method_ids:
            return Response(
                {"error": "Champ 'payment_method' requis (liste d'IDs)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payment_first_name = (request.data.get("first_name") or "").strip()
        payment_last_name = (request.data.get("last_name") or "").strip()
        payment_phone_number = (request.data.get("phone_number") or "").strip()

        if not payment_first_name:
            return Response(
                {"error": "Champ 'first_name' requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not payment_last_name:
            return Response(
                {"error": "Champ 'last_name' requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not payment_phone_number:
            return Response(
                {"error": "Champ 'phone_number' requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        unique_method_ids = list(set(method_ids))
        methods = PaymentMethod.objects.filter(id__in=unique_method_ids)
        if methods.count() != len(unique_method_ids):
            return Response(
                {"error": "Une ou plusieurs methodes de paiement sont invalides."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            order.payment_method.set(methods)
            order.payment_first_name = payment_first_name
            order.payment_last_name = payment_last_name
            order.payment_phone_number = payment_phone_number
            order.payment_status = "paid"
            order.save(
                update_fields=[
                    "payment_first_name",
                    "payment_last_name",
                    "payment_phone_number",
                    "payment_status",
                ]
            )

        try:
            create_notification_if_allowed(
                user=order.customer,
                notification_type="order",
                title="Paiement confirme",
                message=f"Le paiement de la commande #{order.order_number} est confirme.",
            )
        except Exception:
            # Ne pas casser le paiement si la notification echoue.
            pass

        return Response(
            {
                "order_id": order.id,
                "payment_status": order.payment_status,
                "payment_method": list(order.payment_method.values_list("id", flat=True)),
                "payment_first_name": order.payment_first_name,
                "payment_last_name": order.payment_last_name,
                "payment_phone_number": order.payment_phone_number,
            },
            status=status.HTTP_200_OK,
        )

    @decorators.action(detail=True, methods=["patch"], url_path="payment-status")
    def update_payment_status(self, request, pk=None):
        order = self.get_object()
        if not self._can_update_payment_status(order):
            return Response({"error": "Non autorise."}, status=status.HTTP_403_FORBIDDEN)

        new_status = request.data.get("payment_status")
        if not new_status:
            return Response(
                {"error": "Champ 'payment_status' requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed_transitions = {
            "pending": {"paid", "failed"},
            "paid": {"refunded"},
            "failed": {"pending"},
            "refunded": set(),
        }

        current = order.payment_status
        if new_status == current:
            return Response({"payment_status": current}, status=status.HTTP_200_OK)

        if new_status not in allowed_transitions.get(current, set()):
            return Response(
                {
                    "error": "Transition de statut non autorisee.",
                    "from": current,
                    "to": new_status,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.payment_status = new_status
        order.save(update_fields=["payment_status"])

        try:
            create_notification_if_allowed(
                user=order.customer,
                notification_type="order",
                title="Mise a jour paiement",
                message=(
                    f"Le statut de paiement de la commande #{order.order_number} "
                    f"est passe a '{new_status}'."
                ),
            )
        except Exception:
            # Ne pas casser la mise a jour si la notification echoue.
            pass

        return Response({"payment_status": order.payment_status}, status=status.HTTP_200_OK)

    @decorators.action(detail=False, methods=["get"])
    def shop_orders(self, request):
        """
        GET /orders/shop_orders/?shop_id=<id> (optionnel)
        - Staff/superuser: voit toutes les commandes (optionnellement filtrees par shop_id).
        - Proprietaire: voit les commandes de ses boutiques.
        - Si shop_id est fourni pour un proprietaire, il doit lui appartenir.
        """
        user = request.user
        shop_id = request.query_params.get("shop_id")
        context = self.get_serializer_context()

        if user.is_staff or user.is_superuser:
            if shop_id:
                try:
                    shop_id_int = int(shop_id)
                except (TypeError, ValueError):
                    return Response({"error": "shop_id invalide."}, status=status.HTTP_400_BAD_REQUEST)
                queryset = Orders.objects.filter(
                    lignes_commande__shop_id=shop_id_int
                ).distinct().order_by("-order_date")
                context["shop_id"] = shop_id_int
            else:
                queryset = Orders.objects.all().order_by("-order_date")
            serializer = self.get_serializer(queryset, many=True, context=context)
            return Response(serializer.data)

        if not hasattr(user, "seller_account"):
            return Response(
                {"error": "Acces reserve aux proprietaires de boutiques."},
                status=status.HTTP_403_FORBIDDEN,
            )

        owned_shop_ids = self._get_user_owned_shop_ids()
        if not owned_shop_ids:
            return Response([], status=status.HTTP_200_OK)

        if shop_id:
            try:
                shop_id_int = int(shop_id)
            except (TypeError, ValueError):
                return Response({"error": "shop_id invalide."}, status=status.HTTP_400_BAD_REQUEST)

            if shop_id_int not in owned_shop_ids:
                return Response(
                    {"error": "Vous ne pouvez voir que les commandes de vos propres boutiques."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            queryset = Orders.objects.filter(
                lignes_commande__shop_id=shop_id_int
            ).distinct().order_by("-order_date")
            context["shop_id"] = shop_id_int
        else:
            queryset = Orders.objects.filter(
                lignes_commande__shop_id__in=owned_shop_ids
            ).distinct().order_by("-order_date")
            context["shop_ids"] = owned_shop_ids

        serializer = self.get_serializer(queryset, many=True, context=context)
        return Response(serializer.data)

    @decorators.action(detail=False, methods=["get"], url_path="my-orders")
    def my_orders(self, request):
        queryset = Orders.objects.filter(customer=request.user).order_by("-order_date")
        context = {**self.get_serializer_context()}
        context.pop("shop_id", None)
        context.pop("shop_ids", None)
        serializer = self.get_serializer(queryset, many=True, context=context)
        return Response(serializer.data)


class QuoteViewSet(viewsets.ModelViewSet):
    queryset = (
        Quote.objects
        .select_related('user', 'shop', 'converted_order')
        .prefetch_related('lines__product', 'lines__variant__product')
    )
    serializer_class = QuoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset
        if user.is_staff or user.is_superuser:
            return qs

        if hasattr(user, 'seller_account'):
            return qs.filter(DQ(user=user) | DQ(shop__owner=user.seller_account)).distinct()

        return qs.filter(user=user)

    def perform_create(self, serializer):
        shop = serializer.validated_data.get('shop')
        if hasattr(self.request.user, 'seller_account') and shop and shop.owner_id == self.request.user.seller_account.id:
            raise ValidationError("Vous ne pouvez pas creer une quote pour votre propre boutique.")
        serializer.save(user=self.request.user, status='draft')

    def _is_shop_owner(self, quote, user):
        return hasattr(user, 'seller_account') and quote.shop.owner_id == user.seller_account.id

    def _is_quote_participant(self, quote, user):
        return quote.user_id == user.id or self._is_shop_owner(quote, user)

    def _is_expired(self, quote):
        return quote.expires_at <= timezone.now()

    def _create_order_from_quote(self, request, quote, delivery_address, delivery_cost, mark_paid=False):
        lines = list(quote.lines.select_related('product', 'variant', 'variant__product').all())
        if not lines:
            raise ValueError('Quote sans lignes.')

        with transaction.atomic():
            order = Orders.objects.create(
                customer=request.user,
                delivery_address=delivery_address,
                delivery_cost=delivery_cost,
                total_amount=Decimal('0.00'),
                payment_status='paid' if mark_paid else 'pending',
                payment_first_name=(request.data.get('first_name') or '').strip() or None,
                payment_last_name=(request.data.get('last_name') or '').strip() or None,
                payment_phone_number=(request.data.get('phone_number') or '').strip() or None,
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

    @action(detail=False, methods=['get'], url_path='my')
    def my_quotes(self, request):
        qs = self.get_queryset().filter(user=request.user).order_by('-created_at')
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='shop')
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

        if not self._is_shop_owner(quote, request.user):
            return Response({'error': 'Seul le vendeur peut envoyer la proposition.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status not in ('draft', 'countered'):
            return Response({'error': 'Statut invalide pour envoyer la quote.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'sent'
        quote.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='counter')
    def counter(self, request, pk=None):
        quote = self.get_object()

        if not self._is_quote_participant(quote, request.user):
            return Response({'error': 'Non autorise.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status not in ('sent', 'countered'):
            return Response({'error': 'Statut invalide pour contre-proposition.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'countered'
        quote.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        quote = self.get_object()

        if quote.user_id != request.user.id:
            return Response({'error': 'Seul le client peut accepter la quote.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status not in ('sent', 'countered'):
            return Response({'error': 'Statut invalide pour acceptation.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'accepted'
        quote.accepted_at = timezone.now()
        quote.save(update_fields=['status', 'accepted_at', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        quote = self.get_object()

        if not self._is_quote_participant(quote, request.user):
            return Response({'error': 'Non autorise.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status in ('converted', 'rejected'):
            return Response({'error': 'Action non autorisee pour ce statut.'}, status=status.HTTP_400_BAD_REQUEST)

        quote.status = 'rejected'
        quote.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(quote).data)

    @action(detail=True, methods=['post'], url_path='payment-link')
    def payment_link(self, request, pk=None):
        quote = self.get_object()

        if not self._is_shop_owner(quote, request.user):
            return Response({'error': 'Seul le vendeur peut generer le lien de paiement.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status != 'accepted':
            return Response(
                {'error': 'La quote doit etre acceptee avant generation du lien.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if self._is_expired(quote):
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

        preview_relative_url = f"/api/products/quotes/pay/{token}/preview/"
        pay_relative_url = f"/api/products/quotes/pay/{token}/"
        return Response(
            {
                'quote_id': quote.id,
                'token': token,
                'payment_link_expires_at': quote.payment_link_expires_at,
                'preview_url': request.build_absolute_uri(preview_relative_url),
                'pay_url': request.build_absolute_uri(pay_relative_url),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['get'], url_path=r'pay/(?P<token>[^/.]+)/preview')
    def pay_preview(self, request, token=None):
        quote = Quote.objects.filter(payment_link_token=token).prefetch_related(
            'lines__product', 'lines__variant__product'
        ).select_related('shop', 'user').first()

        if not quote:
            return Response({'error': 'Lien de paiement invalide.'}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id:
            return Response({'error': 'Ce lien ne vous appartient pas.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.converted_order_id:
            return Response({'error': 'Cette quote est deja convertie.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.payment_link_expires_at is None or quote.payment_link_expires_at <= timezone.now():
            return Response({'error': 'Lien de paiement expire.'}, status=status.HTTP_400_BAD_REQUEST)

        lines_payload = []
        subtotal = Decimal('0.00')
        for line in quote.lines.all():
            product = line.product or (line.variant.product if line.variant_id else None)
            unit_price = getattr(line.negotiated_price, 'amount', line.negotiated_price)
            line_total = Decimal(str(unit_price)) * int(line.quantity or 0)
            subtotal += line_total
            lines_payload.append({
                'line_id': line.id,
                'product_id': product.id if product else None,
                'product_name': product.name if product else None,
                'variant_id': line.variant_id,
                'quantity': line.quantity,
                'negotiated_unit_price': unit_price,
                'line_total': line_total,
            })

        return Response(
            {
                'quote_id': quote.id,
                'shop': {'id': quote.shop_id, 'name': quote.shop.name},
                'expires_at': quote.expires_at,
                'payment_link_expires_at': quote.payment_link_expires_at,
                'lines': lines_payload,
                'subtotal': subtotal,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'], url_path=r'pay/(?P<token>[^/.]+)')
    def pay_by_token(self, request, token=None):
        quote = Quote.objects.filter(payment_link_token=token).select_related('shop', 'user').first()

        if not quote:
            return Response({'error': 'Lien de paiement invalide.'}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id:
            return Response({'error': 'Ce lien ne vous appartient pas.'}, status=status.HTTP_403_FORBIDDEN)
        if quote.converted_order_id:
            return Response(
                {'detail': 'Quote deja convertie.', 'order_id': quote.converted_order_id},
                status=status.HTTP_200_OK,
            )
        if quote.payment_link_expires_at is None or quote.payment_link_expires_at <= timezone.now():
            return Response({'error': 'Lien de paiement expire.'}, status=status.HTTP_400_BAD_REQUEST)
        if quote.status != 'accepted':
            return Response(
                {'error': 'Statut de quote invalide pour paiement. Quote acceptee requise.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_address = (request.data.get('delivery_address') or '').strip()
        if not delivery_address:
            return Response({'error': "Champ 'delivery_address' requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delivery_cost = Decimal(str(request.data.get('delivery_cost', 0) or 0))
        except Exception:
            return Response({'error': "Champ 'delivery_cost' invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = self._create_order_from_quote(
                request=request,
                quote=quote,
                delivery_address=delivery_address,
                delivery_cost=delivery_cost,
                mark_paid=True,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'quote_id': quote.id,
                'order_id': order.id,
                'status': quote.status,
                'payment_status': order.payment_status,
                'total_amount': order.total_amount,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='checkout')
    def checkout(self, request, pk=None):
        quote = self.get_object()

        if quote.user_id != request.user.id:
            return Response({'error': 'Seul le client de la quote peut convertir en commande.'}, status=status.HTTP_403_FORBIDDEN)

        if quote.status != 'accepted':
            return Response({'error': 'La quote doit etre acceptee avant checkout.'}, status=status.HTTP_400_BAD_REQUEST)

        if self._is_expired(quote):
            quote.status = 'expired'
            quote.save(update_fields=['status', 'updated_at'])
            return Response({'error': 'La quote a expire.'}, status=status.HTTP_400_BAD_REQUEST)

        if quote.converted_order_id:
            return Response(
                {
                    'detail': 'Quote deja convertie.',
                    'order_id': quote.converted_order_id,
                },
                status=status.HTTP_200_OK,
            )

        delivery_address = (request.data.get('delivery_address') or '').strip()
        if not delivery_address:
            return Response({'error': "Champ 'delivery_address' requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delivery_cost = Decimal(str(request.data.get('delivery_cost', 0) or 0))
        except Exception:
            return Response({'error': "Champ 'delivery_cost' invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = self._create_order_from_quote(
                request=request,
                quote=quote,
                delivery_address=delivery_address,
                delivery_cost=delivery_cost,
                mark_paid=False,
            )
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'quote_id': quote.id,
                'order_id': order.id,
                'status': quote.status,
                'total_amount': order.total_amount,
            },
            status=status.HTTP_201_CREATED,
        )