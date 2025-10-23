# user_profile_app/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    """
    사용자의 AI 호감도 점수와 같은 페르소나 관련 데이터를 저장하는 모델.
    이 데이터는 AI 응답의 톤을 동적으로 결정하는 데 사용됩니다.
    """
    # 🚨 수정: related_name을 'ai_profile'로 변경하여 기존 'profile' 이름과의 충돌을 회피합니다.
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_profile')

    # 💡 AI 페르소나 적용에 사용되는 핵심 필드
    # 0 (가장 낮음) ~ 100 (가장 높음) 사이의 호감도 점수
    affinity_score = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='AI 호감도 점수'
    )

    # 기타 사용자 정의 필드 (예: 선호하는 AI 언어 스타일 등)
    preferred_style = models.CharField(max_length=50, default='casual', verbose_name='선호 스타일')

    def __str__(self):
        return f"{self.user.username}'s Profile (Score: {self.affinity_score})"

    class Meta:
        verbose_name = '사용자 프로필'
        verbose_name_plural = '사용자 프로필'

# 🚨 신규 사용자 생성 시 Profile 객체를 자동으로 생성하는 시그널
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # 🚨 수정: profile 대신 'ai_profile'로 접근합니다.
        Profile.objects.create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    # 기존 사용자라도 profile이 없으면 생성 (안전장치)
    # 🚨 수정: profile 대신 'ai_profile'로 접근합니다.
    if not hasattr(instance, 'ai_profile'):
        Profile.objects.create(user=instance)
    else:
        instance.ai_profile.save()
