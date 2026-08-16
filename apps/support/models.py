from django.db import models
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


class SupportTicket(models.Model):
    CATEGORY_CHOICES = [
        ('commande', 'Commande'),
        ('paiement', 'Paiement'),
        ('livraison', 'Livraison'),
        ('retour', 'Retour / Remboursement'),
        ('compte', 'Compte'),
        ('autre', 'Autre'),
    ]
    PRIORITY_CHOICES = [
        ('basse', 'Basse'),
        ('moyenne', 'Moyenne'),
        ('haute', 'Haute'),
    ]
    STATUS_CHOICES = [
        ('ouvert', 'Ouvert'),
        ('en_cours', 'En cours'),
        ('resolu', 'Résolu'),
        ('ferme', 'Fermé'),
    ]

    ticket_number = models.CharField(max_length=20, unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='autre')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='moyenne')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ouvert')
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets'
    )
    order = models.ForeignKey(
        'orders.Orders', on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets'
    )
    product = models.ForeignKey(
        'products.Products', on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            self.ticket_number = f"TK-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ticket_number} - {self.subject}"


class SupportTicketMessage(models.Model):
    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.CASCADE, related_name='messages'
    )
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='support_ticket_messages'
    )
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.ticket.ticket_number} - {self.user_id} - {self.created_at:%d/%m/%Y %H:%M}"
