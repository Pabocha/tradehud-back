"""
Service pour envoyer les notifications de manière centralisée.
Utilise les templates définis et respecte les préférences utilisateur.
"""

from django.contrib.auth import get_user_model
from apps.notifications.models import Notifications
from apps.notifications.templates import get_template
from django.utils import timezone
from typing import Dict, Optional
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    """Service centralisé pour gérer les notifications"""
    
    @staticmethod
    def send_notification(
        user: User,
        template_key: str,
        template_data: Dict,
        related_object_id: Optional[int] = None,
        related_model: Optional[str] = None,
    ) -> Optional[Notifications]:
        """
        Envoie une notification à un utilisateur.
        
        Args:
            user: L'utilisateur qui reçoit la notification
            template_key: Clé du template à utiliser (ex: 'new_message')
            template_data: Données à passer au template (kwargs)
            related_object_id: ID de l'objet associé (commande, message, etc.)
            related_model: Modèle associé (ex: 'Order', 'ChatMessage')
        
        Returns:
            L'objet Notification créé, ou None si les notifications sont désactivées
        """
        
        # Récupérer les préférences de notification de l'utilisateur
        if not NotificationService.should_notify(user, template_key):
            logger.info(f"Notification ignorée pour {user.email} - {template_key}")
            return None
        
        # Récupérer le template
        template = get_template(template_key)
        if not template:
            logger.warning(f"Template {template_key} non trouvé")
            return None
        
        try:
            # Générer le titre et le message
            title = template.get_title(**template_data)
            message = template.get_message(**template_data)
            notification_type = template.NOTIFICATION_TYPE
            
            # Créer l'objet notification
            notification = Notifications.objects.create(
                user=user,
                type=notification_type,
                title=title,
                message=message,
                is_read=False,
            )
            
            logger.info(f"Notification créée pour {user.email} - {template_key}")
            return notification
        
        except Exception as e:
            logger.error(f"Erreur lors de la création de la notification: {str(e)}")
            return None
    
    @staticmethod
    def should_notify(user: User, template_key: str) -> bool:
        """
        Vérifie si l'utilisateur doit être notifié en fonction de ses préférences.
        """
        try:
            from apps.accounts.models import UserSettings
            settings = UserSettings.objects.get(user=user)
            
            # Si les notifications globales sont désactivées
            if not settings.notifications_enabled:
                return False
            
            # Déterminer le type de notification à partir de la clé du template
            notification_type = _get_notification_type_from_template_key(template_key)
            
            # Vérifier les préférences spécifiques
            prefs = settings.notification_preferences
            if isinstance(prefs, dict):
                # Si "all" est désactivé, vérifier la préférence spécifique
                if not prefs.get('all', True):
                    return prefs.get(notification_type, True)
                else:
                    # Si "all" est activé, la notification doit être envoyée
                    return True
            
            return True
        
        except Exception as e:
            logger.warning(f"Erreur lors de la vérification des préférences: {str(e)}")
            return True  # En cas d'erreur, on envoie la notification par défaut
    
    @staticmethod
    def send_bulk_notifications(
        users: list,
        template_key: str,
        template_data_list: list,
    ) -> list:
        """
        Envoie des notifications à plusieurs utilisateurs.
        
        Args:
            users: Liste des utilisateurs
            template_key: Clé du template
            template_data_list: Liste des données pour chaque utilisateur
        
        Returns:
            Liste des notifications créées
        """
        notifications = []
        for user, template_data in zip(users, template_data_list):
            notif = NotificationService.send_notification(
                user=user,
                template_key=template_key,
                template_data=template_data,
            )
            if notif:
                notifications.append(notif)
        return notifications
    
    @staticmethod
    def mark_as_read(notification_id: int) -> bool:
        """Marque une notification comme lue"""
        try:
            notification = Notifications.objects.get(id=notification_id)
            notification.is_read = True
            notification.save()
            return True
        except Notifications.DoesNotExist:
            return False
    
    @staticmethod
    def mark_all_as_read(user: User, notification_type: Optional[str] = None) -> int:
        """
        Marque toutes les notifications d'un utilisateur comme lues.
        
        Args:
            user: L'utilisateur
            notification_type: Type spécifique à marquer comme lu (optionnel)
        
        Returns:
            Le nombre de notifications marquées comme lues
        """
        qs = Notifications.objects.filter(user=user, is_read=False)
        if notification_type:
            qs = qs.filter(type=notification_type)
        count = qs.update(is_read=True)
        return count
    
    @staticmethod
    def delete_notification(notification_id: int) -> bool:
        """Supprime une notification"""
        try:
            Notifications.objects.filter(id=notification_id).delete()
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_unread_count(user: User, notification_type: Optional[str] = None) -> int:
        """
        Obtient le nombre de notifications non lues.
        
        Args:
            user: L'utilisateur
            notification_type: Filtre par type (optionnel)
        
        Returns:
            Le nombre de notifications non lues
        """
        qs = Notifications.objects.filter(user=user, is_read=False)
        if notification_type:
            qs = qs.filter(type=notification_type)
        return qs.count()
    
    @staticmethod
    def get_notifications(user: User, limit: int = 20, offset: int = 0) -> list:
        """
        Récupère les notifications d'un utilisateur.
        
        Args:
            user: L'utilisateur
            limit: Nombre de notifications à récupérer
            offset: Décalage de pagination
        
        Returns:
            Liste des notifications
        """
        return Notifications.objects.filter(user=user).order_by('-created_at')[offset:offset+limit]


def _get_notification_type_from_template_key(template_key: str) -> str:
    """
    Déduit le type de notification à partir de la clé du template.
    
    Mappings:
    - 'new_message', 'group_message', 'unread_messages' → 'message'
    - 'order_*' → 'order'
    - 'delivery_*', '*_initiated' → 'delivery'
    - 'payment_*' → 'order' (ou peut être customisé)
    """
    if 'message' in template_key:
        return 'message'
    elif 'delivery' in template_key or 'return' in template_key or 'refund' in template_key or 'shipped' in template_key or 'transit' in template_key or 'delivered' in template_key:
        return 'delivery'
    elif 'order' in template_key:
        return 'order'
    elif 'payment' in template_key:
        return 'order'
    else:
        return 'support'
