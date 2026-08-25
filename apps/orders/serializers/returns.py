from django.db import transaction

from rest_framework import serializers

from ..models import OrderLine, Orders, Refund, ReturnItem, ReturnRequest


class ReturnItemCreateSerializer(serializers.Serializer):
    order_line_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)


class ReturnRequestCreateSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=ReturnRequest.REASON_CHOICES)
    description = serializers.CharField(required=False, allow_blank=True)
    items = ReturnItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Au moins un article est requis.")
        return value

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user if request else None

        try:
            order = Orders.objects.get(id=attrs['order_id'])
        except Orders.DoesNotExist:
            raise serializers.ValidationError({"order_id": "Commande introuvable."})

        if order.customer_id != user.id:
            raise serializers.ValidationError({"order_id": "Cette commande ne vous appartient pas."})

        if order.status != 'delivered':
            raise serializers.ValidationError({"order_id": "Seules les commandes livrées peuvent faire l'objet d'un retour."})

        if ReturnRequest.objects.filter(order=order, status__in=('pending', 'approved', 'shipped_back')).exists():
            raise serializers.ValidationError({"order_id": "Un retour est déjà en cours pour cette commande."})

        attrs['order'] = order

        for item in attrs['items']:
            try:
                order_line = OrderLine.objects.get(id=item['order_line_id'], order=order)
            except OrderLine.DoesNotExist:
                raise serializers.ValidationError(
                    {"items": f"Ligne de commande {item['order_line_id']} introuvable."}
                )
            if item['quantity'] > order_line.quantity:
                raise serializers.ValidationError(
                    {"items": f"Quantité demandée ({item['quantity']}) supérieure à la quantité commandée ({order_line.quantity})."}
                )
            item['order_line'] = order_line

        return attrs

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = validated_data.pop('order')

        with transaction.atomic():
            return_request = ReturnRequest.objects.create(
                order=order,
                reason=validated_data['reason'],
                description=validated_data.get('description', ''),
            )

            for item in items_data:
                ReturnItem.objects.create(
                    return_request=return_request,
                    order_line=item['order_line'],
                    quantity=item['quantity'],
                    reason=item.get('reason', ''),
                    description=item.get('description', ''),
                )

        return return_request


class ReturnItemSerializer(serializers.ModelSerializer):
    refund_amount = serializers.ReadOnlyField()
    product_name = serializers.SerializerMethodField()

    class Meta:
        model = ReturnItem
        fields = ['id', 'order_line', 'product_name', 'quantity', 'reason', 'description', 'refund_amount']

    def get_product_name(self, obj):
        if obj.order_line.variant:
            return obj.order_line.variant.product.name
        if obj.order_line.product:
            return obj.order_line.product.name
        return None


class ReturnRequestSerializer(serializers.ModelSerializer):
    items = ReturnItemSerializer(many=True, read_only=True)
    total_refund_amount = serializers.ReadOnlyField()
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = ReturnRequest
        fields = [
            'id', 'order', 'order_number', 'status', 'reason', 'description',
            'staff_note', 'items', 'total_refund_amount',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['status', 'staff_note']


class RefundSerializer(serializers.ModelSerializer):
    processed_by_name = serializers.CharField(source='processed_by.email', read_only=True, default=None)

    class Meta:
        model = Refund
        fields = [
            'id', 'return_request', 'order', 'amount', 'method',
            'status', 'reference_number', 'processed_by', 'processed_by_name',
            'created_at', 'processed_at',
        ]
        read_only_fields = ['status', 'reference_number', 'processed_by', 'processed_at']
