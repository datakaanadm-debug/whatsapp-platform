# api/app/config.py — Configuración centralizada de la plataforma
# Usa pydantic-settings para validación y carga desde variables de entorno

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración global de la plataforma WhatsApp API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Base de datos PostgreSQL ──────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/whatsapp_platform"

    # ── Redis ─────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Autenticación JWT ─────────────────────────────────────────
    JWT_SECRET: str = "cambiar-en-produccion-secreto-seguro"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60 * 24  # 24 horas

    # ── API Key ───────────────────────────────────────────────────
    API_KEY_HEADER: str = "X-API-Key"

    # ── Almacenamiento S3 (compatible con MinIO) ──────────────────
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_BUCKET: str = "whatsapp-media"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"

    # ── Anthropic (IA para agentes) ───────────────────────────────
    ANTHROPIC_API_KEY: str = ""

    # ── Logging ───────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    # ── CORS ──────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── Rate limiting ─────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # ── Almacenamiento local de medios (fallback si no hay S3) ────
    MEDIA_STORAGE_PATH: str = "./media"

    # ── Webhooks ──────────────────────────────────────────────────
    WEBHOOK_RETRY_MAX: int = 5
    WEBHOOK_RETRY_DELAY: int = 30  # segundos entre reintentos


@lru_cache()
def get_settings() -> Settings:
    """Retorna la instancia cacheada de configuración."""
    return Settings()
