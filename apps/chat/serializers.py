from rest_framework import serializers
from django.db.models import Q
from django.db.models import F
from django.utils.timezone import now
from apps.products.serializers import ProductListSerializer, ProductVariantSerializer
from apps.orders.models import Quote
from .models import ChatRoom, ChatMessage


class ChatMemberSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	email = serializers.EmailField(allow_null=True, required=False)
	first_name = serializers.CharField(allow_blank=True, required=False)
	last_name = serializers.CharField(allow_blank=True, required=False)
	phone_number = serializers.CharField(allow_blank=True, required=False)
	country_code = serializers.CharField(allow_blank=True, required=False)
	type_user = serializers.CharField(allow_blank=True, required=False)
# from .models import Messages


# class MessageSerializer(ModelSerializer):

#     class Meta:
#         model = Messages
#         fields = ('__all__')

class ChatRoomSerializer(serializers.ModelSerializer):
	member = ChatMemberSerializer(many=True, read_only=True)
	members = serializers.ListField(write_only=True)
	pinned_product_detail = serializers.SerializerMethodField()
	unread_count = serializers.IntegerField(read_only=True, default=0)
	seller_user_id = serializers.SerializerMethodField()
	current_user_is_seller = serializers.SerializerMethodField()
	can_generate_payment_link = serializers.SerializerMethodField()
	active_quote_id = serializers.SerializerMethodField()
	current_user_quote_role = serializers.SerializerMethodField()

	def create(self, validatedData):
		memberObject = validatedData.pop('members')
		chatRoom = ChatRoom.objects.create(**validatedData)
		chatRoom.member.set(memberObject)
		return chatRoom

	class Meta:
		model = ChatRoom
		exclude = ['id']

	def get_pinned_product_detail(self, obj):
		if not obj.pinned_product:
			return None
		return ProductListSerializer(obj.pinned_product, context=self.context).data

	def _get_active_quote(self, obj):
		if hasattr(obj, "_active_quote_cache"):
			return obj._active_quote_cache

		member_ids = list(obj.member.values_list("id", flat=True))
		if len(member_ids) < 2:
			obj._active_quote_cache = None
			return None

		qs = (
			Quote.objects
			.select_related("shop", "shop__owner", "shop__owner__user", "user")
			.filter(
				status__in=["draft", "sent", "countered", "accepted"],
				user_id__in=member_ids,
				shop__owner__user_id__in=member_ids,
			)
			.exclude(shop__owner__user_id=F("user_id"))
		)

		if obj.pinned_product and getattr(obj.pinned_product, "shop_id", None):
			qs = qs.filter(shop_id=obj.pinned_product.shop_id)

		obj._active_quote_cache = qs.order_by("-updated_at").first()
		return obj._active_quote_cache

	def _resolve_seller_user_id(self, obj):
		quote = self._get_active_quote(obj)
		if not quote or not getattr(quote.shop, "owner", None):
			return None
		return getattr(quote.shop.owner, "user_id", None)

	def get_seller_user_id(self, obj):
		return self._resolve_seller_user_id(obj)

	def get_current_user_is_seller(self, obj):
		request = self.context.get("request")
		if not request or not request.user or not request.user.is_authenticated:
			return False
		return request.user.id == self._resolve_seller_user_id(obj)

	def get_active_quote_id(self, obj):
		quote = self._get_active_quote(obj)
		return quote.id if quote else None

	def get_current_user_quote_role(self, obj):
		request = self.context.get("request")
		if not request or not request.user or not request.user.is_authenticated:
			return "none"

		quote = self._get_active_quote(obj)
		if not quote:
			return "none"

		if quote.user_id == request.user.id:
			return "buyer"
		if getattr(quote.shop, "owner", None) and quote.shop.owner.user_id == request.user.id:
			return "seller"
		return "none"

	def get_can_generate_payment_link(self, obj):
		return self.get_current_user_quote_role(obj) == "seller"

class ChatMessageSerializer(serializers.ModelSerializer):
	userName = serializers.SerializerMethodField()
	product_detail = serializers.SerializerMethodField()
	variant_detail = serializers.SerializerMethodField()
	active_price = serializers.SerializerMethodField()
	min_order_quantity = serializers.SerializerMethodField()
	image = serializers.ImageField(required=False, allow_null=True)
	# userImage = serializers.ImageField(source='user.image')

	class Meta:
		model = ChatMessage
		exclude = ['id', 'chat']

	def get_userName(self, Obj):
		if not Obj.user:
			return ""
		return Obj.user.first_name + ' ' + Obj.user.last_name

	def get_product_detail(self, obj):
		if not obj.product:
			return None
		return ProductListSerializer(obj.product, context=self.context).data

	def get_variant_detail(self, obj):
		if not obj.variant:
			return None
		return ProductVariantSerializer(obj.variant, context=self.context).data

	def get_min_order_quantity(self, obj):
		if not obj.product:
			return None
		return obj.product.min_order_quantity

	def get_active_price(self, obj):
		"""
		Calcule le prix actif:
		- variante si price_override
		- promo active
		- palier (en fonction de min_order_quantity)
		- base_price
		"""
		if not obj.product:
			return None

		product = obj.product
		qty = product.min_order_quantity or 1

		if obj.variant and obj.variant.price_override:
			return {
				'type': 'variant',
				'amount': float(obj.variant.price_override.amount),
				'currency': str(obj.variant.price_override.currency),
				'quantity': qty,
			}

		# promo active
		promo = product.promotions.filter(
			is_active=True,
			start_at__lte=now(),
			end_at__gte=now()
		).first()
		if promo:
			return {
				'type': 'promo',
				'amount': float(promo.promo_price.amount),
				'currency': str(promo.promo_price.currency),
				'quantity': qty,
			}

		# palier
		tier = (
			product.price_tiers
			.filter(min_quantity__lte=qty)
			.filter(Q(max_quantity__gte=qty) | Q(max_quantity__isnull=True))
			.order_by("min_quantity")
			.first()
		)
		if tier:
			return {
				'type': 'tier',
				'amount': float(tier.price.amount),
				'currency': str(tier.price.currency),
				'quantity': qty,
			}

		# base
		return {
			'type': 'base',
			'amount': float(product.base_price.amount),
			'currency': str(product.base_price.currency),
			'quantity': qty,
		}
