from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.marketing.models import FlashSale
from apps.marketing.services import sync_flash_sale_products
from apps.products.models import ProductPromotion, Products


class Command(BaseCommand):
    help = (
        "Crée (ou met à jour) une vente flash de démonstration : "
        "crée des promotions actives sur quelques produits si aucune n'existe, "
        "puis resynchronise la sélection de la vente flash."
    )

    def add_arguments(self, parser):
        parser.add_argument('--name', default='Vente Flash', help="Nom de la vente flash")
        parser.add_argument('--hours', type=int, default=48, help="Durée de la vente flash en heures")
        parser.add_argument('--promo-products', type=int, default=10, help="Nombre de produits en promotion de démo à créer si nécessaire")
        parser.add_argument('--min-discount', type=float, default=15, help="Remise minimale en %% pour la sélection")
        parser.add_argument('--max-days', type=int, default=5, help="Promotion se terminant au plus tard dans X jours")

    def handle(self, *args, **options):
        name = options['name']
        hours = options['hours']
        promo_products = options['promo_products']
        now = timezone.now()
        end_at = now + timedelta(hours=hours)

        # 1. Promotions de démo si aucune n'est active
        active_promos = ProductPromotion.objects.filter(
            is_active=True,
            start_at__lte=now,
            end_at__gte=now,
        ).count()
        if active_promos == 0:
            candidates = list(
                Products.objects.filter(is_active=True, status='available')[:promo_products]
            )
            created = 0
            for product in candidates:
                base = product.base_price.amount
                if base <= 0:
                    continue
                factor = Decimal('1') - Decimal(str(0.25 + (created % 3) * 0.10))
                ProductPromotion.objects.create(
                    product=product,
                    promo_price=base * factor,
                    start_at=now,
                    end_at=now + timedelta(hours=48),
                    is_active=True,
                )
                created += 1
            self.stdout.write(self.style.SUCCESS(
                f"Aucune promotion active : {created} promotion(s) de démo créée(s) "
                f"(remises entre 25% et 45%)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"{active_promos} promotion(s) active(s) déjà présentes, création de démo ignorée."
            ))

        # 2. Vente flash
        existing = FlashSale.objects.filter(name=name).first()
        if existing:
            existing.start_at = now
            existing.end_at = end_at
            existing.is_active = True
            existing.save(update_fields=['start_at', 'end_at', 'is_active', 'updated_at'])
            verb = 'mise à jour'
        else:
            existing = FlashSale.objects.create(
                name=name,
                description="Sélection de produits en promotion, offre limitée dans le temps.",
                start_at=now,
                end_at=end_at,
                is_active=True,
                target_type='product',
            )
            verb = 'créée'

        # 3. Resync de la sélection
        selected = sync_flash_sale_products(
            existing,
            min_discount=options['min_discount'],
            max_days=options['max_days'],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Vente flash {verb} : {name} ({hours}h). {len(selected)} produit(s) sélectionné(s)."
        ))
