"""
📧 GUIDE D'UTILISATION - SYSTÈME DE NOTIFICATIONS

Ce guide explique comment utiliser le système de notifications prêt à envoyer
dans votre application Django.

================================================================================
📌 STRUCTURE DU SYSTÈME
================================================================================

Le système est composé de 3 fichiers principaux :

1. notification_templates.py
   → Contient les templates pré-définis pour chaque type de notification
   → Classes héritant de NotificationTemplate avec title/message/data

2. notification_service.py
   → Service centralisé pour envoyer les notifications
   → Gère les préférences utilisateur
   → Marque comme lu, supprime, etc.

3. notification_tasks.py
   → Tâches Celery pour envoyer les notifications en arrière-plan
   → Appelé de façon asynchrone lors d'événements

================================================================================
🚀 UTILISATION RAPIDE
================================================================================

### 1️⃣ ENVOYER UNE NOTIFICATION SIMPLE

from ecom_app.notification_service import NotificationService

# Notifications synchrones (direct)
NotificationService.send_notification(
    user=user,
    template_key='order_confirmed',
    template_data={
        'order_id': order.id,
        'order_number': order.order_number,
        'shop_name': 'Mon Magasin',
        'total_amount': '50.000 XOF',
    }
)

### 2️⃣ ENVOYER UNE NOTIFICATION ASYNCHRONE (Celery)

from ecom_app.notification_tasks import notify_order_confirmed

# Notifications asynchrones (en arrière-plan via Celery)
notify_order_confirmed.delay(order_id=123)

### 3️⃣ ENVOYER PLUSIEURS NOTIFICATIONS

from ecom_app.notification_service import NotificationService

users = [user1, user2, user3]
data_list = [
    {'sender_name': 'Alice', 'room_id': 1, 'sender_id': 10},
    {'sender_name': 'Bob', 'room_id': 1, 'sender_id': 11},
    {'sender_name': 'Charlie', 'room_id': 1, 'sender_id': 12},
]

NotificationService.send_bulk_notifications(
    users=users,
    template_key='new_message',
    template_data_list=data_list,
)

================================================================================
📨 TEMPLATES DISPONIBLES
================================================================================

### MESSAGES / CHAT
──────────────────
✅ 'new_message'
   Données : sender_name, room_id, sender_id, preview

✅ 'group_message'
   Données : sender_name, group_name, room_id, sender_id, preview

✅ 'unread_messages'
   Données : unread_count


### COMMANDES
────────────
✅ 'order_confirmed'
   Données : order_id, order_number, shop_name, total_amount

✅ 'order_processing'
   Données : order_id, order_number, shop_name

✅ 'order_cancelled'
   Données : order_id, order_number, reason (optionnel)

✅ 'order_query'
   Données : order_id, order_number, sender_id, sender_name, query_preview


### LIVRAISON
────────────
✅ 'delivery_pending'
   Données : order_id, order_number, estimated_delivery, tracking_number

✅ 'order_shipped'
   Données : order_id, order_number, carrier, tracking_number

✅ 'order_in_transit'
   Données : order_id, order_number, estimated_delivery

✅ 'order_delivered'
   Données : order_id, order_number, shop_name, shop_id

✅ 'delivery_delayed'
   Données : order_id, order_number, reason, new_estimated

✅ 'delivery_failed'
   Données : order_id, order_number, reason

✅ 'return_initiated'
   Données : order_id, order_number, reason, return_id

✅ 'refund_initiated'
   Données : order_id, order_number, refund_amount


### PAIEMENTS
─────────────
✅ 'payment_received'
   Données : order_id, order_number, amount

✅ 'payment_failed'
   Données : order_id, order_number, reason

================================================================================
📝 EXEMPLES D'INTÉGRATION
================================================================================

### DANS VOS VIEWS

# File: commandes/views.py
from ecom_app.notification_tasks import notify_order_confirmed
from rest_framework.response import Response
from rest_framework import status

class OrderViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        order = serializer.save()
        
        # Envoyer la notification en arrière-plan
        notify_order_confirmed.delay(order_id=order.id)
        
        return order


### DANS VOTRE MODÈLE (signals)

# File: commandes/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from commandes.models import Orders
from ecom_app.notification_tasks import (
    notify_order_confirmed,
    notify_order_processing,
    notify_order_shipped,
)

@receiver(post_save, sender=Orders)
def order_status_changed(sender, instance, created, **kwargs):
    """Envoie une notification quand le statut change"""
    if not created and instance.tracker.has_changed('status'):
        old_status = instance.tracker.previous('status')
        new_status = instance.status
        
        if new_status == 'confirmed':
            notify_order_confirmed.delay(order_id=instance.id)
        
        elif new_status == 'processing':
            notify_order_processing.delay(order_id=instance.id)
        
        elif new_status == 'shipped':
            notify_order_shipped.delay(
                order_id=instance.id,
                carrier='DHL',
                tracking_number='ABC123456'
            )


### DANS LE CHAT

# File: chat/views.py
from ecom_app.notification_tasks import notify_new_message
from chat.models import ChatMessage

class ChatMessageCreateView(CreateAPIView):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        message = serializer.save(user=self.request.user)
        
        # Envoyer la notification aux autres membres
        notify_new_message.delay(
            room_id=message.chat.id,
            sender_id=self.request.user.id,
            sender_name=self.request.user.get_full_name(),
            preview=message.content[:100],
        )


### GESTION DES NOTIFICATIONS UTILISATEUR

# File: comptes/views.py
from ecom_app.notification_service import NotificationService

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_unread_notifications(request):
    """Récupère le nombre de notifications non lues"""
    count = NotificationService.get_unread_count(request.user)
    return Response({'unread_count': count})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_as_read(request, notification_id):
    """Marque une notification comme lue"""
    success = NotificationService.mark_as_read(notification_id)
    return Response({
        'success': success,
        'message': 'Notification marquée comme lue' if success else 'Notification non trouvée'
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_as_read(request, notification_type=None):
    """Marque toutes les notifications d'un type comme lues"""
    count = NotificationService.mark_all_as_read(request.user, notification_type)
    return Response({
        'count': count,
        'message': f'{count} notification(s) marquée(s) comme lue(s)'
    })

