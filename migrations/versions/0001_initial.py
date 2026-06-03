"""create var_jobs audit table

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-24 00:00:00

This is the initial migration. It creates the var_jobs table which
serves as the durable audit log for all VaR computation requests.

IMPORTANT: This table is an AUDIT LOG. Rows are never deleted
programmatically. S3 lifecycle rules handle result file expiry.
The table itself should be retained indefinitely for compliance.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "var_jobs",
        # Primary key — UUID for distributed uniqueness
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # Celery task ID — matches the Celery result backend key
        sa.Column("task_id", sa.String(64), nullable=False),
        # User who submitted the job (from JWT sub claim)
        sa.Column("user_id", sa.String(128), nullable=False),
        # Lifecycle status: pending | started | success | failure
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Error details (for failed jobs)
        sa.Column("error_message", sa.Text(), nullable=True),
        # Request parameters stored for audit and billing
        sa.Column("portfolio_value", sa.Float(), nullable=False),
        sa.Column("n_simulations", sa.Integer(), nullable=False),
        sa.Column("confidence_level", sa.Float(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        # Scalar results (stored inline for queryability — no S3 fetch needed)
        sa.Column("var_pct", sa.Float(), nullable=True),
        sa.Column("var_abs", sa.Float(), nullable=True),
        sa.Column("cvar_pct", sa.Float(), nullable=True),
        sa.Column("cvar_abs", sa.Float(), nullable=True),
        # S3 key for the full Parquet result (loss distribution array)
        sa.Column("result_s3_key", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_var_jobs_task_id"),
    )

    # Index for user history queries: SELECT * FROM var_jobs WHERE user_id=? ORDER BY created_at DESC
    op.create_index(
        "ix_var_jobs_user_created",
        "var_jobs",
        ["user_id", "created_at"],
    )

    # Index for task_id lookups: GET /var/result/{task_id}
    op.create_index(
        "ix_var_jobs_task_id",
        "var_jobs",
        ["task_id"],
    )

    # Index for status monitoring: COUNT(*) WHERE status='pending'
    op.create_index(
        "ix_var_jobs_status",
        "var_jobs",
        ["status"],
    )


def downgrade() -> None:
    # CAUTION: dropping this table permanently loses the audit log.
    # In production, prefer disabling writes rather than dropping.
    op.drop_index("ix_var_jobs_status", table_name="var_jobs")
    op.drop_index("ix_var_jobs_task_id", table_name="var_jobs")
    op.drop_index("ix_var_jobs_user_created", table_name="var_jobs")
    op.drop_table("var_jobs")
