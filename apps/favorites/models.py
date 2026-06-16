from django.db import models
from django.contrib.auth import get_user_model

# Create your models here.

User = get_user_model()

class Favorites(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    product = models.ForeignKey('products.Products', on_delete=models.CASCADE, related_name='favorited_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['product']),
        ]
    def __str__(self):
        return f"{self.user.email} ♥ {self.product.name}"