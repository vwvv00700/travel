import os
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
import travel.routing  # ✅ 이게 있어야 함!

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'travelAgent.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            travel.routing.websocket_urlpatterns  # ✅ 이 경로 연결됨
        )
    ),
})