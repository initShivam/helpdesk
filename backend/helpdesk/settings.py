"""Django settings for helpdesk project.

Generated via Context7 documentation for Django 5.x.
"""
import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / '.env')

DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').strip().lower()
IS_PRODUCTION = DJANGO_ENV == 'production'
_secret_key = os.getenv('DJANGO_SECRET_KEY', '')
if IS_PRODUCTION and (not _secret_key or _secret_key == 'replace-this-with-a-secure-key'):
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set to a unique secret in production.')
SECRET_KEY = _secret_key or 'replace-this-with-a-secure-key'

# Outbound support notifications use the configured Gmail mailbox by default.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_SMTP_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_SMTP_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_SMTP_USE_TLS', 'True').lower() == 'true'
EMAIL_USE_SSL = os.getenv('EMAIL_SMTP_USE_SSL', 'False').lower() == 'true'
EMAIL_HOST_USER = (
    os.getenv('EMAIL_SMTP_USERNAME', '').strip()
    or os.getenv('EMAIL_IMAP_USERNAME', '').strip()
)
EMAIL_HOST_PASSWORD = (
    os.getenv('EMAIL_SMTP_APP_PASSWORD', '').strip()
    or os.getenv('EMAIL_IMAP_PASSWORD', '').strip()
)
DEFAULT_FROM_EMAIL = (
    os.getenv('EMAIL_FROM_ADDRESS', '').strip()
    or EMAIL_HOST_USER
    or 'helpdesk@example.com'
)
EMAIL_TIMEOUT = int(os.getenv('EMAIL_SMTP_TIMEOUT_SECONDS', '15'))

# Keep production safe by default and refuse an explicit unsafe override.
DEBUG = os.getenv('DJANGO_DEBUG', 'False' if IS_PRODUCTION else 'True').lower() == 'true'
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured('DJANGO_DEBUG must be False when DJANGO_ENV=production.')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if host.strip()
]

if os.getenv('RENDER_EXTERNAL_HOSTNAME'):
    ALLOWED_HOSTS.append(os.getenv('RENDER_EXTERNAL_HOSTNAME'))
if IS_PRODUCTION and (not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('Set DJANGO_ALLOWED_HOSTS to explicit production hostnames.')
LOG_LEVEL = os.getenv('DJANGO_LOG_LEVEL', 'INFO')
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': LOG_LEVEL,
    },
}

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third‑party
    'rest_framework',
    'django_filters',
    'corsheaders',
    'django_prometheus',
    # Local apps
    'tickets',
    'accounts',
    'email_ingestion',
    'knowledge_base',
]

MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'helpdesk.middleware.AuditLogMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

# Session Security
SESSION_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = 'None' if IS_PRODUCTION else 'Lax'
SESSION_COOKIE_AGE = int(
    os.getenv('SESSION_COOKIE_AGE', '28800' if IS_PRODUCTION else '1209600')
)


# CSRF Security
CSRF_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SAMESITE = 'None' if IS_PRODUCTION else 'Lax'
CSRF_COOKIE_HTTPONLY = False  # Needed for React frontend

# Security Headers (OWASP Top 10)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'
if IS_PRODUCTION:
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True

ROOT_URLCONF = 'helpdesk.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'helpdesk.wsgi.application'

# Database – default to PostgreSQL, fallback to SQLite for quick dev
DATABASE_URL = os.getenv('DATABASE_URL')
if os.getenv('HELPDESK_E2E') == '1':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('E2E_POSTGRES_DB', 'helpdesk_e2e'),
            'USER': os.getenv('E2E_POSTGRES_USER', os.getenv('POSTGRES_USER', 'postgres')),
            'PASSWORD': os.getenv('E2E_POSTGRES_PASSWORD', os.getenv('POSTGRES_PASSWORD', 'postgres')),
            'HOST': os.getenv('E2E_POSTGRES_HOST', os.getenv('POSTGRES_HOST', 'localhost')),
            'PORT': os.getenv('E2E_POSTGRES_PORT', os.getenv('POSTGRES_PORT', '5432')),
        }
    }
elif DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=IS_PRODUCTION,
        )
    }
