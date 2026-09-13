"""
api/routes/billing.py — Stripe Checkout + webhook flow, Phase A (item 5)

Reasoning:
- Scope is deliberately narrow — see docs/plan-monetization-implementation.md
  §4: billing plumbing only. The existing higher rate-limit cap
  (api/middleware/rate_limit.py, cfg.rate_limit_pro_daily) is the entire Pro
  value proposition for now; no priority queue, no extended result
  retention (that's Phase B, explicitly deferred).
- Stripe Checkout, not a custom card form: pyvar's own infrastructure never
  touches card data (PCI SAQ-A scope, not SAQ-D) — the plan doc's own
  recommendation, matching CLAUDE.md §3.4's "secrets never touch our own
  code" posture. Monthly-only, no trial (confirmed decisions) — a single
  Stripe Price ID (cfg.stripe_price_id_pro), no plan selector.
- Enterprise stays entirely out of this file, by design: it's a manual,
  sales-assisted path (a "Contact us" link already on the homepage), not a
  checkout-button feature — confirmed decision, plan doc §4.4.
- Three routes, three different trust boundaries:
    1. POST /billing/checkout — JWT-authenticated (Depends(get_current_user)),
       same as every compute endpoint.
    2. POST /billing/webhook — NOT JWT-authenticated. Stripe calls this
       directly with no Authorization header at all; trust instead comes
       from verifying the request body against cfg.stripe_webhook_secret
       (stripe.Webhook.construct_event) exactly the way an HMAC-signed
       webhook should be verified, not from any bearer token.
    3. GET /billing/checkout/complete — NOT JWT-authenticated either. This
       is hit by a plain browser redirect after Stripe's hosted Checkout
       page, which cannot carry an Authorization header. Trust instead
       comes from ?session_id being an unguessable Stripe-generated ID that
       is verified server-to-server against Stripe's own API
       (stripe.checkout.Session.retrieve), never taken as client-asserted
       fact.
- The JWT staleness gap this closes: api/middleware/auth.py's TokenPayload
  (and therefore enforce_compute_rate_limit's tier check) is decoded
  entirely from the JWT's own embedded "tier" claim — it never re-queries
  the database. So flipping users.tier in the DB via the webhook does NOT
  by itself change what an *already-issued* JWT is entitled to; the caller
  needs a NEW token with "tier": "pro" baked in. GET /billing/checkout/complete
  is that: the one place, symmetric with GET /auth/verify, where a fresh
  token gets issued reflecting the user's current DB tier. Without it, a
  successful subscription would be real in the database but invisible to
  actual enforcement until the user found some other way to get a new
  token — and today there is no other way (this app has no login/refresh
  endpoint at all; see api/routes/auth.py's own "minimum viable" scope
  note). This route is that minimum necessary bridge, not a general-purpose
  token refresh mechanism.
- stripe_customer_id (0007_user_stripe_customer_id) is the join key for all
  three routes: Stripe events and the Checkout Session both carry a Stripe
  customer ID, never a pyvar external_id. Created once, on this user's
  first-ever checkout, and reused for every subscription after that.
- Downgrade paths: customer.subscription.deleted (a cancellation reaching
  the end of its billing period) and invoice.payment_failed (a renewal that
  exhausted Stripe's own retry schedule) both flip tier back to "free" —
  the plan doc's own definition of done is explicit that failed/cancelled
  payments must not be silently left on "pro" forever.
- Item 5 §8 follow-on: every tier change here (upgrade, either downgrade
  path, and the restore path below) now writes a durable BillingEvent audit
  row (api/middleware/billing_lifecycle.py) in the same transaction as the
  User.tier mutation, and sends a best-effort SES notification — closing the
  "downgrade happens silently" gap flagged when Phase A first shipped.
- Restore path: invoice.paid / invoice.payment_succeeded (Stripe's "an
  invoice was paid" signal, checked for both since Stripe emits one or the
  other depending on API version/integration age) restores "pro" for any
  account that isn't already Pro — see
  billing_lifecycle.restore_after_payment_succeeded's own docstring for why
  this applies to ANY successful payment, not narrowly the monthly-limit-
  downgrade scenario it was added for (api/middleware/rate_limit.py,
  api/routes/var.py's monthly caps).
- Idempotent against Stripe's at-least-once redelivery guarantee: every
  tier-changing event's Stripe event ID is checked against
  BillingEvent.stripe_event_id before acting, so a redelivered event doesn't
  duplicate the audit row or resend the notification.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from api.middleware.auth import TokenPayload, create_access_token, get_current_user
from api.middleware.billing_lifecycle import (
    DOWNGRADE_PAYMENT_FAILED,
    DOWNGRADE_SUBSCRIPTION_CANCELLED,
    EVENT_DOWNGRADED_PAYMENT_FAILED,
    EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED,
    EVENT_UPGRADED,
    record_billing_event,
    restore_after_payment_succeeded,
    send_tier_change_email,
)
from config import get_settings
from schemas.billing import CheckoutCompleteResponse, CheckoutResponse
from storage.models import BillingEvent, User
from storage.session import get_sessionmaker

router = APIRouter(prefix="/billing", tags=["Billing"])
logger = structlog.get_logger()
cfg = get_settings()

# Subscription-lifecycle events this webhook acts on — see module docstring.
# Anything else Stripe sends (customer.updated, etc.) is acknowledged with
# 200 and otherwise ignored; Stripe requires a fast 2xx regardless of
# whether an event is one this app acts on.
_DOWNGRADE_EVENTS = {
    "customer.subscription.deleted": (EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED, DOWNGRADE_SUBSCRIPTION_CANCELLED),
    "invoice.payment_failed": (EVENT_DOWNGRADED_PAYMENT_FAILED, DOWNGRADE_PAYMENT_FAILED),
}
# Both are Stripe's "an invoice was paid" signal (invoice.paid is the modern
# name; invoice.payment_succeeded is the older/still-emitted equivalent) —
# treated identically. See billing_lifecycle.restore_after_payment_succeeded's
# own docstring for why ANY successful payment restores Pro, not narrowly
# "was downgraded for a monthly limit specifically" (item 5 §8 follow-on).
_RESTORE_EVENTS = {"invoice.paid", "invoice.payment_succeeded"}


def _stripe_client() -> Any:
    """Configure and return the stripe module — a one-off inline builder,
    same pattern as api/routes/auth.py's get_ses_client(). This is the
    mock boundary in tests/test_billing.py, exactly as get_ses_client is
    in tests/test_auth.py.
    """
    import stripe

    stripe.api_key = cfg.stripe_secret_key
    return stripe


def _require_billing_configured() -> None:
    if not cfg.stripe_secret_key or not cfg.stripe_price_id_pro:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Billing is not configured on this deployment.",
        )


def _resolve_stripe_secrets() -> None:
    """Fetch the three Stripe secrets into cfg at startup, mirroring
    observability/setup.py's _resolve_sentry_dsn() -- see api_stack.py's
    comment above stripe_secret_key's construction for why these are no
    longer wired via ECS's native `secrets={}` mechanism (task-launch-
    blocking, and takes down every other route on this container with it).

    Only attempts the fetch when actually running in a real ECS task
    (cfg.ecs_container_metadata_uri_v4 set) and only when not already
    configured (local dev / anything injecting these via .env keeps that
    value, and never touches boto3 -- same "no real AWS in tests" rule
    _resolve_sentry_dsn() follows). A Secrets Manager failure here leaves
    cfg.stripe_secret_key unset, which every billing route already handles
    via _require_billing_configured()'s 503 -- so a propagation delay or
    outage degrades billing specifically, never blocks task launch or any
    of the platform's actual risk-computation routes.
    """
    if cfg.stripe_secret_key:
        return
    if not cfg.ecs_container_metadata_uri_v4:
        return
    try:
        import boto3

        client = boto3.client("secretsmanager")
        cfg.stripe_secret_key = client.get_secret_value(
            SecretId=f"pyvar/{cfg.app_env}/stripe-secret-key"
        ).get("SecretString")
        cfg.stripe_webhook_secret = client.get_secret_value(
            SecretId=f"pyvar/{cfg.app_env}/stripe-webhook-secret"
        ).get("SecretString")
        cfg.stripe_price_id_pro = client.get_secret_value(
            SecretId=f"pyvar/{cfg.app_env}/stripe-price-id-pro"
        ).get("SecretString")
    except Exception:
        logger.warning("stripe_secret_resolution_failed", exc_info=True)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(user: TokenPayload = Depends(get_current_user)) -> CheckoutResponse:
    """Start a Pro subscription: create/reuse a Stripe Customer, return a
    hosted Checkout URL for the client to redirect the browser to.
    """
    _require_billing_configured()
    stripe = _stripe_client()

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(select(User).where(User.external_id == user.user_id))
        ).scalar_one_or_none()

        if row is None:
            # Every JWT is minted for a real users row (create_access_token
            # is only ever called from api/routes/auth.py::verify() and this
            # module's own checkout_complete(), both post-DB-lookup) — this
            # branch means the row was deleted out from under a still-valid
            # token, not a normal user-facing case.
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

        if row.stripe_customer_id is None:
            customer = stripe.Customer.create(
                email=row.email, metadata={"external_id": user.user_id}
            )
            row.stripe_customer_id = customer.id
            await session.commit()

        customer_id = row.stripe_customer_id

    checkout_session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=user.user_id,
        mode="subscription",
        line_items=[{"price": cfg.stripe_price_id_pro, "quantity": 1}],
        success_url=(
            f"{cfg.public_base_url}/dashboard.html" "?checkout_session_id={CHECKOUT_SESSION_ID}"
        ),
        cancel_url=f"{cfg.public_base_url}/dashboard.html?checkout_cancelled=1",
    )
    logger.info("checkout_session_created", user_id=user.user_id)
    return CheckoutResponse(checkout_url=checkout_session.url)


@router.get("/checkout/complete", response_model=CheckoutCompleteResponse)
async def checkout_complete(session_id: str) -> CheckoutCompleteResponse:
    """Issue a fresh JWT reflecting the caller's current tier, after Stripe
    redirects the browser back from a completed Checkout. See module
    docstring for why this route exists and why it can't be JWT-authenticated.
    """
    _require_billing_configured()
    stripe = _stripe_client()

    checkout_session = stripe.checkout.Session.retrieve(session_id)
    if checkout_session.payment_status != "paid":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Checkout was not completed.")

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                select(User).where(User.stripe_customer_id == checkout_session.customer)
            )
        ).scalar_one_or_none()

        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

        external_id = row.external_id
        tier = row.tier

    access_token = create_access_token(user_id=external_id, tier=tier)
    return CheckoutCompleteResponse(access_token=access_token, tier=tier)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request) -> dict:
    """Stripe webhook receiver — see module docstring for the trust model
    (signature verification, not a JWT) and which events flip tier which way.

    Idempotent against Stripe's own at-least-once redelivery guarantee: every
    tier-changing event's `event["id"]` is checked against BillingEvent.
    stripe_event_id before acting, so a redelivered event is acknowledged
    with 200 but never processed twice (item 5 §8 follow-on) — matters here
    specifically because processing now has side effects beyond the tier
    flip itself (an audit row, a notification email) that must not double up.
    """
    _require_billing_configured()
    stripe = _stripe_client()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, cfg.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("stripe_webhook_verification_failed", error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature.") from exc

    event_type = event["type"]
    event_object = event["data"]["object"]
    customer_id = event_object.get("customer")
    stripe_event_id = event["id"]

    is_upgrade = event_type == "checkout.session.completed"
    is_downgrade = event_type in _DOWNGRADE_EVENTS
    is_restore = event_type in _RESTORE_EVENTS
    if not (is_upgrade or is_downgrade or is_restore):
        return {"received": True}

    if not customer_id:
        # Shouldn't happen for these event types (every one carries a
        # customer), but a missing join key is exactly the kind of thing
        # worth logging rather than silently 200-ing over.
        logger.warning("stripe_webhook_missing_customer", event_type=event_type)
        return {"received": True}

    async with get_sessionmaker()() as session:
        duplicate = (
            await session.execute(
                select(BillingEvent).where(BillingEvent.stripe_event_id == stripe_event_id)
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            logger.info(
                "stripe_webhook_duplicate_event_ignored",
                event_type=event_type,
                stripe_event_id=stripe_event_id,
            )
            return {"received": True}

        row = (
            await session.execute(select(User).where(User.stripe_customer_id == customer_id))
        ).scalar_one_or_none()

        if row is None:
            logger.warning(
                "stripe_webhook_unknown_customer", event_type=event_type, customer_id=customer_id
            )
            return {"received": True}

        old_tier = row.tier
        email = row.email
        fired_event_type: str | None

        if is_restore:
            fired_event_type = restore_after_payment_succeeded(
                session, row, stripe_event_id=stripe_event_id
            )
            if fired_event_type is None:
                # Already Pro (e.g. the first invoice.payment_succeeded for a
                # brand-new subscription, which checkout.session.completed
                # already handled) — nothing changed, nothing to record.
                await session.commit()
                return {"received": True}
            new_tier = "pro"
        elif is_upgrade:
            new_tier = "pro"
            row.tier = new_tier
            row.tier_downgrade_reason = None
            fired_event_type = EVENT_UPGRADED
            record_billing_event(
                session,
                user_id=row.external_id,
                event_type=fired_event_type,
                old_tier=old_tier,
                new_tier=new_tier,
                stripe_event_id=stripe_event_id,
            )
        else:
            fired_event_type, downgrade_reason = _DOWNGRADE_EVENTS[event_type]
            new_tier = "free"
            row.tier = new_tier
            row.tier_downgrade_reason = downgrade_reason
            record_billing_event(
                session,
                user_id=row.external_id,
                event_type=fired_event_type,
                old_tier=old_tier,
                new_tier=new_tier,
                stripe_event_id=stripe_event_id,
            )

        await session.commit()

    logger.info(
        "stripe_webhook_tier_updated",
        event_type=event_type,
        customer_id=customer_id,
        old_tier=old_tier,
        new_tier=new_tier,
    )
    send_tier_change_email(email, fired_event_type)
    return {"received": True}
