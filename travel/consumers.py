import json, datetime, traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom, ChatMessage

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.room_id = int(self.scope['url_route']['kwargs']['room_id'])
            self.room_group_name = f"chat_{self.room_id}"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
            print(f"[CONNECT] channel {self.channel_name} joined {self.room_group_name}")
        except Exception as e:
            traceback.print_exc()
            await self.close()

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            print(f"[DISCONNECT] {self.channel_name} left {self.room_group_name} ({close_code})")
        except Exception as e:
            print("[ERROR][disconnect]", e)
            traceback.print_exc()

    async def receive(self, text_data):
        try:
            print("[RECEIVE raw]", text_data)
            data = json.loads(text_data)
            message = data.get('message', '').strip()
            if not message:
                print("[RECEIVE] empty message; ignored")
                return

            user = self.scope.get("user")
            username = getattr(user, "username", "익명")
            user_id = getattr(user, "id", None)
            print(f"[RECEIVE parsed] user={username} id={user_id} message={message!r}")

            # Save to DB (async wrapper)
            await self.save_message(user_id, self.room_id, message)

            # Broadcast
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": message,
                    "username": username,
                    "timestamp": datetime.datetime.now().isoformat()
                }
            )
        except Exception as e:
            print("[ERROR][receive]", e)
            traceback.print_exc()
            await self.close()

    async def chat_message(self, event):
        try:
            await self.send(text_data=json.dumps({
                "message": event["message"],
                "username": event["username"],
                "timestamp": event["timestamp"]
            }))
        except Exception as e:
            print("[ERROR][chat_message]", e)
            traceback.print_exc()

    @database_sync_to_async
    def save_message(self, user_id, room_id, content):
        try:
            print(f"[DB] try save room_id={room_id} user_id={user_id} content={content!r}")
            room = ChatRoom.objects.using('chat_db').get(id=room_id)
            ChatMessage.objects.using('chat_db').create(room=room, sender_id=user_id, message=content)
            print("[DB] saved ok")
        except Exception as e:
            print("[ERROR][save_message]", e)
            traceback.print_exc()
            # re-raise so receive catches and closes connection with 1011
            raise