from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Ratings, ShopRatings


@receiver([post_save, post_delete], sender=Ratings)
def update_product_average_rating(sender, instance, **kwargs):
    product = instance.product
    ratings = product.ratings.all()
    total = ratings.count()

    if total > 0:
        average = sum(r.rating for r in ratings) / total
    else:
        average = 0.0

    product.average_rating = round(average, 1)
    product.numbers_reviews = total
    product.save()

    # AJOUT — La note publique de la boutique est 100% dérivée des notes produits.
    if product.shop_id:
        from apps.shops.views import recompute_shop_rating
        recompute_shop_rating(product.shop)


@receiver([post_save, post_delete], sender=ShopRatings)
def update_shop_statistics_on_shop_rating_change(sender, instance, **kwargs):
    # Import local to avoid circular imports at app load.
    from apps.shops.views import recompute_shop_rating
    from apps.shops.models import ShopStatistics

    if not instance.shop_id:
        return
    average_rating, number_of_reviews = recompute_shop_rating(instance.shop)
    ShopStatistics.objects.update_or_create(
        shop=instance.shop,
        date=timezone.localdate(),
        defaults={
            'shop_average_rating': average_rating,
            'shop_number_of_reviews': number_of_reviews,
        },
    )
