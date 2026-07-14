from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class ShippingZone(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    countries = models.JSONField(default=list, blank=True, help_text="Liste de codes pays ISO 3166-1 alpha-2 (ex: ['SN', 'ML', 'CI'])")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Zone de livraison'
        verbose_name_plural = 'Zones de livraison'

    def __str__(self):
        return self.name


class ShippingRate(models.Model):
    METHOD_CHOICES = [
        ('standard', 'Standard'),
        ('express', 'Express'),
        ('pickup', 'Retrait'),
    ]

    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name='rates')
    shop = models.ForeignKey(
        'shops.Shops',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='shipping_rates',
        help_text="Tarif spécifique à une boutique. Si vide, c'est un tarif global par défaut."
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='standard')
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Prix de base de la livraison"
    )
    price_per_kg = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Prix supplémentaire par kg (optionnel)"
    )
    free_shipping_threshold = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Sous-total minimum pour livraison gratuite"
    )
    min_delivery_days = models.PositiveIntegerField(default=1)
    max_delivery_days = models.PositiveIntegerField(default=7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['zone', 'method', 'shop']
        unique_together = ['zone', 'shop', 'method']
        verbose_name = 'Tarif de livraison'
        verbose_name_plural = 'Tarifs de livraison'

    def __str__(self):
        shop_label = self.shop.name if self.shop else "Global"
        return f"{self.zone.name} - {self.method} ({shop_label}) - {self.base_price}"
