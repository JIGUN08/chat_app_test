# app_server/app_server/urls.py

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse # 추가

def root_status_view(request):
    return JsonResponse({"status": "ok", "message": "API is alive (via root)"})

urlpatterns = [
    path('', root_status_view),
    path('admin/', admin.site.urls),
    # 💡 핵심: api 앱의 모든 URL을 'api/' 경로 아래에 포함
    path('api/', include('api.urls')), 
]
