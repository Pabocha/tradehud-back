import os
from PIL import Image
from django.db import models
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError
from apps.shops.models import Shops
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.shops.models import Shops
from djmoney.models.fields import MoneyField
from django_countries.fields import CountryField
from taggit.managers import TaggableManager
from django.conf import settings
User = get_user_model()
import hashlib
from django.utils.timezone import now

def get_file_hash(file):
    hash_md5 = hashlib.md5()
    for chunk in file.chunks():
        hash_md5.update(chunk)
    return hash_md5.hexdigest()


# Create your models here.

class Colors(models.Model):
    name = models.CharField(max_length=50)
    code_hex = models.CharField(max_length = 7)

    class Meta:
        verbose_name_plural = "Colors"

    def __str__(self):
        return self.name  


class ProductQuerySet(models.QuerySet):
    def with_total_stock(self):
        return self.annotate(
            total_stock=Sum('variants__stock_quantity')
        )


class Products(models.Model):
    CHOICES_STATUS = [
        ('available', 'Disponible'),
        ('unavailable', 'En rupture'),
        ('pre_order', 'Pre-commande'), 
    ]

    def validate_image_file(image):
        max_size_mb = 5
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.jfif']

        # Taille du fichier (toujours disponible)
        if image.size > max_size_mb * 1024 * 1024:
            raise ValidationError(
                f"La taille de l'image ne doit pas dépasser {max_size_mb} MB."
            )

        # âœ… Vérification extension
        ext = os.path.splitext(image.name)[1].lower()
        if ext not in allowed_extensions:
            raise ValidationError(
                "Format d'image non valide. Formats autorisés : JPEG, PNG, GIF, JFIF."
            )

        # âœ… Vérification réele du fichier image
        try:
            img = Image.open(image)
            img.verify()
        except Exception:
            raise ValidationError("Le fichier uploadé n'est pas une image valide.")

    name = models.CharField(max_length=255)
    base_price = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF')
    brand = models.CharField(max_length=255, blank=True, null=True)
    shop = models.ForeignKey('shops.Shops', on_delete=models.CASCADE, related_name="product")
    date_added = models.DateTimeField(auto_now_add=True)
    min_order_quantity = models.PositiveIntegerField(default=1)
    stock_quantity = models.PositiveIntegerField(blank=True, null=True) # Stock global (pour produits sans variantes)
    status = models.CharField(max_length=50, choices=CHOICES_STATUS, default='available')
    image = models.ImageField(upload_to='', validators=[validate_image_file])
    description = models.TextField()
    numbers_reviews = models.PositiveIntegerField(default=0)
    average_rating = models.FloatField(default=0.0)
    category = models.ForeignKey('categories.Categories', models.SET_NULL, null=True, blank=True)
    country_origin = CountryField(blank=True, null=True)
    views_count = models.PositiveIntegerField(default=0)
    is_sponsored = models.BooleanField(default=False)
    sponsored_start = models.DateTimeField(blank=True, null=True)
    sponsored_end = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Poids en kg")
    length = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Longueur en cm")
    width = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Largeur en cm")
    height = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Hauteur en cm")
    tags = TaggableManager(blank=True)  # champ tags libre
    remarks = models.TextField(blank=True, null=True)
    attribute = models.JSONField(default=dict, blank=True)
    features = models.JSONField(
        default=list, blank=True,
        help_text="Points forts du produit, liste de chaines (ex: ['Résistant à l'eau', 'Charge rapide'])"
    )
    # Ordre des attributs de variantes pour reconstruire l'arbre côté frontend
    variant_structure = models.JSONField(default=list, blank=True)
    objects = ProductQuerySet.as_manager()

    @property
    def is_currently_sponsored(self):
        now = timezone.now()
        return (
            self.is_sponsored and
            self.sponsored_start is not None and
            self.sponsored_end is not None and
            self.sponsored_start <= now <= self.sponsored_end
        )

    def get_unit_price(self, quantity=1):
        # 1. Flash Sale active
        from apps.marketing.models import FlashSale
        now_ts = now()
        flash_sales = FlashSale.objects.filter(
            is_active=True, start_at__lte=now_ts, end_at__gte=now_ts
        )
        for fs in flash_sales:
            if fs.target_type == 'all':
                return fs.compute_discounted_price(self.base_price)
            if fs.target_type == 'product' and fs.target_products.filter(id=self.id).exists():
                return fs.compute_discounted_price(self.base_price)
            if fs.target_type == 'category' and self.category and fs.target_categories.filter(id=self.category_id).exists():
                return fs.compute_discounted_price(self.base_price)
            if fs.target_type == 'shop' and fs.target_shops.filter(id=self.shop_id).exists():
                return fs.compute_discounted_price(self.base_price)

        # 2. Promo active
        promo = self.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now()
        ).first()
        if promo:
            return promo.promo_price

        # 3. Prix par palier
        tier = (
            self.price_tiers
            .filter(
                min_quantity__lte=quantity
            )
            .filter(
                Q(max_quantity__gte=quantity) | Q(max_quantity__isnull=True)
            )
            .order_by("min_quantity")
            .first()
        )
        if tier:
            return tier.price

        # 4. Prix normal
        return self.base_price

    class Meta:
        verbose_name = ('Product')
        verbose_name_plural = ('Products')

    def __str__(self):
        return self.name

