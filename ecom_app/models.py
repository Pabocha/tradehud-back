from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal

# Create your models here.

User = get_user_model()

class PayementMethod(models.Model):
    value = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='image/payment', null=True)

    def __str__(self):
        return self.name

class Favorites(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey('produits.Products', on_delete=models.CASCADE, related_name='favorited_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['product']),
        ]
    def __str__(self):
        return f"{self.user.email} ♥ {self.product.name}"

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
    target_products = models.ManyToManyField('produits.Products', blank=True)
    target_shops = models.ManyToManyField('boutique.Shops', blank=True)

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
    order = models.ForeignKey('commandes.Orders', on_delete=models.PROTECT, related_name='coupon_usages')
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('coupon', 'order')
        indexes = [
            models.Index(fields=['coupon', 'user']),
        ]


class Notifications(models.Model):

    NOTIFICATION_TYPES = [
        ('order', 'Commande'),
        ('promo', 'Promotion'),
        ('message', 'Message'),
        ('delivery', 'Livraison'),
        ('product', 'Produit'),
        ('support', 'Support'),
        ('account', 'Compte'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.title[:30]}"
    

class Banner(models.Model):
    title = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="banners/")
    link = models.URLField(blank=True)
    target = models.CharField(max_length=50, choices=[('shop', 'Boutique'), ('category', 'Catégorie'), ('product', 'Produit'), ('region', 'Région'), ('restaurant', 'Restaurant')], default='product')
    type = models.CharField(max_length=50, choices=[('slider', 'Slider'), ('popup', 'Popup'), ('sidebar', 'Sidebar')], default='slider')
    is_active = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=0)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
