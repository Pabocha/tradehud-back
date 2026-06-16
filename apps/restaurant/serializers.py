from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Restaurant, RestaurantOrder, RestaurantReview, RestaurantSchedule, 
    OrderItem, Payment, Meal, MenuCategory, RestaurantCategory, RestaurantSettings
)
from .models import MealReview
from ecommerce.validators import validate_image_file

User = get_user_model()


# ============================================
# Serializers imbriqués pour éviter les fields='__all__'
# ============================================

class UserBasicSerializer(serializers.ModelSerializer):
    """Informations basiques de l'utilisateur"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class RestaurantCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantCategory
        fields = ['id', 'name', 'description', 'icon', 'is_active']


class RestaurantScheduleSerializer(serializers.ModelSerializer):
    day_display = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = RestaurantSchedule
        fields = ['id', 'day_of_week', 'day_display', 'opening_time', 'closing_time', 'is_closed']

    def validate(self, data):
        if not data.get('is_closed'):
            if not data.get('opening_time') or not data.get('closing_time'):
                raise serializers.ValidationError(
                    "Les horaires d'ouverture et de fermeture sont obligatoires si le restaurant n'est pas fermé"
                )
            if data['opening_time'] >= data['closing_time']:
                raise serializers.ValidationError(
                    "L'heure d'ouverture doit être avant l'heure de fermeture"
                )
        return data


class MealSerializer(serializers.ModelSerializer):
    # Validate meal image size/type
    image = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_file])
    final_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    discount_percentage = serializers.IntegerField(read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    restaurant_name = serializers.CharField(source='category.restaurant.name', read_only=True)
    restaurant_id = serializers.IntegerField(source='category.restaurant.id', read_only=True)  # 👈 Ajouter
    
    class Meta:
        model = Meal
        fields = [
            'id', 'category', 'category_name', 'restaurant_name', 'restaurant_id', 'name', 'description',
            'price', 'discount_price', 'final_price', 'discount_percentage',
            'image', 'is_available', 'preparation_time', 'ingredients', 'calories',
            'is_vegetarian', 'is_vegan', 'is_gluten_free', 'allergens',
            'total_orders', 'rating', 'total_reviews', 'created_at'
        ]
        read_only_fields = ['id', 'total_orders', 'rating', 'total_reviews', 'created_at']

    def validate(self, data):
        if data.get('discount_price') and data.get('price'):
            if data['discount_price'] >= data['price']:
                raise serializers.ValidationError({
                    'discount_price': "Le prix réduit doit être inférieur au prix normal"
                })
        return data


class MenuCategorySerializer(serializers.ModelSerializer):
    meals = MealSerializer(many=True, read_only=True)
    meals_count = serializers.IntegerField(source='meals.count', read_only=True)
    
    class Meta:
        model = MenuCategory
        fields = ['id', 'restaurant', 'name', 'description', 'order', 'is_active', 'meals_count', 'meals']
        read_only_fields = ['id']


class RestaurantListSerializer(serializers.ModelSerializer):
    """Serializer pour la liste des restaurants (moins détaillé)"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    country = serializers.SerializerMethodField()
    
    # Validate logo/cover images
    logo = serializers.ImageField(required=False, validators=[validate_image_file])
    cover_image = serializers.ImageField(required=False, validators=[validate_image_file])

    class Meta:
        model = Restaurant
        fields = [
            'id', 'name', 'category', 'category_name', 'owner_name',
            'description', 'city', 'address', 'country', 'logo', 'cover_image',
            'is_open', 'rating', 'total_reviews',
            'minimum_order', 'average_preparation_time', 'is_active'
        ]
        read_only_fields = ['id', 'rating', 'total_reviews']

    def get_country(self, obj):
        return obj.country.name


class RestaurantSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour un restaurant"""
    category_details = RestaurantCategorySerializer(source='category', read_only=True)
    owner_details = UserBasicSerializer(source='owner', read_only=True)
    schedules = RestaurantScheduleSerializer(many=True, read_only=True)
    categories = MenuCategorySerializer(many=True, read_only=True)
    reviews_count = serializers.IntegerField(source='total_reviews', read_only=True)
    country = serializers.SerializerMethodField()
    
    class Meta:
        model = Restaurant
        fields = [
            'id', 'owner', 'owner_details', 'name', 'category', 'category_details',
            'description', 'address', 'city', 'country', 'latitude', 'longitude',
            'phone', 'email', 'logo', 'cover_image', 'is_open', 'rating',
            'reviews_count',  'minimum_order', 'average_preparation_time',
            'is_active', 'created_at', 'updated_at', 'schedules', 'categories'
        ]
        read_only_fields = ['id', 'owner', 'rating', 'reviews_count', 'created_at', 'updated_at']

    def get_country(self, obj):
        return obj.country.name

    def validate_phone(self, value):
        """Validation du numéro de téléphone"""
        if value and not value.replace('+', '').replace(' ', '').isdigit():
            raise serializers.ValidationError("Numéro de téléphone invalide")
        return value


class RestaurantReviewSerializer(serializers.ModelSerializer):
    user_details = UserBasicSerializer(source='user', read_only=True)
    restaurant_name = serializers.CharField(source='apps.vendor.restaurant.name', read_only=True)
    
    class Meta:
        model = RestaurantReview
        fields = [
            'id', 'restaurant', 'restaurant_name', 'user', 'user_details',
            'rating', 'comment', 'order', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Le rating doit être entre 1 et 5")
        return value

    def validate(self, data):
        # Empêcher un utilisateur de laisser plusieurs avis pour le même restaurant
        user = self.context['request'].user
        restaurant = data.get('restaurant')

        qs = RestaurantReview.objects.filter(user=user, restaurant=restaurant)
        # Exclude the current instance when updating
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "Vous avez déjà laissé un avis pour ce restaurant."
            )
        return data


class MealReviewSerializer(serializers.ModelSerializer):
    user_details = UserBasicSerializer(source='user', read_only=True)
    meal_name = serializers.CharField(source='meal.name', read_only=True)

    class Meta:
        model = MealReview
        fields = [
            'id', 'meal', 'meal_name', 'user', 'user_details',
            'rating', 'comment', 'order_item', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Le rating doit être entre 1 et 5")
        return value

    def validate(self, data):
        user = self.context['request'].user
        meal = data.get('meal')
        order_item = data.get('order_item')
        if order_item and MealReview.objects.filter(
            user=user, meal=meal, order_item=order_item
        ).exists():
            raise serializers.ValidationError("Vous avez déjà laissé un avis pour cet item de commande")
        return data


class OrderItemSerializer(serializers.ModelSerializer):
    meal_details = MealSerializer(source='meal', read_only=True)
    meal_name = serializers.CharField(source='meal.name', read_only=True)
    
    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'meal', 'meal_name', 'meal_details',
            'quantity', 'price', 'total', 'special_requests'
        ]
        read_only_fields = ['id', 'total']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("La quantité doit être au moins 1")
        return value


class OrderItemCreateSerializer(serializers.ModelSerializer):
    """Serializer pour la création d'items (plus simple)"""
    class Meta:
        model = OrderItem
        fields = ['meal', 'quantity', 'special_requests']

    def validate(self, data):
        meal = data.get('meal')
        if not meal.is_available:
            raise serializers.ValidationError(f"Le plat {meal.name} n'est plus disponible")
        return data


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'order_number', 'amount', 'status', 'status_display',
            'transaction_id', 'payment_date', 'refund_date', 'refund_reason'
        ]
        read_only_fields = ['id', 'payment_date']


