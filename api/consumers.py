from .models import ChatMessage

from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.conf import settings
from channels.db import database_sync_to_async 
import json
import asyncio
import traceback # 디버깅을 위해 임포트
import base64 
import os

# AI 서비스 파일 임포트 (통합된 파일 사용)
from services.ai_persona_service import AIPersonaService 
from services.emotion_service import analyze_emotion
from services.context_service import search_activities_for_context, get_activity_recommendation 

# -----------------------------------------------------------------------------
# [제거됨]: save_base64_image_and_get_url 함수 정의는 삭제합니다.
# -----------------------------------------------------------------------------

# 💡 [CRITICAL FIX]: save_message 함수 정의에서 image_url 인수를 제거하고,
# 순수 텍스트 메시지만 저장하도록 수정합니다.
@database_sync_to_async
def save_message(user, content, sender):
    ChatMessage.objects.create(
        user=user, 
        content=content, 
        sender=sender,
        # 💡 image_url 필드는 이제 저장하지 않으므로 제거합니다.
        # ChatMessage 모델에서도 이 필드를 제거해야 합니다.
    )

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    # 연결 수립 (connect 함수는 변경 없음)
    async def connect(self):
        self.ai_service = None
        self.user = None
        # ... (인증 로직은 생략)
        try:
            # ... (인증 및 user 로드 로직 생략)
            await self.accept() # 토큰 유효 시 연결 승인
        except Exception as e:
            print(f"WebSocket 인증 실패: {e}")
            await self.close(code=4000)
            return

        try:
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
            self.ai_service = AIPersonaService(self.user, api_key)
            print(f"WebSocket 연결 성공 및 서비스 초기화: User {self.user.username}")
        except Exception as e:
            print(f"AI 서비스 초기화 오류: {e}")
            await self.close()
            
    # 메시지 수신 (GPT API 호출 및 스트리밍 응답)
    async def receive(self, text_data):
        try:
            if not self.ai_service:
                await self.send(text_data=json.dumps({"type": "error", "message": "Service not initialized."}))
                return
            
            # 💡 [FIX]: 이미지 저장을 제거했으므로 final_image_url 초기화 필요 없음
            user_image_data_for_ai = None 
            
            data = json.loads(text_data)
            message_type = data.get('type') 
            user_message = data.get('message')
            
            image_base64 = data.get('image_base64') # Base64 데이터만 LLM에 전달할 용도
            
            if message_type != 'chat_message' or (not user_message and not image_base64): 
                await self.send(text_data=json.dumps({"type": "error", "message": "Invalid message format or empty message."}))
                return
            
            
            # -----------------------------------------------------------------
            # [이미지 저장/업로드 로직 전체 제거]
            # -----------------------------------------------------------------
            
            if image_base64:
                # 💡 Base64 데이터를 정제하여 AI 서비스에 바로 전달할 준비
                clean_image_base64 = image_base64.strip() if isinstance(image_base64, str) else image_base64
                if not clean_image_base64 or clean_image_base64.lower() in ('none', '없음'):
                    user_image_data_for_ai = None
                else:
                    user_image_data_for_ai = clean_image_base64
            
            # ... (컨텍스트 검색 및 추가 로직은 변경 없음)
            
            # -----------------------------------------------------------------
            # [AI 서비스 호출 및 스트리밍]
            # -----------------------------------------------------------------
            
            # 💡 [CRITICAL FIX]: image_url 인수가 제거된 save_message 호출
            # 사용자 메시지 DB 저장 (순수 텍스트 메시지만 저장)
            await save_message(self.user, user_message, 'user')
            
            # AI 서비스 호출: Base64 데이터는 LLM에게만 전달됨
            stream_generator = self.ai_service.get_ai_response_stream(
                user_message=user_message,
                image_base64=user_image_data_for_ai 
            )
            
            # 스트림 처리
            full_ai_response_chunks = []
            async for chunk in stream_generator:
                await self.send(text_data=json.dumps({
                    "type": "chat_message",
                    "message": chunk
                }))
                full_ai_response_chunks.append(chunk)

            final_bot_message = "".join(full_ai_response_chunks)

            # AI 메시지 DB 저장
            await save_message(self.user, final_bot_message, 'ai')

            # ... (감정 분석 및 완료 신호 전송 로직 생략)
            emotion_label = await database_sync_to_async(analyze_emotion)(final_bot_message)
            await self.send(text_data=json.dumps({
                "type": "message_complete",
                "emotion": emotion_label
            }))

        except Exception as e:
            error_message = f"AI 처리 오류 발생: {e}"
            print(f"--- [CRITICAL CONSUMER CRASH] Unhandled Exception in receive: ---")
            print(traceback.format_exc()) 
            
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": f"Server Error: {type(e).__name__}. Check console logs."
            }))
            await self.send(text_data=json.dumps({
                "type": "message_complete",
                "emotion": "슬픔"
            }))

    async def disconnect(self, close_code):
        username = getattr(self, 'user', None).username if hasattr(self, 'user') else 'Unknown'
        print(f"WebSocket disconnected for User {username}. Code: {close_code}")
