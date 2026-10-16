"""add api_keys table and api_usage.client

Revision ID: 0009_api_keys
Revises: 0008_billing_events_downgrade
Create Date: 2026-10-16 00:00:00

Why (docs/plan-durable-api-keys.md): the "API key" a new user received was a
60-minute JWT with the tier baked in, shown once, and a verified account could
not get another one by email. Plugin users paste a key once, so they were locked
out an hour later. api_keys holds durable, revocable keys (only the SHA-256 of
the secret is stored), looked up per request so the tier is always current.

api_usage.client records which official client made a call (allowlisted header),
so plugin adoption can be split by surface without storing a user identifier.

Purely additive; nullable/new, no backfill. Revision id kept under 32 chars
(alembic_version.version_num is VARCHAR(32), see 0008's note).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_api_keys"
down_revision: Union[str, None] = "0008_billing_events_downgrade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.add_column("api_usage", sa.Column("client", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("api_usage", "client")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_table("api_keys")
