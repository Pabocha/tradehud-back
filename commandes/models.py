from django.db import models
from django.contrib.auth import get_user_model
from produits.models import Products
import uuid
from decimal import Decimal

User = get_user_model()

# Create your models here.


class Orders(models.Model):

    CHOICES_STATUS = [
        ('pending', 'En attente'), 
        ('processing', 'En traitement'), 
        ('shipped', 'Expédiée'), 
        ('in_transit', 'En cours de livraison'),
        ('delivered', 'Livrée'), 
        ('cancelled', 'Annulée')
        ]
    
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    order_date = models.DateTimeField(auto_now_add=True)
    delivery_address = models.TextField()
    total_amount = models.DecimalField(max_digits=15, decimal_places=2)
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=50, choices=CHOICES_STATUS, default='pending')
    payment_method = models.ManyToManyField('ecom_app.PayementMethod')
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'En attente'),
            ('paid', 'Payée'),
            ('failed', 'Échouée'),
            ('refunded', 'Remboursée'),
        ],
        default='pending'
    )
    order_number = models.CharField(max_length=100, unique=True, blank=True, null=True)  # Peut être généré automatiquement
    payment_first_name = models.CharField(max_length=100, blank=True, null=True)
    payment_last_name = models.CharField(max_length=100, blank=True, null=True)
    payment_phone_number = models.CharField(max_length=30, blank=True, null=True)
    customer_note = models.TextField(blank=True, null=True)
    shipping_date = models.DateTimeField(blank=True, null=True)
    estimated_delivery_date = models.DateTimeField(blank=True, null=True)
    discount = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)
    applied_coupon = models.ForeignKey(
        'ecom_app.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    applied_coupon_code = models.CharField(max_length=50, blank=True, null=True)

    @property
    def total_order_price(self):
        total_lignes = sum(ligne.total_price for ligne in self.lignes_commande.all())
        total = total_lignes - (self.discount or 0)
        total += self.delivery_cost
        return total
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)  # 👈 ne calcule pas total_amount ici

    def update_stock(self):
        for ligne in self.lignes_commande.all():
            ligne.variant.stock_quantity -= ligne.quantity
            ligne.variant.save()
    
    def __str__(self):
        return self.order_number


class LigneCommande(models.Model):
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='lignes_commande')

    variant = models.ForeignKey(
        'produits.ProductVariant',
        on_delete=models.PROTECT, 
        null=True
    )
    product = models.ForeignKey(
        Products,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    shop = models.ForeignKey(
        'boutique.Shops',
        on_delete=models.PROTECT,
        null=True
    )

    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)

    @property
    def total_price(self):
        return self.unit_price * self.quantity

    def __str__(self):
        shop_name = self.shop.name if self.shop else 'Unknown'
        if self.variant:
            return f"{self.quantity} x {self.variant.product.name} (Boutique: {shop_name}) - Commande {self.order.order_number}"
        if self.product:
            return f"{self.quantity} x {self.product.name} (Boutique: {shop_name}) - Commande {self.order.order_number}"
        return f"{self.quantity} x Article (Boutique: {shop_name}) - Commande {self.order.order_number}"