class RestaurantOrderListSerializer(serializers.ModelSerializer):
    """Serializer pour la liste des commandes"""
    restaurant_name = serializers.CharField(source='apps.vendor.restaurant.name', read_only=True)
    customer_name = serializers.CharField(source='customer.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items_count = serializers.IntegerField(source='items.count', read_only=True)
    
    class Meta:
        model = RestaurantOrder
        fields = [
            'id', 'order_number', 'restaurant', 'restaurant_name',
            'customer', 'customer_name', 'status', 'status_display',
            'total_price', 'delivery_type', 'items_count', 'created_at'
        ]
        read_only_fields = ['id', 'order_number', 'created_at']


class RestaurantOrderSerializer(serializers.ModelSerializer):
    """Serializer détaillé pour une commande"""
    restaurant_details = RestaurantListSerializer(source='restaurant', read_only=True)
    customer_details = UserBasicSerializer(source='customer', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    payment = PaymentSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    delivery_type_display = serializers.CharField(source='get_delivery_type_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    
    class Meta:
        model = RestaurantOrder
        fields = [
            'id', 'order_number', 'restaurant', 'restaurant_details',
            'customer', 'customer_details', 'status', 'status_display',
            'subtotal', 'total_price',
            'payment_method', 'payment_method_display',
            'delivery_type', 'delivery_type_display',
            'delivery_address',  'special_instructions',
            'estimated_delivery_time', 'actual_delivery_time',
            'items', 'payment', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'order_number', 'customer', 'subtotal', 
            'total_price', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        # Vérifier que l'adresse est fournie pour une livraison
        if data.get('delivery_type') == 'delivery' and not data.get('delivery_address'):
            raise serializers.ValidationError({
                'delivery_address': "L'adresse de livraison est obligatoire pour une livraison"
            })
        
        # Vérifier que le restaurant est actif
        restaurant = data.get('restaurant')
        if restaurant and not restaurant.is_active:
            raise serializers.ValidationError({
                'restaurant': "Ce restaurant n'est pas actif actuellement"
            })
        
        return data


class RestaurantOrderCreateSerializer(serializers.ModelSerializer):
    """Serializer pour créer une commande avec items"""
    items = OrderItemCreateSerializer(many=True, write_only=True)

    
    class Meta:
        model = RestaurantOrder
        fields = [
            'restaurant', 'delivery_type', 'delivery_address', 
            'payment_method', 'special_instructions', 'items'
        ]

    def validate(self, data):
        print(data)
        items = data.get('items', [])
        if not items:
            raise serializers.ValidationError({
                'items': "La commande doit contenir au moins un plat"
            })
        
        # Vérifier que tous les plats appartiennent au même restaurant
        restaurant = data.get('restaurant')
        for item_data in items:
            meal = item_data['meal']
            if meal.category.restaurant != restaurant:
                raise serializers.ValidationError({
                    'items': f"Le plat {meal.name} n'appartient pas à ce restaurant"
                })
        
        # plus de contraintes de livraison
        
        return data

    def create(self, validated_data):
        print(validated_data)
        items_data = validated_data.pop('items')
        
        # Créer la commande
        order = RestaurantOrder.objects.create(**validated_data)
        
        # Ajouter les items
        for item_data in items_data:
            meal = item_data['meal']
            OrderItem.objects.create(
                order=order,
                meal=meal,
                quantity=item_data['quantity'],
                price=meal.final_price,
                special_requests=item_data.get('special_requests', '')
            )
        
        # Calculer le total
        order.calculate_total()
        
        return order
    

class RestaurantSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RestaurantSettings
        fields = [
            'id', 'restaurant', 'notify_new_orders', 'notify_reviews',
            'notify_promotions', 'notify_low_stock', 
            'auto_accept_orders', 'auto_close_when_busy', 'max_concurrent_orders',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'restaurant', 'created_at', 'updated_at']
    
    def validate_delivery_radius(self, value):
        if value < 1 or value > 50:
            raise serializers.ValidationError(
                "Le rayon de livraison doit être entre 1 et 50 km"
            )
        return value
    

class RestaurantScheduleUpdateSerializer(serializers.ModelSerializer):
    """Serializer pour mise à jour des horaires"""
    day_display = serializers.CharField(source='get_day_of_week_display', read_only=True)
    
    class Meta:
        model = RestaurantSchedule
        fields = [
            'id', 'day_of_week', 'day_display', 
            'opening_time', 'closing_time', 'is_closed'
        ]
        read_only_fields = ['id']
    
    def validate(self, data):
        # Récupérer l'instance existante (pour les PATCH)
        instance = self.instance
        
        # Déterminer la valeur finale de is_closed
        is_closed = data.get('is_closed', instance.is_closed if instance else False)
        
        if not is_closed:
            # Récupérer les valeurs finales (nouvelles ou existantes)
            opening_time = data.get('opening_time') or (instance.opening_time if instance else None)
            closing_time = data.get('closing_time') or (instance.closing_time if instance else None)
            
            # Vérifier que les deux horaires sont présents
            if not opening_time or not closing_time:
                raise serializers.ValidationError({
                    'opening_time': "Les horaires sont obligatoires si non fermé",
                    'closing_time': "Les horaires sont obligatoires si non fermé"
                })
            
            # Vérifier la cohérence des horaires
            if opening_time >= closing_time:
                raise serializers.ValidationError({
                    'opening_time': "L'heure d'ouverture doit être avant la fermeture"
                })
        
        return data


class RestaurantDeliverySettingsSerializer(serializers.Serializer):
    """Serializer pour mise à jour des paramètres de livraison"""
    delivery_fee = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2,
        min_value=0
    )
    minimum_order = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0
    )
    delivery_radius = serializers.IntegerField(min_value=1, max_value=50)
    
    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance