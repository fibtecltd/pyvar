"""add billing_events table and users.tier_downgrade_reason

Revision ID: 0008_billing_events_and_downgrade_reason
Revises: 0007_user_stripe_customer_id
Create Date: 2026-09-13 00:00:00

Item 5 §8 follow-on (docs/plan-monetization-implementation.md): a durable,
queryable audit trail of every tier change, and the column that tells the
Stripe webhook's invoice.payment_succeeded handler whether a "free" account
should auto-restore to "pro" (it was auto-downgraded and is still an active,
successfully-billed subscriber) or genuinely never subscribed.

Nullable, no backfill: no existing user has ever been auto-downgraded (this
migration adds the mechanism), so there is nothing to backfill for either
the new column or the new table.

Purely additive — no existing column is touched, per CLAUDE.md's migration
rule (never edit a committed migration, create a new one).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_billing_events_and_downgrade_reason"
down_revision: Union[str, None] = "0007_user_stripe_customer_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tier_downgrade_reason", sa.String(64), nullable=True))

    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("old_tier", sa.String(16), nullable=False),
        sa.Column("new_tier", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("stripe_event_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_billing_events_user_created", "billing_events", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_billing_events_stripe_event_id", "billing_events", ["stripe_event_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_billing_events_stripe_event_id", table_name="billing_events")
    op.drop_index("ix_billing_events_user_created", table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_column("users", "tier_downgrade_reason")
