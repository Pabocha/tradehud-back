from django.db import models
from django.core.validators import MinValueValidator
from django_countries.fields import CountryField
from decimal import Decimal


class ShippingZone(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    countries = models.JSONField(
        default=list, blank=True,
        help_text="Liste de codes pays ISO 3166-1 alpha-2 (ex: ['SN', 'ML', 'CI'])"
    )
    cities = models.JSONField(
        default=list, blank=True,
        help_text="Liste de villes pour affiner le matching (ex: ['Dakar', 'Thiès'])"
    )
    has_port = models.BooleanField(
        default=False,
        help_text="Cette zone contient un port ou aéroport international"
    )
    priority = models.IntegerField(
        default=0,
        help_text="Priorité de match: plus élevé = prioritaire (zone ville > zone pays)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = 'Zone de livraison'
        verbose_name_plural = 'Zones de livraison'

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    name = models.CharField(max_length=100)
    zone = models.ForeignKey(
        ShippingZone, on_delete=models.PROTECT, related_name='warehouses'
    )
    country = CountryField()
    city = models.CharField(max_length=100)
    address = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Entrepôt'
        verbose_name_plural = 'Entrepôts'

    def __str__(self):
        return f"{self.name} ({self.city})"


class PackageSize(models.Model):
    SIZE_CHOICES = [
        ('small', 'Petit'),
        ('medium', 'Moyen'),
        ('large', 'Grand'),
        ('extra_large', 'Très grand'),
    ]
    name = models.CharField(max_length=20, choices=SIZE_CHOICES, unique=True)
    max_weight_kg = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Poids maximum en kg"
    )
    max_length_cm = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Longueur maximum en cm"
    )
    max_width_cm = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Largeur maximum en cm"
    )
    max_height_cm = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Hauteur maximum en cm"
    )
    display_name = models.CharField(
        max_length=50,
        help_text="Nom affiché (ex: 'Petit colis')"
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order']
        verbose_name = 'Taille de colis'
        verbose_name_plural = 'Tailles de colis'

    def __str__(self):
        return self.display_name


class ShippingPricing(models.Model):
    TRANSPORT_CHOICES = [
        ('road', 'Route'),
        ('sea', 'Mer'),
        ('air', 'Air'),
    ]
    origin_zone = models.ForeignKey(
        ShippingZone, on_delete=models.CASCADE, related_name='pricing_from'
    )
    destination_zone = models.ForeignKey(
        ShippingZone, on_delete=models.CASCADE, related_name='pricing_to'
    )
    package_size = models.ForeignKey(
        PackageSize, on_delete=models.CASCADE, related_name='pricing'
    )
    transport_mode = models.CharField(max_length=10, choices=TRANSPORT_CHOICES)
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Prix fixe par colis pour cette route"
    )
    price_per_kg = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Prix supplémentaire par kg (utilisé principalement pour le fret mer/air)"
    )
    estimated_days_min = models.PositiveIntegerField(default=1)
    estimated_days_max = models.PositiveIntegerField(default=7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['origin_zone', 'destination_zone', 'package_size', 'transport_mode']
        unique_together = [
            'origin_zone', 'destination_zone', 'package_size', 'transport_mode'
        ]
        verbose_name = 'Tarif de livraison'
        verbose_name_plural = 'Tarifs de livraison'

    def __str__(self):
        return (
            f"{self.origin_zone.name} → {self.destination_zone.name} | "
            f"{self.package_size.display_name} | "
            f"{self.get_transport_mode_display()} | {self.base_price}"
        )

    def compute_cost(self, weight_kg=None):
        cost = self.base_price
        if self.price_per_kg and weight_kg:
            cost += self.price_per_kg * Decimal(str(weight_kg))
        return cost


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
        help_text="[DEPRECATED] Tarif spécifique à une boutique."
    )
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='standard')
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    price_per_kg = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    free_shipping_threshold = models.DecimalField(
        max_digits=15, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    min_delivery_days = models.PositiveIntegerField(default=1)
    max_delivery_days = models.PositiveIntegerField(default=7)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['zone', 'method', 'shop']
        unique_together = ['zone', 'shop', 'method']
        verbose_name = 'Tarif de livraison (legacy)'
        verbose_name_plural = 'Tarifs de livraison (legacy)'

    def __str__(self):
        shop_label = self.shop.name if self.shop else "Global"
        return f"[LEGACY] {self.zone.name} - {self.method} ({shop_label}) - {self.base_price}"
