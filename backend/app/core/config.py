"""Application settings loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173"

    # Postgres
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "health_steward"
    POSTGRES_USER: str = "health"
    POSTGRES_PASSWORD: str = "changeme"

    # Multimodal model API
    MULTIMODAL_API_BASE: str = "https://api.openai.com/v1"
    MULTIMODAL_API_KEY: str = ""
    MULTIMODAL_API_MODEL: str = "gpt-4o"

    # Text model API
    TEXT_API_BASE: str = "https://api.openai.com/v1"
    TEXT_API_KEY: str = ""
    TEXT_API_MODEL: str = "gpt-4o-mini"

    # Local LLM
    LOCAL_LLM_BASE: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "llama3"

    # Text provider routing: text_api | local_llm
    TEXT_PROVIDER_PRIORITY: str = "text_api"

    # Feishu bot (V0.4)
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_VERIFICATION_TOKEN: str = ""
    FEISHU_ENCRYPT_KEY: str = ""

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Sync URL used by Alembic migrations."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
