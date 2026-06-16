from django.db import models

# Create your models here.

class PaymentMethod(models.Model):
    value = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='image/payment', null=True)

    def __str__(self):
        return self.name