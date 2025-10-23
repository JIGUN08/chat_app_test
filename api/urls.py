# app_server/api/urls.py

from django.urls import path
from . import views
from .views import RegisterView, LoginView, LogoutView

urlpatterns = [
    # 실제 Flutter 앱이 요청할 엔드포인트
    path('auth/register/', RegisterView.as_view(), name='register'), 
    path('auth/login/', LoginView.as_view(), name='login'),       
    path('auth/logout/', LogoutView.as_view(), name='logout'),      
    path('proactive_message/', views.proactive_message_view, name='proactive_message')
]
