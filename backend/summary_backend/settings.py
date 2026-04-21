import logging
from pathlib import Path
from datetime import timedelta
import os
import sys

BASE_DIR = Path(__file__).resolve().parent.parent

WORKSPACE_ROOT = BASE_DIR.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))



SECRET_KEY = 'django-insecure-bybxt97-yxn5dgy73aljwqk$u41f(af%eiwcx!bj9#$tp2aj%n'


DEBUG = True

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'backend',
]

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
    'corsheaders',

    'puma_summary.apps.PumaSummaryConfig',
    'image_processor.apps.ImageProcessorConfig',
    'final_summary.apps.FinalSummaryConfig',
    'top_five.apps.TopFiveConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'summary_backend.urls'

# ── Django REST Framework ─────────────────────────────────────────────────────
REST_FRAMEWORK = {
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
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
 
    "ROTATE_REFRESH_TOKENS":    True,   
    "BLACKLIST_AFTER_ROTATION": True,
 
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
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:5173",   # Vite default
#     "http://localhost:3000",   # CRA default
# ]

# extra_host = os.getenv('DJANGO_ALLOWED_HOST')
# if extra_host:
#     CORS_ALLOWED_ORIGINS.append(extra_host)

CORS_ALLOW_ALL_ORIGINS = True

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
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'summary_db'),
        'USER': os.getenv('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.getenv('POSTGRES_HOST', 'postgres'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
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



class AppUserDateHandler(logging.Handler):
    """Routes logs to logs/<app>/<username>/<date>.log"""
    def emit(self, record):
        from datetime import date
        app      = getattr(record, 'app', record.name.split('.')[0])
        username = getattr(record, 'username', 'system')
        day      = date.today().strftime('%Y-%m-%d')

        log_path = LOG_DIR / app / username
        log_path.mkdir(parents=True, exist_ok=True)

        file_path = log_path / f"{day}.log"
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(self.format(record) + '\n')

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "app_user_date": {
            "()": AppUserDateHandler,
            "formatter": "standard",
        },
    },
    "loggers": {
        "puma_summary":    {"handlers": ["app_user_date", "console"], "level": "INFO", "propagate": False},
        "image_processor": {"handlers": ["app_user_date", "console"], "level": "INFO", "propagate": False},
        "final_summary":   {"handlers": ["app_user_date", "console"], "level": "INFO", "propagate": False},
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

TOP_FIVE_SETTINGS = {
    "TOP_FIVE_TEMPLATE_PATH": TEMPLATE_ROOT / "template.xlsx",
    "OUTPUT_DIR" :        BASE_DIR / "media/output/top_five",
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
    'top_five.run_top5_job':                 {'queue': 'celery'},
}