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
# context_service 임포트
from services.context_service import search_activities_for_context, get_activity_recommendation 

# DB에 이미지 URL 저장을 위해 필드 추가
@database_sync_to_async
def save_message(user, content, sender, image_url=None):
    ChatMessage.objects.create(
        user=user, 
        content=content, 
        sender=sender, 
        image_url=image_url # 이미지 URL 필드 추가
    )
    
# Base64 데이터를 디코딩하고 파일로 저장/업로드하는 더미 비동기 함수
@database_sync_to_async
def save_base64_image_and_get_url(user_id, base64_data):
    """
    Base64 데이터를 디코딩하여 서버/S3에 저장하고, 저장된 이미지의 URL을 반환합니다.
    (실제 S3/Storage 로직으로 대체해야 합니다.)
    """
    import uuid
    import time
    
    # Base64 MIME 타입 헤더 제거
    if ';base64,' in base64_data:
        _, image_data = base64_data.split(';base64,')
    else:
        image_data = base64_data
    
    # Base64 디코딩
    try:
        decoded_image_bytes = base64.b64decode(image_data)
    except Exception as e:
        print(f"Base64 디코딩 오류: {e}")
        return None, None # 오류 발생 시 None 반환

    # [TODO: S3/Storage 실제 업로드 로직]
    # 실제 환경에서는 S3에 업로드하고 외부 URL 반환
    final_image_url = f"https://your-storage.com/images/user_{user_id}_{int(time.time())}.jpg"
    
    # LLM에 전달할 이미지 바이트
    # Base64 문자열 자체를 전달해도 되고, 바이트를 전달해도 됩니다.
    # 여기서는 Base64 문자열을 그대로 반환하여 AI 서비스에서 처리한다고 가정
    return final_image_url, image_data # Base64 문자열 반환

User = get_user_model()

class ChatConsumer(AsyncWebsocketConsumer):
    # 연결 수립 (인증 및 초기 설정)
    async def connect(self):
        """WebSocket 연결을 수락하고 JWT 인증 및 사용자 데이터를 로드합니다."""
        self.ai_service = None
        self.user = None # 초기화
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
            
    # 메시지 수신 (GPT API 호출 및 스트리밍 응답)
    async def receive(self, text_data):
        # 🚨 [CRITICAL FIX] 최상위 try-except 블록을 사용하여 Consumer가 죽는 것을 방지
        try:
            if not self.ai_service:
                await self.send(text_data=json.dumps({"type": "error", "message": "Service not initialized."}))
                return
            
            # 💡 [FIX 1] UnboundLocalError 방지를 위해 변수 초기화
            final_image_url = None
            user_image_data_for_ai = None
            
            data = json.loads(text_data)
            message_type = data.get('type') 
            user_message = data.get('message')
            
            #  Flutter에서 전송한 필드들
            image_base64 = data.get('image_base64')
            chat_history = data.get('history', []) # JSON 배열 형태 (사용하지 않음)
            
            # 메시지 타입 및 내용 유효성 검사
            if message_type != 'chat_message' or not user_message:
                if not image_base64: # 이미지도 메시지도 없으면 무시
                    await self.send(text_data=json.dumps({"type": "error", "message": "Invalid message format or empty message."}))
                    return
                
            
            # -----------------------------------------------------------------
            # [신규] Base64 이미지 처리 및 URL 획득
            # -----------------------------------------------------------------
            
            if image_base64:
                # 비동기로 DB/S3에 이미지를 저장하고 최종 URL과 Base64 데이터를 획득
                try:
                    # 💡 [FIX 1] 초기화된 변수에 할당
                    final_image_url, user_image_data_for_ai = await save_base64_image_and_get_url(
                        self.user.id, 
                        image_base64
                    )
                    if not final_image_url:
                          # 이미지 저장 실패는 여기서 처리하여 아래에서 raise Exception을 피함
                        print("이미지 저장/업로드 실패: URL이 반환되지 않았습니다.")
                        user_image_data_for_ai = None # AI에 전달할 데이터도 무효화
                    
                    # 💡 Base64 데이터를 전달하기 위해 user_image_data_for_ai만 AI 서비스에 사용합니다.
                    
                except Exception as e:
                    print(f"이미지 처리 과정 중 예외 발생: {e}")
                    # 예외 발생 시 크래시를 막고 None으로 처리하여 진행
                    final_image_url = None
                    user_image_data_for_ai = None
                
            
            # -----------------------------------------------------------------
            # [컨텍스트 검색 및 추가] - RAG Service로 통합되어 사용되지 않음
            # -----------------------------------------------------------------
            
            # 1. 활동 기록 검색 (사용자의 과거 메모, 장소 등 검색)
            activity_context = await database_sync_to_async(search_activities_for_context)(self.user, user_message)         
            # 2. 활동 추천 컨텍스트 (최근 방문 장소 분석)
            recommendation_context = await database_sync_to_async(get_activity_recommendation)(self.user, user_message)
            
            # 3. 컨텍스트 조합 (LLM System Context에 추가될 부분)
            # 이 코드는 AI Service 내부로 이동했기 때문에 더 이상 사용되지 않습니다.
            context_list = []
            if activity_context:
                context_list.append(activity_context)
            if recommendation_context:
                context_list.append(recommendation_context)
                
            final_system_context = "\n".join(context_list)
            if final_system_context:
                final_system_context = final_system_context.strip()
            else:
                final_system_context = None 
            
            # -----------------------------------------------------------------
            # [AI 서비스 호출 및 스트리밍]
            # -----------------------------------------------------------------
            
            # 💡 [CRITICAL FIX] AIPersonaService.get_ai_response_stream의 시그니처 수정
            # 1. chat_history (위치 인수) 제거: 서비스가 내부적으로 관리
            # 2. system_context (키워드 인수) 제거: 서비스가 내부적으로 RAG 컨텍스트를 빌드
            stream_generator = self.ai_service.get_ai_response_stream(
                user_message=user_message,
                image_base64=user_image_data_for_ai # 이제 유일하게 남은 키워드 인수
            )
            
            # 사용자 메시지 DB 저장 시 image_url도 함께 저장 (이미지 처리가 성공했을 경우에만 URL이 존재)
            await save_message(self.user, user_message, 'user', image_url=final_image_url)
            
            # 스트림 처리
            full_ai_response_chunks = []  # AI 응답 청크를 조립(저장)하기 위한 변수
            async for chunk in stream_generator:
                await self.send(text_data=json.dumps({
                    "type": "chat_message",
                    "message": chunk
                }))
                # 서버에 청크 저장 (조립)
                full_ai_response_chunks.append(chunk)

            # 스트리밍 완료 후, 모든 청크를 하나의 문자열로 결합
            final_bot_message = "".join(full_ai_response_chunks)

            # AI 메시지 DB 저장 (AI 메시지는 이미지 URL을 저장하지 않음)
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
            # 💡 [DEBUGGING] 상세 에러 출력을 위해 traceback.format_exc()를 사용
            print(f"--- [CRITICAL CONSUMER CRASH] Unhandled Exception in receive: ---")
            print(traceback.format_exc()) 
            
            # 오류 발생 시 클라이언트에 에러 알림 후 '슬픔' 감정 전송
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": f"Server Error: {type(e).__name__}. Check console logs."
            }))
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