elif os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
            'HOST': os.getenv('POSTGRES_HOST', 'db'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalisation
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
if IS_PRODUCTION:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'

# Django REST Framework defaults – use session authentication
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'tickets.auth.SessionAuthenticationWith401',
    ],
}
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    'ai': os.getenv('AI_REQUESTS_PER_HOUR', '60/hour'),
}

if IS_PRODUCTION:
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ]
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].update({
        'anon': '100/hour',
        'user': '1000/hour',
        'login': '10/hour',
        'ai': os.getenv('AI_REQUESTS_PER_HOUR', '60/hour'),
    })
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': os.getenv(
                'DJANGO_CACHE_URL',
                os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'),
            ),
            'KEY_PREFIX': 'helpdesk',
        }
    }

# CORS – allow either hostname commonly used by the local Vite server.
# CORS
CORS_ALLOW_CREDENTIALS = True

CORS_ORIGIN_WHITELIST = [] if IS_PRODUCTION else [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5174',
    'http://127.0.0.1:5174',
]

FRONTEND_URL = os.getenv('FRONTEND_URL')
if IS_PRODUCTION and FRONTEND_URL and not FRONTEND_URL.startswith('https://'):
    raise ImproperlyConfigured('FRONTEND_URL must use HTTPS in production.')

if FRONTEND_URL:
    CORS_ORIGIN_WHITELIST.append(FRONTEND_URL)

CSRF_TRUSTED_ORIGINS = [] if IS_PRODUCTION else [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5174',
    'http://127.0.0.1:5174',
]

if FRONTEND_URL:
    CSRF_TRUSTED_ORIGINS.append(FRONTEND_URL)

MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
MEDIA_STORAGE_BACKEND = os.getenv('MEDIA_STORAGE_BACKEND', 'filesystem').strip().lower()
if MEDIA_STORAGE_BACKEND == 's3':
    required_s3_settings = ('AWS_STORAGE_BUCKET_NAME', 'AWS_S3_REGION_NAME', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')
    missing_s3_settings = [key for key in required_s3_settings if not os.getenv(key)]
    if missing_s3_settings:
        raise ImproperlyConfigured(
            'S3 media storage requires: ' + ', '.join(missing_s3_settings)
        )
    INSTALLED_APPS.append('storages')
    STORAGES = {
        **globals().get('STORAGES', {}),
        'default': {
            'BACKEND': 'storages.backends.s3.S3Storage',
            'OPTIONS': {
                'bucket_name': os.environ.get('AWS_STORAGE_BUCKET_NAME'),
                'region_name': os.getenv('AWS_S3_REGION_NAME') or None,
                'endpoint_url': os.getenv('AWS_S3_ENDPOINT_URL') or None,
                'access_key': os.getenv('AWS_ACCESS_KEY_ID') or None,
                'secret_key': os.getenv('AWS_SECRET_ACCESS_KEY') or None,
                'default_acl': None,
                'file_overwrite': False,
                'querystring_auth': True,
            },
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }
elif MEDIA_STORAGE_BACKEND != 'filesystem':
    raise ImproperlyConfigured('MEDIA_STORAGE_BACKEND must be filesystem or s3.')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True
# Keep AI actions usable in a local setup without a running Redis/Celery worker.
# Production continues to enqueue work for the configured worker.
CELERY_TASK_ALWAYS_EAGER = os.getenv(
    'CELERY_TASK_ALWAYS_EAGER',
    'False' if IS_PRODUCTION else 'True',
) == 'True'
CELERY_BEAT_SCHEDULE = {
    'fetch-emails': {
        'task': 'email_ingestion.tasks.fetch_emails',
        'schedule': float(os.getenv('EMAIL_POLL_INTERVAL_SECONDS', '60')),
    },
}

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-6-luna')
EMBEDDING_PROVIDER = os.getenv('EMBEDDING_PROVIDER', 'ollama').strip().lower()
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')
OLLAMA_EMBEDDING_MODEL = os.getenv('OLLAMA_EMBEDDING_MODEL', 'nomic-embed-text')
OLLAMA_TIMEOUT_SECONDS = int(os.getenv('OLLAMA_TIMEOUT_SECONDS', '120'))
PGVECTOR_ENABLED = os.getenv('PGVECTOR_ENABLED', 'False') == 'True'
AI_SUGGESTION_TIMEOUT = int(os.getenv('AI_SUGGESTION_TIMEOUT', '30'))
