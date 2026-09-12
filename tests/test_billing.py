"""
tests/test_billing.py — Integration tests for the Stripe Checkout + webhook
flow (item 5, Phase A — api/routes/billing.py).

Reasoning:
- Same FakeAsyncSession/patch_sessionmaker pattern as tests/test_auth.py —
  the DB session is mocked at api.routes.billing.get_sessionmaker, never a
  real Postgres.
- The real `stripe` module is imported and used for its exception types
  (stripe.error.SignatureVerificationError) — only the specific SDK calls
  each test cares about are patched (stripe.Webhook.construct_event,
  stripe.Customer.create, stripe.checkout.Session.create/retrieve), never
  the whole module replaced with a MagicMock, since api/routes/billing.py's
  own `except stripe.error.SignatureVerificationError` needs a real
  exception class to catch, not a mock attribute. api/routes/billing.py's
  `_stripe_client()` is patched to return this same real module — no
  network call to api.stripe.com ever happens because every method that
  would make one is itself patched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import stripe as stripe_sdk
from httpx import ASGITransport, AsyncClient
from jose import jwt

from api.middleware.auth import create_access_token
from api.routes import billing as billing_module
from config import get_settings
from main import create_app
from storage.models import User

cfg = get_settings()


# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class FakeAsyncSession:
    """Same shape as tests/test_auth.py's FakeAsyncSession."""

    def __init__(self, lookup_result=None):
        self._lookup_result = lookup_result
        self.added: list[User] = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return FakeResult(self._lookup_result)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def patch_sessionmaker(fake_session: FakeAsyncSession):
    return patch("api.routes.billing.get_sessionmaker", return_value=lambda: fake_session)


def patch_stripe_client():
    """Route _stripe_client() to the real stripe module (imported above),
    so real exception types stay catchable — see module docstring."""
    return patch("api.routes.billing._stripe_client", return_value=stripe_sdk)


def configure_billing(monkeypatch, *, price_id: str = "price_pro_123") -> None:
    monkeypatch.setattr(billing_module.cfg, "stripe_secret_key", "sk_test_123")
    monkeypatch.setattr(billing_module.cfg, "stripe_price_id_pro", price_id)


@pytest.fixture
def app():
    return create_app()


def auth_header(user_id: str = "ext-1", tier: str = "free") -> dict:
    token = create_access_token(user_id=user_id, tier=tier)
    return {"Authorization": f"Bearer {token}"}


