"""
Système de templates de notifications réutilisables.
Chaque template contient les messages pré-définis pour différents types d'événements.
"""

# ============================================
# 📨 TEMPLATES DE NOTIFICATION
# ============================================

class NotificationTemplate:
    """Classe de base pour les templates de notification"""
    NOTIFICATION_TYPE = None
    
    @classmethod
    def get_message(cls, **kwargs):
        """Retourne le message de notification avec les variables remplacées"""
        raise NotImplementedError


# ==========================================
# 💬 NOTIFICATIONS DE MESSAGE / CHAT
# ==========================================

class NewMessageNotification(NotificationTemplate):
    """Notification pour les nouveaux messages reçus"""
    NOTIFICATION_TYPE = 'message'
    
    @classmethod
    def get_title(cls, sender_name: str, **kwargs) -> str:
        """Retourne le titre de la notification"""
        return f"Nouveau message de {sender_name}"
    
    @classmethod
    def get_message(cls, sender_name: str, preview: str = "", **kwargs) -> str:
        """Retourne le message complet"""
        if preview:
            return f"{sender_name} : {preview[:50]}{'...' if len(preview) > 50 else ''}"
        return f"Vous avez reçu un nouveau message de {sender_name}"
    
    @classmethod
    def get_data(cls, **kwargs):
        """Retourne les données supplémentaires pour le frontend"""
        return {
            'type': cls.NOTIFICATION_TYPE,
            'room_id': kwargs.get('room_id'),
            'sender_id': kwargs.get('sender_id'),
            'sender_name': kwargs.get('sender_name'),
            'preview': kwargs.get('preview', ''),
        }


class GroupMessageNotification(NotificationTemplate):
    """Notification pour les messages de groupe/conversation"""
    NOTIFICATION_TYPE = 'message'
    
    @classmethod
    def get_title(cls, group_name: str, **kwargs) -> str:
        return f"Nouveau message dans {group_name}"
    
    @classmethod
    def get_message(cls, sender_name: str, group_name: str, preview: str = "", **kwargs) -> str:
        if preview:
            return f"{sender_name} dans {group_name} : {preview[:40]}{'...' if len(preview) > 40 else ''}"
        return f"{sender_name} a envoyé un message dans {group_name}"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'room_id': kwargs.get('room_id'),
            'sender_id': kwargs.get('sender_id'),
            'sender_name': kwargs.get('sender_name'),
            'group_name': kwargs.get('group_name'),
            'preview': kwargs.get('preview', ''),
        }


class UnreadMessagesNotification(NotificationTemplate):
    """Notification pour résumer les messages non lus"""
    NOTIFICATION_TYPE = 'message'
    
    @classmethod
    def get_title(cls, unread_count: int, **kwargs) -> str:
        return f"Vous avez {unread_count} message{'s' if unread_count > 1 else ''} non lu{'s' if unread_count > 1 else ''}"
    
    @classmethod
    def get_message(cls, unread_count: int, **kwargs) -> str:
        return f"{unread_count} nouveau{'x' if unread_count > 1 else ''} message{'s' if unread_count > 1 else ''} en attente de votre réponse"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'unread_count': kwargs.get('unread_count'),
        }


# ==========================================
# 🛍️ NOTIFICATIONS DE COMMANDE
# ==========================================

class OrderConfirmedNotification(NotificationTemplate):
    """Notification : Commande confirmée"""
    NOTIFICATION_TYPE = 'order'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} confirmée"
    
    @classmethod
    def get_message(cls, order_number: str, shop_name: str, total_amount: str, **kwargs) -> str:
        return f"Votre commande #{order_number} auprès de {shop_name} a été confirmée. Montant : {total_amount}"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'shop_name': kwargs.get('shop_name'),
            'shop_id': kwargs.get('shop_id'),
            'total_amount': kwargs.get('total_amount'),
        }


class OrderProcessingNotification(NotificationTemplate):
    """Notification : Commande en traitement"""
    NOTIFICATION_TYPE = 'order'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} en préparation"
    
    @classmethod
    def get_message(cls, order_number: str, shop_name: str, **kwargs) -> str:
        return f"La commande #{order_number} de {shop_name} est en cours de préparation et sera expédiée bientôt"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'shop_name': kwargs.get('shop_name'),
        }