class Attribute(models.Model):
    name = models.CharField(max_length=50, help_text="Nom de l'attribut (ex: Couleur, Taille)")
    code = models.SlugField(unique=True, help_text="Code unique de l'attribut (ex: color, size)")            
    is_variant = models.BooleanField(default=True, help_text="Détermine si l'attribut est utilisé pour les variantes de produit") 
    # position = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name
    
class AttributeValue(models.Model):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=50, help_text="Valeur de l'attribut (ex: Rouge, M)")          # Rouge, M
    code = models.SlugField(help_text="Code unique de la valeur (ex: red, m)")                         # red, m
    hex_color = models.CharField(
        max_length=7, blank=True, null=True,
        help_text="Code hexadécimal de la couleur (ex: #FF0000)"
    ) 
    # position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('attribute', 'value')

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"

class ProductColorImage(models.Model):
    product = models.ForeignKey(
        Products,
        related_name="color_images",
        on_delete=models.CASCADE
    )
    color = models.ForeignKey(
        AttributeValue,
        on_delete=models.CASCADE,
        limit_choices_to={'attribute__name': 'Couleur'}
    )
    image = models.ImageField(upload_to="products/colors/")

    class Meta:
        unique_together = ('product', 'color')

    
class ProductVariant(models.Model):
    product = models.ForeignKey(Products, related_name='variants', on_delete=models.CASCADE)
    sku = models.CharField(max_length=100, unique=True, blank=True, null=True)
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    length = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Longueur en cm")
    width = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Largeur en cm")
    height = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Hauteur en cm")
    price_override = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF', null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=1)
    # Attributs personnalisÃ©s (non-officiels) saisis par l'utilisateur
    custom_attributes = models.JSONField(default=list, blank=True)
    attributes = models.ManyToManyField(AttributeValue)

    class Meta:
        unique_together = ['product', 'sku']

    def get_effective_weight(self):
        return self.weight or self.product.weight

    def get_effective_length(self):
        return self.length or self.product.length

    def get_effective_width(self):
        return self.width or self.product.width

    def get_effective_height(self):
        return self.height or self.product.height

    def get_unit_price(self, quantity=1):
        """
        Ordre de priorité pour déterminer le prix à utiliser :
        1) Promo active
        2) Prix de variation (price_override)
        3) Prix par palier
        4) Prix de base
        """
        product = self.product

        # 1. Promo active
        promo = product.promotions.filter(
            is_active=True,
            start_at__lte=now(),
            end_at__gte=now()
        ).first()
        if promo:
            return promo.promo_price

        # 2. Prix de variation
        if self.price_override:
            return self.price_override

        # 3. Prix par palier
        tier = (
            product.price_tiers
            .filter(min_quantity__lte=quantity)
            .filter(Q(max_quantity__gte=quantity) | Q(max_quantity__isnull=True))
            .order_by("min_quantity")
            .first()
        )
        if tier:
            return tier.price

        # 4. Prix de base
        return product.base_price
    
    def get_unit_price(self, quantity=1):
        # 1. Flash Sale active
        from apps.marketing.models import FlashSale
        now_ts = now()
        product = self.product
        flash_sales = FlashSale.objects.filter(
            is_active=True, start_at__lte=now_ts, end_at__gte=now_ts
        )
        for fs in flash_sales:
            if fs.target_type == 'all':
                if self.price_override:
                    return fs.compute_discounted_price(self.price_override)
                return fs.compute_discounted_price(product.base_price)
            if fs.target_type == 'product' and fs.target_products.filter(id=product.id).exists():
                if self.price_override:
                    return fs.compute_discounted_price(self.price_override)
                return fs.compute_discounted_price(product.base_price)
            if fs.target_type == 'category' and product.category and fs.target_categories.filter(id=product.category_id).exists():
                if self.price_override:
                    return fs.compute_discounted_price(self.price_override)
                return fs.compute_discounted_price(product.base_price)
            if fs.target_type == 'shop' and fs.target_shops.filter(id=product.shop_id).exists():
                if self.price_override:
                    return fs.compute_discounted_price(self.price_override)
                return fs.compute_discounted_price(product.base_price)

        # 2. Prix spécifique à la variante
        if self.price_override:
            return self.price_override

        # 3. Fallback produit
        return product.get_unit_price(quantity)
    def save(self, *args, **kwargs):
        # GÃ©nÃ©rer un SKU si non fourni
        if not self.sku:
            self.sku = f"{self.product.id}-{hashlib.md5(os.urandom(16)).hexdigest()[:8]}"
        super().save(*args, **kwargs)
    
