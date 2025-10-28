from .models import ChatMessage

# 💡 [수정 1] AsyncWebsocketConsumer 대신 AsyncJsonWebsocketConsumer 임포트
from channels.generic.websocket import AsyncJsonWebsocketConsumer 
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


@database_sync_to_async
def save_message(user, content, sender):
    ChatMessage.objects.create(
        user=user, 
        content=content, 
        sender=sender,
    )

User = get_user_model()

# 💡 [수정 2] AsyncWebsocketConsumer 대신 AsyncJsonWebsocketConsumer 상속
class ChatConsumer(AsyncJsonWebsocketConsumer):
    # 연결 수립 (인증 및 초기 설정)
    async def connect(self):
        self.ai_service = None
        self.user = None

        # 1. 사용자 인증 및 연결 수락
        try:
            # Query String에서 토큰 추출
            query_string = self.scope['query_string'].decode()
            if 'token=' not in query_string:
                raise ValueError("토큰 쿼리 파라미터가 누락되었습니다.")

            token = query_string.split('token=')[1].split('&')[0]
            if not token:
                raise ValueError("토큰 없음")

            # JWT 토큰 검증 및 사용자 ID 추출
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            
            # DB에서 사용자 정보 로드
            self.user = await database_sync_to_async(
                User.objects.select_related('ai_profile').get
                )(pk=user_id)
            
            if not self.user.is_active:
                raise ValueError("비활성화된 사용자")
            
            # 인증 및 활성화 성공 시 연결 승인
            await self.accept() 

        # 인증 과정 중 발생하는 모든 오류 (JWT 오류, DB 오류, ValueError 등) 처리
        except Exception as e:
            # 💡 [핵심 수정 1]: 인증 오류 발생 시 에러 메시지 출력 후 바로 연결 종료
            print(f"WebSocket 인증 오류: {e}")
            await self.close()
            return # 함수 실행 중단

        # 2. AI 클라이언트 및 세션 설정 (인증 성공 시만 이 블록에 진입)
        if self.user is None:
            print("WebSocket 연결 후, self.user가 None이어서 AI 서비스 초기화 실패.")
            await self.close()
            return

        try:
            # AI 서비스 초기화
            api_key = getattr(settings, 'OPENAI_API_KEY', None)
            
            # self.user가 None이 아님이 보장되므로 안전하게 접근 가능
            self.ai_service = AIPersonaService(self.user, api_key)
            print(f"WebSocket 연결 성공 및 서비스 초기화: User {self.user.username}")

        except Exception as e:
            # AI 서비스 초기화 중 발생하는 오류 (ex: API 키 오류) 처리
            print(f"AI 서비스 초기화 오류 (2단계): {e}")
            await self.close()
            return # 함수 실행 중단
            
    # 메시지 수신 (GPT API 호출 및 스트리밍 응답)
    # 💡 [수정 3] receive_json 사용. content는 이미 파이썬 딕셔너리입니다.
    async def receive_json(self, content):
        # 🚨 [디버깅 코드]: receive 함수 진입을 확실하게 로그에 남깁니다.
        print(f"--- [DEBUG] RECEIVE_JSON START. Data: {content}")

        try:
            if not self.ai_service:
                # 💡 send_json은 딕셔너리를 바로 받습니다.
                await self.send_json({"type": "error", "message": "Service not initialized."})
                return
            
            user_image_data_for_ai = None 
            
            data = content # 이미 딕셔너리
            message_type = data.get('type') 
            user_message = data.get('message') 
            image_base64 = data.get('image_base64') 
            
            # 💡 [핵심 수정 4]: history 인자 추출
            chat_history = data.get('history', []) 
            
            # 1. 기본 유효성 검사
            if message_type != 'chat_message' or (user_message is None and image_base64 is None):
                await self.send_json({"type": "error", "message": "Invalid message format or empty message."})
                return

            # 2. 메시지/이미지 상태에 따른 변수 설정 (NoneType 방지)
            user_message_to_save = None # DB 저장을 위한 텍스트
            user_message_for_ai = None # AI 호출을 위한 텍스트

            if user_message and isinstance(user_message, str):
                # 유효한 텍스트 메시지인 경우
                user_message_to_save = user_message
                user_message_for_ai = user_message
            elif image_base64:
                # 텍스트 없이 이미지만 전송된 경우 (DB에 저장할 내용 필요)
                user_message_to_save = "[이미지만 전송]"
                user_message_for_ai = "" # AI에게는 빈 텍스트를 전달
            else:
                # 메시지 내용과 이미지가 모두 유효하지 않은 경우 
                await self.send_json({"type": "error", "message": "Message content missing."})
                return
            
            # 3. Base64 이미지 데이터 정리
            if image_base64:
                # Base64 데이터를 정제하여 AI 서비스에 바로 전달할 준비
                clean_image_base64 = image_base64.strip() if isinstance(image_base64, str) else image_base64
                if clean_image_base64 and clean_image_base64.lower() not in ('none', '없음'):
                    user_image_data_for_ai = clean_image_base64
            
            # -----------------------------------------------------------------
            # [AI 서비스 호출 및 스트리밍]
            # -----------------------------------------------------------------
            
            # DB에 저장
            await save_message(self.user, user_message_to_save, 'user')
            
            # 💡 [핵심 수정 5]: history 인자 추가
            stream_generator = self.ai_service.get_ai_response_stream(
                user_message=user_message_for_ai,
                image_base64=user_image_data_for_ai,
                history=chat_history # 👈 필수 인자 추가
            )
            
            # 스트림 처리
            full_ai_response_chunks = []
            async for chunk in stream_generator:
                # 💡 send_json 사용
                await self.send_json({
                    "type": "chat_message",
                    "message": chunk
                })
                full_ai_response_chunks.append(chunk)

            final_bot_message = "".join(full_ai_response_chunks)

            # AI 응답 저장
            if final_bot_message:
                await save_message(self.user, final_bot_message, 'ai')
            else:
                print("Warning: Received empty response from AI service.")

            # 감정 분석 및 완료 신호 전송 로직
            emotion_label = await database_sync_to_async(analyze_emotion)(final_bot_message)
            # 💡 send_json 사용
            await self.send_json({
                "type": "message_complete",
                "emotion": emotion_label
            })

        except Exception as e:
            print(f"--- [CRITICAL CONSUMER CRASH] Unhandled Exception in receive_json: ---")
            print(traceback.format_exc()) 
            
            # 💡 [핵심 수정 6]: text_data 인자 제거 후 딕셔너리 바로 전달
            await self.send_json({ 
                "type": "error",
                "message": f"Server Error: {type(e).__name__}. Check console logs. Full Traceback printed on server."
            })
            # 💡 send_json 사용
            await self.send_json({
                "type": "message_complete",
                "emotion": "슬픔"
            })

    # 💡 [핵심 수정 7]: receive 함수 제거 (receive_json만 사용)

    async def disconnect(self, close_code):
        """WebSocket 연결이 종료될 때 호출됩니다."""
        if hasattr(self, 'user') and self.user is not None:
             username = self.user.username
        else:
             username = 'Unknown (Auth Failed)'

        print(f"WebSocket disconnected for User {username}. Code: {close_code}")
