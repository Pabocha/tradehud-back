# accounts/management/commands/purge_deleted_accounts.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from comptes.models import DeletionRequest, CustomUser

PURGE_AFTER_DAYS = 30  # délai avant suppression définitive

class Command(BaseCommand):
    help = "Purge les comptes marqués processed ou désactivés depuis plus de PURGE_AFTER_DAYS"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=PURGE_AFTER_DAYS)

        # 1) Purge des DeletionRequest processed avant cutoff
        drs = DeletionRequest.objects.filter(status="processed", processed_at__lte=cutoff)
        for dr in drs:
            user = dr.user
            try:
                # hard delete ou anonymize selon politique
                user.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted user {user.email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to delete {user.email}: {e}"))

        # 2) Option : Purge utilisateurs is_active=False depuis cutoff
        users = CustomUser.objects.filter(is_active=False, deleted_at__lte=cutoff)
        for user in users:
            try:
                user.delete()
                self.stdout.write(self.style.SUCCESS(f"Deleted inactive user {user.email}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to delete {user.email}: {e}"))
