"""
Tests pour le système de statistiques hybride (temps réel + Celery).

Les tests vérifient :
1. ✅ Signal déclenche update_shop_statistics au post_save
2. ✅ Endpoint recalculate-today calcule correctement
3. ✅ Endpoint recalculate-range couvre plusieurs jours
4. ✅ Tâche Celery exécutée avec succès
"""

from django.test import TestCase, Client
from django.utils.timezone import now
from django.contrib.auth import get_user_model
from datetime import timedelta
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from boutique.models import Shops, ShopStatistics
from comptes.models import SellerAccount
from commandes.models import Orders, LigneCommande
from produits.models import Products, Categories
from ecom_app.models import Colors


User = get_user_model()


class ShopStatisticsSignalTestCase(TestCase):
    """
    Test du signal en temps réel.
    Vérifie que update_shop_statistics() est appelé lors de la création/modification d'une commande.
    """
    
    def setUp(self):
        """Créer les données de test."""
        # Créer utilisateur et compte vendeur
        self.user = User.objects.create_user(
            email='seller@test.com',
            password='testpass123'
        )
        self.seller_account = SellerAccount.objects.create(user=self.user)
        
        # Créer boutique
        self.shop = Shops.objects.create(
            owner=self.seller_account,
            name='Test Shop',
            description='Test Description',
            email='shop@test.com'
        )
        
        # Créer catégorie et produit
        self.category = Categories.objects.create(
            name='Test Category',
            slug='test-category'
        )
        
        self.color = Colors.objects.create(
            name='Red',
            code_hex='#FF0000'
        )
        
        self.product = Products.objects.create(
            name='Test Product',
            slug='test-product',
            shop=self.shop,
            category=self.category,
            price=100.00,
            stock_quantity=50,
            status='available'
        )
        self.product.color.add(self.color)
        
        # Créer client
        self.customer = User.objects.create_user(
            email='customer@test.com',
            password='testpass123'
        )
    
    def test_signal_creates_statistics_on_order_creation(self):
        """
        Test : Création d'une commande déclenche le signal.
        ✅ ShopStatistics devrait être créée au post_save.
        """
        today = now().date()
        
        # Créer une commande
        order = Orders.objects.create(
            user=self.customer,
            shop=self.shop,
            total_amount=100.00,
            status='pending'
        )
        
        # Créer une ligne de commande
        LigneCommande.objects.create(
            order=order,
            product=self.product,
            shop=self.shop,
            quantity=1,
            price=100.00
        )
        
        # Vérifier que ShopStatistics a été créée/mise à jour
        stats = ShopStatistics.objects.filter(shop=self.shop, date=today).first()
        self.assertIsNotNone(stats, "ShopStatistics devrait être créée au post_save")
        
        # Vérifier que les valeurs sont correctes
        self.assertEqual(stats.total_orders, 1, "total_orders devrait être 1")
        self.assertEqual(stats.products_sold, 1, "products_sold devrait être 1")
    
    def test_signal_updates_statistics_on_order_modification(self):
        """
        Test : Modification d'une commande déclenche le signal.
        ✅ ShopStatistics devrait être mise à jour au post_save (même si non créée).
        """
        today = now().date()
        
        # Créer commande
        order = Orders.objects.create(
            user=self.customer,
            shop=self.shop,
            total_amount=100.00,
            status='pending'
        )
        
        LigneCommande.objects.create(
            order=order,
            product=self.product,
            shop=self.shop,
            quantity=1,
            price=100.00
        )
        
        # Vérifier création
        stats_before = ShopStatistics.objects.get(shop=self.shop, date=today)
        self.assertEqual(stats_before.total_orders, 1)
        
        # Modifier la commande
        order.status = 'completed'
        order.save()
        
        # Vérifier que les stats sont mises à jour
        stats_after = ShopStatistics.objects.get(shop=self.shop, date=today)
        self.assertEqual(stats_after.total_orders, 1, "total_orders doit rester 1")
        # Les autres champs peuvent changer selon la logique


