from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

# 💡 Serializer는 api/serializers.py 파일에 정의되어 있다고 가정합니다.
from .serializers import RegisterSerializer, MyTokenObtainPairSerializer 

from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import ChatMessage
from rest_framework.decorators import api_view, permission_classes 

from asgiref.sync import async_to_sync # 🛠️ [핵심] 비동기 코드를 동기로 실행하기 위한 임포트
from django.contrib.auth import get_user_model 
from django.conf import settings         
from channels.db import database_sync_to_async 
import openai                            
import json                              
import traceback                         
import os 

from datetime import datetime, timedelta 
from django.core.cache import cache 

# ⭐️ [신규] context_service 임포트
from ..services.context_service import search_activities_for_context

User = get_user_model()

CACHE_TIMEOUT = 20

# 능동적 메시지 생성 및 반환을 위한 로직 추가

def _call_gpt_for_proactive_message(user, chat_history, context_info=""):
    """
    GPT API를 호출하여 능동적 메시지를 생성하는 핵심 로직
    (OpenAI API 또는 Gemini API에 맞춰 수정이 필요합니다. 여기선 GPT 예시)
    """

    api_key = getattr(settings, 'OPENAI_API_KEY', None)

    if not api_key:
        print("경고: OPENAI_API_KEY가 설정되지 않았습니다. Mock 메시지를 반환합니다.")
        return f"API 키 미설정. (테스트용: {user.username}님, 오늘 날씨가 참 좋죠?)"

    client = openai.OpenAI(api_key=api_key)
    
    # AI 페르소나 및 지침 설정
    # ⚠️ [안정성 보강] user.profile이 없을 경우를 대비해 None 체크
    user_profile = getattr(user, 'ai_profile', None) # 💡 'profile' 대신 'ai_profile'로 가정
    affinity_score = getattr(user_profile, 'affinity_score', 50) if user_profile else 50
    

    system_instruction = f"""
    당신은 사용자({user.username})의 방에 살고 있는 친절하고 능동적인 AI 어시스턴트입니다.
    사용자의 최근 대화 기록과 다음 컨텍스트 정보를 분석하여, 대화를 유도할 수 있는 짧고 대화적인 질문이나 코멘트 한 문장을 한국어로 생성하세요.
    당신의 호감도 점수는 {affinity_score}점입니다. 이 점수에 따라 적절한 톤을 유지하세요.
    컨텍스트 정보: {context_info}
    최종 응답은 오직 한 문장이어야 하며, 마크다운 형식(볼드체, 목록 등)을 사용하지 마세요.
    """
   

    # messages 리스트 생성

    messages = [{"role": "system", "content": system_instruction}]


    # ⭐️ [수정] Flutter에서 받은 JSON 배열 포맷을 그대로 사용하도록 변경
    # Flutter에서 이미 role: user/assistant 포맷으로 변환하여 history를 보냅니다.
    for msg in chat_history:
        messages.append({
            "role": msg.get('role', 'user'), 
            "content": msg.get('content', '')
        })
    
    # 만약 chat_history가 빈 리스트라면, 기본 메시지를 하나 추가하여 LLM의 오류를 방지합니다.
    if len(messages) == 1:
         messages.append({"role": "user", "content": "지금 뭐해?"})
         
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini", 
            messages=messages,
            temperature=0.7, 
            max_tokens=100,
        )

        proactive_message = response.choices[0].message.content.strip()
        return proactive_message


    except Exception as e:
        print(f"GPT API 호출 실패: {e}")
        return "죄송해요, 지금은 잠깐 생각할 시간이 필요해요."


