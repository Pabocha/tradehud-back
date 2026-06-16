from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

# Create your models here.

class Contacts(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True, null=True)
    subject = models.CharField(max_length=255)
    message = models.TextField()

    class Meta:
        verbose_name = ('Contact')
        verbose_name_plural = ('Contacts')

    def __str__(self):
        return f"{self.user.first_name}-{self.status}"