class ProductPriceTier(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="price_tiers")
    min_quantity = models.PositiveIntegerField()
    max_quantity = models.PositiveIntegerField(blank=True, null=True)
    price = MoneyField(max_digits=15, decimal_places=2, default_currency="XOF")

    class Meta:
        ordering = ["min_quantity"]
    def __str__(self):
        return f"{self.product.name} - {self.min_quantity}+ : {self.price}"
    
class ProductPromotion(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="promotions")
    promo_price = MoneyField(max_digits=15, decimal_places=2, default_currency="XOF")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Promo {self.promo_price} for {self.product.name} from {self.start_at} to {self.end_at}"
    
class GalerieImages(models.Model):
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name='galerie_images')
    image = models.ImageField(upload_to='produits/galerie')
    position = models.IntegerField(default=0)
    date_added = models.DateTimeField(auto_now_add=True)
    type_image = models.CharField(max_length=50, choices=[('principale', 'Principale'), ('supplementaire', 'Supplémentaire'), ('detail', 'Détail')], default='supplementaire')
    alt_text = models.CharField(max_length=255, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True, null=True)
    hash = models.CharField(max_length=64, editable=False)

    def save(self, *args, **kwargs):
        if not self.hash and self.image:
            # Calculer le hash seulement si pas encore dÃ©fini
            self.hash = get_file_hash(self.image)

        # VÃ©rifier si une image identique existe dÃ©jÃ  pour ce produit
        if GalerieImages.objects.filter(product=self.product, hash=self.hash).exclude(pk=self.pk).exists():
            # Si oui, on arrÃªte -> soit on ignore, soit on update, soit on skip
            return  # <-- Ã©vite de sauvegarder le doublon

        super().save(*args, **kwargs)


    class Meta:
        unique_together = ('product', 'hash')
        ordering = ('-date_added',)

class RecentlyViewedProduct(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='recently_viewed_products'
    )
    product = models.ForeignKey(
        'products.Products',
        on_delete=models.CASCADE,
        related_name='recent_views'
    )
    viewed_at = models.DateTimeField(default=timezone.now)  # Date de dernière consultation
    view_count = models.PositiveIntegerField(default=1)  # Nombre de fois que ce produit a été consulté
    session_key = models.CharField(max_length=100, null=True, blank=True)  # Pour les utilisateurs anonymes
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-viewed_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'],
                condition=Q(user__isnull=False),
                name='uniq_recent_view_user_product',
            ),
            models.UniqueConstraint(
                fields=['session_key', 'product'],
                condition=Q(user__isnull=True),
                name='uniq_recent_view_session_product',
            ),
        ]
        verbose_name = 'Produit consulté récemment'
        verbose_name_plural = 'Produits consultés récemment'

    def __str__(self):
        return f"{self.user or 'Anonymous'} a vu {self.product.name} ({self.view_count}x)"


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('sale', 'Vente'),
        ('restock', 'Réapprovisionnement'),
        ('adjustment', 'Ajustement manuel'),
        ('return', 'Retour client'),
        ('cancelled', 'Commande annulée'),
    ]

    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name='stock_movements', null=True, blank=True)
    variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, related_name='stock_movements', null=True, blank=True)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.IntegerField(help_text="Positif = entrée, négatif = sortie")
    previous_stock = models.PositiveIntegerField(help_text="Stock avant le mouvement")
    new_stock = models.PositiveIntegerField(help_text="Stock après le mouvement")
    reference_type = models.CharField(max_length=20, blank=True, null=True, help_text="'order', 'manual', 'system'")
    reference_id = models.CharField(max_length=100, blank=True, null=True, help_text="Numéro de commande ou raison")
    note = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', 'created_at']),
            models.Index(fields=['variant', 'created_at']),
            models.Index(fields=['movement_type']),
        ]

    def __str__(self):
        target = self.variant or self.product
        return f"[{self.movement_type}] {target} x{self.quantity} ({self.previous_stock} → {self.new_stock})"


class ProductComparison(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True, related_name='comparisons'
    )
    session_key = models.CharField(max_length=100, null=True, blank=True)
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name='compared_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-added_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'],
                condition=models.Q(user__isnull=False),
                name='uniq_comparison_user_product',
            ),
            models.UniqueConstraint(
                fields=['session_key', 'product'],
                condition=models.Q(user__isnull=True),
                name='uniq_comparison_session_product',
            ),
        ]

    def __str__(self):
        return f"Comparison: {self.user or self.session_key} - {self.product.name}"
