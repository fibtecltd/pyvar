"""add email verification columns to users

Revision ID: 0004_user_email_verification
Revises: 0003_api_usage
Create Date: 2026-07-22 00:00:00

Adds (P8 Task 3 — API key registration flow):
- users.email: the address a new account registers with. NOT the same as
  external_id (0002_users_and_tier: "Matches the 'sub' claim in the JWT —
  external identity provider ID") — there is no external identity provider
  yet, so api/routes/auth.py generates a fresh external_id (a UUID) at
  registration and uses it as the JWT 'sub' claim once verified.
- users.email_verified: false until GET /auth/verify succeeds.
- users.verification_token: one-time token emailed (see
  api/routes/auth.py's send_verification_email — currently a log-only stub,
  #149) to confirm the address; cleared after use.
- users.verification_sent_at: token issuance time, checked against
  Settings.verification_token_expiry_minutes on verify.

Purely additive — no existing column is touched, per CLAUDE.md's migration
rule (never edit a committed migration, create a new one).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_user_email_verification"
down_revision: Union[str, None] = "0003_api_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable=True (not False): this is an ALTER TABLE on an existing table,
    # not a CREATE TABLE. A NOT NULL column with no server_default fails
    # outright if the table already has any rows. Every row created via
    # api/routes/auth.py's register() always sets email (schemas.auth.
    # RegisterRequest requires it), so the "email is required" invariant is
    # enforced at the application layer instead of the DB layer here.
    op.add_column("users", sa.Column("email", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("verification_token", sa.String(64), nullable=True))
    op.add_column(
        "users", sa.Column("verification_sent_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_index("ix_users_verification_token", "users", ["verification_token"])


def downgrade() -> None:
    op.drop_index("ix_users_verification_token", table_name="users")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "verification_sent_at")
    op.drop_column("users", "verification_token")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "email")
