"""
api/middleware/billing_lifecycle.py — shared tier-change audit + notification
helpers (item 5 §8 follow-on).

Reasoning:
- Every site that mutates User.tier — the Stripe webhook's upgrade/downgrade
  handling (api/routes/billing.py) and the two monthly-limit downgrade paths
  (api/middleware/rate_limit.py, api/routes/var.py) — needs to do the same
  two things: write a BillingEvent audit row in the same transaction as the
  tier mutation, and send the user a best-effort notification email. Shared
  here so all three call sites stay in sync rather than drifting.
- send_tier_change_email mirrors api/routes/auth.py::send_verification_email
  exactly (same get_ses_client() shape, same non-fatal try/except pattern) —
  deliberately NOT imported from auth.py or extracted into a shared module:
  auth.py's own docstring already explains why its SES client builder is a
  one-off per caller, not centralized, and that reasoning applies here too
  now that there's a second caller with the identical shape.
- downgrade_for_monthly_limit is idempotent by design: a client whose JWT
  still carries the (now stale) "pro" claim keeps hitting the calling
  dependency on every subsequent request until it fetches a fresh token
  (GET /billing/checkout/complete is the only place that happens today —
  see docs/plan-monetization-implementation.md's JWT-staleness writeup).
  Re-downgrading an already-"free" account here is a no-op (skips the
  duplicate audit row and duplicate email); the CALLER is still responsible
  for rejecting the request either way, every time.
- restore_after_payment_succeeded treats ANY successful Stripe payment as
  sufficient signal to restore Pro access, not narrowly "was downgraded for
  exceeding a monthly limit specifically" — see its own docstring.
"""

from __future__ import annotations

from typing import Any

import boto3
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from storage.models import BillingEvent, User
from storage.session import get_sessionmaker

cfg = get_settings()
logger = structlog.get_logger()

# ── Downgrade reasons (User.tier_downgrade_reason) ──────────────────────────
DOWNGRADE_PAYMENT_FAILED = "payment_failed"
DOWNGRADE_SUBSCRIPTION_CANCELLED = "subscription_cancelled"
DOWNGRADE_MONTHLY_REQUEST_LIMIT = "monthly_request_limit_exceeded"
DOWNGRADE_MONTHLY_SIMULATION_LIMIT = "monthly_simulation_limit_exceeded"

# ── BillingEvent.event_type ──────────────────────────────────────────────────
EVENT_UPGRADED = "upgraded"
EVENT_DOWNGRADED_PAYMENT_FAILED = "downgraded_payment_failed"
EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED = "downgraded_subscription_cancelled"
EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT = "downgraded_monthly_request_limit"
EVENT_DOWNGRADED_MONTHLY_SIMULATION_LIMIT = "downgraded_monthly_simulation_limit"
EVENT_RESTORED_AFTER_PAYMENT_SUCCEEDED = "restored_after_payment_succeeded"

_NOTIFICATION_COPY: dict[str, tuple[str, str]] = {
    EVENT_UPGRADED: (
        "Welcome to pyvar Pro",
        "Your pyvar account is now on the Pro plan. Higher daily limits and "
        "larger simulation sizes are active immediately.",
    ),
    EVENT_DOWNGRADED_PAYMENT_FAILED: (
        "Your pyvar Pro payment failed",
        "Your most recent payment for pyvar Pro didn't go through, so your "
        "account has moved to the Free plan. Update your payment method and "
        "resubscribe any time from your dashboard.",
    ),
    EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED: (
        "Your pyvar Pro subscription ended",
        "Your pyvar Pro subscription has been cancelled and your account is "
        "now on the Free plan. You can resubscribe any time from your "
        "dashboard.",
    ),
    EVENT_DOWNGRADED_MONTHLY_REQUEST_LIMIT: (
        "pyvar Pro monthly request limit reached",
        "Your account reached its Pro plan's request limit for this billing "
        "period and has moved to the Free plan's limits for the rest of the "
        "period. Your Pro subscription is still active — your full Pro "
        "limits resume automatically at your next billing date.",
    ),
    EVENT_DOWNGRADED_MONTHLY_SIMULATION_LIMIT: (
        "pyvar Pro monthly simulation limit reached",
        "Your account reached its Pro plan's simulation-count limit for "
        "this billing period and has moved to the Free plan's limits for "
        "the rest of the period. Your Pro subscription is still active — "
        "your full Pro limits resume automatically at your next billing "
        "date.",
    ),
    EVENT_RESTORED_AFTER_PAYMENT_SUCCEEDED: (
        "Your pyvar Pro access is active again",
        "A successful payment on your pyvar Pro subscription has restored "
        "your full Pro limits.",
    ),
}


