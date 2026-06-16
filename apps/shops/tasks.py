"""
Tâches Celery pour le module boutique.
Recalcule les statistiques des boutiques régulièrement.
"""
from celery import shared_task
from django.utils.timezone import now
from datetime import timedelta
from .models import Shops, ShopStatistics
from .views import update_shop_statistics
import logging

logger = logging.getLogger(__name__)


@shared_task
def recalculate_daily_shop_statistics():
    """
    Tâche planifiée : Recalcule les stats de toutes les boutiques pour aujourd'hui.
    À exécuter chaque nuit (via Celery Beat).
    """
    try:
        date = now().date()
        shops = Shops.objects.filter(is_deleted=False)
        
        count = 0
        for shop in shops:
            try:
                update_shop_statistics(shop, date)
                count += 1
            except Exception as e:
                logger.error(f"Erreur mise à jour stats boutique {shop.id}: {str(e)}")
        
        logger.info(f"✅ Recalcul stats complété: {count} boutiques mises à jour")
        return {"status": "success", "shops_updated": count}
    
    except Exception as e:
        logger.error(f"❌ Erreur recalcul stats: {str(e)}")
        return {"status": "error", "message": str(e)}


@shared_task
def recalculate_shop_statistics_range(shop_id, days=7):
    """
    Tâche pour recalculer les stats d'une boutique sur une plage de jours.
    Utile après correction de données ou import.
    
    Args:
        shop_id: ID de la boutique
        days: Nombre de jours à recalculer (par défaut 7)
    """
    try:
        shop = Shops.objects.get(id=shop_id)
        date_to = now().date()
        date_from = date_to - timedelta(days=days)
        
        count = 0
        current_date = date_from
        while current_date <= date_to:
            update_shop_statistics(shop, current_date)
            count += 1
            current_date += timedelta(days=1)
        
        logger.info(f"✅ Stats boutique {shop.name} recalculées sur {count} jours")
        return {"status": "success", "days_updated": count}
    
    except Shops.DoesNotExist:
        logger.error(f"❌ Boutique {shop_id} non trouvée")
        return {"status": "error", "message": f"Shop {shop_id} not found"}
    except Exception as e:
        logger.error(f"❌ Erreur recalcul: {str(e)}")
        return {"status": "error", "message": str(e)}


@shared_task
def cleanup_old_statistics(days=90):
    """
    Nettoie les anciennes statistiques (optionnel).
    Garde seulement les stats des 90 derniers jours par défaut.
    """
    try:
        cutoff_date = now().date() - timedelta(days=days)
        deleted_count, _ = ShopStatistics.objects.filter(date__lt=cutoff_date).delete()
        logger.info(f"✅ {deleted_count} anciennes stats supprimées")
        return {"status": "success", "deleted": deleted_count}
    except Exception as e:
        logger.error(f"❌ Erreur nettoyage: {str(e)}")
        return {"status": "error", "message": str(e)}
