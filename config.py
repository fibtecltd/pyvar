"""
config.py — Central settings for pyvar.com
All environment variables are read here. Every module imports from this file.
Rationale: single source of truth; pydantic-settings validates types at startup.
"""

from functools import lru_cache
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Application ────────────────────────────────────────────────────────────
    app_name: str = "pyvar"
    app_env: str = "development"  # development | staging | production
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # ── Security ───────────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    # Email verification link (api/routes/auth.py) expires after this long —
    # separate from jwt_expiry_minutes, which governs the *issued* token once
    # verification succeeds, not the one-time link itself.
    verification_token_expiry_minutes: int = 1440  # 24h

    # Base URL this API is reachable at — used only to log a human-readable
    # verification link (see api/routes/auth.py's send_verification_email
    # stub; no real email transport exists yet, see #149). Dev CloudFront
    # domain by default, matching scripts/test_cold_start.sh.
    public_base_url: str = "https://d1mqqddh8gu2qi.cloudfront.net"

    # ── Redis (Celery broker + result backend + cache) ─────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_result_ttl: int = 3600  # seconds — results cached for 1 hour

    # ── PostgreSQL (audit log, job metadata) ───────────────────────────────────
    postgres_dsn: str = "postgresql+asyncpg://postgres:pyvar@localhost:5432/pyvar"

    # DB connection components, injected individually from Secrets Manager on AWS
    # (DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD). ECS cannot compose a
    # multi-field DSN from a single secret key, so the app assembles it: when all
    # five are present, postgres_dsn is built from them (see _assemble_postgres_dsn).
    # Left unset for local dev, where postgres_dsn (above / .env) is used directly.
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None

    # ── S3 / MinIO (large Parquet result storage) ─────────────────────────────
    s3_endpoint_url: str = "http://localhost:9000"  # set to None for real AWS
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "pyvar-results"
    s3_region: str = "eu-west-1"

    # Separate small bucket for status.json / demo-result.json (P8 Task 1/2),
    # written by pyvar-cdk/stacks/public_data_stack.py's scheduled Lambda and
    # served by api/routes/public_data.py — deliberately not the same bucket
    # as s3_bucket above (different lifecycle: regenerable, no retention).
    public_data_bucket: str = "pyvar-public"

    # ── Monte Carlo defaults ───────────────────────────────────────────────────
    default_n_simulations: int = 100_000
    default_confidence_level: float = 0.99
    default_horizon_days: int = 1
    max_n_simulations: int = 1_000_000

    # ── Observability ─────────────────────────────────────────────────────────
    sentry_dsn: str | None = None
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _assemble_postgres_dsn(self) -> "Settings":
        """Build postgres_dsn from individually-injected DB_* components.

        On AWS the ECS task receives DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD
        as separate Secrets Manager fields. When all five are present they take
        precedence and postgres_dsn is composed from them (user/password are
        URL-encoded). When any is missing, postgres_dsn keeps its default/.env
        value, preserving the local-dev workflow.

        Returns:
            Settings: this instance, with postgres_dsn populated when applicable.
        """
        components = (
            self.db_host,
            self.db_port,
            self.db_name,
            self.db_user,
            self.db_password,
        )
        if all(component is not None for component in components):
            user = quote(str(self.db_user), safe="")
            password = quote(str(self.db_password), safe="")
            self.postgres_dsn = (
                f"postgresql+asyncpg://{user}:{password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.
    Use: from config import get_settings; cfg = get_settings()
    """
    return Settings()
