import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import User
from travel.models import ChatRoom, ChatMessage
from asgiref.sync import sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # URL에서 room_name을 가져옵니다 (room_name = chat_1_5 형식)
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'chat_%s' % self.room_name

        # Room Group에 합류
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        
        # 💡 DB에서 과거 메시지 내역 불러오기
        messages = await self.get_last_messages()
        for message in messages:
            await self.send(text_data=json.dumps({
                'message': message['content'],
                'sender': message['sender__username'],
                'timestamp': message['timestamp'].strftime("%H:%M")
            }))


    async def disconnect(self, close_code):
        # Room Group에서 퇴장
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 웹소켓에서 메시지를 받을 때 실행
    async def receive(self, text_data):
        data_json = json.loads(text_data)
        message = data_json['message']
        
        # 💡 현재 사용자(로그인 정보) 가져오기
        user = self.scope["user"]
        
        # 1. 메시지를 DB에 저장
        await self.save_message(user, message)

        # 2. Room Group의 모든 채널에 메시지 전송
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message', # 아래 chat_message 핸들러로 전달
                'message': message,
                'sender': user.username,
                'timestamp': timezone.now().strftime("%H:%M")
            }
        )

    # group.send에서 type:'chat_message'가 오면 실행
    async def chat_message(self, event):
        # 웹소켓으로 메시지 전송
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))
        
    @sync_to_async
    def save_message(self, user, content):
        """메시지를 DB에 비동기적으로 저장"""
        try:
            # DB에서 채팅방 객체를 가져옵니다.
            room = ChatRoom.objects.get(room_name=self.room_name)
            
            # 새 메시지 객체 생성 및 저장
            ChatMessage.objects.create(
                room=room,
                sender=user,
                content=content
            )
        except ChatRoom.DoesNotExist:
            print(f"Error: ChatRoom {self.room_name} does not exist.")
            
    @sync_to_async
    def get_last_messages(self, limit=50):
        """DB에서 과거 메시지 50개를 불러옵니다"""
        try:
            room = ChatRoom.objects.get(room_name=self.room_name)
            # 최근 50개 메시지를 역순으로 가져와 다시 순방향으로 정렬
            messages = ChatMessage.objects.filter(room=room).order_by('-timestamp')[:limit][::-1]
            # 필요한 필드만 포함하도록 딕셔너리로 변환
            return list(messages.values('content', 'sender__username', 'timestamp'))
        except ChatRoom.DoesNotExist:
            return []