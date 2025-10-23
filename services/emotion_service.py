#app_server/services/emotion_service.py

import os
import torch
from transformers import pipeline

class EmotionAnalyzer:
    """
    Hugging Face의 사전 훈련된 모델을 사용하여 감정 분석을 수행하는 클래스.
    모델 로딩은 리소스가 많이 소모되므로, 클래스 인스턴스 생성 시 한 번만 수행됩니다.
    """
    def __init__(self):
        self.classifier = None
        try:
            self.classifier = pipeline("text-classification", model="dlckdfuf141/korean-emotion-kluebert-v2", top_k=None)
            print("--- EmotionAnalyzer model loaded successfully. ---")
        except Exception as e:
            print(f"--- Failed to load EmotionAnalyzer model: {e} ---")

    def analyze(self, text: str):
        """
        주어진 텍스트의 감정을 분석하고, 모든 감정 레이블과 점수를 반환합니다.
        """
        if not self.classifier or not isinstance(text, str) or not text.strip():
            return []
        
        try:
            emotion_scores = self.classifier(text)[0]
            emotion_scores.sort(key=lambda x: x['score'], reverse=True)
            return emotion_scores
        except Exception as e:
            print(f"--- Emotion analysis failed for text '{text}': {e} ---")
            return []

# Django 앱이 로드될 때 단 하나의 분석기 인스턴스만 생성하고 재사용합니다.
emotion_analyzer_instance = EmotionAnalyzer()

def analyze_emotion(bot_message_text: str) -> str:
    """
    AI의 메시지를 분석하여 모델이 예측한 최종 감정 라벨(문자열)을 반환합니다.
    """
    default_model_label = "중립"

    try:
        emotion_results = emotion_analyzer_instance.analyze(bot_message_text)

        if not emotion_results:
            return default_model_label

        ID_TO_LABEL_MAP = {
            0: '공포', 1: '놀람', 2: '분노', 3: '슬픔', 4: '중립', 5: '행복', 6: '혐오'
        }

        # 모델 결과에서 가장 확률이 높은 레이블(예: '3')을 가져옵니다.
        top_label_str = emotion_results[0]['label']
        
        # 문자열 레이블을 정수로 변환합니다.
        top_label_int = int(top_label_str)

        # 맵을 사용해 최종 감정 문자열을 찾습니다.
        final_label = ID_TO_LABEL_MAP.get(top_label_int, default_model_label)

        print(f"\n--- Emotion Analysis (Refactored) ---")
        print(f"Message: {bot_message_text}")
        print(f"Top Emotion ID: {top_label_int} -> Final Label: {final_label}")
        print(f"---------------------------------")

        return final_label

    except (ValueError, TypeError, IndexError) as e:
        print(f"--- Emotion Service Error during processing: {e} ---")
        return default_model_label
