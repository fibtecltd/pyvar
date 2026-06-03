"""
config.py — Central settings for pyvar.com
All environment variables are read here. Every module imports from this file.
Rationale: single source of truth; pydantic-settings validates types at startup.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Application ────────────────────────────────────────────────────────────
    app_name: str = "pyvar"
    app_env: str = "development"  # development | staging | production
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # ── Security ───────────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # ── Redis (Celery broker + result backend + cache) ─────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_result_ttl: int = 3600  # seconds — results cached for 1 hour

    # ── PostgreSQL (audit log, job metadata) ───────────────────────────────────
    postgres_dsn: str = "postgresql+asyncpg://postgres:pyvar@localhost:5432/pyvar"

    # ── S3 / MinIO (large Parquet result storage) ─────────────────────────────
    s3_endpoint_url: str = "http://localhost:9000"  # set to None for real AWS
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "pyvar-results"
    s3_region: str = "us-east-1"

    # ── Monte Carlo defaults ───────────────────────────────────────────────────
    default_n_simulations: int = 100_000
    default_confidence_level: float = 0.99
    default_horizon_days: int = 1
    max_n_simulations: int = 1_000_000

    # ── Observability ─────────────────────────────────────────────────────────
    sentry_dsn: str | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.
    Use: from config import get_settings; cfg = get_settings()
    """
    return Settings()
