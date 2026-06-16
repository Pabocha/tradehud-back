from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Ratings, ShopRatings
from produits.models import Products
from boutique.models import Shops
from commandes.models import Orders, LigneCommande

User = get_user_model()


class RatingPermissionsTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email='u1@example.com', password='pass')
        self.user2 = User.objects.create_user(email='u2@example.com', password='pass')
        self.product = Products.objects.create(name='P', price=100, shop=Shops.objects.first() or Shops.objects.create(name='S'))
        self.order_item = LigneCommande.objects.create(order=Orders.objects.create(shop=self.product.shop, user=self.user1), product=self.product, quantity=1, unit_price=100)

    def test_only_owner_can_update_rating(self):
        self.client.login(email='u1@example.com', password='pass')
        resp = self.client.post('/api/ratings/', {'product': self.product.id, 'order_item': self.order_item.id, 'rating': 4}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rid = resp.data['id']
        # try update as other user
        self.client.logout()
        self.client.login(email='u2@example.com', password='pass')
        resp2 = self.client.patch(f'/api/ratings/{rid}/', {'rating': 5}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)
        # as owner
        self.client.logout()
        self.client.login(email='u1@example.com', password='pass')
        resp3 = self.client.patch(f'/api/ratings/{rid}/', {'rating': 5}, format='json')
        self.assertIn(resp3.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))
        self.assertTrue(Ratings.objects.get(id=rid).is_edited)


class ShopRatingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='u3@example.com', password='pass')
        self.shop = Shops.objects.create(name='Test Shop')
        self.order = Orders.objects.create(shop=self.shop, user=self.user)

    def test_create_and_validate_rating_range(self):
        self.client.login(email='u3@example.com', password='pass')
        resp = self.client.post('/api/ratings/shop-ratings/', {'shop': self.shop.id, 'order': self.order.id, 'rating': 6}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp2 = self.client.post('/api/ratings/shop-ratings/', {'shop': self.shop.id, 'order': self.order.id, 'rating': 4}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        # duplicate attempt
        resp3 = self.client.post('/api/ratings/shop-ratings/', {'shop': self.shop.id, 'order': self.order.id, 'rating': 4}, format='json')
        self.assertEqual(resp3.status_code, status.HTTP_400_BAD_REQUEST)