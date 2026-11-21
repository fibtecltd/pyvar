"""
api/middleware/billing_lifecycle.py — shared tier-change audit + notification
helpers (item 5 §8 follow-on).

Reasoning:
- Every site that mutates User.tier from Stripe — the webhook's upgrade and
  subscription-ended handling (api/routes/billing.py) — and the education grant
  routes (api/education_grants.py) needs to do the same two things: write a
  BillingEvent audit row in the same transaction as the tier mutation, and send
  the user a best-effort notification email. Shared here so the call sites stay
  in sync rather than drifting.
- Since 2026-11-21 (docs/plan-pro-tier-stripe.md) a Pro account's tier changes in
  exactly two ways: Stripe Checkout completing moves Free to Pro, and the end of
  the Stripe subscription moves Pro to Free. A monthly usage cap and a failed
  payment no longer change the tier: a cap is a 429 (api/middleware/rate_limit.py,
  api/routes/var.py) and Stripe retries a failed payment itself. The old
  downgrade_for_monthly_limit and restore_after_payment_succeeded paths are gone;
  billing_events rows they wrote stay (audit log, CLAUDE.md 3.3) and their event
  types remain valid strings in the table.
- send_tier_change_email mirrors api/routes/auth.py::send_verification_email
  exactly (same get_ses_client() shape, same non-fatal try/except pattern) —
  deliberately NOT imported from auth.py or extracted into a shared module:
  auth.py's own docstring already explains why its SES client builder is a
  one-off per caller, not centralized, and that reasoning applies here too
  now that there's a second caller with the identical shape.
- The holder's e-mail address is never written to a log line here (docs/plan-education-tier.md
  section 12): server logs reach CloudWatch and, through the default logging integration, Sentry (a
  failed send becomes an error event, a successful one a breadcrumb on any later error), and the
  privacy policy does not list addresses among what Sentry sees. Logs carry the address's domain and,
  where the caller has it, the account id. A failure logs the exception's class and AWS error code, never
  its text or a traceback: SES error messages can echo the recipient's address.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import boto3
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from observability.redact import aws_error_code, email_domain
from storage.models import BillingEvent

cfg = get_settings()
logger = structlog.get_logger()

# ── Downgrade reason (User.tier_downgrade_reason) ───────────────────────────
# The only reason now written. Older rows may still hold "payment_failed", "monthly_request_limit_exceeded" or
# "monthly_simulation_limit_exceeded" from the paths removed on 2026-11-21; nothing reads them.
DOWNGRADE_SUBSCRIPTION_CANCELLED = "subscription_cancelled"

# ── BillingEvent.event_type ──────────────────────────────────────────────────
EVENT_UPGRADED = "upgraded"
EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED = "downgraded_subscription_cancelled"
# The education tier (docs/plan-education-tier.md): written by api/education_grants.py in the same transaction as
# the change. Their `reason` is a code and the cohort label, never an applicant's name or words.
EVENT_EDUCATION_GRANTED = "education_granted"
EVENT_EDUCATION_EXTENDED = "education_extended"
EVENT_EDUCATION_REVOKED = "education_revoked"
EVENT_EDUCATION_SUSPENDED = "education_suspended"
# Housekeeping rows written by the operator's quiet commands (no entry in _NOTIFICATION_COPY: nobody is e-mailed):
# a lapsed education label reset to free (api/education_grants.py::tidy), and an account erased at its holder's
# request (api/account_erasure.py).
EVENT_EDUCATION_TIDIED = "education_tidied"
EVENT_ACCOUNT_ERASED = "account_erased"

_NOTIFICATION_COPY: dict[str, tuple[str, str]] = {
    EVENT_UPGRADED: (
        "Welcome to pyvar Pro",
        "Your pyvar account is now on the Pro plan. Higher daily and monthly limits "
        "and larger simulation sizes are active immediately. Manage or cancel your "
        "subscription from your dashboard; if you cancel, Pro continues to the end "
        "of the period you have paid for.",
    ),
    EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED: (
        "Your pyvar Pro subscription ended",
        "Your pyvar Pro subscription has been cancelled and your account is "
        "now on the Free plan. You can resubscribe any time from your "
        "dashboard.",
    ),
    EVENT_EDUCATION_GRANTED: (
        "Your pyvar education access is active",
        "Your pyvar account now has education access: higher daily limits and larger simulation "
        "sizes for teaching and study. It is for non-commercial use and ends on {end_date}; "
        "after that your account is on the Free plan and your API keys keep working with the "
        "Free limits. To ask for an extension, reply to the e-mail you applied with.",
    ),
    EVENT_EDUCATION_EXTENDED: (
        "Your pyvar education access was extended",
        "Your pyvar education access has been extended. It now ends on {end_date}.",
    ),
    EVENT_EDUCATION_REVOKED: (
        "Your pyvar education access has ended",
        "Your pyvar education access has ended and your account is on the Free plan. "
        "Your API keys keep working with the Free limits.",
    ),
    EVENT_EDUCATION_SUSPENDED: (
        "Your pyvar education access is paused",
        "Your pyvar education access has been paused and your account is on the Free plan "
        "for now. Your API keys keep working with the Free limits.",
    ),
}


def _get_ses_client() -> Any:
    """One-off boto3 SES client builder — see module docstring for why this
    isn't shared with api/routes/auth.py's identically-shaped helper."""
    return boto3.client("ses", region_name=cfg.ses_region)


def _end_date_text(end_date: date | datetime | None) -> str:
    """ "20 May 2027": unambiguous for a reader in any country. Without a date, the old wording."""
    if end_date is None:
        return "the date agreed"
    return f"{end_date.day} {end_date.strftime('%B %Y')}"


def send_tier_change_email(
    email: str | None,
    event_type: str,
    *,
    end_date: date | datetime | None = None,
    account_id: str | None = None,
) -> None:
    """Best-effort notification on any tier change. Never raises — the tier
    mutation itself has already been committed by the time this is called
    from every call site below, so a notification failure must never look
    like the tier change itself failed.

    Args:
        email: Where to send it; nothing is sent (or logged) if empty.
        event_type: One of the EVENT_* names with copy in `_NOTIFICATION_COPY`.
        end_date: For the education grant and extension e-mails, the day access ends; the copy
            says "the date agreed" if it is missing.
        account_id: The account's external id, logged in place of the address when the caller has it.

    The address is never logged (see the module docstring): logs carry its domain, the event, the
    account id if given and, on failure, the exception class and AWS error code.
    """
    if not email:
        return

    copy = _NOTIFICATION_COPY.get(event_type)
    if copy is None:
        logger.warning("tier_change_email_unknown_event_type", event_type=event_type)
        return
    subject, body = copy
    if "{end_date}" in body:
        body = body.replace("{end_date}", _end_date_text(end_date))

    try:
        _get_ses_client().send_email(
            Source=cfg.ses_sender_email,
            Destination={"ToAddresses": [email]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        logger.info(
            "tier_change_email_sent",
            email_domain=email_domain(email),
            account_id=account_id,
            event_type=event_type,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort send, see docstring
        # No exc_info and no str(exc): an SES error message can echo the recipient's address, and this
        # line reaches Sentry. The class and the AWS error code are enough to act on.
        logger.error(
            "tier_change_email_send_failed",
            email_domain=email_domain(email),
            account_id=account_id,
            event_type=event_type,
            error_type=type(exc).__name__,
            error_code=aws_error_code(exc),
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
