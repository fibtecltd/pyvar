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
- Tier changes (docs/plan-pro-tier-stripe.md): exactly two events act. checkout.session.completed moves a
  free or education account to "pro"; customer.subscription.deleted (Stripe's own end of the subscription: the
  end of the paid period after a cancellation, or the cancellation Stripe makes when its payment retries run
  out) moves a "pro" account to "free". Nothing else changes a tier. In particular a failed payment does NOT:
  Stripe sends invoice.payment_failed on every attempt, not after the last, and retries on its own schedule;
  and a monthly usage cap is a 429 (api/middleware/rate_limit.py), not a downgrade. Both used to move the
  account to Free; an account that paid late or filled its month must keep Pro.
- A paid checkout never changes an enterprise or internal account (a custom plan is not a Pro subscription),
  and a second checkout.session.completed for an account that is already "pro" changes nothing and is logged
  for an operator to refund.
- Every tier change here writes a durable BillingEvent audit row (api/middleware/billing_lifecycle.py) in the
  same transaction as the User.tier mutation, and sends a best-effort SES notification.
- POST /billing/portal opens Stripe's hosted Billing Portal for the caller's Stripe customer: update the card,
  see invoices, cancel at the end of the period. The cancellation itself arrives as customer.subscription.deleted.
- "Billing is not configured on this deployment" is an expected answer (prod has no Stripe secrets until the
  live keys are loaded), so it is returned as a 503 response, not raised: a raised 5xx HTTPException is reported
  to Sentry as an error (the one event in the 2026-11-14 to 2026-11-21 weekly report).
- Idempotent against Stripe's at-least-once redelivery guarantee: every
  tier-changing event's Stripe event ID is checked against
  BillingEvent.stripe_event_id before acting, so a redelivered event doesn't
  duplicate the audit row or resend the notification.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select

from api.middleware.auth import TokenPayload, create_access_token, get_current_user
from api.middleware.billing_lifecycle import (
    DOWNGRADE_SUBSCRIPTION_CANCELLED,
    EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED,
    EVENT_UPGRADED,
    record_billing_event,
    send_tier_change_email,
)
from api.tiers import effective_tier
from config import get_settings
from schemas.billing import CheckoutCompleteResponse, CheckoutResponse, PortalResponse
from storage.models import BillingEvent, User
from storage.session import get_sessionmaker

router = APIRouter(prefix="/billing", tags=["Billing"])
logger = structlog.get_logger()
cfg = get_settings()

# The two Stripe events this webhook acts on — see the module docstring. Anything else Stripe sends
# (customer.updated, invoice.payment_failed, invoice.paid, ...) is acknowledged with 200 and ignored; Stripe
# requires a fast 2xx regardless of whether an event is one this app acts on.
_UPGRADE_EVENT = "checkout.session.completed"
_ENDED_EVENT = "customer.subscription.deleted"
_HANDLED_EVENTS = {_UPGRADE_EVENT, _ENDED_EVENT}
# Tiers a completed checkout may upgrade. Enterprise and internal are custom or service plans, never Pro.
_UPGRADABLE_TIERS = {"free", "education"}
NOT_CONFIGURED_DETAIL = "Billing is not configured on this deployment."
# The Stripe account is SHARED with other Fibtec services (etlgen, TenGrade, DocuGen), and Stripe
# sends every endpoint every event. Every object pyvar creates carries metadata service=pyvar, so the
# others can tell ours from theirs (TenGrade's webhook ignores anything without its own marker).
# pyvar's own webhook does not read it: it finds the user by Stripe customer id, so another service's
# event is an unknown customer and changes nothing.
STRIPE_SERVICE = "pyvar"


def _stripe_client() -> Any:
    """Configure and return the stripe module — a one-off inline builder,
    same pattern as api/routes/auth.py's get_ses_client(). This is the
    mock boundary in tests/test_billing.py, exactly as get_ses_client is
    in tests/test_auth.py.
    """
    import stripe

    stripe.api_key = cfg.stripe_secret_key
    return stripe


def _billing_unavailable() -> JSONResponse | None:
    """None when billing is configured; otherwise the 503 to return. A response, not a raised HTTPException, so
    that this expected answer is not reported to Sentry as an error (see the module docstring)."""
    if not cfg.stripe_secret_key or not cfg.stripe_price_id_pro:
        # Lazy retry: the one-shot fetch at startup (main.py::create_app())
        # may have failed transiently for this specific task (Secrets
        # Manager throttling, a momentary network blip) while other tasks
        # behind the same ALB fetched fine -- see the incident this retry
        # was added for: a user completed a real Stripe Checkout (meaning
        # some healthy task served POST /checkout successfully) but hit
        # this route on a task that never got its secrets, with no retry
        # ever attempted for the rest of that task's lifetime. Cheap when
        # already configured (this block is skipped, and _resolve_stripe_secrets
        # fetches nothing when none of the three is missing) and bounded when
        # genuinely unconfigured (only fires while a billing route is actually hit).
        _resolve_stripe_secrets()
    if not cfg.stripe_secret_key or not cfg.stripe_price_id_pro:
        logger.warning("billing_not_configured")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": NOT_CONFIGURED_DETAIL},
        )
    return None


