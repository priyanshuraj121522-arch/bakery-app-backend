# core/settings.py
from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()  # reads .env if present

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Basic project settings ---
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-key")
DEBUG = os.getenv("DEBUG", "1") == "1"

def _csv(env_name: str) -> list[str]:
    raw = os.getenv(env_name, "")
    return [x.strip() for x in raw.split(",") if x.strip()]

ALLOWED_HOSTS = _csv("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = _csv("CSRF_TRUSTED_ORIGINS")

# --- Installed apps (admin enabled) ---
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "corsheaders",
    "drf_spectacular",

    # Local apps
    "bakery",
]

# --- Middleware (CORS should be near the top) ---
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

# --- Templates / WSGI ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "core.wsgi.application"

# --- Database ---
# If Postgres env vars are present, use them; otherwise fallback to SQLite (good for dev).
if os.getenv("PGHOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("PGDATABASE", "postgres"),
            "USER": os.getenv("PGUSER", "postgres"),
            "PASSWORD": os.getenv("PGPASSWORD", ""),
            "HOST": os.getenv("PGHOST", "localhost"),
            "PORT": os.getenv("PGPORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Password validation (defaults) ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N / TZ ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- CORS ---
# Default: open in dev. In prod, set CORS_ALLOW_ALL=0 and FRONTEND_ORIGIN to your UI.
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL", "1") == "1"
CORS_ALLOW_CREDENTIALS = True

if not CORS_ALLOW_ALL_ORIGINS:
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "")
    CORS_ALLOWED_ORIGINS = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ] + ([FRONTEND_ORIGIN] if FRONTEND_ORIGIN else [])

# --- DRF, JWT & API schema ---
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",  # health/docs are explicitly opened in views/urls
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MIN", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Bakery API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Optional: S3-compatible storage placeholders for Cloudflare R2 (wire later) ---
R2_BUCKET = os.getenv("R2_BUCKET", "")
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
