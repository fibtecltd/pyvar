"""add verified_at timestamp to users

Revision ID: 0006_user_verified_at
Revises: 0005_user_email_suppression
Create Date: 2026-09-07 00:00:00

Adds users.verified_at: the moment GET /auth/verify succeeded for this user
(api/routes/auth.py::verify()), distinct from verification_sent_at (when the
one-time link was emailed, 0004_user_email_verification). Needed to answer
"how many users verified today" — email_verified alone only answers
"how many, ever" (cumulative), with no day-level breakdown.

Nullable, no backfill: existing verified rows (email_verified=true) have no
recorded verification day and are left NULL rather than approximated from
created_at or verification_sent_at, which would misattribute anyone who
verified more than a few minutes after registering/receiving the link.
Cumulative counts (COUNT(email_verified=true)) are unaffected by this gap —
only day-level counts are, and only for rows verified before this migration.

Purely additive — no existing column is touched, per CLAUDE.md's migration
rule (never edit a committed migration, create a new one).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_verified_at"
down_revision: Union[str, None] = "0005_user_email_suppression"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "verified_at")
