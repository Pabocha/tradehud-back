from django.db import models
from django.contrib.auth import get_user_model
from apps.products.models import Products
import uuid
from djmoney.models.fields import MoneyField

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
    total_amount = MoneyField(max_digits=15, decimal_places=2, default_currency="XOF")
    delivery_cost = MoneyField(max_digits=10, decimal_places=2, default_currency="XOF")
    status = models.CharField(max_length=50, choices=CHOICES_STATUS, default='pending')
    payment_method = models.ManyToManyField('payments.PaymentMethod')
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
        'coupons.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    applied_coupon_code = models.CharField(max_length=50, blank=True, null=True)

    @property
    def total_order_price(self):
        total_lines = sum(line.total_price for line in self.order_lines.all())
        total = total_lines - (self.discount or 0)
        total += self.delivery_cost
        return total
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs) 

    def update_stock(self):
        for line in self.order_lines.all():
            line.variant.stock_quantity -= line.quantity
            line.variant.save()
    
    def __str__(self):
        return self.order_number


class OrderLine(models.Model):
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='order_lines')

    variant = models.ForeignKey(
        'products.ProductVariant',
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
        'shops.Shops',
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


class Quote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    shop = models.ForeignKey('shops.Shops', on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Brouillon"),
            ("sent", "Envoye"),
            ("countered", "Contre-proposition"),
            ("accepted", "Accepte"),
            ("rejected", "Refuse"),
            ("expired", "Expire"),
            ("converted", "Converti"),
        ],
        default="draft",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    payment_link_token = models.CharField(max_length=128, unique=True, null=True, blank=True)
    payment_link_expires_at = models.DateTimeField(null=True, blank=True)
    payment_link_sent_at = models.DateTimeField(null=True, blank=True)
    converted_order = models.ForeignKey(
        "orders.Orders",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_quotes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quote #{self.id} - {self.status}"

class QuoteLine(models.Model):
    quote = models.ForeignKey(Quote, related_name="lines", on_delete=models.CASCADE)
    product = models.ForeignKey(Products, on_delete=models.CASCADE, null=True, blank=True)
    variant = models.ForeignKey('products.ProductVariant', on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField()
    negotiated_price = MoneyField(max_digits=15, decimal_places=2, default_currency='XOF')
    remarks = models.TextField(blank=True, null=True)