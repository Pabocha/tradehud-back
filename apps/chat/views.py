from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from .serializers import ChatMessageSerializer, ChatRoomSerializer
from .models import ChatRoom, ChatMessage
from apps.products.models import Products, ProductVariant
from apps.shops.models import Shops
from apps.accounts.models import UserProfile
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.generics import ListAPIView
from rest_framework.pagination import LimitOffsetPagination
from django.db.models import Count, Q
from django.db.models import F
from django.contrib.auth import get_user_model
from apps.orders.models import Quote
from django.utils import timezone
from datetime import timedelta
# from .models import Messages
# from .serializers import MessageSerializer
# Create your views here.

User = get_user_model()


def _user_photo_url(user, request):
	try:
		profile = getattr(user, 'userprofile', None)
		if not profile or not getattr(profile, 'photo', None):
			return None
		url = profile.photo.url
		return request.build_absolute_uri(url) if request else url
	except Exception:
		return None
def room(request, room_name):
    return render(request, 'chat/room.html', {
        'room_name': room_name
    })


class ChatRoomView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        chatRooms = (
            ChatRoom.objects
            .filter(member=user.id)
            .annotate(
                unread_count=Count(
                    "messages",
                    filter=Q(messages__is_read=False) & ~Q(messages__user=user),
                    distinct=True,
                )
            )
        )
        serializer = ChatRoomSerializer(chatRooms, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        my_user_id = request.user.id
        members = request.data.get("members", [])
        product_id = request.data.get("product_id")
        variant_id = request.data.get("variant_id")
        if my_user_id not in members:
            members.append(my_user_id)

        if len(members) == 2:
            user1, user2 = members

            # Chercher une room DM existante entre les deux utilisateurs
            room = ChatRoom.objects.annotate(num_members=Count('member')) \
                .filter(type='DM', num_members=2, member__id=user1) \
                .filter(member__id=user2).first()
            if room:
                serializer = ChatRoomSerializer(room, context={"request": request})
                return Response(serializer.data, status=status.HTTP_200_OK)

            # Générer le champ name avec les emails des 2 membres
            users = User.objects.filter(id__in=members)
            if users.count() == 2:
                email_list = sorted([user.email for user in users])
                room_name = f"{email_list[0]} & {email_list[1]}"
            else:
                room_name = None
        else:
            room_name = None

        data = {
            "members": members,
            "name": room_name,
        }
        if variant_id:
            variant = ProductVariant.objects.filter(id=variant_id).first()
            if not variant:
                return Response({"detail": "Variante introuvable."}, status=status.HTTP_404_NOT_FOUND)
            data["pinned_product"] = variant.product_id
        elif product_id:
            data["pinned_product"] = product_id
        serializer = ChatRoomSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            room = serializer.save()
            if variant_id:
                ChatMessage.objects.create(
                    chat=room,
                    user=request.user,
                    product_id=variant.product_id,
                    variant=variant,
                    message_type="product",
                    message="",
                )
            elif product_id:
                product = Products.objects.filter(id=product_id).first()
                if product:
                    ChatMessage.objects.create(
                        chat=room,
                        user=request.user,
                        product=product,
                        message_type="product",
                        message="",
                    )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MessagesView(ListAPIView):
	serializer_class = ChatMessageSerializer
	pagination_class = LimitOffsetPagination

	def get_queryset(self):
		roomId = self.kwargs['roomId']
		return ChatMessage.objects.\
			filter(chat__roomId=roomId).order_by('-timestamp')

	def list(self, request, *args, **kwargs):
		queryset = self.get_queryset()
		room_id = self.kwargs['roomId']
		room = ChatRoom.objects.filter(roomId=room_id).prefetch_related('member').first()
		room_meta = ChatRoomSerializer(room, context={"request": request}).data if room else None

		page = self.paginate_queryset(queryset)
		if page is not None:
			serializer = self.get_serializer(page, many=True)
			response = self.get_paginated_response(serializer.data)
			response.data["room_meta"] = room_meta
			return response

		serializer = self.get_serializer(queryset, many=True)
		return Response(
			{
				"results": serializer.data,
				"room_meta": room_meta,
			},
			status=status.HTTP_200_OK,
		)


class ChatMessageCreateView(APIView):
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser, JSONParser]

	def post(self, request, roomId):
		message = request.data.get("message", "")
		image = request.FILES.get("image")
		product_id = request.data.get("product_id")
		variant_id = request.data.get("variant_id")
		message_type = request.data.get("message_type")

		if not message and not image and not product_id and not variant_id:
			return Response(
				{"detail": "message, image, product_id ou variant_id requis."},
				status=status.HTTP_400_BAD_REQUEST
			)

		room = ChatRoom.objects.filter(roomId=roomId).first()
		if not room:
			return Response({"detail": "Chat introuvable."}, status=status.HTTP_404_NOT_FOUND)

		product = None
		variant = None
		if variant_id:
			variant = ProductVariant.objects.filter(id=variant_id).first()
			if not variant:
				return Response({"detail": "Variante introuvable."}, status=status.HTTP_404_NOT_FOUND)
			product = variant.product
			if product_id and str(product.id) != str(product_id):
				return Response({"detail": "Le produit ne correspond pas a la variante."}, status=status.HTTP_400_BAD_REQUEST)
			message_type = "product"
		elif product_id:
			product = Products.objects.filter(id=product_id).first()
			if not product:
				return Response({"detail": "Produit introuvable."}, status=status.HTTP_404_NOT_FOUND)
			message_type = "product"

			is_intro_product = (
				message_type == "product"
				and (message is None or message == "")
				and image is None
			)
			if is_intro_product:
				member_ids = list(room.member.values_list("id", flat=True))
				quote_qs = (
					Quote.objects
					.select_related("shop", "shop__owner", "shop__owner__user", "user")
					.filter(
						user_id__in=member_ids,
						shop__owner__user_id__in=member_ids,
					)
					.exclude(shop__owner__user_id=F("user_id"))
				)
				if product and getattr(product, "shop_id", None):
					quote_qs = quote_qs.filter(shop_id=product.shop_id)

				cutoff = timezone.now() - timedelta(hours=24)
				existing = ChatMessage.objects.filter(
					chat=room,
					message_type="product",
					product=product,
					variant=variant,
					timestamp__gte=cutoff,
				).first()

				if existing:
					terminal_exists = quote_qs.filter(
						status__in=["rejected", "expired", "converted"]
					).exists()
					if not terminal_exists:
						serializer = ChatMessageSerializer(existing, context={"request": request})
						return Response(serializer.data, status=status.HTTP_200_OK)

		if not message_type:
			if image:
				message_type = "image"
			else:
				message_type = "text"

		chat_message = ChatMessage.objects.create(
			chat=room,
			user=request.user,
			message=message or "",
			image=image,
			product=product,
			variant=variant,
			message_type=message_type,
		)

		serializer = ChatMessageSerializer(chat_message, context={"request": request})
		payload = serializer.data
		payload["action"] = "message"
		payload["roomId"] = room.roomId

		channel_layer = get_channel_layer()
		if channel_layer:
			async_to_sync(channel_layer.group_send)(
				room.roomId,
				{
					"type": "chat_message",
					"message": payload
				}
			)
		return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatMessageReadView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def post(self, request, roomId):
		message_ids = request.data.get("message_ids")
		room = ChatRoom.objects.filter(roomId=roomId).first()
		if not room:
			return Response({"detail": "Chat introuvable."}, status=status.HTTP_404_NOT_FOUND)

		qs = ChatMessage.objects.filter(chat=room, is_read=False).exclude(user=request.user)

		if message_ids:
			if not isinstance(message_ids, list):
				return Response({"detail": "message_ids doit etre une liste."}, status=status.HTTP_400_BAD_REQUEST)
			qs = qs.filter(id__in=message_ids)

		message_ids_to_mark = list(qs.values_list("id", flat=True))
		updated = qs.update(is_read=True)

		if message_ids_to_mark:
			channel_layer = get_channel_layer()
			if channel_layer:
				async_to_sync(channel_layer.group_send)(
					room.roomId,
					{
						"type": "chat_message",
						"message": {
							"action": "read",
							"roomId": room.roomId,
							"user": request.user.id,
							"message_ids": message_ids_to_mark,
						},
					},
				)

		return Response({"updated": updated}, status=status.HTTP_200_OK)


