from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-s_bth01eb8%#p@3#h&658$#@ed^qg64=hw4jj1qgqbdi^zkoaz'

DEBUG = False

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    '12.81.64.130',
    'go',
]

CSRF_TRUSTED_ORIGINS = [
    'https://12.81.64.130:8000',
    'https://go',
    'https://12.81.64.130:8001',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'facts.apps.FactsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'app_db',
        'USER': 'minuk12.choi',
        'PASSWORD': 'Test1234!@',
        'HOST': '12.81.64.130',
        'PORT': '3306',
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000

USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_AGE = 60*60*8

CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True

CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

CSRF_COOKIE_PATH = '/'
SESSION_COOKIE_PATH = '/'

APPEND_SLASH = True
PREPEND_WWW = False

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
)

LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/facts/dashboard/'
LOGOUT_REDIRECT_URL = '/facts/dashboard/'

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# ==================================================
# python3-saml 설정
# ==================================================

SAML_AUTH_ROOT = BASE_DIR / 'saml'
SAML_SETTINGS_JSON = SAML_AUTH_ROOT / 'settings.json'
SAML_ADVANCED_SETTINGS_JSON = SAML_AUTH_ROOT / 'advanced_settings.json'

# 회사 가이드상 설치 필요
XMLSEC_BINARY = r'C:\xmlsec1-1.3.9-win64\xmlsec\bin\xmlsec.exe'

# 시작 페이지 / ACS endpoint
SAML_DEFAULT_NEXT_URL = '/facts/dashboard/'
SAML_ACS_URL = 'https://12.81.64.130:8000/facts/saml/acs/'
SAML_LOGIN_URL = '/admin/login/'
SAML_LOGOUT_URL = '/facts/saml/logout/'

# 필요 시 claim key 우선순위 조정
SAML_USERNAME_CLAIM_CANDIDATES = [
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
    'name',
    'UserID',
]

SAML_EMAIL_CLAIM_CANDIDATES = [
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
    'email',
]

SAML_FIRST_NAME_CLAIM_CANDIDATES = [
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
    'givenname',
]

SAML_LAST_NAME_CLAIM_CANDIDATES = [
    'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
    'surname',
]

SAML_PUBLIC_BASE_URL = 'https://12.81.64.130:8000'
