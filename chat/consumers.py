import json
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import ChatRoom, ChatMessage
from produits.models import Products, ProductVariant
from .serializers import ChatMessageSerializer
from comptes.models import CustomUser, OnlineUser

class ChatConsumer(AsyncWebsocketConsumer):
	def getUser(self, userId):
		return CustomUser.objects.get(id=userId)

	def getOnlineUsers(self):
		onlineUsers = OnlineUser.objects.all()
		return [onlineUser.user.id for onlineUser in onlineUsers]

	def addOnlineUser(self, user):
		try:
			OnlineUser.objects.create(user=user)
		except:
			pass

	def deleteOnlineUser(self, user):
		try:
			OnlineUser.objects.get(user=user).delete()
		except:
			pass

	def saveMessage(self, message, userId, roomId, image=None, product_id=None, variant_id=None, message_type=None):
		userObj = CustomUser.objects.get(id=userId)
		chatObj = ChatRoom.objects.get(roomId=roomId)
		product = None
		variant = None
		if variant_id:
			variant = ProductVariant.objects.filter(id=variant_id).first()
			if variant:
				product = variant.product
				message_type = "product"
		elif product_id:
			product = Products.objects.filter(id=product_id).first()
			if product:
				message_type = "product"
		if not message_type:
			if image:
				message_type = "image"
			else:
				message_type = "text"
		is_intro_product = (
			message_type == "product"
			and (message is None or message == "")
			and image is None
		)
		if is_intro_product:
			existing = ChatMessage.objects.filter(
				chat=chatObj,
				message_type="product",
				product=product,
				variant=variant,
			).first()
			if existing:
				return None

		chatMessageObj = ChatMessage.objects.create(
			chat=chatObj,
			user=userObj,
			message=message or "",
			image=image,
			product=product,
			variant=variant,
			message_type=message_type,
		)
		payload = ChatMessageSerializer(chatMessageObj).data
		payload["action"] = "message"
		payload["roomId"] = roomId
		return payload

	async def sendOnlineUserList(self):
		onlineUserList = await database_sync_to_async(self.getOnlineUsers)()
		chatMessage = {
			'type': 'chat_message',
			'message': {
				'action': 'onlineUser',
				'userList': onlineUserList
			}
		}
		await self.channel_layer.group_send('onlineUser', chatMessage)

	async def connect(self):
		self.userId = self.scope['url_route']['kwargs']['userId']
		self.userRooms = await database_sync_to_async(
			list
		)(ChatRoom.objects.filter(member=self.userId))
		for room in self.userRooms:
			await self.channel_layer.group_add(
				room.roomId,
				self.channel_name
			)
		await self.channel_layer.group_add('onlineUser', self.channel_name)
		self.user = await database_sync_to_async(self.getUser)(self.userId)
		await database_sync_to_async(self.addOnlineUser)(self.user)
		await self.sendOnlineUserList()
		await self.accept()

	async def disconnect(self, close_code):
		await database_sync_to_async(self.deleteOnlineUser)(self.user)
		await self.sendOnlineUserList()
		for room in self.userRooms:
			await self.channel_layer.group_discard(
				room.roomId,
				self.channel_name
			)

	async def receive(self, text_data):
		text_data_json = json.loads(text_data)
		action = text_data_json['action']
		roomId = text_data_json['roomId']
		chatMessage = {}
		if action == 'message':
			message = text_data_json['message']
			userId = text_data_json['user']
			image = text_data_json.get('image')
			product_id = text_data_json.get('product_id')
			variant_id = text_data_json.get('variant_id')
			message_type = text_data_json.get('message_type')
			chatMessage = await database_sync_to_async(
				self.saveMessage
			)(message, userId, roomId, image=image, product_id=product_id, variant_id=variant_id, message_type=message_type)
			if chatMessage is None:
				return
		elif action == 'typing':
			chatMessage = {
				'type': 'typing',
				'user': text_data_json['user'],
				'roomId': text_data_json['roomId']
			}
		elif action == 'stop_typing':
			chatMessage = {
				'type': 'stop_typing',
				'user': text_data_json['user'],
				'roomId': text_data_json['roomId']
			}


		await self.channel_layer.group_send(
			roomId,
			{
				'type': 'chat_message',
				'message': chatMessage
			}
		)

	async def chat_message(self, event):
		message = event['message']
		await self.send(text_data=json.dumps(message))
