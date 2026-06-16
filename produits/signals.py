from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import models
from .models import Products, GalerieImages
# from commentaires.models import Comments
# from .models import Products

# @receiver(post_save, sender=Comments)
# def update_notice(sender, instance, created, **kwargs):
#     if created:
#         produit = instance.product  # Assure-toi que le modèle Comment a bien une relation ForeignKey vers Product
#         commentaires = produit.comments.all()  # Utilisation de related_name='comments' dans Product
#         # Mettre à jour le nombre de commentaires
#         produit.numbers_reviews = commentaires.count()
#         produit.average_stars = commentaires.aggregate(models.Avg('numbers_stars'))['numbers_stars__avg'] or 0
#         produit.save()

@receiver(post_save, sender=Products)
@receiver(post_delete, sender=Products)
def update_total_products(sender, instance, **kwargs):
    shop = instance.shop
    if shop:
        shop.total_products = Products.objects.filter(shop=shop).count()
        shop.save()

@receiver(post_delete, sender=GalerieImages)
def delete_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)
