
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "LinkedIn AI Agent"
    APP_ENV: str = "development"
    DEBUG: bool = True
    JWT_SECRET_KEY: str
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres"
        "@localhost:5432/linkedin_ai_agent"
    )

    REDIS_URL: str = "redis://localhost:6379/0"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:4b"

    # Comma-separated extra origins allowed by CORS (in addition to the Vite dev origin).
    CORS_ALLOWED_ORIGINS: str = ""

    # User-provided Easy Apply answers (README.md manual flow); override in .env.
    APPLY_TOTAL_EXPERIENCE_YEARS: str = "5"
    APPLY_SKILL_EXPERIENCE_YEARS: str = "5"  # Java / backend / frontend / full stack / software dev
    APPLY_CURRENT_SALARY: str = "30 LPA"
    APPLY_EXPECTED_SALARY: str = "50 LPA"
    APPLY_NOTICE_PERIOD: str = "Less than 15 days"
    # Start-button runs click Submit as soon as a form is complete (user's choice).
    # Set to false in .env to pause on the Review page for approval instead.
    APPLY_AUTO_SUBMIT: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
