from django.db import models

# Create your models here.


class PaymentMethod(models.Model):
    value = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to='image/payment', null=True)
    type = models.CharField(max_length=255, blank=True, default='')
    requires_phone = models.BooleanField(default=False)
    # AJOUT — Liste de codes ISO pays (ex: ['SN', 'CI']). Liste vide = méthode internationale (dispo partout).
    countries = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name