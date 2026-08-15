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
    # A single long-lived access token, no refresh-token flow — this is an
    # internal ops dashboard for a handful of accounts, not a public
    # multi-tenant SaaS, so re-logging in every 30 minutes would just be friction.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    # CORS — comma-separated list of allowed browser origins.
    # In production the SPA is served from the same origin as the API
    # (Caddy proxies /api and /ws to the backend), so no cross-origin
    # request happens at all and this list stays empty. The defaults only
    # cover the Vite dev server.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        """Parsed CORS_ORIGINS, with the credentials-unsafe wildcard removed.

        `allow_origins=["*"]` together with `allow_credentials=True` is
        rejected by browsers and, where it is honoured, lets any site read
        authenticated responses. Origins must therefore be listed
        explicitly; a bare "*" is dropped rather than silently trusted.
        """
        return [
            origin
            for origin in (o.strip() for o in self.CORS_ORIGINS.split(","))
            if origin and origin != "*"
        ]


# Singleton instance
settings = Settings()