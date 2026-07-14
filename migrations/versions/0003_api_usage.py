"""add api_usage operational telemetry table

Revision ID: 0003_api_usage
Revises: 0002_users_and_tier
Create Date: 2026-07-14 00:00:00

Adds:
- api_usage: one row per compute API request (domain, function, tier, latency,
  HTTP status), written asynchronously by the usage-tracking middleware for the
  weekly usage analytics in observability/queries.sql.

REGULATORY / RETENTION NOTE — read before touching this table:
- This is OPERATIONAL TELEMETRY, not a regulatory record. It stores no client
  identity, order, transaction, or computation data — only usage/performance
  signals. It is therefore NOT subject to the var_jobs audit-log rule
  (CLAUDE.md §3.3 / migration 0001: "AUDIT LOG … rows never deleted … retained
  indefinitely for compliance").
- Rows here ARE expected to be pruned on a retention schedule (recommended: ~90
  days) — it shares the Aurora instance with regulatory data, so it must not be
  allowed to grow unbounded. A scheduled DELETE WHERE created_at < now() -
  interval '90 days' (pg_cron or an external job) is the intended mechanism and
  is explicitly ALLOWED for this table (and ONLY this table — do not delete from
  var_jobs). Retention automation is a follow-up, not created here.
- Single index on created_at keeps inserts cheap on this write-heavy table and
  serves both the weekly-window queries and the retention delete.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_api_usage"
down_revision: Union[str, None] = "0002_users_and_tier"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_usage",
        # BigInteger identity PK (not UUID like other tables): append-heavy
        # telemetry benefits from a monotonic key; random UUIDv4 PKs fragment
        # the index under high insert volume.
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        # Risk domain from the request path, e.g. "market-risk", "var".
        sa.Column("domain", sa.String(64), nullable=False),
        # Specific function/endpoint, e.g. "expected-shortfall", "compute".
        sa.Column("function_name", sa.String(128), nullable=False),
        # Caller tier from the JWT: free | pro | enterprise | unknown.
        sa.Column("tier", sa.String(16), nullable=False, server_default="unknown"),
        # Wall-clock request duration in milliseconds.
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        # HTTP status code of the response (errors are status >= 400).
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_api_usage_created_at", "api_usage", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_usage_created_at", table_name="api_usage")
    op.drop_table("api_usage")
