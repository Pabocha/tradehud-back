from django.db import models
from django.contrib.auth import get_user_model

# Create your models here.

User = get_user_model()

class Notifications(models.Model):

    NOTIFICATION_TYPES = [
        ('order', 'Commande'),
        ('promo', 'Promotion'),
        ('message', 'Message'),
        ('delivery', 'Livraison'),
        ('product', 'Produit'),
        ('support', 'Support'),
        ('account', 'Compte'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.title[:30]}"
    
