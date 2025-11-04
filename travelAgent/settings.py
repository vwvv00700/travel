from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()  # .env 파일에서 환경 변수 로드

# 2. 지원할 언어 정의 (언어 코드와 이름)
LANGUAGES = [
    ('ko', 'Korean'),  # 한국어
    ('en', 'English'), # 영어
    ('es', 'Spanish'), # 스페인어
]

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale'),
]

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise Exception('SECRET_KEY 환경변수가 설정되어 있지 않습니다. .env 파일을 확인하세요.')

DEBUG = True
ALLOWED_HOSTS = []

# === 앱 정의 ===
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "import_export",
    "travel.apps.TravelConfig",
    'channels',       # ✅ Channels 필수
]

MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    'django.middleware.locale.LocaleMiddleware',
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "travelAgent.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "travel_file": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "travel.log"),   # 문자열로 명시
            "encoding": "utf-8",
            "formatter": "verbose",
        },
        "user_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "user.log"),     # 문자열로 명시
            "encoding": "utf-8",
            "formatter": "verbose",
        },
    },
    "loggers": {
        # Django 기본 로그 (필요시 파일로도 남기려면 handlers에 travel_file 추가)
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        # 커스텀 로거 (views 등에서 getLogger('travelAgent') 사용)
        "travelAgent": {
            "handlers": ["travel_file", "console"],  # 파일 + 콘솔 둘 다 출력
            "level": "DEBUG",
            "propagate": False,
        },
        "user": {
            "handlers": ["user_file", "console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    # 선택사항: 루트 로거 (안 쓰면 생략 가능)
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

WSGI_APPLICATION = 'travelAgent.wsgi.application'
ASGI_APPLICATION = 'travelAgent.asgi.application'  # ✅ Channels용 ASGI

# === 데이터베이스 ===
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
    "diary_db": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "diary_db.sqlite3",
    },
    "chat_db": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "chat_db.sqlite3",
    }
}

DATABASE_ROUTERS = [
    'travelAgent.db_routers.DiaryRouter',
    'travelAgent.db_routers.ChatRouter'
]

# === 비밀번호 검증 ===
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]

LANGUAGE_CODE = "ko"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles" 
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DATA_DIR = BASE_DIR / "data"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === Channels 설정 ===
CHANNEL_LAYERS = {
    'default': {
        "BACKEND": "channels.layers.InMemoryChannelLayer"  # ✅ 개발용, Redis 불필요
    }
}

MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN", "")

# === 로그인/세션 설정 ===
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 1800  # 30분
SESSION_SAVE_EVERY_REQUEST = True
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]