================================================================================
⚙️ CONFIGURATION REQUISE
================================================================================

1. S'ASSURER QUE CELERY EST CONFIGURÉ

   # File: ecommerce/celery.py
   from celery import Celery
   import os
   
   os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
   
   app = Celery('ecommerce')
   app.config_from_object('django.conf:settings', namespace='CELERY')
   app.autodiscover_tasks()


2. AJOUTER LES PRÉFÉRENCES DE NOTIFICATION AUX PARAMÈTRES UTILISATEUR
   
   UserSettings modèle déjà inclut :
   - notifications_enabled (booléen)
   - notification_preferences (JSONField)


3. AJOUTER LES ROUTES D'API POUR GÉRER LES NOTIFICATIONS
   
   # File: ecommerce/urls.py ou comptes/routers.py
   path('api/notifications/unread/', get_unread_notifications),
   path('api/notifications/<int:notification_id>/read/', mark_notification_as_read),
   path('api/notifications/mark-all-read/', mark_all_as_read),


================================================================================
🔐 RESPECT DES PRÉFÉRENCES UTILISATEUR
================================================================================

Le service respecte automatiquement les préférences de notification de l'utilisateur.

Les utilisateurs peuvent désactiver :
- Toutes les notifications (notifications_enabled = False)
- Les notifications par type (notification_preferences)

Exemple de structure notification_preferences:
{
    "all": true,                    # Maître on/off
    "order": true,                  # Notifications de commande
    "delivery": true,               # Notifications de livraison
    "message": true,                # Notifications de message
    "promo": true,                  # Promotions
    "product": true,                # Produits
    "support": true,                # Support
    "account": true                 # Compte
}

Si l'utilisateur a désactivé "delivery", aucune notification de livraison
ne sera envoyée, même si vous appelez notify_order_shipped.delay().

================================================================================
🧪 TESTS
================================================================================

# File: tests/test_notifications.py
from django.test import TestCase
from django.contrib.auth import get_user_model
from ecom_app.notification_service import NotificationService
from ecom_app.models import Notifications

User = get_user_model()

class NotificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass',
            first_name='Test',
            last_name='User'
        )
    
    def test_send_order_notification(self):
        notif = NotificationService.send_notification(
            user=self.user,
            template_key='order_confirmed',
            template_data={
                'order_id': 123,
                'order_number': 'ORD-001',
                'shop_name': 'Test Shop',
                'total_amount': '50.000 XOF',
            }
        )
        
        self.assertIsNotNone(notif)
        self.assertEqual(notif.type, 'order')
        self.assertFalse(notif.is_read)
        self.assertIn('ORD-001', notif.title)
    
    def test_unread_count(self):
        NotificationService.send_notification(
            user=self.user,
            template_key='new_message',
            template_data={'sender_name': 'Alice', 'room_id': 1}
        )
        
        count = NotificationService.get_unread_count(self.user)
        self.assertEqual(count, 1)
        
        NotificationService.mark_all_as_read(self.user)
        count = NotificationService.get_unread_count(self.user)
        self.assertEqual(count, 0)

================================================================================
✨ BONNES PRATIQUES
================================================================================

1. ✅ Toujours utiliser les tâches Celery pour les notifications asynchrones
   - Plus rapide pour l'utilisateur
   - N'interrompt pas le flux de la requête

2. ✅ Utiliser les templates existants autant que possible
   - Consistance des messages
   - Facilité de maintenance

3. ✅ Respecter les préférences utilisateur
   - NotificationService.should_notify() gère cela automatiquement
   - Les utilisateurs ont le contrôle

4. ✅ Tester les notifications avec de vrais utilisateurs
   - Vérifier que les titres et messages sont clairs
   - Envoyer des données complètes

5. ❌ Ne pas envoyer trop de notifications
   - Regrouper les notifications connexes quand possible
   - Eviter le spam

================================================================================
📞 SUPPORT & CUSTOMISATION
================================================================================

Pour ajouter un nouveau template :

1. Créer une classe héritant de NotificationTemplate :

   class MyCustomNotification(NotificationTemplate):
       NOTIFICATION_TYPE = 'custom'
       
       @classmethod
       def get_title(cls, **kwargs) -> str:
           return f"Titre personnalisé"
       
       @classmethod
       def get_message(cls, **kwargs) -> str:
           return f"Message personnalisé"
       
       @classmethod
       def get_data(cls, **kwargs):
           return {'type': cls.NOTIFICATION_TYPE}

2. L'ajouter au registre NOTIFICATION_TEMPLATES

3. Utiliser via NotificationService.send_notification()

================================================================================
"""

# Ce fichier est un guide - il ne contient pas de code à exécuter
# Consultez-le pour comprendre comment utiliser le système !
