from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch


class OTPThrottlingTests(APITestCase):
    url = '/api/compte/password/forgot/'

    @patch('comptes.views.send_otp_email')
    def test_otp_throttle_exceeded(self, mock_send):
        mock_send.return_value = True

        # First 3 requests should succeed
        for i in range(3):
            resp = self.client.post(self.url, {'email': f'user{i}@example.com'}, format='json')
            self.assertIn(resp.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))

        # 4th request should be throttled (429)
        resp = self.client.post(self.url, {'email': 'user3@example.com'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class LoginThrottlingTests(APITestCase):
    url = '/api/token/'

    @override_settings(REST_FRAMEWORK={'DEFAULT_THROTTLE_RATES': {'login': '3/min'}})
    def test_login_throttle_exceeded(self):
        # Make 3 invalid login attempts (receive 401), 4th should be 429
        for i in range(3):
            resp = self.client.post(self.url, {'email': f'user{i}@example.com', 'password': 'badpass'}, format='json')
            self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST))

        resp = self.client.post(self.url, {'email': 'user3@example.com', 'password': 'badpass'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
