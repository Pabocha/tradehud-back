from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.marketing.models import FlashSale
from apps.marketing.services import sync_flash_sale_products


@shared_task
def renew_flash_sale_products():
    """Renouvelle la sélection de produits de chaque vente flash active.

    Planifié toutes les nuits à minuit (UTC) : n'agit que les jours pairs,
    soit concrètement tous les 2 jours. Prolonge la fenêtre de la vente
    flash si elle expire, puis resynchronise ses produits (resync totale).
    """
    if timezone.now().date().toordinal() % 2 != 0:
        return

    now = timezone.now()
    refreshed = 0
    for flash_sale in FlashSale.objects.filter(is_active=True):
        if flash_sale.end_at <= now + timedelta(days=1):
            flash_sale.start_at = now
            flash_sale.end_at = now + timedelta(days=2)
            flash_sale.save(update_fields=['start_at', 'end_at', 'updated_at'])
        sync_flash_sale_products(flash_sale)
        refreshed += 1
    return refreshed
