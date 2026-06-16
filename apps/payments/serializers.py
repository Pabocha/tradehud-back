from rest_framework import serializers
from .models import PayementMethod


class PaymentMethodSerializer(serializers.ModelSerializer):

    class Meta:
        model = PayementMethod
        fields = '__all__'