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

    # Database — SQLite for native development (no Docker required)
    DATABASE_URL: str = "sqlite+aiosqlite:///c:/Projekty/FrigoCore/backend/frigocore.db"

    # Redis
    REDIS_URL: str = "redis://:frigocore_redis_dev@localhost:6379/0"

    # EMQX / MQTT
    EMQX_HOST: str = "localhost"
    EMQX_PORT: int = 1883
    MQTT_USER: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_WS_URL: str = "ws://localhost:8083"

    # Security
    SECRET_KEY: str = "change-this-to-a-random-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30


# Singleton instance
settings = Settings()