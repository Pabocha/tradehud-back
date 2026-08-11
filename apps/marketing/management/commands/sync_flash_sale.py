from django.core.management.base import BaseCommand

from apps.marketing.models import FlashSale
from apps.marketing.services import sync_flash_sale_products


class Command(BaseCommand):
    help = (
        "Resynchronise la sélection de produits d'une vente flash (resync totale). "
        "Critères : produit actif & disponible, promotion active avec remise >= min_discount, "
        "stock > 0 et promotion se terminant dans <= max_days jours."
    )

    def add_arguments(self, parser):
        parser.add_argument('--name', default='Vente Flash', help="Nom de la vente flash à synchroniser")
        parser.add_argument('--min-discount', type=float, default=15, help="Remise minimale en %% (défaut : 15)")
        parser.add_argument('--max-days', type=int, default=5, help="Promotion se terminant au plus tard dans X jours (défaut : 5)")
        parser.add_argument('--limit', type=int, default=0, help="Nombre max de produits (0 = illimité)")

    def handle(self, *args, **options):
        name = options['name']
        flash_sale = FlashSale.objects.filter(name=name).first()
        if not flash_sale:
            self.stderr.write(self.style.ERROR(f"Vente flash '{name}' introuvable."))
            return

        selected = sync_flash_sale_products(
            flash_sale,
            min_discount=options['min_discount'],
            max_days=options['max_days'],
            limit=options['limit'],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Vente flash '{flash_sale.name}' : {len(selected)} produit(s) sélectionné(s) "
            f"(remise >= {options['min_discount']:g}%, fin promo <= {options['max_days']}j, resync totale)."
        ))
