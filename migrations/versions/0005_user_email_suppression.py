"""add email suppression columns to users

Revision ID: 0005_user_email_suppression
Revises: 0004_user_email_verification
Create Date: 2026-07-31 00:00:00

Adds (SES production-access review follow-up — bounce/complaint handling):
- users.email_suppressed: true once a permanent bounce or complaint has been
  recorded for this address. Written only by api/routes/internal.py's
  POST /internal/suppress-email, called by
  pyvar-cdk/lambda/ses_suppression_handler/handler.py.
- users.suppression_reason: "bounce_permanent" or "complaint" — a small
  closed vocabulary, not a full audit table (this is operational account
  state, same tier as email_verified right next to it, not a regulatory
  audit record like VaRJob).
- users.suppressed_at: when the suppression was recorded.

SES itself already maintains its own account-level suppression list
(SuppressedReasons: [BOUNCE, COMPLAINT], confirmed via
`aws sesv2 get-account`) and will already refuse to re-send to a
permanently-bounced or complained address. These columns exist so our own
users table reflects that reality (api/routes/auth.py::register() checks
email_suppressed before resending a verification email) and so the
condition is queryable/visible, not just silently enforced by SES.

Purely additive — no existing column is touched, per CLAUDE.md's migration
rule (never edit a committed migration, create a new one).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_user_email_suppression"
down_revision: Union[str, None] = "0004_user_email_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_suppressed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("suppression_reason", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("suppressed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "suppressed_at")
    op.drop_column("users", "suppression_reason")
    op.drop_column("users", "email_suppressed")
