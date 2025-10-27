# app_server/api/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Profile(models.Model):
    # user라는 이름으로 OneToOne 연결
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile') 
    affinity_score = models.IntegerField(default=50) 
    
    # 여기서 related_name이 'profile'이므로, User.objects.select_related('profile')로 접근이 가능합니다.


#  [추가] 컨텍스트 검색 로직을 위한 사용자 활동 모델
class UserActivity(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_date = models.DateField(null=True, blank=True) # 활동 날짜
    place = models.CharField(max_length=100, blank=True, null=True) # 장소
    memo = models.TextField(blank=True, null=True) # 활동 메모
    companion = models.CharField(max_length=100, blank=True, null=True) # 동행자
    
    # 생성/수정 시각 (필요하다면)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.activity_date or 'N/A'} - {self.place or 'N/A'}"
        
    class Meta:
        # 최근 활동 순으로 정렬하기 위한 메타 정보
        ordering = ['-activity_date', '-created_at']

class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    sender = models.CharField(max_length=10, choices=[('user', 'User'), ('ai', 'AI')])
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # ⭐️ [추가] 멀티모달 지원을 위한 이미지 URL 필드
    image_url = models.URLField(max_length=500, null=True, blank=True) 

    def __str__(self):
        return f"{self.user.username}: {self.content[:30]}"
