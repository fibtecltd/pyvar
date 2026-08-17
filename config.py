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

    # Base URL this API is reachable at — used to build the verification
    # link sent by api/routes/auth.py's send_verification_email (#149).
    # Dev CloudFront domain by default, matching scripts/test_cold_start.sh.
    public_base_url: str = "https://d1mqqddh8gu2qi.cloudfront.net"

    # CORS allowlist — explicit per-environment origins, never "*" for any
    # deployed environment. Populated by _default_cors_origins() below when
    # left empty; set directly (e.g. via a CORS_ALLOWED_ORIGINS env var) only
    # to override for local testing.
    #
    # task #42: previously this field didn't exist — main.py picked between
    # ["*"] and ["https://pyvar.com"] based on cfg.debug, which nothing ever
    # sets False in any real deployment (every CDK stack, the Dockerfile,
    # and .env.example were checked — no DEBUG env var anywhere). Confirmed
    # live: both dev and prod reflected an attacker-controlled Origin header
    # back with access-control-allow-credentials: true. The real
    # per-environment signal is app_env, but its live values are the SHORT
    # forms CDK injects ("dev"/"staging"/"prod" — api_stack.py sets
    # APP_ENV=cfg.env_name), not the long forms this field's own default
    # below implies ("development") — comparing against the long forms
    # would silently reproduce the same bug (see tasks #45/#46: the
    # identical mismatch, already live, in observability/setup.py).
    cors_allowed_origins: list[str] = []

    # ── Email (SES transport, #149) ─────────────────────────────────────────
    # Sender identity for verification emails — must match the SES domain
    # identity CDK verifies (pyvar-cdk/stacks/ses_stack.py verifies the
    # pyvar.com domain itself via DKIM, not a subdomain). Safe to leave as
    # the default in local dev / tests: send_verification_email() falls back
    # to logging (its original stub behaviour) if the SES call itself fails,
    # so no real AWS credentials or SES setup are required for that workflow.
    ses_sender_email: str = "noreply@pyvar.com"
    ses_region: str = "eu-west-1"

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
    # Leave all three unset for real AWS: boto3's default credential chain then
    # applies (ECS task role in every deployed environment, AWS_ACCESS_KEY_ID/
    # AWS_SECRET_ACCESS_KEY env vars for local dev — see .env.example). Set all
    # three only to point at a local MinIO container instead, which has no IAM
    # role to assume and needs explicit (dummy) credentials.
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket: str = "pyvar-results"
    s3_region: str = "eu-west-1"

    # Separate small bucket for status.json / demo-result.json (P8 Task 1/2),
    # written by pyvar-cdk/stacks/public_data_stack.py's scheduled Lambda and
    # served by api/routes/public_data.py — deliberately not the same bucket
    # as s3_bucket above (different lifecycle: regenerable, no retention).
    public_data_bucket: str = "pyvar-public"

    # ── Monte Carlo defaults ───────────────────────────────────────────────────
    # default_n_simulations must never exceed the lowest tier cap
    # (api/middleware/auth.py's "free": 10_000) — it's the value used when a
    # request omits n_simulations entirely, for every tier, so a free-tier
    # user who doesn't specify it must never get an automatic 403.
    # max_n_simulations mirrors the highest tier cap ("enterprise"/"internal":
    # 500_000) — schemas/var.py's VaRRequest.n_simulations reads both of these
    # directly rather than hardcoding its own copies.
    default_n_simulations: int = 10_000
    default_confidence_level: float = 0.99
    default_horizon_days: int = 1
    max_n_simulations: int = 500_000

    # ── S3 large-result offload (#130) ──────────────────────────────────────
    # Above this many simulations, tasks/var_task.py writes the full result to
    # S3 (storage/s3.py::write_result_to_s3) as Parquet and strips loss_dist
    # from the inline/Celery-cached result, returning a presigned URL instead
    # (api/routes/var.py, api/routes/caching.py). At/below this threshold,
    # behavior is unchanged from before #130 — loss_dist inline, no S3 write.
    # Set equal to the free-tier simulation cap: every free-tier request stays
    # inline; only pro/enterprise jobs can ever be large enough to offload.
    s3_result_offload_threshold: int = 10_000

    # ── Rate limiting (#146) ────────────────────────────────────────────────────
    # Account-wide daily quota across ALL /api/v1 compute endpoints (var + the 8
    # domains), enforced by api/middleware/rate_limit.py. No verified traffic
    # data or drafted spec exists for these numbers (see PR description) — kept
    # as config so they can be retuned from real api_usage data post-launch
    # without a code change. enterprise and internal (service/cron JWTs) tiers
    # are unconditionally exempt — no setting needed for them.
    rate_limit_unauth_per_hour: int = 5  # per-IP, /public/* only
    rate_limit_free_daily: int = 10  # per-user, all /api/v1 compute endpoints
    rate_limit_pro_daily: int = 500  # per-user, all /api/v1 compute endpoints

    # ── Observability ─────────────────────────────────────────────────────────
    sentry_dsn: str | None = None
    log_level: str = "INFO"

    # AWS injects this into every real ECS Fargate/EC2 task automatically --
    # used by observability/setup.py's _resolve_sentry_dsn() to detect "am I
    # actually running in a deployed ECS task" before attempting a Secrets
    # Manager fetch, rather than gating on an app_env string (CI's test job
    # runs with APP_ENV=test, not "development" -- a name-based check would
    # have let a real AWS call slip into test runs, violating CLAUDE.md's
    # "never use real AWS services in tests" rule). Never set locally/in CI.
    ecs_container_metadata_uri_v4: str | None = None

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

    @model_validator(mode="after")
    def _default_cors_origins(self) -> "Settings":
        """Fill cors_allowed_origins from app_env when not explicitly set.

        Keyed on the SHORT-form app_env values real deployments actually use
        ("dev"/"staging"/"prod" — see cors_allowed_origins's own comment).
        Anything else (local dev's "development" default, CI's "test") keeps
        the permissive wildcard local dev has always had — no deployed,
        credential-bearing environment is affected by that branch.

        Returns:
            Settings: this instance, with cors_allowed_origins populated when
            not already set.
        """
        if self.cors_allowed_origins:
            return self
        origins_by_env: dict[str, list[str]] = {
            "prod": ["https://pyvar.com", "https://www.pyvar.com"],
            "dev": ["https://dev.pyvar.com"],
            # staging is never actually deployed (same "don't fix what
            # isn't in active use" scoping as api_base_url's prod-only
            # override in pyvar-cdk/config.py) — kept explicit rather than
            # falling through to "*" so it isn't wide open the moment it
            # ever is deployed.
            "staging": ["https://dev.pyvar.com"],
        }
        self.cors_allowed_origins = origins_by_env.get(self.app_env, ["*"])
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.
    Use: from config import get_settings; cfg = get_settings()
    """
    return Settings()
