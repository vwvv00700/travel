from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from travel import consumers

application = ProtocolTypeRouter({
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("ws/test_room/", consumers.TestChatConsumer.as_asgi()),  # ✅ 테스트용 consumer 연결
        ])
    ),
})