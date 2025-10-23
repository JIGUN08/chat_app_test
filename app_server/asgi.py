# app_server/app_server/asgi.py

import os
from django.core.asgi import get_asgi_application

# 💡 1. Django 설정 초기화 (이 부분이 핵심)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app_server.settings')
django_asgi_app = get_asgi_application() 


from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import api.routing # api/routing.py에서 WebSocket URL 패턴을 가져옵니다.

application = ProtocolTypeRouter({
    # 💡 HTTP 요청 (REST API)은 Django의 기본 ASGI 핸들러로 라우팅
    "http": django_asgi_app,
    
    # 💡 WebSocket 요청은 인증 미들웨어를 거쳐 ChatConsumer로 라우팅
    "websocket": AuthMiddlewareStack(
        URLRouter(
            api.routing.websocket_urlpatterns
        )
    ),
})
