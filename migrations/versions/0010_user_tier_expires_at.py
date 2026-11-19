"""add users.tier_expires_at

Revision ID: 0010_user_tier_expires_at
Revises: 0009_api_keys
Create Date: 2026-11-19 00:00:00

Why (docs/plan-education-tier.md): the education tier is a finite grant, not a plan someone subscribes to. An
account with tier "education" counts as one only while this timestamp is in the future; with no expiry, or a past
one, api/tiers.py::effective_tier treats it as "free". Storing the end date on the row means nothing has to run
at expiry: an elapsed grant simply stops being read. Revoking is an UPDATE that sets the tier back to "free".

Purely additive: one nullable column, no default, no backfill (every existing row keeps NULL). The column is not
indexed; the only query that scans it (the grant caps and `list`) is by tier, over at most a few dozen rows.
Revision id kept under 32 chars (alembic_version.version_num is VARCHAR(32), see 0008's note).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_user_tier_expires_at"
down_revision: Union[str, None] = "0009_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tier_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "tier_expires_at")
