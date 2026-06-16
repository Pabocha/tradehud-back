from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Avg
from django_countries.fields import CountryField

User = settings.AUTH_USER_MODEL


class RestaurantCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    icon = models.ImageField(upload_to='restaurant_categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Catégorie de restaurant"
        verbose_name_plural = "Catégories de restaurants"
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'name']),
        ]

    def __str__(self):
        return self.name


class Restaurant(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='restaurants')
    name = models.CharField(max_length=255, db_index=True)
    category = models.ForeignKey(RestaurantCategory, on_delete=models.SET_NULL, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    country = CountryField(blank=True, null=True)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    logo = models.ImageField(upload_to='restaurants/logos/', blank=True, null=True)
    cover_image = models.ImageField(upload_to='restaurants/covers/', blank=True, null=True)
    is_open = models.BooleanField(default=True)
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)])
    total_reviews = models.PositiveIntegerField(default=0)
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, validators=[MinValueValidator(0.0)])
    average_preparation_time = models.PositiveIntegerField(default=30, help_text="Temps moyen en minutes")
    is_active = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)  # Soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Paramètres de notification
    notify_new_orders = models.BooleanField(default=True)
    notify_reviews = models.BooleanField(default=True)
    notify_promotions = models.BooleanField(default=False)

    class Meta:
        ordering = ['-rating', '-created_at']
        indexes = [
            models.Index(fields=['city', 'is_active', '-rating']),
            models.Index(fields=['is_active', 'is_deleted']),
            models.Index(fields=['owner', 'is_deleted']),
        ]

    def __str__(self):
        return self.name

    def update_rating(self):
        """Mise à jour automatique du rating"""
        stats = self.reviews.aggregate(
            avg_rating=Avg('rating'),
            total=models.Count('id')
        )
        self.rating = round(stats['avg_rating'] or 0, 2)
        self.total_reviews = stats['total']
        self.save(update_fields=['rating', 'total_reviews'])

    def soft_delete(self):
        """Suppression logique"""
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=['is_deleted', 'is_active'])


class RestaurantSchedule(models.Model):
    DAYS_OF_WEEK = [
        ('monday', 'Lundi'),
        ('tuesday', 'Mardi'),
        ('wednesday', 'Mercredi'),
        ('thursday', 'Jeudi'),
        ('friday', 'Vendredi'),
        ('saturday', 'Samedi'),
        ('sunday', 'Dimanche'),
    ]

    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.CharField(max_length=20, choices=DAYS_OF_WEEK)
    opening_time = models.TimeField(blank=True, null=True)
    closing_time = models.TimeField(blank=True, null=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('restaurant', 'day_of_week')
        ordering = ['day_of_week']

    def __str__(self):
        return f"{self.restaurant.name} - {self.get_day_of_week_display()}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.is_closed and self.opening_time and self.closing_time:
            if self.opening_time >= self.closing_time:
                raise ValidationError("L'heure d'ouverture doit être avant l'heure de fermeture")


class MenuCategory(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = "Menu Categories"
        indexes = [
            models.Index(fields=['restaurant', 'is_active', 'order']),
        ]

    def __str__(self):
        return f"{self.name} ({self.restaurant.name})"


class Meal(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name='meals', verbose_name='menu' \
    '')
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    discount_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, validators=[MinValueValidator(0)])
    image = models.ImageField(upload_to='meals/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    preparation_time = models.PositiveIntegerField(help_text="Temps de préparation en minutes", default=15)
    ingredients = models.TextField(blank=True, null=True)
    calories = models.PositiveIntegerField(blank=True, null=True)
    is_vegetarian = models.BooleanField(default=False)
    is_vegan = models.BooleanField(default=False)
    is_gluten_free = models.BooleanField(default=False)
    allergens = models.CharField(max_length=255, blank=True, null=True, help_text="Séparer par des virgules")
    total_orders = models.PositiveIntegerField(default=0)  # Popularité
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)])
    total_reviews = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_orders', 'name']
        indexes = [
            models.Index(fields=['category', 'is_available']),
            models.Index(fields=['-total_orders']),
        ]

    def __str__(self):
        return f"{self.name} - {self.category.restaurant.name}"

    @property
    def final_price(self):
        return self.discount_price if self.discount_price else self.price

    @property
    def discount_percentage(self):
        if self.discount_price and self.price > 0:
            return round(((self.price - self.discount_price) / self.price) * 100, 0)
        return 0

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.discount_price and self.discount_price >= self.price:
            raise ValidationError("Le prix réduit doit être inférieur au prix normal")

    def update_rating(self):
        """Mise à jour automatique du rating du plat"""
        stats = self.reviews.aggregate(
            avg_rating=Avg('rating'),
            total=models.Count('id')
        )
        self.rating = round(stats['avg_rating'] or 0, 2)
        self.total_reviews = stats['total']
        self.save(update_fields=['rating', 'total_reviews'])


