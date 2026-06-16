from django.test import TestCase
from apps.vendor.boutique.models import Shops
from apps.vendor.produits.models import Products
from commandes.models import Orders, LigneCommande
from django.contrib.auth import get_user_model

User = get_user_model()


class LigneCommandeShopFieldTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='tester@example.com', password='pass')
        self.shop = Shops.objects.create(name='Shop A')
        self.product = Products.objects.create(name='Product A', price=100, shop=self.shop)
        self.order = Orders.objects.create(customer=self.user, total_amount=0, delivery_address='addr')

    def test_shop_saved_on_line(self):
        ligne = LigneCommande.objects.create(order=self.order, product=self.product, quantity=2, unit_price=100)
        self.assertIsNotNone(ligne.shop)
        self.assertEqual(ligne.shop, self.shop)
