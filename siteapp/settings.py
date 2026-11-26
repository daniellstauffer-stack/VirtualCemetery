"""Django settings for Virtual Cemetery.

Designed for Cloud Run + Cloud SQL (PostgreSQL) + Private Cloud Storage +
Google Cloud Identity Platform + Cloud Tasks, with frictionless local
development fallbacks (SQLite/PostgreSQL, local filesystem storage, local
auth emulator, and console/Mailpit email).
"""
from __future__ import annotations

import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")
DEBUG = _env_bool("DJANGO_DEBUG", default=(DJANGO_ENV == "development"))
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-change-me-virtual-cemetery-local-key",
)

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = _env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "http://localhost:8000").rstrip("/")
PILOT_JURISDICTION = os.environ.get("PILOT_JURISDICTION", "Oregon, United States")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@example-virtualcemetery.org")
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "Virtual Cemetery Pilot Operator")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Virtual Cemetery domain apps (matches architecture blueprint)
    "siteapp.accounts",
    "siteapp.planning",
    "siteapp.stewardship",
    "siteapp.memorials",
    "siteapp.events",
    "siteapp.integrations",
    "siteapp.jobs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "siteapp.middleware.PrivacyAndSecurityHeadersMiddleware",
]

ROOT_URLCONF = "siteapp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "siteapp" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "siteapp.accounts.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "siteapp.wsgi.application"
ASGI_APPLICATION = "siteapp.asgi.application"

# Database: PostgreSQL via DATABASE_URL (Cloud SQL or Docker), SQLite fallback locally
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/plan/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "siteapp" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "siteapp.storage.PrivateMediaStorage",
    },
    "evidence": {
        "BACKEND": "siteapp.storage.IsolatedEvidenceStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Private media & isolated case evidence directories (local dev) or GCS buckets (cloud)
MEDIA_ROOT = BASE_DIR / "local_media"
EVIDENCE_ROOT = BASE_DIR / "local_evidence"
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB per photo/document
ALLOWED_PHOTO_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EVIDENCE_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}

# --- Google Cloud Platform Placeholders --------------------------------------
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-gcp-project-id-placeholder")
GCP_REGION = os.environ.get("GCP_REGION", "us-west1")
USE_GCS_STORAGE = _env_bool("USE_GCS_STORAGE", default=False)
GCP_MEDIA_BUCKET = os.environ.get("GCP_MEDIA_BUCKET", "your-gcp-project-vc-private-media")
GCP_EVIDENCE_BUCKET = os.environ.get("GCP_EVIDENCE_BUCKET", "your-gcp-project-vc-case-evidence")
GCP_EVIDENCE_RETENTION_DAYS = int(os.environ.get("GCP_EVIDENCE_RETENTION_DAYS", "90"))

# --- Google Cloud Identity Platform Placeholders -----------------------------
LOCAL_AUTH_EMULATOR = _env_bool("LOCAL_AUTH_EMULATOR", default=(DJANGO_ENV == "development"))
GCP_IDENTITY_PLATFORM_PROJECT_ID = os.environ.get(
    "GCP_IDENTITY_PLATFORM_PROJECT_ID", "your-gcp-project-id-placeholder"
)
GCP_IDENTITY_PLATFORM_API_KEY = os.environ.get(
    "GCP_IDENTITY_PLATFORM_API_KEY", "your-identity-platform-web-api-key-placeholder"
)
GCP_IDENTITY_PLATFORM_AUTH_DOMAIN = os.environ.get(
    "GCP_IDENTITY_PLATFORM_AUTH_DOMAIN", "your-gcp-project-id-placeholder.firebaseapp.com"
)
IDENTITY_PLATFORM_EMULATOR_HOST = os.environ.get("IDENTITY_PLATFORM_EMULATOR_HOST", "")

# --- Google Cloud Tasks & Worker Placeholders --------------------------------
CLOUD_TASKS_ENABLED = _env_bool("CLOUD_TASKS_ENABLED", default=False)
GCP_TASKS_LOCATION = os.environ.get("GCP_TASKS_LOCATION", "us-west1")
GCP_TASKS_QUEUE_NAME = os.environ.get("GCP_TASKS_QUEUE_NAME", "vc-background-jobs")
WORKER_BASE_URL = os.environ.get("WORKER_BASE_URL", "https://vc-worker-REPLACE-uc.a.run.app")
WORKER_OIDC_SERVICE_ACCOUNT = os.environ.get(
    "WORKER_OIDC_SERVICE_ACCOUNT",
    "vc-tasks-invoker@your-gcp-project-id-placeholder.iam.gserviceaccount.com",
)
WORKER_SHARED_SECRET = os.environ.get("WORKER_SHARED_SECRET", "replace-with-local-worker-shared-secret")