class RestaurantReview(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='restaurant_reviews')
    rating = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, null=True)
    order = models.ForeignKey('RestaurantOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='review')
    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        # Un seul avis par restaurant par utilisateur (indépendamment de la commande)
        unique_together = ('restaurant', 'user')
        indexes = [
            models.Index(fields=['restaurant', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user} - {self.restaurant} ({self.rating}/5)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mise à jour automatique du rating du restaurant
        self.restaurant.update_rating()


class MealReview(models.Model):
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='meal_reviews')
    rating = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True, null=True)
    order_item = models.ForeignKey('OrderItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='meal_reviews')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('meal', 'user', 'order_item')
        indexes = [
            models.Index(fields=['meal', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user} - {self.meal} ({self.rating}/5)"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mise à jour automatique du rating du meal
        self.meal.update_rating()

    def delete(self, *args, **kwargs):
        meal = self.meal
        super().delete(*args, **kwargs)
        meal.update_rating()


class RestaurantOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('accepted', 'Acceptée'),
        ('preparing', 'En préparation'),
        ('ready', 'Prête'),
        ('on_delivery', 'En livraison'),
        ('completed', 'Terminée'),
        ('cancelled', 'Annulée'),
    ]

    DELIVERY_CHOICES = [
        ('pickup', 'À emporter'),
        ('delivery', 'Livraison'),
    ]

    PAYMENT_METHODS = [
        ('cash', 'Espèces'),
        ('card', 'Carte bancaire'),
        ('mobile_money', 'Mobile Money'),
    ]

    order_number = models.CharField(max_length=50, unique=True, editable=False)
    restaurant = models.ForeignKey(Restaurant, on_delete=models.PROTECT, related_name='orders')
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name='restaurant_orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_address = models.CharField(max_length=255, blank=True, null=True)
    delivery_type = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default='delivery')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash')
    special_instructions = models.TextField(blank=True, null=True)
    estimated_delivery_time = models.DateTimeField(blank=True, null=True)
    actual_delivery_time = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['restaurant', 'status', '-created_at']),
            models.Index(fields=['order_number']),
        ]

    def __str__(self):
        return f"Commande {self.order_number} - {self.restaurant.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            import uuid
            self.order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def calculate_total(self):
        """Calcul automatique du total"""
        self.subtotal = sum(item.total for item in self.items.all())
        self.total_price = self.subtotal
        self.save(update_fields=['subtotal', 'total_price'])


class OrderItem(models.Model):
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name='items')
    meal = models.ForeignKey(Meal, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    special_requests = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.meal.name} x{self.quantity}"

    def save(self, *args, **kwargs):
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)
        # Incrémenter la popularité du plat
        self.meal.total_orders += self.quantity
        self.meal.save(update_fields=['total_orders'])


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('paid', 'Payé'),
        ('failed', 'Échoué'),
        ('refunded', 'Remboursé'),
    ]

    order = models.OneToOneField(RestaurantOrder, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    refund_date = models.DateTimeField(blank=True, null=True)
    refund_reason = models.TextField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', '-payment_date']),
            models.Index(fields=['transaction_id']),
        ]

    def __str__(self):
        return f"Paiement #{self.id} - {self.status}"


class RestaurantSettings(models.Model):
    """Paramètres avancés du restaurant"""
    restaurant = models.OneToOneField(
        Restaurant, 
        on_delete=models.CASCADE, 
        related_name='settings'
    )
    
    # Notifications
    notify_new_orders = models.BooleanField(default=True)
    notify_reviews = models.BooleanField(default=True)
    notify_promotions = models.BooleanField(default=False)
    notify_low_stock = models.BooleanField(default=True)
    
    # (Supprimé) Champs liés à la livraison et tarification
    
    # Automatisation
    auto_accept_orders = models.BooleanField(default=False)
    auto_close_when_busy = models.BooleanField(default=False)
    max_concurrent_orders = models.PositiveIntegerField(default=10)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Paramètres du restaurant"
        verbose_name_plural = "Paramètres des restaurants"
    
    def __str__(self):
        return f"Paramètres - {self.restaurant.name}"