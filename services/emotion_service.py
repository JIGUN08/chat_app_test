# app_server/services/emotion_service.py

import os
import json
import re
from openai import OpenAI

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class EmotionAnalyzer:
    """
    기존 구조 그대로 유지.
    GPT 모델을 내부적으로 사용해 감정 점수를 계산하는 클래스.
    """
    def __init__(self):
        self.classifier = True  # 기존 호환성 유지를 위해 더미 값 유지
        print("--- EmotionAnalyzer (GPT API version) initialized successfully. ---")

    def analyze(self, text: str):
        """
        주어진 텍스트의 감정을 분석하고, 모든 감정 레이블과 점수를 반환합니다.
        반환 형식:
        [
            {"label": "0", "score": 0.05},
            {"label": "1", "score": 0.10},
            {"label": "2", "score": 0.07},
            {"label": "3", "score": 0.15},
            {"label": "4", "score": 0.40},
            {"label": "5", "score": 0.18},
            {"label": "6", "score": 0.05}
        ]
        """
        if not self.classifier or not isinstance(text, str) or not text.strip():
            return []

        try:
            prompt = f"""
            아래 문장의 감정을 각각의 점수(0~1)로 평가하세요.
            가능한 감정은 다음 7가지입니다:
            0: 공포, 1: 놀람, 2: 분노, 3: 슬픔, 4: 중립, 5: 행복, 6: 혐오

            문장: "{text}"

            각 감정에 대해 확률처럼 보이는 점수를 부여한 뒤,
            아래 JSON 배열 형식으로 출력하세요.
            예시:
            [
              {{"label": "0", "score": 0.05}},
              {{"label": "1", "score": 0.12}},
              {{"label": "2", "score": 0.08}},
              {{"label": "3", "score": 0.20}},
              {{"label": "4", "score": 0.40}},
              {{"label": "5", "score": 0.10}},
              {{"label": "6", "score": 0.05}}
            ]
            """

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 한국어 감정 분석 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )

            result_text = response.choices[0].message.content.strip()
            json_match = re.search(r"\[.*\]", result_text, re.DOTALL)

            if not json_match:
                print(f"--- Invalid GPT response format: {result_text} ---")
                return []

            emotion_scores = json.loads(json_match.group())

            # 점수 내림차순 정렬
            emotion_scores.sort(key=lambda x: x["score"], reverse=True)
            return emotion_scores

        except Exception as e:
            print(f"--- Emotion analysis failed for text '{text}': {e} ---")
            return []


# ✅ Django 앱 로드 시 1회만 인스턴스 생성
emotion_analyzer_instance = EmotionAnalyzer()


def analyze_emotion(bot_message_text: str) -> str:
    """
    기존 analyze_emotion 로직도 그대로 유지.
    GPT가 예측한 결과 중 가장 높은 감정 ID를 변환하여 반환.
    """
    default_model_label = "중립"

    try:
        emotion_results = emotion_analyzer_instance.analyze(bot_message_text)

        if not emotion_results:
            return default_model_label

        ID_TO_LABEL_MAP = {
            0: "공포", 1: "놀람", 2: "분노", 3: "슬픔",
            4: "중립", 5: "행복", 6: "혐오"
        }

        # 기존과 동일: 최고 점수의 레이블 선택
        top_label_str = emotion_results[0]["label"]
        top_label_int = int(top_label_str)
        final_label = ID_TO_LABEL_MAP.get(top_label_int, default_model_label)

        print(f"\n--- Emotion Analysis (GPT API, Original Structure) ---")
        print(f"Message: {bot_message_text}")
        print(f"Top Emotion ID: {top_label_int} -> Final Label: {final_label}")
        print(f"---------------------------------------------")

        return final_label

    except (ValueError, TypeError, IndexError) as e:
        print(f"--- Emotion Service Error during processing: {e} ---")
        return default_model_label