# (cfg attribute, name suffix): each is read from Secrets Manager at pyvar/{app_env}/<suffix>.
_STRIPE_SECRETS: tuple[tuple[str, str], ...] = (
    ("stripe_secret_key", "stripe-secret-key"),
    ("stripe_webhook_secret", "stripe-webhook-secret"),
    ("stripe_price_id_pro", "stripe-price-id-pro"),
)


def _resolve_stripe_secrets() -> None:
    """Fetch the three Stripe secrets into cfg, mirroring
    observability/setup.py's _resolve_sentry_dsn() -- see api_stack.py's
    comment above stripe_secret_key's construction for why these are no
    longer wired via ECS's native `secrets={}` mechanism (task-launch-
    blocking, and takes down every other route on this container with it).
    Called once at startup (main.py::create_app()) and again lazily from
    _require_billing_configured() if still unconfigured on a later request.

    Only attempts the fetch when actually running in a real ECS task
    (cfg.ecs_container_metadata_uri_v4 set) and only for the secrets still
    missing (local dev / anything injecting these via .env keeps that
    value, and never touches boto3 -- same "no real AWS in tests" rule
    _resolve_sentry_dsn() follows). Each secret is fetched independently:
    a Secrets Manager failure on one (propagation delay, deleted secret,
    IAM policy change) must not prevent the other two from being picked up,
    and must degrade to "billing unconfigured" rather than raise and block
    task launch -- every billing route already 503s via
    _billing_unavailable() when either required value is unset.

    "Still missing" is decided per secret, not once for the lot: the lazy
    retry has to be able to pick up the one secret a startup fetch missed
    even though the other two arrived. (It used to return as soon as
    stripe_secret_key was set, which left a task that had lost only the
    price id answering "Billing is not configured" until it was replaced.)
    """
    if not cfg.ecs_container_metadata_uri_v4:
        return
    missing = [(attr, suffix) for attr, suffix in _STRIPE_SECRETS if not getattr(cfg, attr)]
    if not missing:
        return

    import boto3

    client = boto3.client("secretsmanager")
    for attr, secret_suffix in missing:
        try:
            value = client.get_secret_value(SecretId=f"pyvar/{cfg.app_env}/{secret_suffix}").get(
                "SecretString"
            )
            if value:
                setattr(cfg, attr, value)
            else:
                # A secret created as SecretBinary has no SecretString: that is not an exception,
                # so without this line nothing would say why the secret stayed unset.
                logger.warning("stripe_secret_empty", secret=secret_suffix)
        except Exception:
            logger.warning("stripe_secret_resolution_failed", secret=secret_suffix, exc_info=True)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    user: TokenPayload = Depends(get_current_user),
) -> CheckoutResponse | JSONResponse:
    """Start a Pro subscription: create/reuse a Stripe Customer, return a
    hosted Checkout URL for the client to redirect the browser to.

    Refused with 409 for an account that is already Pro (a second subscription would be charged twice) and for
    enterprise or internal accounts (a custom plan: contact us).
    """
    unavailable = _billing_unavailable()
    if unavailable is not None:
        return unavailable
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

        if row.tier == "pro":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Your account is already on Pro. Use Manage billing to update or cancel it.",
            )
        if row.tier not in _UPGRADABLE_TIERS:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Your account is on a custom plan. Contact info@pyvar.com to change it.",
            )

        if row.stripe_customer_id is None:
            customer = stripe.Customer.create(
                email=row.email,
                metadata={"external_id": user.user_id, "service": STRIPE_SERVICE},
            )
            row.stripe_customer_id = customer.id
            await session.commit()

        customer_id = row.stripe_customer_id

    checkout_session = stripe.checkout.Session.create(
        customer=customer_id,
        client_reference_id=user.user_id,
        mode="subscription",
        line_items=[{"price": cfg.stripe_price_id_pro, "quantity": 1}],
        # The session's events (checkout.session.completed) and the subscription's (customer.
        # subscription.*, and the invoices' subscription details) carry the marker.
        metadata={"service": STRIPE_SERVICE},
        subscription_data={"metadata": {"service": STRIPE_SERVICE}},
        success_url=(
            f"{cfg.public_base_url}/dashboard.html" "?checkout_session_id={CHECKOUT_SESSION_ID}"
        ),
        cancel_url=f"{cfg.public_base_url}/dashboard.html?checkout_cancelled=1",
    )
    logger.info("checkout_session_created", user_id=user.user_id)
    return CheckoutResponse(checkout_url=checkout_session.url)


