from django.db import models
from django.contrib.auth import get_user_model
import shortuuid
from django.db.models import Count
from apps.products.models import Products, ProductVariant

User = get_user_model()

# Create your models here.

# class Messages(models.Model):
#     sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
#     receiver = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
#     content = models.TextField()
#     timestamp = models.DateTimeField(auto_now_add=True)
#     is_read = models.BooleanField(default=False)

class ChatRoom(models.Model):
    roomId = models.CharField(max_length=22, unique=True, default=shortuuid.uuid)
    type = models.CharField(max_length=10, default='DM')  # DM = direct message
    member = models.ManyToManyField(User, related_name="chat_rooms")
    name = models.CharField(max_length=255, null=True, blank=True)
    pinned_product = models.ForeignKey(
        Products,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pinned_in_chats",
    )
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.roomId + ' -> ' + str(self.name)

    @classmethod
    def get_or_create_one_to_one(cls, user1, user2):
        # Cherche une room existante avec exactement ces deux membres
        existing_room = cls.objects.annotate(num_members=Count('member'))\
            .filter(num_members=2, member=user1)\
            .filter(member=user2, type='DM').first()

        if existing_room:
            return existing_room, False

        # Sinon on crée la room
        new_room = cls.objects.create(type='DM')
        new_room.member.add(user1, user2)
        return new_room, True

class ChatMessage(models.Model):
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('product', 'Product'),
    ]
    chat = models.ForeignKey(ChatRoom, on_delete=models.SET_NULL, null=True, related_name="messages")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="chat_messages")
    message = models.CharField(max_length=255, blank=True)
    image = models.ImageField(upload_to='chat/messages/', null=True, blank=True)
    product = models.ForeignKey(
        Products,
        on_delete=models.SET_NULL,
        null=True,
        blank=True, 
        related_name="chat_messages",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_messages",
    )
    message_type = models.CharField(max_length=10, choices=MESSAGE_TYPES, default='text')
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
	
    class Meta:
        ordering = ['-timestamp']  # derniers messages en premier


    def __str__(self):
	    return self.message
