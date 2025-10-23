# app_server/api/models.py (예시)
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Profile(models.Model):
    # user라는 이름으로 OneToOne 연결
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile') 
    affinity_score = models.IntegerField(default=50) 
    
    # 💡 여기서 related_name이 'profile'이므로, User.objects.select_related('profile')로 접근이 가능합니다.




############                  22일 수정 내용              ################
class ChatMessage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    sender = models.CharField(max_length=10, choices=[('user', 'User'), ('ai', 'AI')])
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}: {self.content[:30]}"
