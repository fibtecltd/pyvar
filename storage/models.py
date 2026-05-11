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

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    __table_args__ = (
        Index("ix_var_jobs_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<VaRJob task_id={self.task_id} status={self.status}>"
