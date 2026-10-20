import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get('DEVANTIQ_DEBUG') == '1'
runtime_path = Path(os.environ.get('DEVANTIQ_RUNTIME', '/run/devantiq/runtime.json'))
runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
def config(name, default=''):
    return os.environ.get(name, runtime.get(name, default))
SECRET_KEY = config('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('DJANGO_SECRET_KEY doit etre configure hors du depot.')
    SECRET_KEY = 'development-only-not-for-production'
ALLOWED_HOSTS = ['devantiq.com', 'www.devantiq.com', '127.0.0.1', 'localhost', 'testserver'] if DEBUG else ['devantiq.com']
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
                 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'oauth2_provider', 'portal']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware',
              'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
              'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware',
              'django.middleware.clickjacking.XFrameOptionsMiddleware', 'portal.middleware.LoginThrottle']
ROOT_URLCONF = 'portal.urls'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'],
              'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request',
              'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'portal.wsgi.application'
DATA_DIR = Path(os.environ.get('DEVANTIQ_DATA_DIR', BASE_DIR / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': DATA_DIR / 'members.sqlite3', 'OPTIONS': {'timeout': 20}}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher', 'django.contrib.auth.hashers.PBKDF2PasswordHasher']
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
LOGIN_URL = '/auth/'
LOGIN_REDIRECT_URL = '/membres.html'
LOGOUT_REDIRECT_URL = '/auth/?deconnecte=1'
SESSION_COOKIE_NAME = 'devantiq_member_session'
SESSION_COOKIE_DOMAIN = None if DEBUG else '.devantiq.com'
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_USE_SESSIONS = True
CSRF_TRUSTED_ORIGINS = ['https://devantiq.com']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Europe/Paris'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/auth/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('SMTP_HOST')
EMAIL_PORT = int(config('SMTP_PORT', '587'))
EMAIL_HOST_USER = config('SMTP_USER')
EMAIL_HOST_PASSWORD = config('SMTP_PASSWORD')
EMAIL_USE_TLS = EMAIL_PORT != 465
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = config('SMTP_FROM', 'DevAntiq <hello@devantiq.com>')
PASSWORD_RESET_TIMEOUT = 3600

# OIDC remains unavailable until a private signing key has been installed.
OAUTH2_PROVIDER_APPLICATION_MODEL = 'oauth2_provider.Application'
oidc_key_path = runtime_path.parent / 'oidc-private.pem'
OAUTH2_PROVIDER = {
    'OIDC_ENABLED': oidc_key_path.is_file(),
    'OIDC_RSA_PRIVATE_KEY': oidc_key_path.read_text() if oidc_key_path.is_file() else '',
    'OIDC_ISS_ENDPOINT': 'https://devantiq.com/auth/oidc',
    'OAUTH2_VALIDATOR_CLASS': 'portal.oidc.MemberOAuthValidator',
    'SCOPES': {'openid': 'Identité DevAntiq', 'profile': 'Nom et compte associé', 'email': 'Adresse e-mail'},
    'DEFAULT_SCOPES': ['openid'],
    'PKCE_REQUIRED': True,
    'ALLOWED_REDIRECT_URI_SCHEMES': ['https'],
    'ACCESS_TOKEN_EXPIRE_SECONDS': 300,
    'AUTHORIZATION_CODE_EXPIRE_SECONDS': 60,
    'ID_TOKEN_EXPIRE_SECONDS': 300,
    'OIDC_RP_INITIATED_LOGOUT_ENABLED': False,
}
