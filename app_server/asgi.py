"""
ASGI config for app_server project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app_server.settings')
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import api.routing # api 앱의 WebSocket URL 라우팅을 임포트


# Django의 기본 HTTP 요청 처리를 위한 ASGI 애플리케이션
django_asgi_app = get_asgi_application()

# ProtocolTypeRouter는 HTTP와 WebSocket 요청을 분리하여 처리합니다.
application = ProtocolTypeRouter({
    # HTTP 요청은 Django의 기본 ASGI 핸들러로 전달
    "http": django_asgi_app,

    # WebSocket 요청은 AuthMiddlewareStack을 통과한 후 URLRouter로 전달
    # AuthMiddlewareStack은 Django의 세션/인증 정보를 WebSocket 범위로 가져옵니다.
    "websocket": AuthMiddlewareStack(
        URLRouter(
            api.routing.websocket_urlpatterns
        )
    ),
})
