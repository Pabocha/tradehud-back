from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import RestaurantReview
from .models import Restaurant

User = get_user_model()


class RestaurantReviewTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(email='a@example.com', password='pass')
        self.user2 = User.objects.create_user(email='b@example.com', password='pass')
        self.restaurant = Restaurant.objects.create(name='R', owner=self.user1)

    def test_single_review_per_restaurant(self):
        self.client.login(email='a@example.com', password='pass')
        resp = self.client.post('/api/restaurants/restaurant-reviews/', {'restaurant': self.restaurant.id, 'rating': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # second attempt should fail
        resp2 = self.client.post('/api/restaurants/restaurant-reviews/', {'restaurant': self.restaurant.id, 'rating': 4}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_edit_and_others_cannot(self):
        self.client.login(email='a@example.com', password='pass')
        resp = self.client.post('/api/restaurants/restaurant-reviews/', {'restaurant': self.restaurant.id, 'rating': 5}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rid = resp.data['id']
        self.client.logout()
        self.client.login(email='b@example.com', password='pass')
        resp2 = self.client.patch(f'/api/restaurants/restaurant-reviews/{rid}/', {'rating': 3}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)
        self.client.logout()
        self.client.login(email='a@example.com', password='pass')
        resp3 = self.client.patch(f'/api/restaurants/restaurant-reviews/{rid}/', {'rating': 4}, format='json')
        self.assertIn(resp3.status_code, (status.HTTP_200_OK, status.HTTP_202_ACCEPTED))
        self.assertTrue(RestaurantReview.objects.get(id=rid).is_edited)
