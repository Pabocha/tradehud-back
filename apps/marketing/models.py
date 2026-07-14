from django.db import models
from django.core.exceptions import ValidationError 
from django.utils import timezone

# Create your models here.

class Announcement(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    badge = models.CharField(max_length=50, blank=True, null=True)
    badge_color = models.CharField(max_length=20, blank=True, null=True, )
    
    def __str__(self):
        return self.title

class Banner(models.Model):
    title = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="banners/")
    link = models.URLField(blank=True, help_text="Lien externe si applicable")
    tag = models.CharField(max_length=50, blank=True, null=True)
    cta = models.CharField(max_length=50, blank=True, null=True, help_text="Texte du bouton (ex: Acheter maintenant)")
    badge = models.CharField(max_length=100, blank=True, null=True, help_text="Tendance")
    badge_color = models.CharField(max_length=20, blank=True, null=True, help_text="bg du badge (ex: bg-orange-500")
    target = models.CharField(max_length=50, choices=[('shop', 'Boutique'), ('category', 'Catégorie'), ('product', 'Produit'), ('country', 'Région'), ('restaurant', 'Restaurant')], default='product')
    
    # Liens vers les objets (A adapter selon tes modèles)
    target_product = models.ForeignKey('products.Products', on_delete=models.SET_NULL, null=True, blank=True)
    target_category = models.ForeignKey('categories.Categories', on_delete=models.SET_NULL, null=True, blank=True)
    target_shop = models.ForeignKey('shops.Shops', on_delete=models.SET_NULL, null=True, blank=True)
    target_restaurant = models.ForeignKey('restaurant.Restaurant', on_delete=models.SET_NULL, null=True, blank=True)

    type = models.CharField(max_length=50, choices=[('slider', 'Slider'), ('slidebanner', 'Slide Banner'), ('popup', 'Popup'), ('sidebar', 'Sidebar')], default='slider')
    is_active = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=0)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            models.Index(fields=['is_active', 'start_date', 'end_date']),
        ]
    
    def clean(self):
        super().clean()
        # Vérifier la cohérence des dates
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("La date de début ne peut pas être après la date de fin.")

    def __str__(self):
        return f"{self.title or 'Sans titre'} ({self.type})"


class Campaign(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    badge = models.CharField(max_length=50, blank=True, null=True, help_text="Ex: -30%")
    badge_color = models.CharField(max_length=20, blank=True, null=True)
    banner_image = models.ImageField(upload_to='campaigns/', blank=True, null=True)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_at']

    def clean(self):
        super().clean()
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValidationError("start_at doit être avant end_at.")

    @property
    def is_currently_active(self):
        now = timezone.now()
        return self.is_active and self.start_at <= now <= self.end_at

    def __str__(self):
        return self.name


class FlashSale(models.Model):
    TARGET_TYPES = [
        ('all', 'Tous les produits'),
        ('category', 'Par catégorie'),
        ('shop', 'Par boutique'),
        ('product', 'Produits spécifiques'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=10, choices=[('percent', 'Pourcentage'), ('fixed', 'Montant fixe')])
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Pourcentage ou montant fixe")
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    target_type = models.CharField(max_length=20, choices=TARGET_TYPES, default='all')
    target_categories = models.ManyToManyField('categories.Categories', blank=True, related_name='flash_sales')
    target_shops = models.ManyToManyField('shops.Shops', blank=True, related_name='flash_sales')
    target_products = models.ManyToManyField('products.Products', blank=True, related_name='flash_sales')
    max_uses = models.PositiveIntegerField(blank=True, null=True)
    uses = models.PositiveIntegerField(default=0)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='flash_sales')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_at']

    def clean(self):
        super().clean()
        if self.discount_type == 'percent' and self.discount_value > 100:
            raise ValidationError("Le pourcentage ne peut pas dépasser 100%.")
        if self.discount_value <= 0:
            raise ValidationError("La valeur de réduction doit être positive.")
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValidationError("start_at doit être avant end_at.")

    @property
    def is_currently_active(self):
        now = timezone.now()
        if not self.is_active or not (self.start_at <= now <= self.end_at):
            return False
        if self.max_uses is not None and self.uses >= self.max_uses:
            return False
        return True

    def compute_discounted_price(self, original_price):
        """Calcule le prix après réduction de cette FlashSale."""
        from decimal import Decimal
        price = Decimal(str(original_price))
        if self.discount_type == 'percent':
            return price * (1 - self.discount_value / 100)
        else:
            discounted = price - self.discount_value
            return max(discounted, Decimal('0'))

    def __str__(self):
        return f"Flash: {self.name} ({self.discount_value}{'%' if self.discount_type == 'percent' else ' XOF'})"