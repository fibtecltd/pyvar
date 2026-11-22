"""tests/test_pro_offer.py — the Pro offer the owner published is the offer the code runs (docs/plan-pro-tier-stripe.md).

Reasoning:
- The offer: £50 per account per month in GBP; one account; all its keys share one set of limits; up to 5 active
  keys; 100,000 simulations per request, 500 requests a day, 5,000 requests and 2,000,000 simulations a month; a
  monthly cap refuses until the window rolls over and never downgrades; cancelling keeps Pro to the end of the paid
  period, then the account returns to Free and its account and keys stay; a failed payment does not end Pro.
- Numbers appear in four places (api/tiers.py via config.py, the Terms, the home page and the dashboard, plus the
  public REST guide). A number that drifts in one of them is a promise nobody made, so each is derived here from
  the policy row and compared with what the pages say.
- The rest pins behaviour that the pieces' own tests cannot see together: a cancelled account's keys keep working
  with the Free limits (a real in-memory database, the real webhook and the real key lookup), and "Billing is not
  configured" reaches Sentry as no event at all (a real client with the FastAPI integration), while a raised 503
  would be an error event (the control, so that the test can fail).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import stripe as stripe_sdk
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from api.middleware.api_keys import generate_key, invalidate_cached_key, resolve_api_key
from api.middleware.auth import create_access_token
from api.routes import billing as billing_module
from api.tiers import policy_for
from config import get_settings
from main import create_app
from storage.models import ApiKey, BillingEvent, User
from tests import test_education_admin as admin_tests
from tests.test_billing import _event
from tests.test_sentry_privacy import events_in, received, recording_client

db = admin_tests.db
redis = admin_tests.redis

cfg = get_settings()
PORTAL = Path(__file__).resolve().parents[1] / "portal"

pytestmark = pytest.mark.filterwarnings("ignore:The send_default_pii option is deprecated")


def page(name: str) -> str:
    return (PORTAL / name).read_text(encoding="utf-8")


def n(value: int) -> str:
    return f"{value:,}"


# ── the numbers ──────────────────────────────────────────────────────────────


def test_the_offer_in_the_tier_table_is_the_published_offer() -> None:
    pro = policy_for("pro")
    assert (
        pro.max_simulations,
        pro.daily_requests,
        pro.monthly_requests,
        pro.monthly_simulations,
    ) == (100_000, 500, 5_000, 2_000_000)
    assert cfg.api_key_max_active_per_user == 5  # tests/test_api_keys.py proves the 6th is refused


def test_the_terms_state_the_offer_in_words_and_numbers() -> None:
    terms = page("terms.html")
    pro = policy_for("pro")
    assert 'id="pro"' in terms
    for words in (
        "open to customers worldwide",
        "&pound;50 per account per month",
        "in pounds sterling",
        "for customers in the United Kingdom the price includes VAT",
        "no annual plan and no free trial",
        "up to 5 active keys",
        "info@pyvar.com, with no guarantee of response times",
        "no priority queue, longer retention or service level",
        "30 days counted from your first request in it",
        "Reaching a limit changes nothing else about your account, and Pro stays active",
        "Pro continues to the end of the period you have paid for",
        "your account and your API keys stay",
        "Stripe retries it on its own schedule and Pro stays active",
    ):
        assert words in terms, words
    figures = (
        f"{n(pro.max_simulations)} simulations per request, {n(pro.daily_requests)} requests a day, "
        f"{n(pro.monthly_requests)} requests a month and {n(pro.monthly_simulations)} simulations a month"
    )
    assert figures in terms


def test_the_home_page_prices_the_three_plans_and_states_the_free_limit() -> None:
    home = page("index.html")
    assert (
        f"Free &pound;0 ({cfg.rate_limit_free_daily} requests a day) &middot; "
        "Pro &pound;50 per account per month, VAT included for UK customers"
    ) in home
    assert 'href="terms.html#pro"' in home and "Enterprise by" in home
    assert cfg.rate_limit_free_daily == 20  # "10" survives only in two old planning documents


def test_the_dashboard_offer_text_matches_the_tier_table() -> None:
    script = page("pyvar.js")
    pro = policy_for("pro")
    assert (
        f"{n(pro.max_simulations)} simulations per request, {n(pro.daily_requests)} requests a day, "
        f"{n(pro.monthly_requests)} requests and {n(pro.monthly_simulations)} simulations a month, "
        "up to 5 active keys"
    ) in script
    assert "£50 per account per month (VAT included for UK customers)" in script
    assert "continues to the end of the period you have paid for" in script


def test_the_public_guide_and_diagram_describe_refusal_not_downgrade() -> None:
    guide = page("guide-rest-api.html")
    diagram = page("guides-assets/rest-tier-lifecycle.svg")
    pro = policy_for("pro")
    assert f"<strong>{n(pro.monthly_requests)} requests/month</strong>" in guide
    assert f"<strong>{n(pro.monthly_simulations)} simulations/month</strong>" in guide
    assert f"{n(pro.monthly_requests)} requests in each 30-day window" in guide
    assert "billing/portal" in guide
    for text in (guide, diagram):
        for stale in ("hard-downgrade", "auto-downgrade", "moved to the Free plan", "restores Pro"):
            assert stale not in text, stale
    assert f"{cfg.rate_limit_free_daily} req/day" in diagram and "10 req/day" not in diagram


def test_the_privacy_page_says_what_is_stored_about_a_payment_and_where_the_rest_is() -> None:
    privacy = page("privacy.html")
    assert (
        "a reference to your Stripe customer, your tier, and a record of each change to it"
        in privacy
    )
    assert "the Manage billing button on your dashboard opens them" in privacy
    assert "the amount charged" not in privacy  # we do not store amounts; Stripe does
    assert "moves to free automatically" not in privacy


# ── cancelling: the account and its keys stay, on the free limits ────────────


async def make_account(db) -> tuple[list[str], str]:
    async with db() as session:
        user = User(
            external_id="ext-pro",
            email="pro@uni.example",
            tier="pro",
            email_verified=True,
            stripe_customer_id="cus_pro",
        )
        session.add(user)
        await session.flush()
        secrets = []
        for label in ("development", "production"):
            secret, prefix, digest = generate_key()
            secrets.append(secret)
            session.add(ApiKey(user_id=user.id, name=label, prefix=prefix, key_hash=digest))
        await session.commit()
        return secrets, "ext-pro"


@pytest.mark.asyncio
async def test_cancelling_returns_the_account_to_free_and_the_keys_keep_working(
    db, redis, monkeypatch
) -> None:
    monkeypatch.setattr(billing_module.cfg, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(billing_module.cfg, "stripe_price_id_pro", "price_x")
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_x")
    secrets, account = await make_account(db)

    first, second = [await resolve_api_key(secret) for secret in secrets]
    assert first is not None and second is not None
    assert (first.tier, second.tier) == ("pro", "pro")
    assert (
        first.user_id == second.user_id == account
    ), "both keys are the one account: one set of counters"

    event = _event("customer.subscription.deleted", customer="cus_pro", event_id="evt_end_e2e")
    with (
        patch("api.routes.billing.get_sessionmaker", return_value=db),
        patch("api.routes.billing._stripe_client", return_value=stripe_sdk),
        patch("api.routes.billing.send_tier_change_email") as email,
        patch.object(stripe_sdk.Webhook, "construct_event", return_value=event),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "x"}
            )
    assert response.status_code == 200
    email.assert_called_once()

    async with db() as session:
        user = (await session.execute(select(User))).scalar_one()
        keys = list((await session.execute(select(ApiKey))).scalars())
        events = list((await session.execute(select(BillingEvent))).scalars())
    assert user.tier == "free" and user.email == "pro@uni.example"
    assert len(keys) == 2 and all(
        key.revoked_at is None for key in keys
    ), "keys stay and are not revoked"
    (written,) = events
    assert (written.event_type, written.old_tier, written.new_tier) == (
        "downgraded_subscription_cancelled",
        "pro",
        "free",
    )

    for key, secret in zip(keys, secrets, strict=True):  # past the 60-second key cache
        await invalidate_cached_key(key.key_hash)
        resolved = await resolve_api_key(secret)
        assert resolved is not None and resolved.tier == "free" and resolved.user_id == account


@pytest.mark.asyncio
async def test_a_failed_payment_leaves_the_account_on_pro(db, redis, monkeypatch) -> None:
    monkeypatch.setattr(billing_module.cfg, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(billing_module.cfg, "stripe_price_id_pro", "price_x")
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_x")
    await make_account(db)

    event = _event("invoice.payment_failed", customer="cus_pro", event_id="evt_fail_e2e")
    with (
        patch("api.routes.billing.get_sessionmaker", return_value=db),
        patch("api.routes.billing._stripe_client", return_value=stripe_sdk),
        patch("api.routes.billing.send_tier_change_email") as email,
        patch.object(stripe_sdk.Webhook, "construct_event", return_value=event),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "x"}
            )
    assert response.status_code == 200
    email.assert_not_called()
    async with db() as session:
        assert (await session.execute(select(User))).scalar_one().tier == "pro"
        assert list((await session.execute(select(BillingEvent))).scalars()) == []


# ── "billing not configured" is not a Sentry error ───────────────────────────


def events_for(sent: list[bytes], fragment: str) -> list[dict[str, Any]]:
    """The recorded events whose request URL contains `fragment`.

    A recording client is process-wide, so it also sees unrelated ERROR log lines raised while it is bound (in CI,
    a connection left by an earlier test, closed by the garbage collector against a closed event loop:
    "RuntimeError: Event loop is closed"). Those have no request; only events of these requests count here.
    """
    return [e for e in events_in(sent) if fragment in str((e.get("request") or {}).get("url", ""))]


def test_billing_not_configured_sends_no_error_event_but_a_raised_503_would() -> None:
    """A real client with the FastAPI integration. The route answers 503 as a response: no event. The control is
    the old behaviour (an HTTPException with status 503, which the integration reports): exactly one event.
    """
    import logging

    import sentry_sdk
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    with (
        patch.object(billing_module.cfg, "stripe_secret_key", None),
        patch.object(billing_module.cfg, "stripe_price_id_pro", None),
        recording_client(FastApiIntegration(transaction_style="endpoint")) as sent,
    ):
        control = FastAPI()

        @control.get("/old-behaviour")
        async def old_behaviour() -> None:
            raise HTTPException(503, billing_module.NOT_CONFIGURED_DETAIL)

        TestClient(control, raise_server_exceptions=False).get("/old-behaviour")
        sentry_sdk.flush()
        assert (
            len(events_for(sent, "/old-behaviour")) == 1
        ), "the control must be reported, or this test proves nothing"
        sent.clear()

        # Unrelated noise, as CI produces: an ERROR log line with an exception and no request. It is captured,
        # and it must not be counted against the billing routes.
        logging.getLogger("unrelated.pool").error(
            "stray", exc_info=RuntimeError("Event loop is closed")
        )

        token = create_access_token(user_id="ext-1", tier="free")
        headers: dict[str, Any] = {"Authorization": f"Bearer {token}"}
        real = TestClient(create_app(), raise_server_exceptions=False)
        for method, path in (
            ("POST", "/api/v1/billing/checkout"),
            ("POST", "/api/v1/billing/portal"),
            ("POST", "/api/v1/billing/webhook"),
            ("GET", "/api/v1/billing/checkout/complete?session_id=cs_test_1"),
        ):
            response = real.request(method, path, headers=headers, content=b"{}")
            assert response.status_code == 503, path
            assert response.json() == {"detail": billing_module.NOT_CONFIGURED_DETAIL}
        sentry_sdk.flush()
        assert any(
            "Event loop is closed" in str(e) for e in events_in(sent)
        ), "the stray error was captured, so the filter below is what keeps it out"
        assert (
            events_for(sent, "/api/v1/billing") == []
        ), "an expected 'not configured' answer must not become an error event"
        assert billing_module.NOT_CONFIGURED_DETAIL not in received(sent)
