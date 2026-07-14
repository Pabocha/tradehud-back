from django.db import models
from django.contrib.auth import get_user_model
from apps.accounts.models import SellerAccount
from django_countries.fields import CountryField
from apps.categories.models import Categories

User = get_user_model()



class Shops(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(SellerAccount, on_delete=models.CASCADE, related_name='shops')
    email_contact = models.EmailField(unique=True)
    description = models.TextField(blank=True, null=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    country_origin = CountryField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    total_products = models.IntegerField(default=0)
    total_orders = models.IntegerField(default=0)
    delivery_conditions = models.TextField(blank=True, null=True)
    delivery_time_estimate = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: 2-5 jours ouvrables")
    free_shipping = models.BooleanField(default=False)
    return_policy = models.TextField(blank=True, null=True)
    categories = models.ManyToManyField('categories.Categories', blank=True)
    status = models.CharField(max_length=50, choices=[('active', 'Active'), ('suspended', 'Suspended'), ('inactive', 'inactive')], default='inactive')
    is_deleted = models.BooleanField(default=False)  # soft delete
    payment_method = models.ManyToManyField('payments.PaymentMethod', blank=True)
    total_follow = models.PositiveSmallIntegerField(default=0)
    number_sale = models.PositiveSmallIntegerField(default=0)
    average_rating = models.FloatField(default=0.0)
    number_of_reviews = models.PositiveIntegerField(default=0)
    is_top_seller = models.BooleanField(default=False)
    is_verifted = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.name
    

class DocumentShop(models.Model):
    TYPE_DOCUMENT_CHOICES = [
        ('carte_identite', 'Carte d’identité'),
        ('passeport', 'Passeport'),
        ('permis', 'Permis de conduite'),
    ]

    shop = models.ForeignKey(Shops, on_delete=models.CASCADE, related_name='shops')
    type_document = models.CharField(max_length=50, choices=TYPE_DOCUMENT_CHOICES)
    image_document_recto = models.ImageField(upload_to='image_document', blank=True, null=True)
    image_document_verso = models.ImageField(upload_to='image_document', blank=True, null=True)
    commercial_register = models.CharField(max_length=100, blank=True, null=True)
    proof_of_address = models.ImageField(upload_to='image_document', blank=True, null=True)
    number_document = models.CharField(max_length=100, blank=True, null=True) 
    date_upload = models.DateTimeField(auto_now_add=True)


class ShopStatistics(models.Model):
    shop = models.ForeignKey(Shops, on_delete=models.CASCADE, related_name="statistics")
    date = models.DateField()

    # Ventes
    total_orders = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    products_sold = models.PositiveIntegerField(default=0)
    average_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Engagement clients
    new_followers = models.PositiveIntegerField(default=0)
    new_customers = models.PositiveIntegerField(default=0)
    repeat_customers = models.PositiveIntegerField(default=0)

    # Trafic
    visits = models.PositiveIntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # en %

    # Retours / annulations
    cancelled_orders = models.PositiveIntegerField(default=0)
    returned_products = models.PositiveIntegerField(default=0)

    # Produits vedettes
    best_selling_product = models.ForeignKey(
        "products.Products", null=True, blank=True, on_delete=models.SET_NULL, related_name="best_in_statistics"
    )

    # Catégorie la plus performante
    top_category = models.ForeignKey(
        "categories.Categories",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="top_in_statistics"
    )

    # Satisfaction & Réputation
    shop_average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    shop_number_of_reviews = models.PositiveIntegerField(default=0)

    # Inventaire
    products_low_stock = models.PositiveIntegerField(default=0)  # produits < 5 unités
    products_out_of_stock = models.PositiveIntegerField(default=0)  # produits en "unavailable"
    average_product_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Promotion & Sponsoring
    active_sponsored_products = models.PositiveIntegerField(default=0)

    # Trafic produits
    total_product_views = models.PositiveIntegerField(default=0)
    average_views_per_product = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Efficacité
    inventory_turnover_ratio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
