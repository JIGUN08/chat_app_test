# api/routing.py 

from django.urls import re_path
from . import consumers # 현재 api 폴더에 있는 consumers.py를 상대 경로로 가져옵니다.

# WebSocket 요청 URL 패턴 리스트
websocket_urlpatterns = [
    # 💡 핵심 채팅 엔드포인트: ws/chat/
    # ws://YOUR_DOMAIN/ws/chat/ 경로로 접속이 들어오면 consumers.ChatConsumer가 처리하도록 연결합니다.
    re_path(r'ws/chat/$', consumers.ChatConsumer.as_asgi()), 
]
