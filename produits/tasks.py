import logging

from celery import shared_task
from django.utils import timezone

from .models import Products, ProductPromotion, Quote

logger = logging.getLogger(__name__)


@shared_task
def deactivate_expired_sponsored_products():
    """
    Desactive le sponsoring des produits dont la date de fin est depassee.
    """
    now = timezone.now()
    updated = Products.objects.filter(
        is_sponsored=True,
        sponsored_end__isnull=False,
        sponsored_end__lte=now,
    ).update(is_sponsored=False)

    logger.info("Sponsored products deactivated: %s", updated)
    return {"status": "success", "updated": updated}


@shared_task
def deactivate_expired_promotions():
    """
    Desactive les promotions actives dont la date de fin est depassee.
    """
    now = timezone.now()
    updated = ProductPromotion.objects.filter(
        is_active=True,
        end_at__lte=now,
    ).update(is_active=False)

    logger.info("Product promotions deactivated: %s", updated)
    return {"status": "success", "updated": updated}


@shared_task
def expire_quotes():
    """
    Passe les quotes expirees au statut 'expired'.
    """
    now = timezone.now()
    updated = Quote.objects.filter(
        expires_at__lte=now,
        status__in=["draft", "sent", "countered", "accepted"],
    ).update(status="expired", updated_at=now)

    logger.info("Quotes expired: %s", updated)
    return {"status": "success", "updated": updated}
