import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = f"chat_{self.room_name}"

        # 그룹에 참가
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # 그룹에서 나가기
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # 클라이언트로부터 메시지 수신
    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']
        sender = data['sender']

        # 그룹에 메시지 전송
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': sender
            }
        )

    # 그룹 메시지 수신
    async def chat_message(self, event):
        message = event['message']
        sender = event['sender']

        # WebSocket으로 메시지 전송
        await self.send(text_data=json.dumps({
            'message': message,
            'sender': sender
        }))