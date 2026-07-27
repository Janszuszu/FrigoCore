"""FrigoCore — Application settings via Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    APP_NAME: str = "FrigoCore"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://frigocore:frigocore_dev@localhost:5432/frigocore"
    )

    # Redis
    REDIS_URL: str = "redis://:frigocore_redis_dev@localhost:6379/0"

    # EMQX / MQTT
    EMQX_HOST: str = "localhost"
    EMQX_PORT: int = 1883
    MQTT_WS_URL: str = "ws://localhost:8083"

    # Security
    SECRET_KEY: str = "change-this-to-a-random-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


# Singleton instance
settings = Settings()