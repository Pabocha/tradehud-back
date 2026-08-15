from rest_framework import serializers
from .models import PaymentMethod


class PaymentMethodSerializer(serializers.ModelSerializer):
    # AJOUT — URL absolue pour l'image (le front l'utilise comme logo)
    image = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = ['id', 'value', 'name', 'image', 'type', 'requires_phone', 'countries']

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        try:
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None