class OrderCancelledNotification(NotificationTemplate):
    """Notification : Commande annulée"""
    NOTIFICATION_TYPE = 'order'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} annulée"
    
    @classmethod
    def get_message(cls, order_number: str, reason: str = "", **kwargs) -> str:
        msg = f"Votre commande #{order_number} a été annulée"
        if reason:
            msg += f". Raison : {reason}"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'reason': kwargs.get('reason', ''),
        }


class OrderQueryNotification(NotificationTemplate):
    """Notification : Question sur la commande"""
    NOTIFICATION_TYPE = 'order'
    
    @classmethod
    def get_title(cls, order_number: str, sender_name: str, **kwargs) -> str:
        return f"Question sur la commande #{order_number} de {sender_name}"
    
    @classmethod
    def get_message(cls, order_number: str, sender_name: str, query_preview: str = "", **kwargs) -> str:
        if query_preview:
            return f"{sender_name} a une question : {query_preview[:60]}{'...' if len(query_preview) > 60 else ''}"
        return f"{sender_name} a posé une question concernant la commande #{order_number}"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'sender_id': kwargs.get('sender_id'),
            'sender_name': kwargs.get('sender_name'),
            'query_preview': kwargs.get('query_preview', ''),
        }


# ==========================================
# 📦 NOTIFICATIONS DE LIVRAISON
# ==========================================

class DeliveryPendingNotification(NotificationTemplate):
    """Notification : Commande prête pour expédition"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} prête pour l'expédition"
    
    @classmethod
    def get_message(cls, order_number: str, estimated_delivery: str = "", **kwargs) -> str:
        msg = f"Votre commande #{order_number} est prête pour être livrée"
        if estimated_delivery:
            msg += f". Livraison estimée : {estimated_delivery}"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'estimated_delivery': kwargs.get('estimated_delivery', ''),
            'tracking_number': kwargs.get('tracking_number', ''),
        }


class OrderShippedNotification(NotificationTemplate):
    """Notification : Commande expédiée"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} expédiée 🚚"
    
    @classmethod
    def get_message(cls, order_number: str, carrier: str = "", tracking_number: str = "", **kwargs) -> str:
        msg = f"Votre commande #{order_number} a été expédiée"
        if carrier:
            msg += f" par {carrier}"
        if tracking_number:
            msg += f". N° de suivi : {tracking_number}"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'carrier': kwargs.get('carrier', ''),
            'tracking_number': kwargs.get('tracking_number', ''),
        }


class OrderInTransitNotification(NotificationTemplate):
    """Notification : Commande en cours de livraison"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} en cours de livraison"
    
    @classmethod
    def get_message(cls, order_number: str, estimated_delivery: str = "", **kwargs) -> str:
        msg = f"Votre commande #{order_number} est en cours de livraison"
        if estimated_delivery:
            msg += f". Arrivée estimée : {estimated_delivery}"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'estimated_delivery': kwargs.get('estimated_delivery', ''),
        }


class OrderDeliveredNotification(NotificationTemplate):
    """Notification : Commande livrée"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Commande #{order_number} livrée ✅"
    
    @classmethod
    def get_message(cls, order_number: str, shop_name: str, **kwargs) -> str:
        return f"Votre commande #{order_number} de {shop_name} a été livrée avec succès. Dites-nous ce que vous en pensez !"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'shop_name': kwargs.get('shop_name'),
            'shop_id': kwargs.get('shop_id'),
        }


class DeliveryDelayedNotification(NotificationTemplate):
    """Notification : Retard de livraison"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"⚠️ Retard livraison commande #{order_number}"
    
    @classmethod
    def get_message(cls, order_number: str, reason: str = "", new_estimated: str = "", **kwargs) -> str:
        msg = f"La livraison de la commande #{order_number} est retardée"
        if reason:
            msg += f" ({reason})"
        if new_estimated:
            msg += f". Nouvelle date estimée : {new_estimated}"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'reason': kwargs.get('reason', ''),
            'new_estimated': kwargs.get('new_estimated', ''),
        }


class DeliveryFailedNotification(NotificationTemplate):
    """Notification : Échec de livraison"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"❌ Échec livraison commande #{order_number}"
    
    @classmethod
    def get_message(cls, order_number: str, reason: str = "", **kwargs) -> str:
        msg = f"La livraison de la commande #{order_number} a échoué"
        if reason:
            msg += f" ({reason}). Veuillez contacter le support"
        else:
            msg += ". Veuillez contacter le support"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'reason': kwargs.get('reason', ''),
        }


