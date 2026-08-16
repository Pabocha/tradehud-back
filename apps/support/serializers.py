from rest_framework import serializers
from .models import SupportTicket, SupportTicketMessage


class SupportTicketMessageSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicketMessage
        fields = ['id', 'user', 'message', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']

    def get_user(self, obj):
        if not obj.user_id:
            return None
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email,
        }


class SupportTicketSerializer(serializers.ModelSerializer):
    assigned_to = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            'id',
            'ticket_number',
            'subject',
            'message',
            'category',
            'priority',
            'status',
            'order',
            'product',
            'assigned_to',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'ticket_number', 'status', 'assigned_to', 'created_at', 'updated_at']

    def get_assigned_to(self, obj):
        if not obj.assigned_to_id:
            return None
        return {
            'id': obj.assigned_to.id,
            'first_name': obj.assigned_to.first_name,
            'last_name': obj.assigned_to.last_name,
            'email': obj.assigned_to.email,
        }


class SupportTicketDetailSerializer(SupportTicketSerializer):
    messages = SupportTicketMessageSerializer(many=True, read_only=True)

    class Meta(SupportTicketSerializer.Meta):
        fields = SupportTicketSerializer.Meta.fields + ['messages']


class SupportTicketAdminListSerializer(SupportTicketSerializer):
    user = serializers.SerializerMethodField()

    class Meta(SupportTicketSerializer.Meta):
        fields = SupportTicketSerializer.Meta.fields + ['user']

    def get_user(self, obj):
        return {
            'id': obj.user.id,
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'email': obj.user.email,
        }


class SupportTicketAdminDetailSerializer(SupportTicketAdminListSerializer):
    messages = SupportTicketMessageSerializer(many=True, read_only=True)

    class Meta(SupportTicketAdminListSerializer.Meta):
        fields = SupportTicketAdminListSerializer.Meta.fields + ['messages']
