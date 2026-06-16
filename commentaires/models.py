from django.db import models
from django.contrib.auth import get_user_model
from produits.models import Products

User = get_user_model()

# Create your models here.

class Ratings(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey(Products, on_delete=models.CASCADE, related_name="ratings")
    order_item = models.ForeignKey("commandes.LigneCommande", on_delete=models.CASCADE, related_name="ratings")  
    date_added = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True) 
    rating = models.FloatField(default=0.0)
    comment = models.TextField(blank=True, null=True)
    is_edited = models.BooleanField(default=False)  

    class Meta:
        verbose_name = "Rating"
        verbose_name_plural = "Ratings"
        unique_together = ('product', 'user', 'order_item')  # un seul avis par produit et par commande

    def __str__(self):
        return f"Commentaire de {self.user} pour {self.product}"

class ShopRatings(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    shop = models.ForeignKey("boutique.Shops", on_delete=models.CASCADE, related_name="ratings")
    order = models.ForeignKey("commandes.Orders", on_delete=models.CASCADE, related_name="shop_ratings")
    date_added = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    rating = models.FloatField(default=0.0)
    comment = models.TextField(blank=True, null=True)
    is_edited = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Shop Rating"
        verbose_name_plural = "Shop Ratings"
        unique_together = ('shop', 'user')
        # 🔒 Un utilisateur ne peut laisser qu’un seul avis par boutique et par commande

    def __str__(self):
        return f"Commentaire de {self.user} pour la boutique {self.shop}"




