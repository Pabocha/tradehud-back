from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from djmoney.money import Money
from rest_framework.test import APIClient

from apps.accounts.models import Address, SellerAccount
from apps.shops.models import Shops
from apps.products.models import Products
from apps.orders.models import Quote, Orders
from apps.chat.models import ChatRoom, ChatMessage

User = get_user_model()


@override_settings(ELASTICSEARCH_DSL_AUTOSYNC=False)
class QuoteFlowTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            email='buyer@test.com', password='pass', first_name='Pablo', last_name='Acheteur',
            phone_number='771000000',
        )
        self.seller = User.objects.create_user(
            email='seller@test.com', password='pass', first_name='Vendeur', last_name='Pro',
            phone_number='772000000',
        )
        self.seller.has_seller_account = True
        self.seller.save()
        self.seller_account = SellerAccount.objects.create(
            user=self.seller, company_name='Boutique Test',
            phone_number='771111111', email_contact='contact@test.com',
        )
        self.shop = Shops.objects.create(
            name='Boutique Test', owner=self.seller_account,
            email_contact='shop@test.com', status='active',
        )
        self.product = Products.objects.create(
            name='Produit Test',
            base_price=Money(10000, 'XOF'),
            shop=self.shop,
            description='Test',
            stock_quantity=50,
            min_order_quantity=2,
            image='',
        )
        self.room = ChatRoom.objects.create(type='DM', pinned_product=self.product)
        self.room.member.add(self.buyer, self.seller)

        self.buyer_client = APIClient()
        self.buyer_client.force_authenticate(self.buyer)
        self.seller_client = APIClient()
        self.seller_client.force_authenticate(self.seller)
        self.base = '/api/v1/orders/'

        self.address = Address.objects.create(
            customer=self.buyer,
            address_type='shipping',
            first_name='Pablo',
            last_name='Acheteur',
            phone_number='771111111',
            street_address='Dakar',
            city='Dakar',
            country='SN',
        )

    def _create_quote(self, price='9000'):
        resp = self.buyer_client.post(
            f'{self.base}quotes/client/',
            {
                'shop': self.shop.id,
                'expires_at': (timezone.now() + timedelta(days=7)).isoformat(),
                'lines': [{
                    'product': self.product.id,
                    'quantity': 5,
                    'negotiated_price': price,
                }],
            },
            format='json',
        )
        return resp

    def test_create_quote_draft_and_room_message(self):
        resp = self._create_quote()
        self.assertEqual(resp.status_code, 201)
        quote = Quote.objects.get(id=resp.data['id'])
        self.assertEqual(quote.status, 'draft')
        self.assertTrue(
            ChatMessage.objects.filter(chat=self.room, message_type='text').exists()
        )

    def test_seller_send(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        resp = self.seller_client.post(f'{self.base}quotes/seller/{quote.id}/send/', {}, format='json')
        self.assertEqual(resp.status_code, 200)
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'sent')

    def test_seller_counter_updates_price(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        resp = self.seller_client.post(
            f'{self.base}quotes/seller/{quote.id}/counter/',
            {
                'lines': [{
                    'product': self.product.id,
                    'quantity': 5,
                    'negotiated_price': '8500',
                }],
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'countered')
        self.assertEqual(quote.lines.count(), 1)
        self.assertEqual(quote.lines.first().negotiated_price.amount, Decimal('8500'))

    def test_counter_rejects_invalid_lines(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        resp = self.seller_client.post(
            f'{self.base}quotes/seller/{quote.id}/counter/',
            {'lines': [{'quantity': 5}]},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_buyer_accept(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        self.seller_client.post(f'{self.base}quotes/seller/{quote.id}/send/', {}, format='json')
        resp = self.buyer_client.post(f'{self.base}quotes/client/{quote.id}/accept/', {}, format='json')
        self.assertEqual(resp.status_code, 200)
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'accepted')

    def test_payment_link_urls(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        self.seller_client.post(f'{self.base}quotes/seller/{quote.id}/send/', {}, format='json')
        self.buyer_client.post(f'{self.base}quotes/client/{quote.id}/accept/', {}, format='json')
        resp = self.seller_client.post(
            f'{self.base}quotes/seller/{quote.id}/payment-link/',
            {'expires_in_minutes': 60},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('/api/v1/orders/quotes/client/pay/', resp.data['preview_url'])
        self.assertIn('/api/v1/orders/quotes/client/pay/', resp.data['pay_url'])
        quote.refresh_from_db()
        self.assertIsNotNone(quote.payment_link_token)

    def test_checkout_creates_order(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        self.seller_client.post(f'{self.base}quotes/seller/{quote.id}/send/', {}, format='json')
        self.buyer_client.post(f'{self.base}quotes/client/{quote.id}/accept/', {}, format='json')
        resp = self.buyer_client.post(
            f'{self.base}quotes/client/{quote.id}/checkout/',
            {'origin_address': self.address.id, 'transport_mode': 'road'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        order = Orders.objects.get(id=resp.data['order_id'])
        self.assertEqual(order.payment_status, 'pending')
        self.assertEqual(order.order_lines.first().unit_price, Decimal('9000'))
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'converted')

    def test_pay_by_token_creates_paid_order(self):
        quote = Quote.objects.get(id=self._create_quote().data['id'])
        self.seller_client.post(f'{self.base}quotes/seller/{quote.id}/send/', {}, format='json')
        self.buyer_client.post(f'{self.base}quotes/client/{quote.id}/accept/', {}, format='json')
        token_resp = self.seller_client.post(
            f'{self.base}quotes/seller/{quote.id}/payment-link/',
            {'expires_in_minutes': 60},
            format='json',
        )
        token = token_resp.data['token']
        resp = self.buyer_client.post(
            f'{self.base}quotes/client/pay/{token}/',
            {'origin_address': self.address.id, 'transport_mode': 'road'},
            format='json',
        )
        self.assertEqual(resp.status_code, 201)
        order = Orders.objects.get(id=resp.data['order_id'])
        self.assertEqual(order.payment_status, 'paid')
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'converted')
