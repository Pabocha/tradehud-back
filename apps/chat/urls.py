# apps/chat/urls.py
from django.urls import path
from . import views as chat_views

app_name = 'messaging'

urlpatterns = [
    # path('message/', chat_views.OldMessageView.as_view(), name='old-message-route'), # Si tu en avais une
    path('chat/<str:room_name>/', chat_views.room, name='chat-room'),
    path('chats/<str:roomId>/messages', chat_views.MessagesView.as_view(), name='message-list'),
    path('chats/<str:roomId>/messages/upload', chat_views.ChatMessageCreateView.as_view(), name='message-create'),
    path('chats/<str:roomId>/messages/read', chat_views.ChatMessageReadView.as_view(), name='message-read'),
    path('user/chats', chat_views.ChatRoomView.as_view(), name='user-chats'),
    path('support-chat/start', chat_views.SupportChatStartView.as_view(), name='support-chat-start'),
    path('user/conversations', chat_views.ChatUserConversationsView.as_view(), name='user-conversations'),
]