@router.post("/portal", response_model=PortalResponse)
async def create_portal_session(
    user: TokenPayload = Depends(get_current_user),
) -> PortalResponse | JSONResponse:
    """Open Stripe's hosted Billing Portal for the caller: update the payment method, see invoices, cancel at
    the end of the period. 409 when the account has never subscribed (no Stripe customer yet)."""
    unavailable = _billing_unavailable()
    if unavailable is not None:
        return unavailable
    stripe = _stripe_client()

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(select(User).where(User.external_id == user.user_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
        customer_id = row.stripe_customer_id

    if customer_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There is no subscription to manage yet. Upgrade to Pro first.",
        )

    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id, return_url=f"{cfg.public_base_url}/dashboard.html"
    )
    logger.info("billing_portal_session_created", user_id=user.user_id)
    return PortalResponse(portal_url=portal_session.url)


@router.get("/checkout/complete", response_model=CheckoutCompleteResponse)
async def checkout_complete(session_id: str) -> CheckoutCompleteResponse | JSONResponse:
    """Issue a fresh JWT reflecting the caller's current tier, after Stripe
    redirects the browser back from a completed Checkout. See module
    docstring for why this route exists and why it can't be JWT-authenticated.

    The tier is read from the database: the webhook may land a moment after the redirect, so a client that
    still sees "free" should ask again after a few seconds.
    """
    unavailable = _billing_unavailable()
    if unavailable is not None:
        return unavailable
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
        tier = effective_tier(row.tier, row.tier_expires_at)

    access_token = create_access_token(user_id=external_id, tier=tier)
    return CheckoutCompleteResponse(access_token=access_token, tier=tier)


@router.post("/webhook", status_code=status.HTTP_200_OK, response_model=dict[str, bool])
async def stripe_webhook(request: Request) -> dict[str, bool] | JSONResponse:
    """Stripe webhook receiver — see module docstring for the trust model
    (signature verification, not a JWT) and the two events that change a tier.

    Idempotent against Stripe's own at-least-once redelivery guarantee: every
    tier-changing event's `event["id"]` is checked against BillingEvent.
    stripe_event_id before acting, so a redelivered event is acknowledged
    with 200 but never processed twice — matters here specifically because
    processing has side effects beyond the tier flip itself (an audit row, a
    notification email) that must not double up.
    """
    unavailable = _billing_unavailable()
    if unavailable is not None:
        return unavailable
    stripe = _stripe_client()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, cfg.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        logger.warning("stripe_webhook_verification_failed", error=str(exc))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid webhook signature.") from exc

    event_type = event["type"]
    if event_type not in _HANDLED_EVENTS:
        return {"received": True}

    # event_object is a real stripe.StripeObject (e.g. checkout.Session), not
    # a dict -- it has no .get(); attribute access is how the SDK proxies to
    # the underlying data, so getattr(..., default) is the dict-.get()
    # equivalent here. (Sentry afa9f2520c744907afa5d069149bfcbb.)
    event_object = event["data"]["object"]
    customer_id = getattr(event_object, "customer", None)
    stripe_event_id = event["id"]

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
        external_id = row.external_id

        if event_type == _UPGRADE_EVENT:
            if old_tier == "pro":
                # A second paid subscription for an account that already has Pro: nothing to change,
                # and a charge an operator should refund.
                logger.warning(
                    "stripe_checkout_completed_already_pro",
                    customer_id=customer_id,
                    stripe_event_id=stripe_event_id,
                )
                return {"received": True}
            if old_tier not in _UPGRADABLE_TIERS:
                logger.warning(
                    "stripe_checkout_completed_ignored",
                    tier=old_tier,
                    customer_id=customer_id,
                    stripe_event_id=stripe_event_id,
                )
                return {"received": True}
            new_tier = "pro"
            fired_event_type = EVENT_UPGRADED
            row.tier = new_tier
            row.tier_downgrade_reason = None
            if old_tier == "education":
                row.tier_expires_at = None  # the grant is replaced by the subscription
        else:
            if old_tier != "pro":
                # The subscription ended for an account that is not on Pro (a stray Stripe customer on a
                # free, education or enterprise account): leave the tier alone.
                logger.info(
                    "stripe_subscription_end_ignored",
                    tier=old_tier,
                    customer_id=customer_id,
                    stripe_event_id=stripe_event_id,
                )
                return {"received": True}
            new_tier = "free"
            fired_event_type = EVENT_DOWNGRADED_SUBSCRIPTION_CANCELLED
            row.tier = new_tier
            row.tier_downgrade_reason = DOWNGRADE_SUBSCRIPTION_CANCELLED

        record_billing_event(
            session,
            user_id=external_id,
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
    send_tier_change_email(email, fired_event_type, account_id=external_id)
    return {"received": True}
