# app_server/services/context_service.py
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from konlpy.tag import Okt
from django.db.models import Count
from api.models import UserActivity

def get_user_place_preferences(user, category_keyword):
    """
    사용자의 활동 기록을 분석하여 특정 카테고리에서 가장 자주 방문한 장소 목록을 반환합니다.
    """
    try:
        preferences = UserActivity.objects.filter(
            user=user, 
            place__icontains=category_keyword
        ).values('place').annotate(
            visit_count=Count('place')
        ).order_by('-visit_count')

        # 순수 장소 이름의 리스트를 반환 (상위 5개)
        return [item['place'] for item in preferences[:5]]
    except Exception as e:
        print(f"--- Could not get user place preferences due to an error: {e} ---")
        return []

def get_activity_recommendation(user, user_message):
    """
    사용자 메시지를 기반으로 활동 추천을 생성합니다. (활동 기록 기반)
    """
    # '추천', '갈만한' 등의 키워드가 있을 때만 작동
    if '추천' not in user_message and '갈만한' not in user_message:
        return ""

    # '카페' 추천 로직 (활동 기록 기반)
    if '카페' in user_message:
        seven_days_ago = timezone.now().date() - timedelta(days=7)
        recent_cafe_visits = UserActivity.objects.filter(
            user=user,
            place__icontains='카페',
            activity_date__gte=seven_days_ago
        ).values('place').annotate(visit_count=Count('place')).order_by('-visit_count')

        if not recent_cafe_visits:
            return ""

        most_visited = recent_cafe_visits[0]
        if most_visited['visit_count'] > 1:
            recommendation = f"이번 주에 {most_visited['place']}은(는) {most_visited['visit_count']}번이나 갔네. 오늘은 다른 곳에 가보는 건 어때? 예를 들면 새로운 동네 카페라던가."
            return f"[시스템 정보: 사용자의 활동 기록을 바탕으로 다음 추천을 생성했어. 이 내용을 참고해서 자연스럽게 제안해봐: '{recommendation}']"
            
    return ""
            
    return ""

def search_activities_for_context(user, user_message):
    """
    사용자 메시지의 키워드를 바탕으로 UserActivity를 검색하여 컨텍스트를 생성합니다.
    KoNLPy 대신 간단한 문자열 분리 로직을 사용합니다.
    """
    try:
        # 1. 사용자 메시지를 공백으로 분리하여 키워드 추출
        # KoNLPy의 명사 추출 대신, 메시지를 분리하고 2글자 이상인 단어를 키워드로 사용합니다.
        user_input_keywords = [k.strip() for k in user_message.split() if k.strip()]
        
        # 사용자 메시지 전체를 하나의 키워드로 추가하여 문맥 검색 정확도를 높입니다.
        if user_message.strip():
            user_input_keywords.append(user_message.strip())
            
        # 2. 2글자 이상인 유니크한 키워드만 사용 (노이즈 감소)
        keywords = [k for k in set(user_input_keywords) if len(k) > 1]
        
        if not keywords:
            return ""

        # 3. Q 객체를 사용하여 여러 필드에서 OR 조건으로 검색
        query = Q()
        for keyword in keywords:
            query |= Q(memo__icontains=keyword)
            query |= Q(place__icontains=keyword)
            query |= Q(companion__icontains=keyword)

        # 현재 사용자의 기억만 대상으로 검색, 최근 순으로 10개까지
        search_results = UserActivity.objects.filter(user=user).filter(query).order_by('-activity_date')[:10]

        if not search_results:
            return ""

        # 4. 검색 결과를 컨텍스트 문자열로 포맷
        result_strings = []
        for mem in search_results:
            base_string = ""
            if mem.activity_date:
                base_string = f"'{mem.activity_date.strftime('%Y-%m-%d')}'의 기억(장소: {mem.place or 'N/A'}, "
            else:
                base_string = f"'날짜 미상'의 기억(장소: {mem.place or 'N/A'}, "
            
            base_string += f"동행: {mem.companion or 'N/A'}, 메모: {mem.memo or 'N/A'})"
            result_strings.append(base_string)
        
        search_context = "[관련 기억 검색 결과: " + ", ".join(result_strings) + "]"
        return search_context

    except Exception as e:
        print(f"--- Could not perform activity search due to an error: {e} ---")
        return ""