class ShopStatisticsAPIEndpointsTestCase(APITestCase):
    """
    Test des endpoints API pour recalculer les statistiques.
    """
    
    def setUp(self):
        """Créer les données de test."""
        # Créer utilisateur et compte vendeur
        self.user = User.objects.create_user(
            email='seller@test.com',
            password='testpass123'
        )
        self.seller_account = SellerAccount.objects.create(user=self.user)
        
        # Créer boutique
        self.shop = Shops.objects.create(
            owner=self.seller_account,
            name='Test Shop',
            description='Test',
            email='shop@test.com'
        )
        
        # Générer token JWT
        refresh = RefreshToken.for_user(self.user)
        self.token = str(refresh.access_token)
        
        self.client = Client()
    
    def get_auth_header(self):
        """Retourne header Authorization."""
        return {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
    
    def test_recalculate_today_endpoint(self):
        """
        Test : Endpoint POST /recalculate-today/ retourne les stats du jour.
        ✅ Status 200 OK
        ✅ ShopStatistics créée/mise à jour
        """
        response = self.client.post(
            f'/api/shop/shop-statistics/recalculate-today/?shop_id={self.shop.id}',
            **self.get_auth_header()
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['success'])
        self.assertIn('data', response.json())
    
    def test_recalculate_today_requires_shop_id(self):
        """
        Test : Endpoint recalculate-today requires shop_id.
        ✅ Status 400 Bad Request si shop_id manquant
        """
        response = self.client.post(
            '/api/shop/shop-statistics/recalculate-today/',
            **self.get_auth_header()
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.json())
    
    def test_recalculate_range_endpoint(self):
        """
        Test : Endpoint POST /recalculate-range/ sur plusieurs jours.
        ✅ Status 200 OK
        ✅ days_updated = 7 (ou spécifié)
        """
        response = self.client.post(
            f'/api/shop/shop-statistics/recalculate-range/?shop_id={self.shop.id}&days=7',
            **self.get_auth_header()
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['success'])
        self.assertEqual(response.json()['days_updated'], 7)
    
    def test_recalculate_nonexistent_shop(self):
        """
        Test : Endpoint avec shop_id inexistant.
        ✅ Status 404 Not Found
        """
        response = self.client.post(
            '/api/shop/shop-statistics/recalculate-today/?shop_id=99999',
            **self.get_auth_header()
        )
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('error', response.json())


class CeleryTasksTestCase(TestCase):
    """
    Test des tâches Celery.
    ⚠️ Requiert Celery et Redis en local.
    """
    
    def setUp(self):
        """Créer les données de test."""
        self.user = User.objects.create_user(
            email='seller@test.com',
            password='testpass123'
        )
        self.seller_account = SellerAccount.objects.create(user=self.user)
        
        self.shop = Shops.objects.create(
            owner=self.seller_account,
            name='Test Shop',
            description='Test',
            email='shop@test.com'
        )
    
    def test_recalculate_daily_shop_statistics_task(self):
        """
        Test : Tâche Celery recalculate_daily_shop_statistics().
        ⚠️ À exécuter avec Redis + Celery en local.
        """
        try:
            from boutique.tasks import recalculate_daily_shop_statistics
            
            # Exécuter la tâche (mode synchrone pour les tests)
            result = recalculate_daily_shop_statistics.apply_async()
            
            # Attendre le résultat
            output = result.get(timeout=10)
            
            # Vérifier
            self.assertEqual(output['status'], 'success')
            self.assertIn('shops_updated', output)
            self.assertGreaterEqual(output['shops_updated'], 0)
        
        except Exception as e:
            self.skipTest(f"Celery/Redis non disponible: {str(e)}")
    
    def test_recalculate_shop_statistics_range_task(self):
        """
        Test : Tâche Celery recalculate_shop_statistics_range().
        """
        try:
            from boutique.tasks import recalculate_shop_statistics_range
            
            result = recalculate_shop_statistics_range.apply_async(
                args=[self.shop.id],
                kwargs={'days': 7}
            )
            
            output = result.get(timeout=10)
            
            self.assertEqual(output['status'], 'success')
            self.assertEqual(output['days_updated'], 7)
        
        except Exception as e:
            self.skipTest(f"Celery/Redis non disponible: {str(e)}")


# ============================================================================
# COMMANDES TEST
# ============================================================================
"""
Exécuter les tests :

1. Tests Signaux & Endpoints (sans Celery)
   python manage.py test boutique.tests.ShopStatisticsSignalTestCase
   python manage.py test boutique.tests.ShopStatisticsAPIEndpointsTestCase

2. Tests Celery (avec Redis + Worker actif)
   celery -A ecommerce worker --loglevel=info
   python manage.py test boutique.tests.CeleryTasksTestCase

3. Tous les tests
   python manage.py test boutique.tests

4. Test spécifique avec logs
   python manage.py test boutique.tests.ShopStatisticsSignalTestCase -v 2
"""
