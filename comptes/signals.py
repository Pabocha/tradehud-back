from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete
from .models import SellerAccount

@receiver(post_save, sender=SellerAccount)
@receiver(post_delete, sender=SellerAccount)
def update_user_account(sender, instance, **kwargs):
    user = instance.user

    # Vérifiez le type de signal en utilisant les objets de signal directement
    if kwargs.get('signal') is post_save:
        # Logique pour post_save
        user.has_seller_account = True
        user.type_user = 'vendeur'
    elif kwargs.get('signal') is post_delete:
        # Logique pour post_delete
        user.has_seller_account = False
        user.type_user = 'client'

    user.save()