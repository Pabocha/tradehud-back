from django.db.models import Q
from django.db import transaction
from rest_framework import decorators, permissions, status, viewsets
from rest_framework.response import Response

from apps.payments.models import PaymentMethod
from apps.notifications.notifications import create_notification_if_allowed
from .models import Orders
from .serializers import OrderCreateSerializer, OrderSerializer


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
            query = Q(customer=user)
            if owned_shop_ids:
                query |= Q(lignes_commande__shop_id__in=owned_shop_ids)
            return Orders.objects.filter(query).distinct()

        if owned_shop_ids:
            return Orders.objects.filter(
                lignes_commande__shop_id__in=owned_shop_ids
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
