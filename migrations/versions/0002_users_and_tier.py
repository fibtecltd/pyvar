"""add users table and tier to var_jobs

Revision ID: 0002_users_and_tier
Revises: 0001_initial
Create Date: 2026-04-24 00:01:00

Adds:
- users table: stores account tier, API key hash, and usage counters
- tier column on var_jobs: denormalised for fast billing queries
  without joining to users on every row
- monthly_simulations counter on var_jobs: rolling 30d usage tracking
"""

from __future__ import annotations
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_users_and_tier"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── users table ────────────────────────────────────────────────────────
    op.create_table(
        "users",

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),

        # Matches the 'sub' claim in the JWT — external identity provider ID
        sa.Column("external_id", sa.String(128), nullable=False),

        # Account tier — drives simulation caps and pricing
        # free | pro | enterprise
        sa.Column("tier", sa.String(16), nullable=False, server_default="free"),

        # API key hash (SHA-256 of the raw key — never store raw key)
        sa.Column("api_key_hash", sa.String(64), nullable=True),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),

        # Usage counters (updated on job completion)
        sa.Column("total_jobs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_simulations", sa.BigInteger(), nullable=False, server_default="0"),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id", name="uq_users_external_id"),
    )

    op.create_index("ix_users_external_id", "users", ["external_id"])
    op.create_index("ix_users_api_key_hash", "users", ["api_key_hash"])

    # ── Add tier column to var_jobs (denormalised for billing queries) ─────
    op.add_column(
        "var_jobs",
        sa.Column(
            "tier",
            sa.String(16),
            nullable=False,
            server_default="free",
        ),
    )

    # ── Add duration_ms for latency tracking ───────────────────────────────
    op.add_column(
        "var_jobs",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("var_jobs", "duration_ms")
    op.drop_column("var_jobs", "tier")
    op.drop_index("ix_users_api_key_hash", table_name="users")
    op.drop_index("ix_users_external_id", table_name="users")
    op.drop_table("users")
