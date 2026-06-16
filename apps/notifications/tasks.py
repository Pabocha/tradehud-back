"""
Tâches Celery pour envoyer les notifications en arrière-plan.
À importer dans ecom_app/tasks.py et à ajouter au CELERY_BEAT_SCHEDULE.
"""

from celery import shared_task
from django.contrib.auth import get_user_model
from apps.notifications.service import NotificationService
from apps.orders.models import Orders
from django.utils import timezone
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


# ================================================
# 📨 TÂCHES DE NOTIFICATION DE MESSAGE
# ================================================

@shared_task
def notify_new_message(room_id, sender_id, sender_name, preview=""):
    """
    Envoie une notification pour un nouveau message.
    
    Args:
        room_id: ID de la room de chat
        sender_id: ID de l'utilisateur qui envoie le message
        sender_name: Nom du sender
        preview: Aperçu du message
    """
    try:
        from apps.chat.models import ChatRoom
        room = ChatRoom.objects.get(id=room_id)
        
        # Identifier les destinataires (membres de la room sauf l'expéditeur)
        for member in room.member.exclude(id=sender_id):
            NotificationService.send_notification(
                user=member,
                template_key='new_message',
                template_data={
                    'sender_name': sender_name,
                    'room_id': room_id,
                    'sender_id': sender_id,
                    'preview': preview,
                }
            )
        
        logger.info(f"Notifications de message envoyées pour room {room_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi des notifications de message: {str(e)}")


@shared_task
def notify_group_message(group_id, group_name, sender_id, sender_name, preview=""):
    """
    Envoie une notification pour un message de groupe.
    """
    try:
        from apps.chat.models import ChatRoom
        group = ChatRoom.objects.get(id=group_id)
        
        for member in group.member.exclude(id=sender_id):
            NotificationService.send_notification(
                user=member,
                template_key='group_message',
                template_data={
                    'sender_name': sender_name,
                    'group_name': group_name,
                    'room_id': group_id,
                    'sender_id': sender_id,
                    'preview': preview,
                }
            )
        
        logger.info(f"Notifications de groupe envoyées pour group {group_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi des notifications de groupe: {str(e)}")


# ================================================
# 🛍️ TÂCHES DE NOTIFICATION DE COMMANDE
# ================================================

@shared_task
def notify_order_confirmed(order_id):
    """
    Envoie une notification pour la confirmation de commande.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_confirmed',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'shop_name': order.lignes_commande.first().shop.name if order.lignes_commande.exists() else 'Boutique',
                'total_amount': str(order.total_order_price),
            }
        )
        
        logger.info(f"Notification de confirmation envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de confirmation: {str(e)}")


@shared_task
def notify_order_processing(order_id):
    """
    Envoie une notification quand la commande est en traitement.
    """
    try:
        order = Orders.objects.get(id=order_id)
        shop_name = order.lignes_commande.first().shop.name if order.lignes_commande.exists() else 'Boutique'
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_processing',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'shop_name': shop_name,
            }
        )
        
        logger.info(f"Notification de traitement envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de traitement: {str(e)}")


@shared_task
def notify_order_cancelled(order_id, reason=""):
    """
    Envoie une notification quand la commande est annulée.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_cancelled',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'reason': reason,
            }
        )
        
        logger.info(f"Notification d'annulation envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification d'annulation: {str(e)}")


@shared_task
def notify_order_query(order_id, sender_id, sender_name, query_preview=""):
    """
    Envoie une notification pour une question sur la commande.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_query',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'sender_id': sender_id,
                'sender_name': sender_name,
                'query_preview': query_preview,
            }
        )
        
        logger.info(f"Notification de question envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de question: {str(e)}")


# ================================================
# 📦 TÂCHES DE NOTIFICATION DE LIVRAISON
# ================================================

@shared_task
def notify_delivery_pending(order_id, estimated_delivery="", tracking_number=""):
    """
    Envoie une notification quand la commande est prête pour livraison.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='delivery_pending',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'estimated_delivery': estimated_delivery,
                'tracking_number': tracking_number,
            }
        )
        
        logger.info(f"Notification de préparation envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de préparation: {str(e)}")


@shared_task
def notify_order_shipped(order_id, carrier="", tracking_number=""):
    """
    Envoie une notification quand la commande est expédiée.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_shipped',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'carrier': carrier,
                'tracking_number': tracking_number,
            }
        )
        
        logger.info(f"Notification d'expédition envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification d'expédition: {str(e)}")


@shared_task
def notify_order_in_transit(order_id, estimated_delivery=""):
    """
    Envoie une notification quand la commande est en cours de livraison.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_in_transit',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'estimated_delivery': estimated_delivery,
            }
        )
        
        logger.info(f"Notification de transit envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de transit: {str(e)}")


@shared_task
def notify_order_delivered(order_id):
    """
    Envoie une notification quand la commande est livrée.
    """
    try:
        order = Orders.objects.get(id=order_id)
        shop_name = order.lignes_commande.first().shop.name if order.lignes_commande.exists() else 'Boutique'
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='order_delivered',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'shop_name': shop_name,
                'shop_id': order.lignes_commande.first().shop.id if order.lignes_commande.exists() else None,
            }
        )
        
        logger.info(f"Notification de livraison envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de livraison: {str(e)}")


@shared_task
def notify_delivery_delayed(order_id, reason="", new_estimated=""):
    """
    Envoie une notification quand la livraison est retardée.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='delivery_delayed',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'reason': reason,
                'new_estimated': new_estimated,
            }
        )
        
        logger.info(f"Notification de retard envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de retard: {str(e)}")


@shared_task
def notify_delivery_failed(order_id, reason=""):
    """
    Envoie une notification quand la livraison échoue.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='delivery_failed',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'reason': reason,
            }
        )
        
        logger.info(f"Notification d'échec de livraison envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification d'échec: {str(e)}")


@shared_task
def notify_return_initiated(order_id, reason="", return_id=""):
    """
    Envoie une notification quand un retour est initié.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='return_initiated',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'reason': reason,
                'return_id': return_id,
            }
        )
        
        logger.info(f"Notification de retour envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de retour: {str(e)}")


@shared_task
def notify_refund_initiated(order_id, refund_amount=""):
    """
    Envoie une notification quand un remboursement est initié.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='refund_initiated',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'refund_amount': refund_amount,
            }
        )
        
        logger.info(f"Notification de remboursement envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de remboursement: {str(e)}")


# ================================================
# 💳 TÂCHES DE NOTIFICATION DE PAIEMENT
# ================================================

@shared_task
def notify_payment_received(order_id, amount):
    """
    Envoie une notification quand un paiement est reçu.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='payment_received',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'amount': str(amount),
            }
        )
        
        logger.info(f"Notification de paiement reçu envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification de paiement: {str(e)}")


@shared_task
def notify_payment_failed(order_id, reason=""):
    """
    Envoie une notification quand un paiement échoue.
    """
    try:
        order = Orders.objects.get(id=order_id)
        
        NotificationService.send_notification(
            user=order.customer,
            template_key='payment_failed',
            template_data={
                'order_id': order.id,
                'order_number': order.order_number,
                'reason': reason,
            }
        )
        
        logger.info(f"Notification de paiement échoué envoyée pour commande {order_id}")
    
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi de notification d'échec de paiement: {str(e)}")
