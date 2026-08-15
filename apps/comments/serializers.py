from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Ratings, ShopRatings

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email"]


class RatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Ratings
        fields = "__all__"
        read_only_fields = ["user"]

    def validate(self, data):
        user = self.context["request"].user
        product = data.get("product") or getattr(self.instance, "product", None)
        order_item = data.get("order_item") or getattr(self.instance, "order_item", None)

        if product is None:
            raise serializers.ValidationError("Le champ 'product' est requis.")
        if order_item is None:
            raise serializers.ValidationError("Le champ 'order_item' est requis.")

        # L'utilisateur ne peut commenter qu'une ligne de sa propre commande.
        if order_item.order.customer_id != user.id:
            raise serializers.ValidationError(
                "Vous ne pouvez commenter que les produits de vos propres commandes."
            )

        # AJOUT — Un commentaire n'est autorisé que lorsque la commande est livrée.
        if order_item.order.status != "delivered":
            raise serializers.ValidationError(
                "Vous ne pouvez commenter qu'une commande livrée."
            )

        # La ligne de commande doit correspondre au produit noté.
        if order_item.product_id and order_item.product_id != product.id:
            raise serializers.ValidationError(
                "La ligne de commande ne correspond pas au produit sélectionné."
            )
        if order_item.variant_id and order_item.variant.product_id != product.id:
            raise serializers.ValidationError(
                "La variante de la ligne de commande ne correspond pas au produit sélectionné."
            )

        existing = Ratings.objects.filter(
            user=user,
            product=product,
            order_item__order=order_item.order,
        )
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                "Vous avez deja commente ce produit dans cette commande."
            )
        return data

    def validate_rating(self, value):
        if value is None:
            return value
        if value < 1 or value > 5:
            raise serializers.ValidationError("La note doit etre comprise entre 1 et 5.")
        return value


class ShopRatingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = ShopRatings
        fields = "__all__"
        read_only_fields = ["user"]

    def validate(self, data):
        user = self.context["request"].user
        shop = data.get("shop") or getattr(self.instance, "shop", None)
        order = data.get("order") or getattr(self.instance, "order", None)

        if shop is None:
            raise serializers.ValidationError("Le champ 'shop' est requis.")
        if order is None:
            raise serializers.ValidationError("Le champ 'order' est requis.")

        # L'utilisateur ne peut commenter qu'une commande qui lui appartient.
        if order.customer_id != user.id:
            raise serializers.ValidationError(
                "Vous ne pouvez commenter que vos propres commandes."
            )

        # La commande doit contenir au moins une ligne de cette boutique.
        if not order.lignes_commande.filter(shop_id=shop.id).exists():
            raise serializers.ValidationError(
                "Cette commande ne contient aucun produit de la boutique selectionnee."
            )

        # Interdit au proprietaire de commenter sa propre boutique.
        if getattr(shop, "owner_id", None) and getattr(shop.owner, "user_id", None) == user.id:
            raise serializers.ValidationError(
                "Vous ne pouvez pas commenter votre propre boutique."
            )

        existing = ShopRatings.objects.filter(user=user, shop=shop)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("Vous avez deja commente cette boutique.")

        return data

    def validate_rating(self, value):
        if value is None:
            return value
        if value < 1 or value > 5:
            raise serializers.ValidationError("La note doit etre comprise entre 1 et 5.")
        return value