def _get_ses_client() -> Any:
    """One-off boto3 SES client builder — see module docstring for why this
    isn't shared with api/routes/auth.py's identically-shaped helper."""
    return boto3.client("ses", region_name=cfg.ses_region)


def send_tier_change_email(email: str | None, event_type: str) -> None:
    """Best-effort notification on any tier change. Never raises — the tier
    mutation itself has already been committed by the time this is called
    from every call site below, so a notification failure must never look
    like the tier change itself failed.
    """
    if not email:
        return

    copy = _NOTIFICATION_COPY.get(event_type)
    if copy is None:
        logger.warning("tier_change_email_unknown_event_type", event_type=event_type)
        return
    subject, body = copy

    try:
        _get_ses_client().send_email(
            Source=cfg.ses_sender_email,
            Destination={"ToAddresses": [email]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        logger.info("tier_change_email_sent", email=email, event_type=event_type)
    except Exception:  # noqa: BLE001 — best-effort send, see docstring
        # Unlike auth.py's send_verification_email, there is no recoverable
        # token a human needs from this log line — always the safe (no
        # secret material) branch, in every environment.
        logger.error(
            "tier_change_email_send_failed", email=email, event_type=event_type, exc_info=True
        )


def record_billing_event(
    session: AsyncSession,
    *,
    user_id: str,
    event_type: str,
    old_tier: str,
    new_tier: str,
    reason: str | None = None,
    stripe_event_id: str | None = None,
) -> None:
    """Adds a BillingEvent row to `session` — does NOT commit. Callers write
    this in the SAME transaction as the User.tier mutation it's auditing, so
    the two can never disagree (a mutation with no event row, or vice versa).
    """
    session.add(
        BillingEvent(
            user_id=user_id,
            event_type=event_type,
            old_tier=old_tier,
            new_tier=new_tier,
            reason=reason,
            stripe_event_id=stripe_event_id,
        )
    )


async def downgrade_for_monthly_limit(
    *,
    user_id: str,
    downgrade_reason: str,
    event_type: str,
    detail: str,
) -> None:
    """Hard-downgrades a Pro account to Free for exceeding a monthly usage
    cap. api/middleware/rate_limit.py (request-count) and api/routes/var.py
    (VaR simulation-count) are the two call sites — see module docstring for
    the idempotency contract both rely on.
    """
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(select(User).where(User.external_id == user_id))
        ).scalar_one_or_none()

        if row is None:
            # Same anomaly noted in api/routes/billing.py::create_checkout —
            # every JWT is minted for a real users row, so this means the row
            # was deleted out from under a still-valid token.
            logger.warning("monthly_limit_downgrade_user_not_found", user_id=user_id)
            return
        if row.tier != "pro":
            return  # already downgraded (stale JWT retry) — nothing to do

        row.tier = "free"
        row.tier_downgrade_reason = downgrade_reason
        record_billing_event(
            session,
            user_id=user_id,
            event_type=event_type,
            old_tier="pro",
            new_tier="free",
            reason=detail,
        )
        await session.commit()
        email = row.email

    logger.info(
        "monthly_limit_downgrade_applied", user_id=user_id, downgrade_reason=downgrade_reason
    )
    send_tier_change_email(email, event_type)


def restore_after_payment_succeeded(
    session: AsyncSession, row: User, *, stripe_event_id: str | None = None
) -> str | None:
    """If `row` isn't already "pro", flips it to "pro" and clears
    tier_downgrade_reason.

    ANY successful payment on this Stripe customer's subscription — not
    narrowly "was downgraded for a monthly limit specifically" — is treated
    as sufficient signal that Pro access should be active: an account whose
    card was previously declined (tier_downgrade_reason ==
    DOWNGRADE_PAYMENT_FAILED) and has now been successfully rebilled
    (Stripe's own automatic retry, or a fixed payment method) gets Pro back
    automatically too, rather than staying stuck on Free until it starts a
    brand new Checkout — closing a real gap the original payment-decline
    downgrade left open.

    Does NOT commit — the caller (api/routes/billing.py's webhook, already
    inside its own session block) commits once alongside this. Returns the
    event_type written for the caller's own post-commit notification email,
    or None if this was a no-op (already "pro").
    """
    if row.tier == "pro":
        return None

    old_tier = row.tier
    row.tier = "pro"
    row.tier_downgrade_reason = None
    record_billing_event(
        session,
        user_id=row.external_id,
        event_type=EVENT_RESTORED_AFTER_PAYMENT_SUCCEEDED,
        old_tier=old_tier,
        new_tier="pro",
        reason="Stripe invoice payment succeeded.",
        stripe_event_id=stripe_event_id,
    )
    return EVENT_RESTORED_AFTER_PAYMENT_SUCCEEDED