class ReturnInitiatedNotification(NotificationTemplate):
    """Notification : Retour de commande initié"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Retour commande #{order_number} en cours"
    
    @classmethod
    def get_message(cls, order_number: str, reason: str = "", **kwargs) -> str:
        msg = f"Le retour de la commande #{order_number} a été initié"
        if reason:
            msg += f". Raison : {reason}"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'reason': kwargs.get('reason', ''),
            'return_id': kwargs.get('return_id', ''),
        }


class RefundInitiatedNotification(NotificationTemplate):
    """Notification : Remboursement initié"""
    NOTIFICATION_TYPE = 'delivery'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Remboursement commande #{order_number} en cours"
    
    @classmethod
    def get_message(cls, order_number: str, refund_amount: str = "", **kwargs) -> str:
        msg = f"Le remboursement de votre commande #{order_number} a été initié"
        if refund_amount:
            msg += f". Montant : {refund_amount}"
        msg += ". Il sera crédité en 5-7 jours ouvrables"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'refund_amount': kwargs.get('refund_amount', ''),
        }


# ==========================================
# 📋 AUTRES NOTIFICATIONS
# ==========================================

class PaymentReceivedNotification(NotificationTemplate):
    """Notification : Paiement reçu"""
    NOTIFICATION_TYPE = 'order'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"Paiement reçu pour commande #{order_number}"
    
    @classmethod
    def get_message(cls, order_number: str, amount: str, **kwargs) -> str:
        return f"Nous avons reçu le paiement de {amount} pour la commande #{order_number}. Merci !"
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'amount': kwargs.get('amount'),
        }


class PaymentFailedNotification(NotificationTemplate):
    """Notification : Paiement échoué"""
    NOTIFICATION_TYPE = 'order'
    
    @classmethod
    def get_title(cls, order_number: str, **kwargs) -> str:
        return f"❌ Paiement échoué - Commande #{order_number}"
    
    @classmethod
    def get_message(cls, order_number: str, reason: str = "", **kwargs) -> str:
        msg = f"Le paiement pour la commande #{order_number} a échoué"
        if reason:
            msg += f" ({reason})"
        msg += ". Veuillez réessayer ou utiliser un autre moyen de paiement"
        return msg
    
    @classmethod
    def get_data(cls, **kwargs):
        return {
            'type': cls.NOTIFICATION_TYPE,
            'order_id': kwargs.get('order_id'),
            'order_number': kwargs.get('order_number'),
            'reason': kwargs.get('reason', ''),
        }


# ==========================================
# REGISTRE DES TEMPLATES
# ==========================================

NOTIFICATION_TEMPLATES = {
    # Messages
    'new_message': NewMessageNotification,
    'group_message': GroupMessageNotification,
    'unread_messages': UnreadMessagesNotification,
    
    # Commandes
    'order_confirmed': OrderConfirmedNotification,
    'order_processing': OrderProcessingNotification,
    'order_cancelled': OrderCancelledNotification,
    'order_query': OrderQueryNotification,
    
    # Livraisons
    'delivery_pending': DeliveryPendingNotification,
    'order_shipped': OrderShippedNotification,
    'order_in_transit': OrderInTransitNotification,
    'order_delivered': OrderDeliveredNotification,
    'delivery_delayed': DeliveryDelayedNotification,
    'delivery_failed': DeliveryFailedNotification,
    'return_initiated': ReturnInitiatedNotification,
    'refund_initiated': RefundInitiatedNotification,
    
    # Paiements
    'payment_received': PaymentReceivedNotification,
    'payment_failed': PaymentFailedNotification,
}


def get_template(template_key: str) -> NotificationTemplate:
    """Récupère un template par sa clé"""
    return NOTIFICATION_TEMPLATES.get(template_key)


def get_all_templates() -> dict:
    """Retourne tous les templates disponibles"""
    return NOTIFICATION_TEMPLATES
