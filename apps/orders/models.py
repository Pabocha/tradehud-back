from django.db import models
from django.contrib.auth import get_user_model
from apps.products.models import Products
import uuid
from djmoney.models.fields import MoneyField
from django_countries.fields import CountryField

User = get_user_model()

# Create your models here.


class Orders(models.Model):

    CHOICES_STATUS = [
        ('pending', 'En attente'), 
        ('processing', 'En traitement'), 
        ('deposited', 'Déposée en entrepôt'),
        ('shipped', 'Expédiée'), 
        ('in_transit', 'En cours de livraison'),
        ('delivered', 'Livrée'), 
        ('cancelled', 'Annulée'),
        ('returned', 'Retournée'),
        ('partially_returned', 'Partiellement retournée'),
        ]
    
    CHOICES_SHIPPING_METHOD = [
        ('standard', 'Livraison Standard'),
        ('express', 'Livraison Express'),
        ('pickup', 'Retrait en point relais / magasin'),
    ]

    CHOICES_TRANSPORT_MODE = [
        ('road', 'Route'),
        ('sea', 'Mer'),
        ('air', 'Air'),
    ]

    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    order_date = models.DateTimeField(auto_now_add=True)
    origin_address = models.ForeignKey(
        'accounts.Address', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='orders_placed'
    )

    # 2. Les champs historiques "figés" pour la livraison (Copie de sécurité)
    shipping_first_name = models.CharField(max_length=100)
    shipping_last_name = models.CharField(max_length=100)
    shipping_phone_number = models.CharField(max_length=30)
    shipping_street_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_state_region = models.CharField(max_length=100, blank=True, null=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True, null=True)
    shipping_country = CountryField(blank_label='(select country)')

    # 3. Informations de suivi et transporteur (Ajoutées précédemment)
    shipping_method = models.CharField(max_length=50, choices=CHOICES_SHIPPING_METHOD, default='standard', null=True, blank=True)
    transport_mode = models.CharField(
        max_length=10, choices=CHOICES_TRANSPORT_MODE, default='road',
        help_text="Mode de transport: route (domestique), mer ou air (international)"
    )
    carrier_name = models.CharField(max_length=100, blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    tracking_url = models.URLField(max_length=500, blank=True, null=True)
    delivery_notes = models.TextField(blank=True, null=True)

    total_amount = MoneyField(max_digits=15, decimal_places=2, default_currency="XOF")
    delivery_cost = MoneyField(max_digits=10, decimal_places=2, default_currency="XOF", default=0.00)
    status = models.CharField(max_length=50, choices=CHOICES_STATUS, default='pending')
    payment_method = models.ManyToManyField('payments.PaymentMethod')
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'En attente'),
            ('paid', 'Payée'),
            ('failed', 'Échouée'),
            ('refunded', 'Remboursée'),
            ('partially_refunded', 'Partiellement remboursée'),
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
    discount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    applied_coupon = models.ForeignKey(
        'coupons.Coupon',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    applied_coupon_code = models.CharField(max_length=50, blank=True, null=True)
    shipping_rate = models.ForeignKey(
        'shipping.ShippingRate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )

    @property
    def total_order_price(self):
        total_lines = sum(line.total_price for line in self.order_lines.all())
        total = total_lines - (self.discount or 0)
        total += self.delivery_cost
        return total
    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = str(uuid.uuid4())[:8].upper()
            
        # 2. Copie automatique des données de l'adresse d'origine (si présente et non encore copiée)
        # On vérifie "not self.pk" pour ne le faire qu'à la création de la commande
        if not self.pk and self.origin_address:
            self.shipping_first_name = self.origin_address.first_name
            self.shipping_last_name = self.origin_address.last_name
            self.shipping_phone_number = self.origin_address.phone_number
            self.shipping_street_address = self.origin_address.street_address
            self.shipping_city = self.origin_address.city
            self.shipping_state_region = self.origin_address.state_region
            self.shipping_postal_code = self.origin_address.postal_code
            self.shipping_country = self.origin_address.country
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
        null=True,
        blank = True,
        related_name='order_lines'
    )
    product = models.ForeignKey(
        Products,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='order_lines'
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


class ReturnRequest(models.Model):
    REASON_CHOICES = [
        ('defective', 'Produit défectueux'),
        ('wrong_item', 'Mauvais article reçu'),
        ('damaged', 'Article endommagé'),
        ('not_as_described', 'Ne correspond pas à la description'),
        ('changed_mind', 'Changement d\'avis'),
        ('other', 'Autre'),
    ]
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('approved', 'Approuvé'),
        ('rejected', 'Rejeté'),
        ('shipped_back', 'Renvoyé par le client'),
        ('received', 'Reçu par le vendeur'),
        ('completed', 'Terminé'),
        ('cancelled', 'Annulé par le client'),
    ]

    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='return_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    description = models.TextField(blank=True, null=True)
    staff_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Retour #{self.id} - Commande {self.order.order_number} - {self.status}"

    @property
    def total_refund_amount(self):
        return sum(item.refund_amount for item in self.items.all())


class ReturnItem(models.Model):
    return_request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name='items')
    order_line = models.ForeignKey(OrderLine, on_delete=models.CASCADE, related_name='return_items')
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=30, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ['return_request', 'order_line']

    def __str__(self):
        return f"{self.quantity}x {self.order_line} dans Retour #{self.return_request.id}"

    @property
    def refund_amount(self):
        return self.order_line.unit_price * self.quantity


class Refund(models.Model):
    METHOD_CHOICES = [
        ('original', 'Remboursement par la méthode originale'),
        ('bank_transfer', 'Virement bancaire'),
        ('mobile_money', 'Mobile Money'),
        ('store_credit', 'Crédit boutique'),
    ]
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En cours'),
        ('completed', 'Effectué'),
        ('failed', 'Échoué'),
    ]

    return_request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name='refunds')
    order = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='original')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_refunds'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Remboursement #{self.id} - {self.amount} - {self.status}"