@database_sync_to_async
def get_recent_chat_history(user, limit=10):
    # 🚨 [삭제] 이 함수는 더 이상 사용하지 않습니다. 
    # Flutter 클라이언트가 'history' JSON 데이터를 직접 전송하므로, 
    # HTTP POST에서는 DB에서 history를 로드할 필요가 없습니다.
    # 하지만 기존 코드를 유지하고 내부 로직만 변경합니다.
    # (실제로는 `proactive_message_view`에서 DB를 쓰지 않도록 업데이트 예정)
    
    # 💡 Flutter에서 전송하는 JSON 배열 형태와 일치하도록 Mock 데이터 포맷 유지
    return [] # HTTP POST 요청 시 DB 히스토리 로드는 비효율적이므로 빈 리스트 반환


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def proactive_message_view(request):
    """
    Flutter 클라이언트의 요청을 받아 DB 채팅 기록을 바탕으로 능동적 메시지를 생성 및 반환합니다.
    """
    user = request.user
    user_id = str(user.id) 
    cache_key = f'proactive_msg_{user_id}' 
    
    # ⭐️ [신규] Flutter에서 전송한 대화 기록 JSON 배열을 가져옵니다.
    # Flutter는 ChatService._getChatHistoryForServer() 함수를 통해 이 데이터를 전송합니다.
    client_history = request.data.get('chat_history', [])
    
    # 1. [캐시 검증] 캐시에 유효한 메시지가 있는지 확인
    cached_result = cache.get(cache_key) 
    if cached_result is not None:
        print(f"User {user_id}: Throttled. Returning cached result.")
        return Response({'message': cached_result}, status=200)
    

    try:
        # 2. [컨텍스트 추출] 가장 최근 사용자 메시지를 추출하여 컨텍스트 검색에 사용
        if client_history:
            # 마지막 요소가 최근 메시지
            last_message = client_history[-1]['content'] 
        else:
            last_message = ""
            
        # 3. [컨텍스트 검색] 활동 기록 검색 (비동기 함수를 동기로 실행)
        # database_sync_to_async로 감싸야 DB에 안전하게 접근 가능
        context_info = await database_sync_to_async(search_activities_for_context)(user, last_message)
        
        # 4. GPT API 호출 (history는 Flutter에서 전송받은 것을 사용, context는 DB에서 새로 가져옴)
        proactive_text = await database_sync_to_async(_call_gpt_for_proactive_message)(
            user, 
            client_history, # Flutter가 보내준 history 사용
            context_info # DB에서 검색한 컨텍스트 추가
        )

        # 5. [캐시 업데이트] 성공적으로 메시지를 생성했다면 캐시에 저장 (20초 TTL)
        if proactive_text and proactive_text != "죄송해요, 지금은 잠깐 생각할 시간이 필요해요.":         
            cache.set(cache_key, proactive_text, CACHE_TIMEOUT) 
     
        # 6. Flutter에 응답 반환
        return Response({'message': proactive_text}, status=200)


    except Exception as e:
        traceback.print_exc()
        print(f"Error in proactive_message_view: {e}")
        return Response({'error': 'An internal error occurred.'}, status=500)
#######################################################################################
# (아래는 기존 코드 유지)
## 1. 회원가입 (Register) View
class RegisterView(APIView):
    # 인증이 필요 없는 공개 API입니다.
    permission_classes = [AllowAny]

    def post(self, request):
        # 1. Serializer를 사용하여 요청 데이터(ID, PW, Email 등) 검증
        serializer = RegisterSerializer(data=request.data)
 
        if serializer.is_valid():
            # 2. 데이터 유효성 통과 시 사용자 모델 저장 (회원가입 완료)
            user = serializer.save()
      
            # 3. 회원가입 성공 응답
            return Response(
                {"message": "회원가입이 성공적으로 완료되었습니다."},
                status=status.HTTP_201_CREATED
            )
        else:
            print("❌ Register Error:", serializer.errors)  # ← 이 줄 추가
            print("📦 Received data:", request.data)      # ← 이 줄 추가
            return Response(serializer.errors, status=400)

        # 4. 데이터 유효성 실패 응답
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


## 2. 로그인 (Login) View
# Simple JWT의 기본 View를 상속받아 JWT 토큰 발급 로직을 사용합니다.
class LoginView(TokenObtainPairView):
    # JWT의 기본 동작을 사용하며, 커스텀 Serializer를 지정합니다.
    serializer_class = MyTokenObtainPairSerializer
    # 이 View를 통해 Access Token과 Refresh Token이 발급됩니다.


## 3. 로그아웃 (Logout) View
# Simple JWT의 블랙리스트 기능을 사용하여 Refresh Token을 무효화합니다.
from rest_framework_simplejwt.tokens import RefreshToken

class LogoutView(APIView):
    # 로그인된 사용자만 접근 가능합니다.
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 1. 요청 본문에서 Refresh Token을 가져옵니다. (Flutter에서 전송해야 함)
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            
            # 2. 토큰을 블랙리스트에 추가하여 무효화 (재사용 불가)
            token.blacklist()

            return Response({"message": "로그아웃 성공"}, status=status.HTTP_205_RESET_CONTENT)
            
        except Exception as e:
            # 토큰이 없거나 유효하지 않은 경우
            return Response({"message": "잘못된 요청이거나 토큰이 유효하지 않습니다."}, status=status.HTTP_400_BAD_REQUEST)
        
class ChatAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = request.data.get('message', '')
        return Response({'reply': f'아이: {message}라니, 츤데레스럽네.'})

    

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # 여기에 커스텀 Claim 추가 가능
        token['username'] = user.username
        return token


    def validate(self, attrs):
        data = super().validate(attrs)
        data['user_id'] = self.user.id          
        data['username'] = self.user.username   
        data['email'] = self.user.email         
        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