# --- Email Provider (Postmark / SMTP / Console) ------------------------------
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "console")
EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "no-reply@example-virtualcemetery.org")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Virtual Cemetery")
POSTMARK_SERVER_TOKEN = os.environ.get("POSTMARK_SERVER_TOKEN", "your-postmark-server-token-placeholder")
POSTMARK_MESSAGE_STREAM = os.environ.get("POSTMARK_MESSAGE_STREAM", "outbound")
POSTMARK_WEBHOOK_SECRET = os.environ.get("POSTMARK_WEBHOOK_SECRET", "your-postmark-webhook-secret-placeholder")
STAGING_ALLOWED_EMAIL_RECIPIENTS = _env_list("STAGING_ALLOWED_EMAIL_RECIPIENTS", "")

if EMAIL_PROVIDER == "smtp":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("SMTP_HOST", "localhost")
    EMAIL_PORT = int(os.environ.get("SMTP_PORT", "1025"))
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --- Third-Party Integrations Placeholders -----------------------------------
FACEBOOK_LOGIN_ENABLED = _env_bool("FACEBOOK_LOGIN_ENABLED", default=False)
FACEBOOK_APP_ID = os.environ.get("FACEBOOK_APP_ID", "your-meta-facebook-app-id-placeholder")
FACEBOOK_APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "your-meta-facebook-app-secret-placeholder")
FACEBOOK_REDIRECT_URI = os.environ.get(
    "FACEBOOK_REDIRECT_URI", f"{SITE_BASE_URL}/integrations/facebook/callback/"
)
FACEBOOK_GRAPH_API_VERSION = os.environ.get("FACEBOOK_GRAPH_API_VERSION", "v21.0")

GOOGLE_PEOPLE_IMPORT_ENABLED = _env_bool("GOOGLE_PEOPLE_IMPORT_ENABLED", default=False)
GOOGLE_OAUTH_CLIENT_ID = os.environ.get(
    "GOOGLE_OAUTH_CLIENT_ID", "your-google-oauth-client-id-placeholder.apps.googleusercontent.com"
)
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get(
    "GOOGLE_OAUTH_CLIENT_SECRET", "your-google-oauth-client-secret-placeholder"
)
GOOGLE_PEOPLE_REDIRECT_URI = os.environ.get(
    "GOOGLE_PEOPLE_REDIRECT_URI", f"{SITE_BASE_URL}/integrations/contacts/google/callback/"
)

MICROSOFT_GRAPH_IMPORT_ENABLED = _env_bool("MICROSOFT_GRAPH_IMPORT_ENABLED", default=False)
MICROSOFT_TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID", "common")
MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID", "your-microsoft-entra-client-id-placeholder")
MICROSOFT_CLIENT_SECRET = os.environ.get("MICROSOFT_CLIENT_SECRET", "your-microsoft-entra-client-secret-placeholder")
MICROSOFT_REDIRECT_URI = os.environ.get(
    "MICROSOFT_REDIRECT_URI", f"{SITE_BASE_URL}/integrations/contacts/microsoft/callback/"
)

GOOGLE_PLACES_ENABLED = _env_bool("GOOGLE_PLACES_ENABLED", default=False)
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "your-google-places-api-key-placeholder")
GOOGLE_PLACES_DAILY_QUOTA = int(os.environ.get("GOOGLE_PLACES_DAILY_QUOTA", "250"))

STRIPE_ENABLED = _env_bool("STRIPE_ENABLED", default=False)
STRIPE_PUBLISHABLE_KEY = os.environ.get(
    "STRIPE_PUBLISHABLE_KEY", "pk_test_your_stripe_publishable_key_placeholder"
)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "sk_test_your_stripe_secret_key_placeholder")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "whsec_your_stripe_webhook_secret_placeholder")
STRIPE_CURRENCY = os.environ.get("STRIPE_CURRENCY", "usd")
STRIPE_PAYEE_LEGAL_NAME = os.environ.get(
    "STRIPE_PAYEE_LEGAL_NAME", "Virtual Cemetery Operator LLC (Placeholder)"
)
STRIPE_TAX_DEDUCTIBLE_STATUS = os.environ.get(
    "STRIPE_TAX_DEDUCTIBLE_STATUS",
    "Contributions are voluntary gifts to support site hosting and operations and are NOT tax-deductible.",
)

# --- Security Defaults (hardened outside development) ------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Structured logging that avoids leaking private text, contact lists, or evidence
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
}
