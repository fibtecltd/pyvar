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

    # nullable=True at the DB layer to match the 0004 migration (an ALTER TABLE
    # on an existing table can't safely add a NOT NULL column with no default).
    # "email is required" is enforced at the application layer instead —
    # schemas.auth.RegisterRequest requires it, and register() always sets it.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When GET /auth/verify succeeded (0006_user_verified_at) — distinct from
    # verification_sent_at above (when the link was emailed). NULL for rows
    # verified before this column existed; see that migration's docstring for
    # why those aren't backfilled.
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Bounce/complaint suppression (0005_user_email_suppression, SES production-
    # access review follow-up). Written only by api/routes/internal.py's
    # POST /internal/suppress-email, called by
    # pyvar-cdk/lambda/ses_suppression_handler/handler.py — never set directly
    # by application code elsewhere. Checked in api/routes/auth.py::register()
    # so a re-registration attempt doesn't keep resending to a known-bad address.
    email_suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suppression_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    suppressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stripe Customer ID (0007_user_stripe_customer_id, Phase A billing —
    # docs/plan-monetization-implementation.md). Set the first time this user
    # starts a Checkout (api/routes/billing.py), then reused as the join key
    # every webhook event and the checkout-complete token exchange use to
    # find this row back — Stripe events carry a customer ID, never a pyvar
    # external_id. Unique, not required: most existing rows will never have
    # one.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Set only when tier == "free" AND the account was auto-downgraded by
    # api/middleware/billing_lifecycle.py rather than starting free or
    # cancelling voluntarily via Stripe's own Dashboard with no replacement
    # subscription (0008_billing_events_and_downgrade_reason — item 5 §8
    # follow-on). One of "payment_failed", "subscription_cancelled",
    # "monthly_request_limit_exceeded", "monthly_simulation_limit_exceeded".
    # Cleared (set back to NULL) whenever tier flips away from "free" again
    # (a fresh Checkout, or Stripe's webhook telling us a payment succeeded —
    # see billing_lifecycle.py's own docstring for why ANY successful payment
    # restores Pro access, not just a limit-exceeded downgrade specifically).
    # Exists so the webhook's invoice.payment_succeeded handler can tell "this
    # account should auto-restore to Pro since it's still an active,
    # successfully-billed subscriber" apart from "this account has simply
    # never subscribed" — both look identical as tier == "free" alone.
    tier_downgrade_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

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

    # Caller tier at submission time (denormalised for billing queries — see
    # 0002_users_and_tier). Was already a column in the DB schema but missing
    # from this ORM model until the var_jobs write path (#118) needed it.
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="free")

    # Job lifecycle
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Wall-clock compute duration, set on completion (see 0002_users_and_tier;
    # same missing-from-the-ORM-model gap as tier above).
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

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


class BillingEvent(Base):
    """Durable, queryable audit trail of every tier change — item 5 §8
    follow-on (0008_billing_events_and_downgrade_reason).

    Supersedes "check CloudWatch" as the only way to answer "why did this
    account change tier": every site that mutates User.tier (the Stripe
    webhook's upgrade/downgrade handling, and the two monthly-limit
    downgrade paths in api/middleware/billing_lifecycle.py) writes one row
    here in the SAME transaction as the tier mutation. Like VaRJob (CLAUDE.md
    §3.3), this is an audit log — rows are never deleted or updated after
    being written.

    user_id stores User.external_id (a plain string), the same convention
    VaRJob.user_id already uses, not a UUID foreign key — keeps this table
    joinable the same way against the same identifier every other
    audit/usage table in this file already keys off.
    """

    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # One of: "upgraded", "downgraded_payment_failed",
    # "downgraded_subscription_cancelled", "downgraded_monthly_request_limit",
    # "downgraded_monthly_simulation_limit", "restored_after_payment_succeeded"
    # — see api/middleware/billing_lifecycle.py's own constants (not a DB
    # enum: new event types are just a new string, no migration needed).
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    old_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    new_tier: Mapped[str] = mapped_column(String(16), nullable=False)

    # Human-readable detail (e.g. "Exceeded 5,000 requests this billing
    # period."). Free text, not structured — this table is for answering
    # "what happened and why" on lookup, not for further querying on reason.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Stripe's own event["id"], for webhook-triggered rows only (NULL for the
    # two monthly-limit downgrade paths, which have no Stripe event behind
    # them) — both a trace-back-to-Stripe-Dashboard convenience and the
    # idempotency key api/routes/billing.py's webhook checks before writing,
    # so a Stripe redelivery of an already-processed event doesn't duplicate
    # a row.
    stripe_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (Index("ix_billing_events_user_created", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<BillingEvent user_id={self.user_id} {self.event_type} {self.old_tier}->{self.new_tier}>"
