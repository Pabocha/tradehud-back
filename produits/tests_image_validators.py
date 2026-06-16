from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from boutique.models import Shops
from comptes.models import SellerAccount
from produits.models import Products
from django.conf import settings


class ImageUploadValidationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email='seller@example.com', password='pass123', first_name='Seller')
        self.seller = SellerAccount.objects.create(user=self.user, company_name='Comp', phone_number='123', email_contact='seller@e.com')
        self.shop = Shops.objects.create(name='Shop1', owner=self.seller, email_contact='shop@example.com')
        self.product = Products.objects.create(
            name='Prod', price=100, shop=self.shop, description='Desc', stock_quantity=1, status='available'
        )
        self.client = APIClient()

    def test_upload_image_exceeds_5mb_rejected(self):
        # Build a fake JPEG file with proper header and size > 5MB
        large_content = b'\xff\xd8' + b'a' * (5 * 1024 * 1024 + 1)
        big_file = SimpleUploadedFile('big.jpg', large_content, content_type='image/jpeg')

        url = f'/api/products/{self.product.id}/images'
        resp = self.client.post(url, {'images': big_file}, format='multipart')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('errors', resp.data) or self.assertIn('message', resp.data)
