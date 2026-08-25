from django.core.management.base import BaseCommand

from apps.orders.models import Orders

from apps.wallets.services import release_order_funds


class Command(BaseCommand):
    help = "Crédite les portefeuilles des vendeurs pour les commandes livrées et payées (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Affiche les mouvements sans rien écrire.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        orders = Orders.objects.filter(status='delivered', payment_status='paid').order_by('id')
        total_released = 0
        for order in orders:
            shop_ids = list(order.order_lines.exclude(shop=None).values_list('shop_id', flat=True).distinct())
            if not shop_ids:
                continue
            released = release_order_funds(order)
            if released:
                total_released += len(released)
                for entry in released:
                    self.stdout.write(
                        f"  Commande #{order.order_number} → boutique {entry['shop_id']}: "
                        f"net={entry['net']} commission={entry['commission']}"
                    )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[DRY-RUN] {total_released} crédit(s) à effectuer. Aucune écriture."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{total_released} crédit(s) créé(s) au total."))
