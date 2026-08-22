import logging
from pathlib import Path
from typing import Set

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("buscaoficio")

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


class Settings(BaseSettings):
    # OpenAPI docs
    OPENAPI_URL: str = "/openapi.json"

    # Database
    DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None
    EXPIRE_ON_COMMIT: bool = False

    # User
    ACCESS_SECRET_KEY: str
    RESET_PASSWORD_SECRET_KEY: str
    VERIFICATION_SECRET_KEY: str
    REGISTRATION_TOKEN_SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 900  # 15 minutes
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 2592000  # 30 days

    # Passwordless (email OTP) auth
    OTP_CODE_EXPIRE_SECONDS: int = 600  # 10 minutes
    REGISTRATION_TOKEN_EXPIRE_SECONDS: int = 900  # 15 minutes

    # Google Sign-In (OAuth 2.0 authorization code flow)
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_STATE_EXPIRE_SECONDS: int = 600  # 10 minutes
    GOOGLE_SESSION_TOKEN_EXPIRE_SECONDS: int = 120  # 2 minutes

    # Email
    MAIL_USERNAME: str | None = None
    MAIL_PASSWORD: str | None = None
    MAIL_FROM: str | None = None
    MAIL_SERVER: str | None = None
    MAIL_PORT: int | None = None
    MAIL_FROM_NAME: str = "Busca oficio"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False
    USE_CREDENTIALS: bool = True
    VALIDATE_CERTS: bool = True
    TEMPLATE_DIR: str = "email_templates"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # Backend's own public base URL — needed to build the Google OAuth
    # redirect_uri (must match exactly what's registered in Google Cloud
    # Console and what's sent on both the authorize and token-exchange
    # legs). Not derived from the incoming request, since that would depend
    # on trusting proxy headers correctly behind Caddy in production.
    BACKEND_URL: str = "http://localhost:8001"

    # CORS
    CORS_ORIGINS: Set[str]

    # Sentry (optional — SDK stays disabled when DSN is empty)
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
