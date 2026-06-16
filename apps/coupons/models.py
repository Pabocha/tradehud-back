from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


# Create your models here.

User = get_user_model()

class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    users = models.ManyToManyField(User, blank=True, related_name='coupons')
    description = models.TextField(blank=True)
    DISCOUNT_TYPES = [
        ('fixed', 'Montant fixe'),
        ('percent', 'Pourcentage'),
        ('shipping', 'Livraison'),
    ]
    AUDIENCE_TYPES = [
        ('public', 'Tout le monde'),
        ('targeted', 'Utilisateurs cibl?s'),
        ('single', 'Utilisateur unique'),
    ]
    SCOPE_TYPES = [
        ('cart', 'Panier'),
        ('product', 'Produit'),
        ('category', 'Cat?gorie'),
        ('shop', 'Boutique'),
        ('shipping', 'Livraison'),
    ]
    SHIPPING_DISCOUNT_TYPES = [
        ('fixed', 'Montant fixe'),
        ('percent', 'Pourcentage'),
    ]
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    max_uses = models.PositiveIntegerField(default=1)
    uses = models.PositiveIntegerField(default=0)
    applicable_to_shipping = models.BooleanField(default=False)  # compatibilit? historique
    scope = models.CharField(max_length=20, choices=SCOPE_TYPES, default='cart')
    audience = models.CharField(max_length=20, choices=AUDIENCE_TYPES, default='public')
    shipping_discount_type = models.CharField(
        max_length=20, choices=SHIPPING_DISCOUNT_TYPES, null=True, blank=True
    )
    shipping_discount_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    shipping_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    # Produits cibl?s	-20% sur les chaussures	R?duction seulement sur certains articles
    target_categories = models.ManyToManyField('categories.Categories', blank=True)
    target_products = models.ManyToManyField('products.Products', blank=True)
    target_shops = models.ManyToManyField('shops.Shops', blank=True)

    def clean(self):
        super().clean()
        errors = {}

        if self.end_date <= self.start_date:
            errors["end_date"] = "La date de fin doit etre apres la date de debut."

        if self.discount_value is None or self.discount_value <= Decimal("0"):
            errors["discount_value"] = "La valeur de reduction doit etre superieure a 0."

        if self.discount_type == "percent" and self.discount_value > Decimal("100"):
            errors["discount_value"] = "Le pourcentage de reduction ne peut pas depasser 100."

        if self.scope == "shipping" and self.discount_type != "shipping":
            errors["discount_type"] = "Pour scope='shipping', discount_type doit etre 'shipping'."

        if self.max_uses is not None and self.uses > self.max_uses:
            errors["uses"] = "Le nombre d'utilisations ne peut pas depasser max_uses."

        if errors:
            raise ValidationError(errors)

    def is_valid_now(self):
        now = timezone.now()
        return (
            self.is_active
            and self.start_date <= now <= self.end_date
            and (self.max_uses is None or self.uses < self.max_uses)
        )

    def is_valid(self):
        return self.is_valid_now()


class CouponUsage(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name='usages')
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='coupon_usages')
    order = models.ForeignKey('orders.Orders', on_delete=models.PROTECT, related_name='coupon_usages')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('coupon', 'order')
        indexes = [
            models.Index(fields=['coupon', 'user']),
        ]
    