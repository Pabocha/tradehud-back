from rest_framework import viewsets, permissions, status, filters
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, Sum, F
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime, timedelta
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth

from .models import (
    Restaurant, RestaurantSchedule, MenuCategory, Meal,
    RestaurantOrder, OrderItem, Payment, RestaurantReview, RestaurantCategory, RestaurantSettings
)
from .serializers import (
    RestaurantScheduleUpdateSerializer, RestaurantSerializer, RestaurantListSerializer, RestaurantScheduleSerializer,
    MenuCategorySerializer, MealSerializer, RestaurantOrderSerializer,
    RestaurantOrderListSerializer, RestaurantOrderCreateSerializer,
    OrderItemSerializer, PaymentSerializer, RestaurantReviewSerializer,
    RestaurantCategorySerializer, RestaurantSettingsSerializer
)
from .models import MealReview
from .serializers import MealReviewSerializer
from .permissions import IsOwnerOrReadOnly, IsRestaurantOwner
from apps.comments.permissions import IsOwnerOrReadOnly

 
# ============================================
# 1ï¸âƒ£  RestaurantCategory ViewSet
# ============================================
class RestaurantCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Liste et dÃ©tails des catÃ©gories de restaurants
    Lecture seule pour tous les utilisateurs
    """
    queryset = RestaurantCategory.objects.filter(is_active=True)
    serializer_class = RestaurantCategorySerializer
    permission_classes = [permissions.AllowAny]


# ============================================
# 2ï¸âƒ£  Restaurant ViewSet (amÃ©liorÃ©)
# ============================================
class RestaurantViewSet(viewsets.ModelViewSet):
    """
    CRUD complet pour les restaurants avec recherche avancÃ©e
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['city', 'category', 'is_active']
    search_fields = ['name', 'description', 'city']
    ordering_fields = ['rating', 'created_at', 'name']
    ordering = ['-rating']

    def get_queryset(self):
        queryset = Restaurant.objects.filter(is_deleted=False).select_related(
            'owner', 'category'
        ).prefetch_related('categories', 'schedules')
        
        # Filtres personnalisÃ©s
        is_open = self.request.query_params.get('is_open')
        min_rating = self.request.query_params.get('min_rating')
        max_delivery_fee = self.request.query_params.get('max_delivery_fee')
        
        if is_open is not None:
            queryset = queryset.filter(is_open=is_open.lower() == 'true')
        
        if min_rating:
            try:
                queryset = queryset.filter(rating__gte=float(min_rating))
            except ValueError:
                pass
        
        if max_delivery_fee:
            try:
                queryset = queryset.filter(delivery_fee__lte=float(max_delivery_fee))
            except ValueError:
                pass
        
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return RestaurantListSerializer
        return RestaurantSerializer

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @action(detail=True, methods=['get'])
    def menu(self, request, pk=None):
        """Retourne le menu complet du restaurant avec les plats disponibles"""
        restaurant = self.get_object()
        categories = restaurant.categories.filter(
            is_active=True
        ).prefetch_related('meals').order_by('order')
        
        serializer = MenuCategorySerializer(categories, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """Retourne les avis du restaurant avec pagination"""
        restaurant = self.get_object()
        reviews = restaurant.reviews.select_related('user').order_by('-created_at')
        
        # Statistiques des avis
        stats = reviews.aggregate(
            total=Count('id'),
            average=Avg('rating'),
            five_stars=Count('id', filter=Q(rating=5)),
            four_stars=Count('id', filter=Q(rating=4)),
            three_stars=Count('id', filter=Q(rating=3)),
            two_stars=Count('id', filter=Q(rating=2)),
            one_star=Count('id', filter=Q(rating=1)),
        )
        
        page = self.paginate_queryset(reviews)
        if page is not None:
            serializer = RestaurantReviewSerializer(page, many=True)
            return self.get_paginated_response({
                'stats': stats,
                'reviews': serializer.data
            })
        
        serializer = RestaurantReviewSerializer(reviews, many=True)
        return Response({
            'stats': stats,
            'reviews': serializer.data
        })

    @action(detail=True, methods=['get'])
    def popular_meals(self, request, pk=None):
        """Retourne les plats les plus commandÃ©s du restaurant"""
        restaurant = self.get_object()
        meals = Meal.objects.filter(
            category__restaurant=restaurant,
            is_available=True
        ).order_by('-total_orders')[:10]
        
        serializer = MealSerializer(meals, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def schedule(self, request, pk=None):
        restaurant = self.get_object()
        schedules = RestaurantSchedule.objects.filter(restaurant=restaurant)
        serializer = RestaurantScheduleSerializer(schedules, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=['post'], permission_classes=[IsRestaurantOwner])
    def toggle_status(self, request, pk=None):
        """Ouvrir/Fermer le restaurant"""
        restaurant = self.get_object()
        restaurant.is_open = not restaurant.is_open
        restaurant.save(update_fields=['is_open'])
        
        return Response({
            'message': f"Restaurant {'ouvert' if restaurant.is_open else 'fermÃ©'}",
            'is_open': restaurant.is_open
        })

    @action(detail=False, methods=['get'])
    def my_restaurants(self, request):
        """Liste des restaurants de l'utilisateur connectÃ©"""
        restaurants = self.get_queryset().filter(owner=request.user)
        serializer = self.get_serializer(restaurants, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """Statistiques du restaurant (pour le propriÃ©taire)"""
        restaurant = self.get_object()
        self.check_object_permissions(request, restaurant)
        
        # PÃ©riode (30 derniers jours par dÃ©faut)
        days = int(request.query_params.get('days', 30))
        start_date = datetime.now() - timedelta(days=days)
        
        orders = restaurant.orders.filter(created_at__gte=start_date)
        
        stats = {
            'total_orders': orders.count(),
            'completed_orders': orders.filter(status='completed').count(),
            'cancelled_orders': orders.filter(status='cancelled').count(),
            'total_revenue': orders.filter(
                status='completed'
            ).aggregate(Sum('total_price'))['total_price__sum'] or 0,
            'average_order_value': orders.filter(
                status='completed'
            ).aggregate(Avg('total_price'))['total_price__avg'] or 0,
            'total_reviews': restaurant.reviews.count(),
            'average_rating': restaurant.rating,
        }
        
        return Response(stats)
    @action(detail=True, methods=['get', 'put', 'patch'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def setting(self, request, pk=None):
        """
        GET: RÃ©cupÃ©rer les paramÃ¨tres
        PUT/PATCH: Mettre Ã  jour les paramÃ¨tres
        """
        restaurant = self.get_object()
        
        # CrÃ©er les paramÃ¨tres s'ils n'existent pas
        settings, created = RestaurantSettings.objects.get_or_create(
            restaurant=restaurant
        )
        
        if request.method == 'GET':
            serializer = RestaurantSettingsSerializer(settings)
            return Response(serializer.data)
        
        # Mise Ã  jour
        serializer = RestaurantSettingsSerializer(
            settings, 
            data=request.data, 
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=True, methods=['get'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def schedules(self, request, pk=None):
        """RÃ©cupÃ©rer tous les horaires du restaurant"""
        restaurant = self.get_object()
        schedules = RestaurantSchedule.objects.filter(restaurant=restaurant)
        serializer = RestaurantScheduleUpdateSerializer(schedules, many=True)
        return Response(serializer.data)
    
    
    @action(detail=True, methods=['put', 'patch'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner],
            url_path='schedules/(?P<day_of_week>[^/.]+)')
    def update_schedule(self, request, pk=None, day_of_week=None):
        """Mettre Ã  jour l'horaire d'un jour spÃ©cifique"""
        restaurant = self.get_object()
        
        # RÃ©cupÃ©rer ou crÃ©er l'horaire pour ce jour
        schedule, created = RestaurantSchedule.objects.get_or_create(
            restaurant=restaurant,
            day_of_week=day_of_week
        )
        
        serializer = RestaurantScheduleUpdateSerializer(
            schedule,
            data=request.data,
            partial=True
        )
        print("\nðŸ“¥ DonnÃ©es reÃ§ues :", serializer.initial_data, "\n")
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            # ðŸ‘‡ Ceci affichera lâ€™erreur complÃ¨te dans ton terminal
            print("\nâŒ Serializer errors:", serializer.errors, "\n")
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=True, methods=['post'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def update_schedules_bulk(self, request, pk=None):
        """Mettre Ã  jour plusieurs horaires en une fois"""
        restaurant = self.get_object()
        schedules_data = request.data.get('schedules', [])
        
        if not schedules_data:
            return Response(
                {'error': 'Aucun horaire fourni'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        updated_schedules = []
        errors = []
        
        for schedule_data in schedules_data:
            day_of_week = schedule_data.get('day_of_week')
            
            if not day_of_week:
                errors.append({'error': 'day_of_week manquant'})
                continue
            
            schedule, created = RestaurantSchedule.objects.get_or_create(
                restaurant=restaurant,
                day_of_week=day_of_week
            )
            
            serializer = RestaurantScheduleUpdateSerializer(
                schedule,
                data=schedule_data,
                partial=True
            )
            
            if serializer.is_valid():
                serializer.save()
                updated_schedules.append(serializer.data)
            else:
                errors.append({
                    'day': day_of_week,
                    'errors': serializer.errors
                })
        
        response_data = {
            'updated': updated_schedules,
            'errors': errors
        }
        
        status_code = status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS
        return Response(response_data, status=status_code)
    
    
    @action(detail=True, methods=['patch'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def delivery_settings(self, request, pk=None):
        """Mettre Ã  jour les paramÃ¨tres de livraison"""
        restaurant = self.get_object()
        
        serializer = RestaurantDeliverySettingsSerializer(
            instance=restaurant,
            data=request.data,
            partial=True
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'ParamÃ¨tres de livraison mis Ã  jour',
                'data': serializer.data
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=True, methods=['post'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def deactivate(self, request, pk=None):
        """DÃ©sactiver temporairement le restaurant"""
        restaurant = self.get_object()
        restaurant.is_active = False
        restaurant.is_open = False
        restaurant.save(update_fields=['is_active', 'is_open'])
        
        return Response({
            'message': 'Restaurant dÃ©sactivÃ© avec succÃ¨s',
            'is_active': restaurant.is_active
        })
    
    
    @action(detail=True, methods=['post'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def activate(self, request, pk=None):
        """RÃ©activer le restaurant"""
        restaurant = self.get_object()
        restaurant.is_active = True
        restaurant.save(update_fields=['is_active'])
        
        return Response({
            'message': 'Restaurant activÃ© avec succÃ¨s',
            'is_active': restaurant.is_active
        })
    
    
    @action(detail=True, methods=['delete'], 
            permission_classes=[permissions.IsAuthenticated, IsRestaurantOwner])
    def soft_delete_restaurant(self, request, pk=None):
        """Suppression logique du restaurant"""
        restaurant = self.get_object()
        restaurant.soft_delete()
        
        return Response({
            'message': 'Restaurant supprimÃ© avec succÃ¨s'
        }, status=status.HTTP_204_NO_CONTENT)


# ============================================
# 3ï¸âƒ£  MenuCategory ViewSet
# ============================================
class MenuCategoryViewSet(viewsets.ModelViewSet):
    queryset = MenuCategory.objects.select_related('restaurant').prefetch_related('meals')
    serializer_class = MenuCategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['restaurant', 'is_active']

    def get_queryset(self):
        queryset = super().get_queryset()
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id, is_active=True)
        return queryset


# ============================================
# 4ï¸âƒ£  Meal ViewSet (amÃ©liorÃ©)
# ============================================
class MealViewSet(viewsets.ModelViewSet):
    queryset = Meal.objects.select_related('category__restaurant')
    serializer_class = MealSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_available', 'is_vegetarian', 'is_vegan', 'is_gluten_free']
    search_fields = ['name', 'description', 'ingredients']
    ordering_fields = ['price', 'total_orders', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filtre par restaurant
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            queryset = queryset.filter(category__restaurant_id=restaurant_id)
        
        # Filtre par prix
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        
        if min_price:
            try:
                queryset = queryset.filter(price__gte=float(min_price))
            except ValueError:
                pass
        
        if max_price:
            try:
                queryset = queryset.filter(price__lte=float(max_price))
            except ValueError:
                pass
        
        return queryset

    @action(detail=False, methods=['get'])
    def popular(self, request):
        """Les plats les plus populaires"""
        meals = self.get_queryset().filter(is_available=True).order_by('-total_orders')
        page = self.paginate_queryset(meals)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(meals, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def on_sale(self, request):
        """Les plats en promotion"""
        meals = self.get_queryset().filter(
            is_available=True,
            discount_price__isnull=False
        ).order_by('-created_at')
        serializer = self.get_serializer(meals, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=['get'], url_path='detail')
    def meal_detail(self, request, pk=None):
        """Détail complet d'un plat avec infos restaurant et menu"""
        meal = self.get_object()
        restaurant = meal.category.restaurant

        menu_categories = MenuCategory.objects.filter(
            restaurant=restaurant,
            is_active=True
        ).prefetch_related('meals')

        related_meals = Meal.objects.filter(
            category__restaurant=restaurant,
            is_available=True
        ).exclude(id=meal.id).order_by('-total_orders')[:8]

        return Response({
            'meal': MealSerializer(meal, context={'request': request}).data,
            'restaurant': RestaurantListSerializer(restaurant, context={'request': request}).data,
            'menu_categories': MenuCategorySerializer(menu_categories, many=True, context={'request': request}).data,
            'related_meals': MealSerializer(related_meals, many=True, context={'request': request}).data,
        })

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        """
        Recherche de plats.
        Param: q (string)
        """
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response({'error': 'Query string \"q\" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        queryset = (
            self.get_queryset()
            .filter(is_available=True)
            .filter(
                Q(name__icontains=query) |
                Q(description__icontains=query) |
                Q(ingredients__icontains=query)
            )
            .order_by('-total_orders', 'name')
        )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# ============================================
# 5ï¸âƒ£  RestaurantOrder ViewSet (amÃ©liorÃ©)
# ============================================
class RestaurantOrderViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'restaurant']
    ordering_fields = ['created_at', 'total_price']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        queryset = RestaurantOrder.objects.select_related(
            'restaurant', 'customer', 'payment'
        ).prefetch_related('items__meal')
        
        if user.is_staff:
            return queryset
        
        # Les clients voient leurs commandes
        # Les propriÃ©taires de restaurants voient les commandes de leurs restaurants
        return queryset.filter(
            Q(customer=user) | Q(restaurant__owner=user)
        ).distinct()

    def get_serializer_class(self):
        if self.action == 'create':
            return RestaurantOrderCreateSerializer
        elif self.action == 'list':
            return RestaurantOrderListSerializer
        return RestaurantOrderSerializer

    def perform_create(self, serializer):
        order = serializer.save(customer=self.request.user)
        
        # CrÃ©er le paiement associÃ© (idempotent)
        Payment.objects.get_or_create(
            order=order,
            defaults={
                'amount': order.total_price,
                'status': 'pending',
            }
        )

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """Modifier le statut de la commande (propriÃ©taire uniquement)"""
        order = self.get_object()
        
        # VÃ©rifier que l'utilisateur est le propriÃ©taire du restaurant
        if order.restaurant.owner != request.user and not request.user.is_staff:
            return Response(
                {'error': "Vous n'avez pas la permission de modifier cette commande"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        new_status = request.data.get('status')
        
        if new_status not in dict(RestaurantOrder.STATUS_CHOICES):
            return Response(
                {'error': "Statut invalide"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # VÃ©rifier la logique de transition de statut
        valid_transitions = {
            'pending': ['accepted', 'cancelled'],
            'accepted': ['preparing', 'cancelled'],
            'preparing': ['ready', 'cancelled'],
            'ready': ['on_delivery', 'completed'],
            'on_delivery': ['completed'],
        }
        
        if order.status in valid_transitions:
            if new_status not in valid_transitions[order.status]:
                return Response(
                    {'error': f"Transition de {order.status} vers {new_status} non autorisÃ©e"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        order.status = new_status
        
        # Enregistrer l'heure de livraison si complÃ©tÃ©e
        if new_status == 'completed':
            order.actual_delivery_time = datetime.now()
        
        order.save()
        
        serializer = RestaurantOrderSerializer(order)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Annuler une commande"""
        order = self.get_object()
        
        # VÃ©rifier que l'utilisateur peut annuler
        if order.customer != request.user and order.restaurant.owner != request.user:
            return Response(
                {'error': "Vous ne pouvez pas annuler cette commande"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # On ne peut annuler que les commandes en attente ou acceptÃ©es
        if order.status not in ['pending', 'accepted']:
            return Response(
                {'error': f"Impossible d'annuler une commande avec le statut {order.status}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        order.status = 'cancelled'
        order.save()
        
        serializer = RestaurantOrderSerializer(order)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_orders(self, request):
        """Commandes de l'utilisateur connectÃ©"""
        orders = self.get_queryset().filter(customer=request.user)
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(orders, many=True)
        # print(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def restaurant_orders(self, request):
        """Commandes des restaurants de l'utilisateur"""
        restaurant_id = request.query_params.get('restaurant')
        
        if restaurant_id:
            # VÃ©rifier que l'utilisateur est propriÃ©taire
            restaurant = get_object_or_404(Restaurant, id=restaurant_id)
            if restaurant.owner != request.user and not request.user.is_staff:
                return Response(
                    {'error': "AccÃ¨s non autorisÃ©"},
                    status=status.HTTP_403_FORBIDDEN
                )
            orders = self.get_queryset().filter(restaurant_id=restaurant_id)
        else:
            orders = self.get_queryset().filter(restaurant__owner=request.user)
        
        page = self.paginate_queryset(orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(orders, many=True)
        return Response(serializer.data)


# ============================================
# 6ï¸âƒ£  Payment ViewSet
# ============================================
class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.select_related('order')
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Payment.objects.all()
        return Payment.objects.filter(
            Q(order__customer=user) | Q(order__restaurant__owner=user)
        )

    @action(detail=True, methods=['post'])
    def confirm_payment(self, request, pk=None):
        """Confirmer un paiement"""
        payment = self.get_object()
        
        if payment.status != 'pending':
            return Response(
                {'error': "Ce paiement a dÃ©jÃ  Ã©tÃ© traitÃ©"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        transaction_id = request.data.get('transaction_id')
        
        payment.status = 'paid'
        payment.transaction_id = transaction_id
        payment.save()
        
        serializer = self.get_serializer(payment)
        return Response(serializer.data)


# ============================================
#   RestaurantReview ViewSet
# ============================================
class RestaurantReviewViewSet(viewsets.ModelViewSet):
    queryset = RestaurantReview.objects.select_related('user', 'restaurant', 'order')
    serializer_class = RestaurantReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['restaurant', 'rating']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        instance = serializer.save()
        if not instance.is_edited:
            instance.is_edited = True
            instance.save()

    def get_queryset(self):
        queryset = super().get_queryset()
        restaurant_id = self.request.query_params.get('restaurant')
        if restaurant_id:
            queryset = queryset.filter(restaurant_id=restaurant_id)
        return queryset


class MealReviewViewSet(viewsets.ModelViewSet):
    queryset = MealReview.objects.select_related('user', 'meal', 'order_item')
    serializer_class = MealReviewSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['meal', 'rating']
    ordering = ['-created_at']

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        meal_id = self.request.query_params.get('meal')
        if meal_id:
            queryset = queryset.filter(meal_id=meal_id)
        return queryset
    @action(detail=False, methods=['get'])
    def restaurant(self, request):
        """Les avis des repas d'un restaurant avec pagination"""
        queryset = self.get_queryset()
        
        # Filtrer par restaurant
        restaurant_id = request.query_params.get('restaurant_id')
        if restaurant_id:
            queryset = queryset.filter(meal__category__restaurant_id=restaurant_id)
        
        queryset = queryset.order_by('-rating', '-created_at')
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# ============================================
# 8ï¸âƒ£  OrderItem ViewSet
# ============================================
class OrderItemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrderItem.objects.select_related('order', 'meal')
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return OrderItem.objects.filter(
            Q(order__customer=user) | Q(order__restaurant__owner=user)
        )

# ============================================
# 1ï¸âƒ£  RestaurantStatistics ViewSet 
# ============================================
class RestaurantStatisticsViewSet(viewsets.ViewSet):
    """
    ViewSet dédié aux statistiques du restaurant
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_restaurant(self, request, pk):
        """Récupère le restaurant et vérifie les permissions"""
        from .models import Restaurant
        restaurant = Restaurant.objects.get(pk=pk, owner=request.user)
        return restaurant

    def get_date_range(self, request):
        """Calcule la période basée sur le paramètre period"""
        period = request.query_params.get('period', '7J')
        now = datetime.now()
        
        if period == '7J':
            start_date = now - timedelta(days=7)
            previous_start = start_date - timedelta(days=7)
        elif period == '30J':
            start_date = now - timedelta(days=30)
            previous_start = start_date - timedelta(days=30)
        elif period == '3M':
            start_date = now - timedelta(days=90)
            previous_start = start_date - timedelta(days=90)
        elif period == 'AnnÃ©e':
            start_date = now - timedelta(days=365)
            previous_start = start_date - timedelta(days=365)
        else:
            start_date = now - timedelta(days=7)
            previous_start = start_date - timedelta(days=7)
        
        return start_date, previous_start, period

    @action(detail=True, methods=['get'])
    def overview(self, request, pk=None):
        """Statistiques principales du restaurant"""
        restaurant = self.get_restaurant(request, pk)
        start_date, previous_start, period = self.get_date_range(request)
        
        # Commandes de la pÃ©riode actuelle
        current_orders = restaurant.orders.filter(
            created_at__gte=start_date
        )
        
        # Commandes de la pÃ©riode prÃ©cÃ©dente (pour comparaison)
        previous_orders = restaurant.orders.filter(
            created_at__gte=previous_start,
            created_at__lt=start_date
        )
        
        # Calculs pÃ©riode actuelle
        current_stats = current_orders.aggregate(
            total_orders=Count('id'),
            completed_orders=Count('id', filter=Q(status='completed')),
            total_revenue=Sum('total_price', filter=Q(status='completed')),
            avg_order_value=Avg('total_price', filter=Q(status='completed'))
        )
        
        # Calculs pÃ©riode prÃ©cÃ©dente
        previous_stats = previous_orders.aggregate(
            total_orders=Count('id'),
            total_revenue=Sum('total_price', filter=Q(status='completed'))
        )
        
        # Calcul des pourcentages de changement
        def calculate_change(current, previous):
            if not previous or previous == 0:
                return 100 if current > 0 else 0
            return round(((current - previous) / previous) * 100, 1)
        
        orders_change = calculate_change(
            current_stats['total_orders'] or 0,
            previous_stats['total_orders'] or 0
        )
        
        revenue_change = calculate_change(
            float(current_stats['total_revenue'] or 0),
            float(previous_stats['total_revenue'] or 0)
        )
        
        return Response({
            'period': period,
            'orders': {
                'total': current_stats['total_orders'] or 0,
                'completed': current_stats['completed_orders'] or 0,
                'change': orders_change
            },
            'revenue': {
                'total': float(current_stats['total_revenue'] or 0),
                'change': revenue_change,
                'average_order': float(current_stats['avg_order_value'] or 0)
            },
            'rating': {
                'average': float(restaurant.rating),
                'total_reviews': restaurant.total_reviews
            }
        })

    @action(detail=True, methods=['get'])
    def sales_chart(self, request, pk=None):
        """Données pour le graphique d'évolution des ventes"""
        restaurant = self.get_restaurant(request, pk)
        start_date, _, period = self.get_date_range(request)
        
        orders = restaurant.orders.filter(
            created_at__gte=start_date,
            status='completed'
        )
        
        # Grouper par jour/semaine/mois selon la pÃ©riode
        if period == '7J':
            trunc_func = TruncDate
            date_format = '%Y-%m-%d'
        elif period == '30J':
            trunc_func = TruncDate
            date_format = '%Y-%m-%d'
        elif period == '3M':
            trunc_func = TruncWeek
            date_format = '%Y-%W'
        else:  # AnnÃ©e
            trunc_func = TruncMonth
            date_format = '%Y-%m'
        
        sales_data = orders.annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            revenue=Sum('total_price'),
            orders_count=Count('id')
        ).order_by('period')
        
        return Response({
            'period': period,
            'data': list(sales_data)
        })

    @action(detail=True, methods=['get'])
    def category_distribution(self, request, pk=None):
        """Répartition des commandes par catégorie de plats"""
        restaurant = self.get_restaurant(request, pk)
        start_date, _, _ = self.get_date_range(request)
        
        from .models import OrderItem
        
        category_stats = OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__created_at__gte=start_date,
            order__status='completed'
        ).values(
            category_name=F('meal__category__name')
        ).annotate(
            orders_count=Sum('quantity'),
            revenue=Sum(F('quantity') * F('price'))
        ).order_by('-orders_count')[:10]
        
        return Response(list(category_stats))

    @action(detail=True, methods=['get'])
    def top_meals(self, request, pk=None):
        """Plats les plus vendus avec détails"""
        restaurant = self.get_restaurant(request, pk)
        start_date, _, _ = self.get_date_range(request)
        
        from .models import OrderItem
        
        # Filtrer pour exclure les OrderItems sans meal et construire la requÃªte
        # Utiliser directement les champs de relation dans values() pour Ã©viter les conflits
        top_meals = OrderItem.objects.filter(
            order__restaurant=restaurant,
            order__created_at__gte=start_date,
            order__status='completed',
            meal__isnull=False  # Exclure les OrderItems sans meal
        ).select_related('meal').values(
            'meal__id',
            'meal__name',
            'meal__image'
        ).annotate(
            orders_count=Sum('quantity'),
            revenue=Sum(F('quantity') * F('price'))
        ).order_by('-orders_count')[:10]
        
        # Convertir le QuerySet en liste et construire les URLs complÃ¨tes pour les images
        result = []
        for item in top_meals:
            meal_image = item.get('meal__image')
            # Construire l'URL absolue de l'image si elle existe
            if meal_image:
                try:
                    # meal_image est dÃ©jÃ  une string (nom du fichier) avec .values()
                    meal_image_url = request.build_absolute_uri('/media/' + str(meal_image))
                except Exception:
                    meal_image_url = None
            else:
                meal_image_url = None
            
            result.append({
                'meal_id': item.get('meal__id'),
                'meal_name': item.get('meal__name'),
                'meal_image': meal_image_url,
                'orders_count': item.get('orders_count', 0),
                'revenue': float(item.get('revenue', 0))
            })
        
        return Response(result)

    @action(detail=True, methods=['get'])
    def recent_reviews(self, request, pk=None):
        """Avis récents du restaurant"""
        restaurant = self.get_restaurant(request, pk)
        
        reviews = restaurant.reviews.select_related('user').order_by('-created_at')[:10]
        
        from .serializers import RestaurantReviewSerializer
        serializer = RestaurantReviewSerializer(reviews, many=True)
        
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def orders_status(self, request, pk=None):
        """Répartition des commandes par statut"""
        restaurant = self.get_restaurant(request, pk)
        start_date, _, _ = self.get_date_range(request)
        
        status_stats = restaurant.orders.filter(
            created_at__gte=start_date
        ).values('status').annotate(
            count=Count('id')
        ).order_by('-count')
        
        return Response(list(status_stats))

    @action(detail=True, methods=['get'])
    def peak_hours(self, request, pk=None):
        """Heures de pointe pour les commandes"""
        restaurant = self.get_restaurant(request, pk)
        start_date, _, _ = self.get_date_range(request)
        
        from django.db.models.functions import ExtractHour
        
        hourly_stats = restaurant.orders.filter(
            created_at__gte=start_date
        ).annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('hour')
        
        return Response(list(hourly_stats))

    @action(detail=True, methods=['get'])
    def payment_methods(self, request, pk=None):
        """Répartition par méthode de paiement"""
        restaurant = self.get_restaurant(request, pk)
        start_date, _, _ = self.get_date_range(request)
        
        payment_stats = restaurant.orders.filter(
            created_at__gte=start_date,
            status='completed'
        ).values('payment_method').annotate(
            count=Count('id'),
            revenue=Sum('total_price')
        )
        
        return Response(list(payment_stats))




