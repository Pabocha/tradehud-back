from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model

from .models import SupportTicket, SupportTicketMessage
from .serializers import (
    SupportTicketSerializer,
    SupportTicketDetailSerializer,
    SupportTicketAdminListSerializer,
    SupportTicketAdminDetailSerializer,
    SupportTicketMessageSerializer,
)
from .permissions import IsSupportOrAdmin

User = get_user_model()


class TicketListCreateView(APIView):
    """Côté client : mes tickets, création d'un ticket."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tickets = SupportTicket.objects.filter(user=request.user)
        serializer = SupportTicketSerializer(tickets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data.copy()
        serializer = SupportTicketSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        ticket = serializer.save(user=request.user)
        out = SupportTicketDetailSerializer(ticket).data
        return Response(out, status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    """Côté client : détail de MES tickets uniquement."""

    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):
        ticket = SupportTicket.objects.filter(id=ticket_id, user=request.user).first()
        if not ticket:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketMessageCreateView(APIView):
    """Côté client : répondre à mon ticket."""

    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):
        ticket = SupportTicket.objects.filter(id=ticket_id, user=request.user).first()
        if not ticket:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if ticket.status == 'ferme':
            return Response(
                {"detail": "Ce ticket est fermé. Ouvrez un nouveau ticket si nécessaire."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response({"detail": "Le message est requis."}, status=status.HTTP_400_BAD_REQUEST)

        msg = SupportTicketMessage.objects.create(
            ticket=ticket,
            user=request.user,
            message=message,
        )
        if ticket.status in ('resolu', 'ferme'):
            ticket.status = 'ouvert'
            ticket.save(update_fields=['status', 'updated_at'])

        return Response(SupportTicketMessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class TicketAdminListView(APIView):
    """Plateforme dédiée : liste de tous les tickets (file d'attente)."""

    permission_classes = [IsSupportOrAdmin]

    def get(self, request):
        queryset = SupportTicket.objects.all()
        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        serializer = SupportTicketAdminListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketAdminDetailView(APIView):
    """Plateforme dédiée : détail d'un ticket avec son fil de réponses."""

    permission_classes = [IsSupportOrAdmin]

    def get(self, request, ticket_id):
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SupportTicketAdminDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketAdminAssignView(APIView):
    """Plateforme dédiée : assigner un ticket à un agent."""

    permission_classes = [IsSupportOrAdmin]

    def post(self, request, ticket_id):
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)

        agent_id = request.data.get("agent_id")
        agent = None
        if agent_id:
            agent = (
                User.objects
                .filter(id=agent_id, is_active=True, type_user__in=('support', 'admin'))
                .first()
            )
            if not agent:
                return Response(
                    {"detail": "Agent introuvable ou rôle invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        ticket.assigned_to = agent
        ticket.save(update_fields=['assigned_to', 'updated_at'])
        return Response({"detail": "Ticket assigné."}, status=status.HTTP_200_OK)


class TicketAdminStatusView(APIView):
    """Plateforme dédiée : changer le statut d'un ticket."""

    permission_classes = [IsSupportOrAdmin]

    def post(self, request, ticket_id):
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status")
        valid_statuses = [c[0] for c in SupportTicket.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return Response(
                {"detail": f"Statut invalide. Valeurs possibles : {', '.join(valid_statuses)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.status = new_status
        ticket.save(update_fields=['status', 'updated_at'])
        return Response({"detail": "Statut mis à jour.", "status": new_status}, status=status.HTTP_200_OK)


class TicketAdminMessageCreateView(APIView):
    """Plateforme dédiée : répondre à un ticket côté agent."""

    permission_classes = [IsSupportOrAdmin]

    def post(self, request, ticket_id):
        ticket = SupportTicket.objects.filter(id=ticket_id).first()
        if not ticket:
            return Response({"detail": "Ticket introuvable."}, status=status.HTTP_404_NOT_FOUND)
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response({"detail": "Le message est requis."}, status=status.HTTP_400_BAD_REQUEST)

        msg = SupportTicketMessage.objects.create(
            ticket=ticket,
            user=request.user,
            message=message,
        )
        if not ticket.assigned_to_id and request.user.type_user in ('support', 'admin'):
            ticket.assigned_to = request.user
        if ticket.status == 'ouvert':
            ticket.status = 'en_cours'
        ticket.save(update_fields=['assigned_to', 'status', 'updated_at'])

        return Response(SupportTicketMessageSerializer(msg).data, status=status.HTTP_201_CREATED)
