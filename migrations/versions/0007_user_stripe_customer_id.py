"""add stripe_customer_id to users

Revision ID: 0007_user_stripe_customer_id
Revises: 0006_user_verified_at
Create Date: 2026-09-12 00:00:00

Adds users.stripe_customer_id — the join key api/routes/billing.py's Stripe
Checkout + webhook flow (item 5, Phase A) uses to find a pyvar user back
from a Stripe event, which only ever carries a Stripe customer ID, never a
pyvar external_id. Set the first time a user starts Checkout; NULL for
every existing row and for any user who has never subscribed.

Nullable, no backfill: no existing user has ever interacted with Stripe (no
billing integration existed before this migration), so there is nothing to
backfill.

Purely additive — no existing column is touched, per CLAUDE.md's migration
rule (never edit a committed migration, create a new one).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_user_stripe_customer_id"
down_revision: Union[str, None] = "0006_user_verified_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_stripe_customer_id", "users", ["stripe_customer_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_stripe_customer_id", "users", type_="unique")
    op.drop_column("users", "stripe_customer_id")
