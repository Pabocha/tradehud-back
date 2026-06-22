from django.db import models
from django.conf import settings
from apps.products.models import Products  # ou ton modèle de produit
from djmoney.models.fields import MoneyField

class CartItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.PROTECT, null=True, blank=True, related_name='cart_items')
    product = models.ForeignKey(Products, on_delete=models.CASCADE, null=True, blank=True, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    # Prix unitaire FIGÉ au moment de l'ajout au panier
    unit_price = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF', null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            ('user', 'variant'),
            ('user', 'product'),
        )

    @property
    def line_total(self):
        """Calcule le total de cette ligne (unit_price * quantity)"""
        if self.unit_price:
            return self.unit_price * self.quantity
        return 0

    def get_current_price(self):
        if self.variant:
            return self.variant.get_unit_price(self.quantity)
        if self.product:
            return self.product.get_unit_price(self.quantity)
        return 0

    def __str__(self):
        if not self.variant:
            if self.product:
                return f"{self.product.name} x {self.quantity} ({self.user.email})"
            return f"Article sans variante x {self.quantity} ({self.user.email})"

        return f"{self.variant.product.name} x {self.quantity} ({self.user.email})"

