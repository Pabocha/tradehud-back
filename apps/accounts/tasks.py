import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import CustomUser, DeletionRequest, PasswordResetOTP

logger = logging.getLogger(__name__)


@shared_task
def purge_deleted_accounts_task(purge_after_days=30):
    """
    Purge les comptes marques supprimes/inactifs apres un delai.
    """
    cutoff = timezone.now() - timedelta(days=purge_after_days)
    deleted_users = 0

    drs = DeletionRequest.objects.filter(status="processed", processed_at__lte=cutoff)
    for dr in drs.select_related("user"):
        user = dr.user
        if not user:
            continue
        try:
            user.delete()
            deleted_users += 1
        except Exception as exc:
            logger.warning("Failed to delete user from processed request %s: %s", dr.id, exc)

    users = CustomUser.objects.filter(is_active=False, deleted_at__lte=cutoff)
    for user in users:
        try:
            user.delete()
            deleted_users += 1
        except Exception as exc:
            logger.warning("Failed to delete inactive user %s: %s", user.id, exc)

    logger.info("Deleted users by purge task: %s", deleted_users)
    return {"status": "success", "deleted_users": deleted_users}


@shared_task
def cleanup_expired_otps(retention_hours=24):
    """
    Supprime les OTP expires et les OTP utilises anciens.
    """
    now = timezone.now()
    otp_expiry_cutoff = now - timedelta(minutes=10)
    old_used_cutoff = now - timedelta(hours=retention_hours)

    expired_unused_deleted, _ = PasswordResetOTP.objects.filter(
        is_used=False,
        created_at__lte=otp_expiry_cutoff,
    ).delete()

    old_used_deleted, _ = PasswordResetOTP.objects.filter(
        is_used=True,
        used_at__isnull=False,
        used_at__lte=old_used_cutoff,
    ).delete()

    deleted = expired_unused_deleted + old_used_deleted
    logger.info("Expired/old OTP deleted: %s", deleted)
    return {"status": "success", "deleted_otps": deleted}
