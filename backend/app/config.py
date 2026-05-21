import sys

from pydantic_settings import BaseSettings


_DEFAULT_SECRET_KEY = "change-me-in-production-use-openssl-rand-hex-32"


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://crm:crm_secret_change_me@db:5432/crm"
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:3000"
    ALGORITHM: str = "HS256"
    ADMIN_PASSWORD: str = ""

    # Gmail integration
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""  # path to service account JSON
    GOOGLE_DELEGATED_USER: str = ""  # admin email for domain-wide delegation
    GMAIL_SYNC_INTERVAL_SECONDS: int = 300  # 5 minutes
    APP_BASE_URL: str = "http://localhost:8000"  # for tracking pixel/link URLs
    SLACK_WEBHOOK_URL: str = ""
    CRM_FRONTEND_BASE_URL: str = "http://localhost:3000"
    CATALYST_INTAKE_WORKER_POLL_SECONDS: float = 5.0

    model_config = {"env_file": ".env"}


settings = Settings()

if settings.SECRET_KEY == _DEFAULT_SECRET_KEY:
    print(
        "FATAL: SECRET_KEY is still the default placeholder. "
        "Set a real SECRET_KEY via environment variable or .env file.",
        file=sys.stderr,
    )
    sys.exit(1)