# ── POST /billing/checkout ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_requires_auth(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/billing/checkout")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_checkout_returns_503_when_not_configured(app, monkeypatch):
    monkeypatch.setattr(billing_module.cfg, "stripe_secret_key", None)
    monkeypatch.setattr(billing_module.cfg, "stripe_price_id_pro", None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/billing/checkout", headers=auth_header())
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_checkout_creates_stripe_customer_when_none_exists(app, monkeypatch):
    configure_billing(monkeypatch)
    user_row = User(external_id="ext-1", email="new-pro@example.com", tier="free")
    session = FakeAsyncSession(lookup_result=user_row)

    fake_stripe = MagicMock()
    fake_stripe.Customer.create.return_value = MagicMock(id="cus_new123")
    fake_stripe.checkout.Session.create.return_value = MagicMock(
        url="https://checkout.stripe.com/session/xyz"
    )

    with patch_sessionmaker(session), patch(
        "api.routes.billing._stripe_client", return_value=fake_stripe
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/billing/checkout", headers=auth_header())

    assert resp.status_code == 200
    assert resp.json() == {"checkout_url": "https://checkout.stripe.com/session/xyz"}
    fake_stripe.Customer.create.assert_called_once()
    assert user_row.stripe_customer_id == "cus_new123"
    assert session.committed is True
    create_kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
    assert create_kwargs["customer"] == "cus_new123"
    assert create_kwargs["mode"] == "subscription"
    assert create_kwargs["line_items"] == [{"price": "price_pro_123", "quantity": 1}]


@pytest.mark.asyncio
async def test_checkout_reuses_existing_stripe_customer(app, monkeypatch):
    configure_billing(monkeypatch)
    user_row = User(
        external_id="ext-2",
        email="returning@example.com",
        tier="free",
        stripe_customer_id="cus_existing",
    )
    session = FakeAsyncSession(lookup_result=user_row)

    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.create.return_value = MagicMock(
        url="https://checkout.stripe.com/session/abc"
    )

    with patch_sessionmaker(session), patch(
        "api.routes.billing._stripe_client", return_value=fake_stripe
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/checkout", headers=auth_header(user_id="ext-2")
            )

    assert resp.status_code == 200
    fake_stripe.Customer.create.assert_not_called()  # not recreated
    assert session.committed is False  # nothing needed writing
    create_kwargs = fake_stripe.checkout.Session.create.call_args.kwargs
    assert create_kwargs["customer"] == "cus_existing"


@pytest.mark.asyncio
async def test_checkout_returns_404_when_user_row_missing(app, monkeypatch):
    configure_billing(monkeypatch)
    session = FakeAsyncSession(lookup_result=None)

    with patch_sessionmaker(session), patch(
        "api.routes.billing._stripe_client", return_value=MagicMock()
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/billing/checkout", headers=auth_header())

    assert resp.status_code == 404


# ── GET /billing/checkout/complete ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_complete_issues_fresh_jwt_with_current_tier(app, monkeypatch):
    configure_billing(monkeypatch)
    # Simulates the webhook having already landed and flipped tier to "pro"
    # before the browser redirect reaches this route.
    user_row = User(
        external_id="ext-3", email="upgraded@example.com", tier="pro", stripe_customer_id="cus_1"
    )
    session = FakeAsyncSession(lookup_result=user_row)

    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.retrieve.return_value = MagicMock(
        payment_status="paid", customer="cus_1"
    )

    with patch_sessionmaker(session), patch(
        "api.routes.billing._stripe_client", return_value=fake_stripe
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/billing/checkout/complete", params={"session_id": "cs_test_1"}
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "pro"
    decoded = jwt.decode(body["access_token"], cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    assert decoded["sub"] == "ext-3"
    assert decoded["tier"] == "pro"


@pytest.mark.asyncio
async def test_checkout_complete_rejects_unpaid_session(app, monkeypatch):
    configure_billing(monkeypatch)
    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.retrieve.return_value = MagicMock(
        payment_status="unpaid", customer="cus_1"
    )

    with patch_sessionmaker(FakeAsyncSession()), patch(
        "api.routes.billing._stripe_client", return_value=fake_stripe
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/billing/checkout/complete", params={"session_id": "cs_test_2"}
            )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_checkout_complete_returns_404_for_unknown_customer(app, monkeypatch):
    configure_billing(monkeypatch)
    fake_stripe = MagicMock()
    fake_stripe.checkout.Session.retrieve.return_value = MagicMock(
        payment_status="paid", customer="cus_unknown"
    )

    with patch_sessionmaker(FakeAsyncSession(lookup_result=None)), patch(
        "api.routes.billing._stripe_client", return_value=fake_stripe
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/billing/checkout/complete", params={"session_id": "cs_test_3"}
            )

    assert resp.status_code == 404


# ── POST /billing/webhook ─────────────────────────────────────────────────────────


def _event(event_type: str, customer: str = "cus_1") -> dict:
    return {"type": event_type, "data": {"object": {"customer": customer}}}


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(app, monkeypatch):
    configure_billing(monkeypatch)
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_test")

    with patch_stripe_client(), patch.object(
        stripe_sdk.Webhook,
        "construct_event",
        side_effect=stripe_sdk.error.SignatureVerificationError("bad signature", "sig_header"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "bad"},
            )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_webhook_checkout_completed_flips_tier_to_pro(app, monkeypatch):
    configure_billing(monkeypatch)
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_test")
    user_row = User(
        external_id="ext-4", email="webhook@example.com", tier="free", stripe_customer_id="cus_1"
    )
    session = FakeAsyncSession(lookup_result=user_row)

    with patch_sessionmaker(session), patch_stripe_client(), patch.object(
        stripe_sdk.Webhook,
        "construct_event",
        return_value=_event("checkout.session.completed"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "valid"},
            )

    assert resp.status_code == 200
    assert user_row.tier == "pro"
    assert session.committed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["customer.subscription.deleted", "invoice.payment_failed"])
async def test_webhook_downgrade_events_flip_tier_to_free(app, monkeypatch, event_type):
    configure_billing(monkeypatch)
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_test")
    user_row = User(
        external_id="ext-5", email="lapsed@example.com", tier="pro", stripe_customer_id="cus_1"
    )
    session = FakeAsyncSession(lookup_result=user_row)

    with patch_sessionmaker(session), patch_stripe_client(), patch.object(
        stripe_sdk.Webhook, "construct_event", return_value=_event(event_type)
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "valid"},
            )

    assert resp.status_code == 200
    assert user_row.tier == "free"


@pytest.mark.asyncio
async def test_webhook_ignores_unhandled_event_type(app, monkeypatch):
    configure_billing(monkeypatch)
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_test")
    session = FakeAsyncSession(lookup_result=User(external_id="ext-6", tier="free"))

    with patch_sessionmaker(session), patch_stripe_client(), patch.object(
        stripe_sdk.Webhook, "construct_event", return_value=_event("invoice.paid")
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "valid"},
            )

    assert resp.status_code == 200
    assert session.committed is False  # never touched the DB


@pytest.mark.asyncio
async def test_webhook_unknown_customer_does_not_raise(app, monkeypatch):
    configure_billing(monkeypatch)
    monkeypatch.setattr(billing_module.cfg, "stripe_webhook_secret", "whsec_test")
    session = FakeAsyncSession(lookup_result=None)  # no matching user row

    with patch_sessionmaker(session), patch_stripe_client(), patch.object(
        stripe_sdk.Webhook,
        "construct_event",
        return_value=_event("checkout.session.completed", customer="cus_ghost"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/billing/webhook",
                content=b"{}",
                headers={"stripe-signature": "valid"},
            )

    assert resp.status_code == 200  # Stripe still gets a 2xx
    assert session.committed is False
