# api/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password


from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    # JWT에 사용자 관련 추가 정보를 담고 싶을 때 customize_payload 메서드를 오버라이딩합니다.
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # 💡 토큰 페이로드에 원하는 사용자 정보(예: 이메일, 닉네임)를 추가합니다.
        # 토큰을 해독하여 사용자 정보를 얻을 수 있으므로 DB 접근 횟수를 줄일 수 있습니다.
        token['username'] = user.username 
        token['email'] = user.email

        return token
    def validate(self, attrs):
        data = super().validate(attrs)

        # ✅ Flutter가 참조할 수 있도록 user_id 추가
        data['user_id'] = self.user.id
        data['username'] = self.user.username
        data['email'] = self.user.email

        return data
# Django의 기본 사용자 모델을 가져옵니다.
User = get_user_model() 

class RegisterSerializer(serializers.ModelSerializer):
    # 비밀번호는 쓰기 전용(write_only)으로 설정하여, 
    # API 응답(JSON)에는 포함되지 않도록 합니다.
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password] # Django 기본 비밀번호 유효성 검사기 사용
    )
    
    # 비밀번호 확인 필드 (데이터베이스에 저장되지 않고 검증용으로만 사용)
    password2 = serializers.CharField(
        write_only=True, 
        required=True
    )

    class Meta:
        # 이 Serializer가 User 모델을 사용함을 명시
        model = User
        # Flutter 앱으로부터 받을 필드들을 정의합니다.
        fields = ('username', 'email', 'password', 'password2')
        # 읽기 전용 필드 (선택 사항)
        extra_kwargs = {
            'email': {'required': True},
        }

    # 💡 1차 유효성 검사: password와 password2가 일치하는지 확인
    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "비밀번호가 일치하지 않습니다."})
        return attrs

    # 💡 2차 저장 로직: 데이터베이스에 저장되기 전에 비밀번호를 해싱
    def create(self, validated_data):
        # validated_data에서 password2 필드를 제외합니다.
        validated_data.pop('password2') 
        
        # User 모델 객체 생성
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'] # create_user가 자동으로 비밀번호를 해싱
        )
        return user
