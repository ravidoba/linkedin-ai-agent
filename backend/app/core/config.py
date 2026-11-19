
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

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
