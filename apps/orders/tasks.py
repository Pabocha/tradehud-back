from celery import shared_task
from django.utils import timezone


@shared_task
def expire_quotes():
    """Fait passer en 'expired' les quotes non converties dont la date d'expiration est passee."""
    from apps.orders.models import Quote

    now = timezone.now()
    count = Quote.objects.filter(
        status__in=["draft", "sent", "countered"],
        expires_at__lt=now,
    ).update(status="expired")
    return {"expired": count}
