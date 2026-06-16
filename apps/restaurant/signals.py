from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import RestaurantReview, OrderItem, RestaurantOrder, Payment


@receiver(post_save, sender=RestaurantReview)
@receiver(post_delete, sender=RestaurantReview)
def update_restaurant_rating(sender, instance, **kwargs):
    """
    Mise à jour automatique du rating du restaurant
    après ajout/modification/suppression d'un avis
    """
    instance.restaurant.update_rating()


@receiver(post_save, sender=OrderItem)
@receiver(post_delete, sender=OrderItem)
def update_order_total(sender, instance, **kwargs):
    """
    Recalcul du total de la commande après ajout/modification/suppression d'un item
    """
    if kwargs.get('created', False) or kwargs.get('update_fields') is None:
        instance.order.calculate_total()


# @receiver(pre_save, sender=RestaurantOrder)
# def set_delivery_fee(sender, instance, **kwargs):
#     """
#     Définir automatiquement les frais de livraison selon le type de commande
#     """
#     if instance.delivery_type == 'delivery':
#         instance.delivery_fee = instance.restaurant.delivery_fee
#     else:
#         instance.delivery_fee = 0


@receiver(post_save, sender=RestaurantOrder)
def create_payment_for_order(sender, instance, created, **kwargs):
    """
    Créer automatiquement un objet Payment lors de la création d'une commande
    """
    if created:
        Payment.objects.get_or_create(
            order=instance,
            defaults={
                'amount': instance.total_price,
                'status': 'pending'
            }
        )