import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack # 사용자 인증 미들웨어
from django.urls import re_path
from travel import consumers

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'travelAgent.settings')

# WebSocket 라우팅 정의
websocket_urlpatterns = [
    # ws/chat/<room_name>/ 형식으로 접속
    re_path(r'ws/chat/(?P<room_name>\w+)/$', consumers.ChatConsumer.as_asgi()), 
]

application = ProtocolTypeRouter({
    "http": get_asgi_application(), # HTTP 요청은 Django가 처리
    "websocket": AuthMiddlewareStack( # WebSocket 요청은 Channels가 처리 (인증 미들웨어 필요)
        URLRouter(
            websocket_urlpatterns
        )
    ),
})