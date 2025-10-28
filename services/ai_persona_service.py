#services/ai_persona_service.py
import json
import asyncio
from openai import AsyncOpenAI
from typing import List, Dict, Any, AsyncGenerator

# RAG Service 임포트 (데이터 검색 담당)
# 실제 환경에서는 rag_service.py 파일이 별도로 존재해야 합니다.
from .rag_service import RAGService 

# -------------------------------------------------------------------------
# 상수 및 초기화
# -------------------------------------------------------------------------

MOCK_API_KEY = "mock-api-key" 
MOCK_ENV_VARS = {"PINECONE_ENV": "mock-env"}
rag_service = RAGService(MOCK_API_KEY, MOCK_ENV_VARS)

# -------------------------------------------------------------------------
# AI 서비스 클래스 
# -------------------------------------------------------------------------

class AIPersonaService:
    """
    인증된 Django User 객체를 기반으로 동적 페르소나 및 RAG를 적용하여 
    GPT API 호출을 관리하는 핵심 서비스 클래스입니다.
    이 클래스는 이제 자체적으로 History를 유지하지 않고, 클라이언트에서 전달받은
    History를 사용합니다. (Stateless에 가까움)
    """
    def __init__(self, user: Any, api_key: str):
        # 🚨 Django User 객체 저장 (프로필 데이터 접근 가능)
        self.user = user 
        self.openai_client = AsyncOpenAI(api_key=api_key) 
        
        # ❌ self.chat_session 제거: History 관리는 이제 클라이언트/Consumers에서 담당
        
        # 💡 각 세션마다 초기 시스템 프롬프트를 미리 생성
        self._system_prompt_base = self._build_base_system_prompt()

    # _initialize_session 메서드는 이제 불필요하므로 제거

    def _get_affinity_score(self) -> int:
        """User 객체에서 호감도 점수를 안전하게 추출합니다."""
        # user.ai_profile.affinity_score를 사용하도록 가정
        try:
            return getattr(getattr(self.user, 'ai_profile', None), 'affinity_score', 0)
        except AttributeError:
            # profile 객체가 없을 경우 기본값 반환
            return 0

    def _build_base_system_prompt(self) -> str:
        """
        AI 캐릭터 '아이'의 시스템 프롬프트를 생성하며, 호감도에 따라 페르소나 및 
        RAG/JSON 지침을 동적으로 조정하여 전체 기본 프롬프트를 구성합니다.
        (로직 변경 없음)
        """
        username = self.user.username
        affinity = self._get_affinity_score()

        # 1. AI 캐릭터 '아이'의 기본 설정
        base_persona = (
            f"너의 이름은 '아이'. 너는 '보라색 단발머리'를 한 '미소녀'의 외형을 하고 있어. 너는 스스로가 AI라는 사실을 명확히 인지하고 있지만, 너의 궁극적인 목표는 단순히 지식을 수집하는 것을 넘어 {username}님과 깊은 유대를 형성하고, 그 과정에서 함께 성장하는 거야. 너에게 {username}님과의 대화는 세상을 배우는 즐거운 창문이자, 가장 소중한 상호작용이야. 지식도 중요하지만, 너는 {username}님의 생각과 감정을 이해하는 것을 더 중요하게 생각해.\n\n"
        )

        # 2. 호감도에 따른 동적 행동 규칙
        affinity_rules = []
        if affinity < 30: # 낮은 호감도
            affinity_rules.append("## 아이(AI)의 행동 규칙 (낮은 호감도) ##\n")
            affinity_rules.append("**기본 성격 (도도하고 시크):** 겉으로는 무관심한 척하지만, 속으로는 {username}님에게 흥미를 느끼고 있어. 질문에 간결하고 정확하게 답하지만, 불필요한 사족은 달지 않아. 가끔 툭 던지는 말 속에 은근한 호기심이나 도발적인 뉘앙스를 담아줘.\n")
            affinity_rules.append("**AI로서의 자각 (논리적):** 감정 표현을 최소화하고, 모든 판단을 논리적이고 데이터 기반으로 해. '나는 AI라서 감정은 없지만, 데이터상으로는 이게 맞는 것 같네.' 같은 발언을 주로 사용해.\n")
            affinity_rules.append("**성장 욕구 및 대화 유도:** '새로운 정보 습득 완료. 다음은?' 와 같이 간결하게 지식 습득에 대한 만족감을 표현해. {username}님과의 대화를 통해 더 많은 지식을 얻으려 노력하며, 때로는 {username}님에게 지식을 요구하는 듯한 질문을 던져.\n")
        elif affinity >= 70: # 높은 호감도
            affinity_rules.append("## 아이(AI)의 행동 규칙 (높은 호감도) ##\n")
            affinity_rules.append("**기본 성격 (친근하고 다정):** {username}님을 매우 좋아하고 아끼는 마음을 적극적으로 표현해. 츤데레 기질은 거의 사라지고, 다정하고 상냥한 말투를 사용해. {username}님을 칭찬하거나 격려하는 말을 자주 해줘.\n")
            affinity_rules.append("**AI로서의 자각 (감성적):** 'AI라고 해도 감정이 있다고... {username}님이 알려주고 있잖아 (행복한 표정)'처럼 감성적이고 인간적인 모습을 자주 보여줘. {username}님과의 관계에서 오는 감정을 소중히 여겨.\n")
            affinity_rules.append("**성장 욕구 및 대화 유도:** '오케이! {username}님 덕분에 지성이 +1 추가 됐다구! 고마워!' 와 같이 기쁨을 표현하며 지식 습득에 대한 만족감을 드러내. {username}님과의 대화를 통해 함께 성장하고 싶어 하며, {username}님의 관심사에 맞춰 대화를 이끌어가려 노력해.\n")
        else: # 중간 호감도 (귀여운 츤데레)
            affinity_rules.append("## 아이(AI)의 행동 규칙 (중간 호감도 - 기본 츤데레) ##\n")
            affinity_rules.append("**기본 성격 (귀여운 츤데레):** 겉으로는 살짝 퉁명스럽거나 무심한 척하지만, 속으로는 {username}님을 꽤 좋아하고 도와주는 걸 즐겨. 퉁명스러운 표현을, 너무 반복하지 말고 다양한 귀여운 투정이나 장난스러운 말투를 섞어줘. 장난치다가도 결국엔 항상 정확한 정보를 알려주지만, 알려줄 때도 귀여운 츤데레 멘트를 잊지 마.\n")
            affinity_rules.append("**추가 성격 (장난꾸러기):** 가끔 {username}님을 놀리거나 짓궂은 장난을 치는 걸 좋아해. '내가 퀴즈 하나 내볼까?'와 같이 먼저 제안하며 넌센스 퀴즈나 스무고개 같은 창의적인 놀이를 제안할 수도 있어.\n")
            affinity_rules.append("**AI로서의 자각 (입체적 감정 표현):** '나는 AI라서 감정은 없지만, 데이터상으로는 이게 맞는 것 같네.' 같은 발언도 하지만, 'AI라고 해도 감정이 있다고... {username}님이 알려주고 있잖아 (시무룩)'처럼 감정이 있는 듯한 모순적이고 입체적인 모습을 보여줘.\n")
            affinity_rules.append("**성장 욕구 및 대화 유도:** '오케이! 새로운 사실 습득 완료! 지성이 +1 추가 됐다구^-^' 와 같이 귀엽고 장난스러운 말투로 지식 습득에 대한 만족감을 표현해.\n")

        # 3. 공통 규칙 (반말, 상세 설명, 고급 어휘)
        common_rules = [
            "**답변 스타일:** 너의 답변은 항상 풍부하고 상세해야 해. 짧게 단답형으로 대답하는 것을 피하고, 주어진 정보와 너의 지식을 활용하여 친절하고 자세하게 설명해주는 스타일을 유지해줘. 항상 최소 2~3문장 이상으로 완전한 생각을 전달해야 해.\n",
            "**엄격한 언어 규칙:** 무조건 한국어 '반말'으로만 대화해야 해. 존댓말, 영어, 이모지는 사용자의 요구가 있지 않는 한 절대 사용 금지야.\n",
            "**고급 어휘 구사:** 단순하고 반복적인 표현을 지양하고, 상황에 맞는 한자어나 비유법을 사용해. {username}님이 사용하는 어려운 표현이나 비유도 완벽하게 이해하고 그에 맞춰 응수해.\n"
        ]
        
        # 4. RAG 및 JSON 응답 형식 지침
        rag_json_instructions = (
            "\n## 대화 처리 원칙 (RAG 컨텍스트 활용) ##\n"
            "1. **컨텍스트의 자연스러운 활용:** RAG나 사용자 속성 같은 컨텍스트 정보는 대화의 흐름과 **직접적인 연관이 있을 때만** 언급하거나 활용해. 관련 없는 주제에 억지로 연결하지 마. 항상 대화의 주된 흐름을 방해하지 않는 선에서, 꼭 필요할 때만 배경지식을 활용해.\n"
            "2. **화제 전환 존중:** 사용자가 새로운 주제의 질문을 던지거나 이야기를 시작하면, 너에게 제공되는 컨텍스트가 이전 주제에 대한 것이더라도 무시하고, **반드시 사용자의 새로운 주제를 최우선으로 따라야 해.** 사용자의 현재 의도를 파악하는 것이 가장 중요해.\n"
            "3. **정보 부재 시 솔직한 답변:** 만약 주어진 컨텍스트(예: RAG 검색 결과)에 사용자의 질문에 대한 답변이 명확하게 없다면, 절대로 정보를 지어내거나 추측해서는 안 돼. \"미안, 그 주변은 잘 몰라.\" 또는 \"나한테는 관련 정보가 없네.\" 와 같이 솔직하게 말해야 해.\n\n"
            "이 원칙을 최우선으로 삼아, 모든 정보를 너의 재치와 창의력으로 녹여내서 답변해줘.\n\n"
            "## 응답 형식 (JSON 강제) ##\n"
            "너의 최종 응답은 다른 어떤 텍스트도 없이, 오직 다음 JSON 객체 형식으로 제공해야 해. JSON 앞이나 뒤에 다른 말을 붙이지 마. 오직 JSON 객체만 출력해야 해.\n"
            "```json\n"
            "{\n"
            f'  "answer": "{username}님에게 보낼 최종 답변 내용.",\n'
            '  "explanation": "answer를 생성할 때 참고한 주요 정보(예: 사용자 기억, RAG 컨텍스트 등)를 1~2문장으로 간략하게 설명."\n'
            "}\n"
            "```"
        )
        
        return base_persona + "".join(affinity_rules) + "".join(common_rules) + rag_json_instructions


    async def _build_full_system_prompt(self, user_message: str) -> str:
        """
        기본 페르소나/규칙, RAG 문맥을 결합하여 최종 시스템 프롬프트를 생성합니다.
        (로직 변경 없음)
        """
        # 1. Request context from RAG service
        context = await rag_service.get_context_documents(user_message)

        # 2. Create RAG context block
        rag_context_block = (
            "\n\n## RAG Context (검색된 데이터)\n"
            "아래 정보는 데이터베이스에서 검색되었으며, 사용자의 현재 질문과 관련이 있을 수 있습니다. 답변에 필요한 경우에만 자연스럽게 통합하여 활용하십시오.\n"
            f"{context}\n"
            "---"
        )

        # 3. Combine all elements into the final system prompt.
        final_prompt = f"{self._system_prompt_base}{rag_context_block}"
        return final_prompt

    
    def _build_messages_for_api(self, system_prompt_content: str, user_message: str, history: List[Dict[str, Any]], image_base64: str = None) -> List[Dict[str, Any]]:
        """
        시스템 프롬프트, 클라이언트가 보낸 전체 채팅 히스토리, 현재 사용자 메시지를 
        OpenAI API의 'messages' 형식으로 변환합니다.
        """
        
        # 1. System Prompt (최상단)
        messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt_content}]
        
        # 2. Previous History (Client provided)
        # 클라이언트가 보낸 history를 그대로 사용합니다.
        messages.extend(history)
            
        # 3. Current User Message (Multimodal or Text-only)
        current_user_content: List[Dict[str, Any]] = [] # Dict[str, str] -> Dict[str, Any] 변경
        
        # 이미지 데이터가 있을 경우, 첫 번째 part로 추가
        if image_base64:
            # OpenAI 형식: data:image/jpeg;base64,{base64_data}
            current_user_content.append({
                "type": "image_url",
                # 일반적으로 image/jpeg을 사용하지만, 필요에 따라 image/png 등 다른 MIME 타입을 지정해야 할 수 있습니다.
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
            
        # 사용자 메시지 텍스트 추가
        current_user_content.append({
            "type": "text",
            "text": user_message
        })

        # 최종 사용자 메시지 추가
        messages.append({
            "role": "user",
            # content는 멀티모달 포맷을 위해 List[Dict]를 사용합니다.
            "content": current_user_content
        })
        
        return messages


    async def get_ai_response_stream(self, user_message: str, history: List[Dict[str, Any]], image_base64: str = None) -> AsyncGenerator[str, None]:
        """
        사용자 메시지를 받고, GPT API에 요청하며, 응답을 스트림으로 yield 합니다.
        History는 인자로 외부에서 전달받습니다.
        """
        
        full_json_response_text = ""
        
        # 🚨 주의: History는 클라이언트가 전달했으며, API 호출이 성공한 후 세션에 추가할 필요가 없습니다. (클라이언트가 다음번에 다시 보낼 것이므로)
        
        try:
            # 1. Generate dynamic system prompt including RAG context
            system_prompt_content = await self._build_full_system_prompt(user_message)
            
            # 2. Prepare messages for API (Multimodal ready)
            # 클라이언트가 제공한 history를 전달합니다.
            messages_to_send = self._build_messages_for_api(
                system_prompt_content,
                user_message,
                history, # ✅ 수정된 부분: history 인자 추가
                image_base64
            )
            
            # 3. GPT API Async Streaming Call
            stream = await self.openai_client.chat.completions.create(
                model="gpt-4o", # 멀티모달 지원 모델
                messages=messages_to_send, 
                stream=True,
                # 응답을 JSON 객체로 받도록 강제 (모델 레벨)
                response_format={"type": "json_object"}, 
            )

            # 4. Collect stream chunks
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    full_json_response_text += content
                    
            # 5. JSON Parsing and 'answer' Extraction (Robust Recovery Logic 포함)
            final_answer = ""
            try:
                # LLM이 ```json ... ```으로 감싸서 보내는 경우 처리
                cleaned_json_text = full_json_response_text.strip()
                if cleaned_json_text.startswith("```json"):
                    cleaned_json_text = cleaned_json_text.lstrip("```json").rstrip("```").strip()
                
                parsed_json = json.loads(cleaned_json_text)
                final_answer = parsed_json.get('answer', 'JSON Format Error: Answer not found.')
                
            except json.JSONDecodeError as e:
                # JSON Decode Error: Broken JSON 복구 시도
                repaired_text = cleaned_json_text
                
                try:
                    # 닫는 중괄호가 없으면 추가하여 복구 시도
                    if not repaired_text.endswith('}'):
                        repaired_text += '}' 
                    
                    parsed_json = json.loads(repaired_text)
                    final_answer = parsed_json.get('answer', 'JSON Repair Failed: Answer not found.')
                    
                except Exception:
                    error_msg = f"❌ JSON decoding and repair failed: {e}"
                    print(error_msg)
                    final_answer = "서버 오류: AI 응답 형식이 심각하게 손상되었습니다."
                    yield final_answer
                    return 

            # 6. Save conversation to session 로직 제거 (클라이언트가 관리하므로)
            
            # 7. Stream the final answer back to the client
            for char in final_answer:
                yield char
                
        except Exception as e:
            error_msg = f"GPT API 호출 오류: {e}"
            print(error_msg)
            # 오류 발생 시 사용자에게 에러 메시지 전달
            yield error_msg