class ChatUserConversationsView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def get(self, request):
		user = request.user
		rooms = (
			ChatRoom.objects
			.filter(member=user) 
			.annotate(
				unread_count=Count(
					"messages",
					filter=Q(messages__is_read=False) & ~Q(messages__user=user),
					distinct=True,
				)
			)
			.prefetch_related('member')
		)
		response = []

		for room in rooms:
			other_user = room.member.exclude(id=user.id).first()
			if not other_user:
				continue
			room_meta = ChatRoomSerializer(room, context={"request": request}).data

			last_msg = (
				ChatMessage.objects
				.filter(chat=room)
				.order_by('-timestamp')
				.first()
			)

			shop_name = None
			if getattr(other_user, "has_seller_account", False):
				shop = (
					Shops.objects
					.filter(owner__user=other_user)
					.order_by('date_created')
					.first()
				)
				if shop:
					shop_name = shop.name

			last_activity = last_msg.timestamp if last_msg else room.last_updated
			response.append({
				"roomId": room.roomId,
				"user": {
					"id": other_user.id,
					"first_name": other_user.first_name,
					"last_name": other_user.last_name,
					"email": other_user.email,
					"photo": _user_photo_url(other_user, request),
					"last_seen": other_user.last_seen.isoformat() if other_user.last_seen else None,
				},
				"is_support": bool(getattr(other_user, "type_user", "") == "support"),
				"shop_name": shop_name,
				"seller_user_id": room_meta.get("seller_user_id"),
				"active_quote_id": room_meta.get("active_quote_id"),
				"current_user_quote_role": room_meta.get("current_user_quote_role"),
				"can_generate_payment_link": room_meta.get("can_generate_payment_link", False),
				"last_message": last_msg.message if last_msg else None,
				"last_message_type": last_msg.message_type if last_msg else None,
				"last_message_time": last_msg.timestamp if last_msg else None,
				"unread_count": getattr(room, "unread_count", 0),
				"_last_activity": last_activity,
			})

		# Trier par date du dernier message (desc)
		response.sort(key=lambda x: x["_last_activity"], reverse=True)
		for item in response:
			item.pop("_last_activity", None)
		return Response(response, status=status.HTTP_200_OK)


