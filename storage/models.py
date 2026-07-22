"""
storage/models.py — SQLAlchemy async ORM models

Reasoning:
- PostgreSQL stores structured metadata: job history, user accounts,
  audit trail. Not the raw simulation output (that goes to S3 as Parquet).
- Async SQLAlchemy (asyncpg driver) keeps the FastAPI event loop non-blocking.
- The VaRJob table provides a durable audit log independent of Redis TTL —
  Redis results expire after celery_result_ttl seconds, but the DB record
  persists for compliance and billing purposes.
- Indexed on (user_id, created_at) for efficient user history queries.
- storing var_pct and cvar_pct inline (not just the S3 path) means scalar
  metrics are queryable without fetching the full Parquet file from S3.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ApiUsage(Base):
    """Operational usage telemetry — one row per compute API request.

    NOT a regulatory audit record. Unlike ``VaRJob`` (which CLAUDE.md §3.3 marks
    as an append-only AUDIT LOG retained indefinitely for compliance), this table
    is purely operational: it holds no client identity, order, or computation
    data — only which domain/function was hit, the caller's tier, latency, and
    HTTP status. It is therefore SAFE (and expected) to prune on a retention
    schedule; see the 0003 migration and observability/queries.sql. Do not apply
    the var_jobs "never delete" rule here, and do not treat it as a compliance
    record.

    Written asynchronously by the usage-tracking middleware AFTER the response is
    sent, so it never adds latency to the request hot path.
    """

    __tablename__ = "api_usage"

    # BigInteger identity PK (not UUID like other tables): this is append-heavy
    # telemetry, and a monotonic key avoids the index fragmentation random UUIDv4
    # PKs cause on high-volume inserts. No need for distributed-unique IDs here.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    function_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # HTTP status code of the response (e.g. 200, 422, 500). errors are status >= 400.
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Single index on created_at: supports the weekly-window analytics queries AND
    # cheap retention deletes, while keeping insert cost low on a write-heavy table
    # (domain/tier grouping over a bounded window is cheap without extra indexes).
    __table_args__ = (Index("ix_api_usage_created_at", "created_at"),)

    def __repr__(self) -> str:
        return f"<ApiUsage {self.domain}/{self.function_name} status={self.status}>"


class User(Base):
    """Registered account — the users table from 0002_users_and_tier, plus the
    email-verification columns added in 0004_user_email_verification (P8 Task 3).

    external_id is documented (0002) as "the 'sub' claim in the JWT — external
    identity provider ID", but no external identity provider exists yet:
    api/routes/auth.py generates a fresh UUID as external_id at registration
    time and embeds it as the JWT 'sub' claim once email_verified is set.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="free")
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_simulations: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<User email={self.email} tier={self.tier} verified={self.email_verified}>"


class VaRJob(Base):
    """
    Audit record for every VaR computation submitted to pyvar.
    Created on POST /var/compute, updated when the Celery task completes.
    """

    __tablename__ = "var_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Job lifecycle
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Request parameters (stored for audit / billing)
    portfolio_value: Mapped[float] = mapped_column(Float, nullable=False)
    n_simulations: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence_level: Mapped[float] = mapped_column(Float, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # Scalar results (stored inline for queryability)
    var_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    var_abs: Mapped[float | None] = mapped_column(Float, nullable=True)
    cvar_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    cvar_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # S3 path to the full Parquet result (loss distribution array)
    result_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (Index("ix_var_jobs_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<VaRJob task_id={self.task_id} status={self.status}>"
