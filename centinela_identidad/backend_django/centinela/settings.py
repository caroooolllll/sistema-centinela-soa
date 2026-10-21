"""
Configuración de Django - Centinela Identidad
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga .env desde backend_django/ primero, luego raíz del repo como fallback
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent.parent / '.env', override=False)


def _require_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise ImproperlyConfigured(
            f"Variable de entorno requerida no configurada: {name}\n"
            f"Copia .env.example a .env y agrega el valor."
        )
    return value


# ── Seguridad ────────────────────────────────────────────────
_raw_secret = os.getenv('SECRET_KEY', '').strip()
if not _raw_secret:
    if os.getenv('DEBUG', 'False').lower() in ('true', '1'):
        # En desarrollo se permite clave insegura con advertencia
        import warnings
        warnings.warn(
            "SECRET_KEY no configurada — usando clave insegura de desarrollo. "
            "Agrega SECRET_KEY en tu .env antes de pasar a producción.",
            stacklevel=2,
        )
        _raw_secret = 'django-insecure-centinela-dev-only-NO-usar-en-produccion'
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY no configurada en .env. "
            "Genera una con: python -c \"from django.core.management.utils import "
            "get_random_secret_key; print(get_random_secret_key())\""
        )

SECRET_KEY = _raw_secret

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1')

_hosts_raw = os.getenv('ALLOWED_HOSTS', '0.0.0.0,localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in _hosts_raw.split(',') if h.strip()]

# ── Aplicaciones ─────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'corsheaders',
    'auth_app',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'centinela.urls'
WSGI_APPLICATION = 'centinela.wsgi.application'

# ── Base de datos ────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'centinela.db',
    }
}

# ── Localización ─────────────────────────────────────────────
LANGUAGE_CODE = 'es-mx'
TIME_ZONE = 'America/Mexico_City'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── CORS ─────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'POST', 'PUT']
CORS_ALLOW_HEADERS = ['Content-Type', 'Authorization']

# ── Email (Gmail SMTP) ───────────────────────────────────────
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')

# URL interna del servicio de chat (FastAPI :9003) — para push de emergencias vía WebSocket
CHAT_SERVICE_URL = os.getenv('CHAT_SERVICE_URL', 'http://localhost:9003')