class SupportChatStartView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def post(self, request):
		user = request.user

		def _room_payload(room, agent):
			serializer = ChatRoomSerializer(room, context={"request": request})
			payload = serializer.data
			payload["support_user"] = {
				"id": agent.id,
				"first_name": agent.first_name,
				"last_name": agent.last_name,
				"email": agent.email,
				"type_user": getattr(agent, "type_user", ""),
				"photo": _user_photo_url(agent, request),
				"last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
			}
			payload["room_type"] = "SUPPORT"
			return payload

		# Réutiliser le fil support existant de l'utilisateur (prioritaire sur la capacité)
		existing_room = (
			ChatRoom.objects
			.annotate(num_members=Count("member"))
			.filter(type="SUPPORT", num_members=2, member__id=user.id)
			.first()
		)
		if existing_room:
			agent = existing_room.member.exclude(id=user.id).first()
			if agent:
				return Response(
					_room_payload(existing_room, agent),
					status=status.HTTP_200_OK,
				)

		# Routage par rôle support + capacité (agents les moins chargés)
		candidates = (
			User.objects
			.filter(is_active=True, type_user='support')
			.exclude(id=user.id)
			.order_by('id')
		)

		def _active_support_chats(agent):
			# Une conversation support compte comme "active" si un message
			# a été échangé au cours des 7 derniers jours.
			cutoff = timezone.now() - timedelta(days=7)
			return (
				ChatMessage.objects
				.filter(chat__type='SUPPORT', chat__member=agent, timestamp__gte=cutoff)
				.values('chat_id')
				.distinct()
				.count()
			)

		support_agent = None
		best_load = None
		for agent in candidates:
			load = _active_support_chats(agent)
			if load < agent.support_max_chats:
				if best_load is None or load < best_load:
					support_agent, best_load = agent, load

		if support_agent is None:
			return Response(
				{"detail": "Aucun agent support disponible pour le moment."},
				status=status.HTTP_503_SERVICE_UNAVAILABLE,
			)

		room = ChatRoom.objects.create(
			type="SUPPORT",
			name=f"Support: {user.email or user.id}",
		)
		room.member.set([user.id, support_agent.id])

		return Response(
			_room_payload(room, support_agent),
			status=status.HTTP_200_OK)
