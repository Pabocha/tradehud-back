from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save
from .models import Shops, DocumentShop
from apps.orders.models import Orders


@receiver(post_save, sender=DocumentShop)
def updated_store(sender, instance, created, **kwargs):
    
    if created:
        shop = instance.shop
        shop.status = 'active'
        shop.save()


@receiver(pre_save, sender=Orders)
def save_old_status(sender, instance, **kwargs):
    """
    Avant sauvegarde, on garde l'ancien status pour détecter les changements.
    """
    if instance.pk:
        try:
            old_instance = Orders.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except Orders.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Orders)
def update_shop_stats_on_order(sender, instance, created, **kwargs):
    """
    Met à jour les stats de la/les boutique(s) concernée(s) par cette commande.
    
    Optimisations :
    ✅ Utilise Celery asynchrone (ne bloque pas le serveur)
    ✅ Déclenche seulement quand le statut est définitif (delivered/cancelled)
    ✅ Pas de mise à jour à chaque modification intermédiaire (pending, processing, shipped)
    """
    from apps.shops.tasks import recalculate_shop_statistics_range
    from datetime import timedelta
    from django.utils.timezone import now
    
    date = instance.order_date.date()
    old_status = getattr(instance, "_old_status", None)
    new_status = instance.status

    # On récupère toutes les boutiques concernées par cette commande
    shops = Shops.objects.filter(product__order_lines__order=instance).distinct()

    for shop in shops:
        # ✅ DÉCLENCHER SEULEMENT SUR LES STATUTS DÉFINITIFS
        # (delivered = commande complète, cancelled = annulée)
        if new_status in ['delivered', 'cancelled']:
            # 🚀 Utiliser Celery asynchrone (ne bloque pas le serveur)
            # Recalculer les stats de ce jour pour cette boutique
            recalculate_shop_statistics_range.delay(
                shop_id=shop.id,
                days=1  # Recalculer juste le jour de la commande
            )

