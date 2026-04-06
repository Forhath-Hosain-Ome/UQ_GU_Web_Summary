from pathlib import Path
from datetime import timedelta
import os
import sys
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# Allow importing the top-level workspace `analysis` package from backend code.
WORKSPACE_ROOT = BASE_DIR.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-bybxt97-yxn5dgy73aljwqk$u41f(af%eiwcx!bj9#$tp2aj%n'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'backend',
    # Add your production domain here, e.g. 'myapp.example.com'
]


# Application definition

INSTALLED_APPS = [
    'daphne',
    'channels',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',

    'puma_summary.apps.PumaSummaryConfig',
    'image_processor.apps.ImageProcessorConfig',
    'final_summary.apps.FinalSummaryConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'summary_backend.urls'

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
    # All endpoints require a valid JWT access token by default.
    # Individual views can override with AllowAny if needed.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        
        "rest_framework.authentication.SessionAuthentication",  
        "rest_framework.authentication.BasicAuthentication",    
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
 
    # Pagination — BatchListView uses 20, ReportListView uses 50
    # (each view overrides page_size via paginate_by / pagination_class)
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
 
    # Consistent error format for React
    "EXCEPTION_HANDLER": "rest_framework.views.exception_handler",
 
    # Date/time formatting
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DATE_FORMAT":     "%Y-%m-%d",
}

# ── Simple JWT ────────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    # Access token expires in 1 hour — user must use refresh token to renew.
    # Refresh token expires in 1 day — re-login required every 24 hours.
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
 
    "ROTATE_REFRESH_TOKENS":    True,   # issue a new refresh token on every refresh
    "BLACKLIST_AFTER_ROTATION": True,   # invalidate old refresh token immediately
                                        # requires 'rest_framework_simplejwt.token_blacklist'
                                        # in INSTALLED_APPS + migration
 
    "ALGORITHM":              "HS256",
    "AUTH_HEADER_TYPES":      ("Bearer",),
    "AUTH_HEADER_NAME":       "HTTP_AUTHORIZATION",
    "USER_ID_FIELD":          "id",
    "USER_ID_CLAIM":          "user_id",
 
    "TOKEN_OBTAIN_SERIALIZER":  "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",
}

# ── Django Channels ───────────────────────────────────────────────────────────
WSGI_APPLICATION = 'summary_backend.wsgi.application'
ASGI_APPLICATION = 'summary_backend.asgi.application'   # adjust to your project name
 
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(os.getenv('REDIS_HOST', '127.0.0.1'), int(os.getenv('REDIS_PORT', 6379)))],
            # Optional tuning
            "capacity":  1500,   # max messages queued per channel
            "expiry":    60,     # seconds before unread messages are dropped
        },
    }
}

# ── CORS (React dev server) ────────────────────────────────────────────────────
# Allow the React dev server to call the API without CORS errors.
# In production, replace with your actual frontend domain.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite default
    "http://localhost:3000",   # CRA default
    os.getenv('DJANGO_ALLOWED_HOST', '')
]

# Allow credentials (cookies, authorization headers) for cross-origin requests
CORS_ALLOW_CREDENTIALS = True

# Allow the Authorization header so Bearer tokens work cross-origin
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

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

WSGI_APPLICATION = 'summary_backend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Templates files

TEMPLATE_URL = "/media/templates/"
TEMPLATE_ROOT = MEDIA_ROOT / "templates"

# Log files

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)  
LOG_FILE = LOG_DIR / "app.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": LOG_FILE,
        },
    },

    "loggers": {
        "puma_summary": {
            "handlers": ["file"],
            "level": "INFO",
            "propagate": True,
        },
        "pdf": {
            "handlers": ["file"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

PUMA_SETTINGS = {
    "CERTIFICATE_TEMPLATE_PATH": TEMPLATE_ROOT / "CERTIFICATE.docx",
    "OUTPUT_DIR":        BASE_DIR / "media/output/puma",
    "RENAMED_PDF_DIR":   BASE_DIR / "media/output/puma/renamed_pdfs",
    "CERTIFICATE_DIR":   BASE_DIR / "media/output/puma/certificates",
}

IMAGE_PROCESSOR_SETTINGS = {
    "DEFECT_IMAGE_TEMPLATE_PATH": TEMPLATE_ROOT / "Defec_pictures.docx",
    "OUTPUT_DIR" :        BASE_DIR / "media/output/defect_image",
    "DEFECT_PDF" :        BASE_DIR / "media/output/defect_image/renamed_pdfs",
    "DEFECT_DOCX":        BASE_DIR / "media/output/defect_image/defect_docx",
}

# Celery Setup


CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

CELERY_TASK_DEFAULT_QUEUE = 'celery'
CELERY_TASK_ROUTES = {
    'puma_summary.process_inspection_batch': {'queue': 'celery'},
    'puma_summary.retry_failed_pdfs':        {'queue': 'celery'},
    'image_processor.process_defect_docx':   {'queue': 'celery'},
    'final_summary.process_audit_upload':    {'queue': 'celery'},
}