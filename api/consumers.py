#app_server/api/consumers.py
from .models import ChatMessage

from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.conf import settings
from channels.db import database_sync_to_async 
import json
import asyncio

# AI 서비스 파일 임포트 (통합된 파일 사용)
from services.ai_persona_service import AIPersonaService 

from services.emotion_service import analyze_emotion

@database_sync_to_async
def save_message(user, content, sender):
    ChatMessage.objects.create(user=user, content=content, sender=sender)


User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    #  연결 수립 (인증 및 초기 설정)
    async def connect(self):
        """WebSocket 연결을 수락하고 JWT 인증 및 사용자 데이터를 로드합니다."""
        self.ai_service = None
        try:
            # Flutter에서 보낸 쿼리 파라미터(token)에서 JWT 토큰 추출
            query_string = self.scope['query_string'].decode()
            if 'token=' not in query_string:
                raise ValueError("토큰 쿼리 파라미터가 누락되었습니다.")

            token = query_string.split('token=')[1].split('&')[0]
            if not token:
                raise ValueError("토큰 없음")

            # JWT 토큰 검증 및 사용자 로드
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            
            # 핵심: database_sync_to_async를 사용하여 DB에서 User 및 ai_profile 동시 로드
            self.user = await database_sync_to_async(
                # select_related('ai_profile')를 사용하여 호감도 정보가 포함된 ai_profile Eager Loading
                User.objects.select_related('ai_profile').get
                )(pk=user_id)
            
            if not self.user.is_active:
                raise ValueError("비활성화된 사용자")

            # ai_profile 로드 확인 (페르소나 적용에 필수)
            if not hasattr(self.user, 'ai_profile') or self.user.ai_profile is None:
                 print(f"경고: User {self.user.username}에 연결된 Profile 객체가 없습니다. 동적 페르소나 적용 불가.")
                 
            await self.accept() # 토큰 유효 시 연결 승인
            
        except Exception as e:
            print(f"WebSocket 인증 실패: {e}")
            await self.close(code=4000) # 인증 실패 시 연결 거부
            return

        #AI 클라이언트 및 세션 설정
        try:
            # settings에서 API Key 가져오기
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
            if not api_key:
                # 테스트를 위해 .env 파일에서 가져오거나 설정에 추가되어야 함
                print("OPENAI_API_KEY가 settings에 설정되지 않았습니다. API 호출은 실패할 수 있습니다.") 
            
            # 로드된 self.user 객체를 서비스에 전달 (호감도 점수 포함)
            self.ai_service = AIPersonaService(self.user, api_key)
            print(f"WebSocket 연결 성공 및 서비스 초기화: User {self.user.username}")
        except Exception as e:
            print(f"AI 서비스 초기화 오류: {e}")
            await self.close()
            
    #메시지 수신 (GPT API 호출 및 스트리밍 응답)
    async def receive(self, text_data):
                
        if not self.ai_service:
            await self.send(text_data=json.dumps({"type": "error", "message": "Service not initialized."}))
            return
            
        try:
            data = json.loads(text_data)
            message_type = data.get('type') 
            user_message = data.get('message')
            
            if message_type != 'chat_message' or not user_message:
                await self.send(text_data=json.dumps({"type": "error", "message": "Invalid message format."}))
                return

            #AI 서비스 호출 및 스트리밍
            stream_generator = self.ai_service.get_ai_response_stream(user_message)

            # AI 응답 청크를 조립(저장)하기 위한 변수
            full_ai_response_chunks = []

            # 사용자 메시지 DB 저장
            await save_message(self.user, user_message, 'user')
            
            # 스트림 처리
            async for chunk in stream_generator:
                await self.send(text_data=json.dumps({
                    "type": "chat_message",
                    "message": chunk
                }))

                # 서버에 청크 저장 (조립)
                full_ai_response_chunks.append(chunk)

            # 스트리밍 완료 후, 모든 청크를 하나의 문자열로 결합
            final_bot_message = "".join(full_ai_response_chunks)

            # AI 메시지 DB 저장
            await save_message(self.user, final_bot_message, 'ai')

            # 최종 응답 텍스트로 감정 분석 (동기 함수이므로 비동기 래퍼 사용)
            emotion_label = await database_sync_to_async(analyze_emotion)(final_bot_message)
                
            # 감정(emotion)이 포함된 응답 완료 신호 전송
            await self.send(text_data=json.dumps({
                "type": "message_complete",
                "emotion": emotion_label  # Flutter가 기다리던값
            }))

            
        except Exception as e:
            error_message = f"AI 처리 오류 발생: {e}"
            print(error_message)
            # 오류 발생 시 '슬픔' 감정을 전송
            await self.send(text_data=json.dumps({
                "type": "message_complete", # 에러 대신 complete를 보내야 Flutter가 대기 상태를 풂
                "emotion": "슬픔"
            }))

    # 💡 3. 연결 해제
    async def disconnect(self, close_code):
        """WebSocket 연결이 종료될 때 호출됩니다."""
        # self.user가 connect에서 설정되지 않았을 경우를 대비
        username = getattr(self, 'user', None).username if hasattr(self, 'user') else 'Unknown'
        print(f"WebSocket disconnected for User {username}. Code: {close_code}")
