from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://crm:crm_secret_change_me@db:5432/crm"
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:3000"
    ALGORITHM: str = "HS256"

    # Gmail integration
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""  # path to service account JSON
    GOOGLE_DELEGATED_USER: str = ""  # admin email for domain-wide delegation
    GMAIL_SYNC_INTERVAL_SECONDS: int = 300  # 5 minutes
    APP_BASE_URL: str = "http://localhost:8000"  # for tracking pixel/link URLs

    model_config = {"env_file": ".env"}


settings = Settings()
