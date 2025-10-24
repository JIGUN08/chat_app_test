from datetime import timedelta 
import os
import dj_database_url # 💡 추가: Render DB 설정을 위해 필요합니다.
from pathlib import Path
from dotenv import load_dotenv
load_dotenv() 

# 환경 변수에서 Redis URL을 가져옵니다. Render Redis를 연결하면 자동으로 설정됩니다.
REDIS_URL = os.environ.get("REDIS_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECRET_KEY는 환경 변수에서 가져오도록 변경합니다. (보안 강화)
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-o51sdqp4+z@uj02rjcn-&8&8mguv*aah@cgu&0ep9i2-jk$j%3')

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG 모드는 환경 변수에 따라 설정됩니다. (Production 환경에서는 False)
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

# ALLOWED_HOSTS는 Render 서비스 URL을 포함하도록 환경 변수를 사용하거나 와일드카드를 사용합니다.
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'api',
    'user_profile_app',
    'corsheaders',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # WhiteNoise 추가
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = True 

CSRF_TRUSTED_ORIGINS = [
    'https://*.example.com',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://127.0.0.1',
    # Render URL을 포함하도록 설정
    os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    )
}

ROOT_URLCONF = 'app_server.urls'

# 🚀 Redis URL이 정의된 경우 Channels Redis를 사용합니다.
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.pubsub.RedisPubSubChannelLayer",
            "CONFIG": {
                # 환경 변수 REDIS_URL을 사용하여 hosts를 설정합니다.
                # Redis URL이 'redis://...' 형식일 경우, channels_redis가 자동으로 파싱합니다.
                "hosts": [REDIS_URL],
            },
        },
    }
else:
    # REDIS_URL이 없는 경우 (개발 환경 등) 기본 인메모리 채널 레이어를 사용합니다.
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'app_server.wsgi.application'

# Database - Render PostgreSQL 또는 SQLite3 설정
# Render는 DATABASE_URL 환경 변수를 제공합니다.
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///' + os.path.join(BASE_DIR, 'db.sqlite3'),
        conn_max_age=600
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# 💡 이 부분이 문법적으로 완벽하게 닫혔는지 확인했습니다.
SIMPLE_JWT = {
    # 사용자님의 목표(오랜 자리 비움)에 맞춰 수명을 8시간으로 연장
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8), 
    
    # Refresh Token은 기본값(1일)으로 유지해도 무방합니다.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1), 
}

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Production 환경을 위한 WhiteNoise 설정
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
