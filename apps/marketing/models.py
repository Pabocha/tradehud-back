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