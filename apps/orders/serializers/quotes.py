from django.utils import timezone

from rest_framework import serializers

from djmoney.contrib.django_rest_framework.fields import MoneyField

from ..models import Quote, QuoteLine


class QuoteLineSerializer(serializers.ModelSerializer):
    negotiated_price = MoneyField(max_digits=15, decimal_places=2)
    product_name = serializers.SerializerMethodField()
    variant_sku = serializers.CharField(source='variant.sku', read_only=True)

    class Meta:
        model = QuoteLine
        fields = [
            'id',
            'product',
            'product_name',
            'variant',
            'variant_sku',
            'quantity',
            'negotiated_price',
            'remarks',
        ]

    def get_product_name(self, obj):
        if obj.product:
            return obj.product.name
        if obj.variant and obj.variant.product:
            return obj.variant.product.name
        return None

    def validate(self, attrs):
        product = attrs.get('product') or getattr(self.instance, 'product', None)
        variant = attrs.get('variant') or getattr(self.instance, 'variant', None)
        if bool(product) == bool(variant):
            raise serializers.ValidationError("Fournissez soit 'product', soit 'variant'.")
        return attrs


class QuoteSerializer(serializers.ModelSerializer):
    lines = QuoteLineSerializer(many=True)
    room_id = serializers.SerializerMethodField()

    class Meta:
        model = Quote
        fields = [
            'id',
            'user',
            'shop',
            'status',
            'expires_at',
            'accepted_at',
            'payment_link_token',
            'payment_link_expires_at',
            'payment_link_sent_at',
            'converted_order',
            'created_at',
            'updated_at',
            'lines',
            'room_id',
        ]
        read_only_fields = [
            'user',
            'status',
            'accepted_at',
            'payment_link_token',
            'payment_link_expires_at',
            'payment_link_sent_at',
            'converted_order',
            'created_at',
            'updated_at',
        ]

    def validate_expires_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("expires_at doit etre dans le futur.")
        return value

    def get_room_id(self, obj):
        from apps.chat.services import resolve_quote_room
        room = resolve_quote_room(obj)
        return room.roomId if room else None

    def validate(self, attrs):
        shop = attrs.get('shop') or getattr(self.instance, 'shop', None)
        lines = attrs.get('lines')
        if self.instance is not None and 'shop' in attrs and attrs['shop'].id != self.instance.shop_id:
            raise serializers.ValidationError({"shop": "La boutique d'une quote ne peut pas etre modifiee."})
        if lines is None and self.instance is not None:
            return attrs
        if not lines:
            raise serializers.ValidationError({"lines": "Au moins une ligne est requise."})

        for line in lines:
            product = line.get('product')
            variant = line.get('variant')
            if bool(product) == bool(variant):
                raise serializers.ValidationError(
                    {"lines": "Chaque ligne doit contenir soit 'product', soit 'variant'."}
                )

            product_obj = product or (variant.product if variant else None)
            if shop and product_obj and product_obj.shop_id != shop.id:
                raise serializers.ValidationError(
                    {"lines": "Toutes les lignes doivent appartenir a la boutique selectionnee."}
                )

            quantity = line.get('quantity') or 0
            if quantity <= 0:
                raise serializers.ValidationError(
                    {"lines": "La quantite doit etre strictement superieure a 0."}
                )
        return attrs

    def create(self, validated_data):
        lines_data = validated_data.pop('lines', [])
        quote = Quote.objects.create(**validated_data)
        for line_data in lines_data:
            QuoteLine.objects.create(quote=quote, **line_data)
        return quote

    def update(self, instance, validated_data):
        lines_data = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if lines_data is not None:
            instance.lines.all().delete()
            for line_data in lines_data:
                QuoteLine.objects.create(quote=instance, **line_data)
        return instance
