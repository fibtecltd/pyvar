"""
tests/test_auth.py — Integration tests for the minimum-viable account flow
(P8 Task 3): POST /auth/register, GET /auth/verify.

Reasoning:
- httpx AsyncClient with app=app, same pattern as test_api.py.
- The DB session is the external dependency here (there is no real Postgres
  in tests, same rule as "never use real AWS services in tests" — Postgres
  isn't AWS, but the same never-hit-a-real-backing-service principle
  applies) — mocked at api.routes.auth.get_sessionmaker, the same boundary
  test_api.py mocks Celery's apply_async at. The DB row itself is a real
  storage.models.User instance (never persisted, just held in memory by the
  fake session) so field access in the route code is exercised for real.
- send_verification_email is patched out: asserting it was called with the
  right token is the useful signal, not writing to real structlog output.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

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
    """Enough of AsyncSession's interface for api/routes/auth.py, backed by
    a single pre-seeded lookup result rather than a real query engine."""

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
    return patch("api.routes.auth.get_sessionmaker", return_value=lambda: fake_session)


@pytest.fixture
def app():
    return create_app()


# ── POST /auth/register ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_new_email_creates_user_and_stubs_email(app):
    session = FakeAsyncSession(lookup_result=None)  # no existing row

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/register", json={"email": "new@example.com"})

    assert resp.status_code == 202
    assert len(session.added) == 1
    assert session.added[0].email == "new@example.com"
    # mapped_column(default=...) only applies on flush/INSERT, not direct
    # construction — this object is never flushed, so check falsy, not `is False`.
    assert not session.added[0].email_verified
    assert session.committed is True
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "new@example.com"


@pytest.mark.asyncio
async def test_register_existing_unverified_regenerates_token(app):
    existing = User(
        external_id="ext-1",
        email="pending@example.com",
        email_verified=False,
        verification_token="stale-token",
    )
    session = FakeAsyncSession(lookup_result=existing)

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/register", json={"email": "pending@example.com"})

    assert resp.status_code == 202
    assert existing.verification_token != "stale-token"  # regenerated
    assert session.added == []  # updated in place, not re-inserted
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_register_already_verified_is_noop(app):
    existing = User(
        external_id="ext-2",
        email="verified@example.com",
        email_verified=True,
        verification_token=None,
    )
    session = FakeAsyncSession(lookup_result=existing)

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/register", json={"email": "verified@example.com"})

    assert resp.status_code == 202
    mock_send.assert_not_called()
    assert existing.verification_token is None  # untouched


@pytest.mark.asyncio
async def test_register_rejects_malformed_email(app):
    session = FakeAsyncSession(lookup_result=None)
    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/register", json={"email": "not-an-email"})
    assert resp.status_code == 422


# ── GET /auth/verify ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_valid_token_issues_jwt(app):
    user = User(
        external_id="ext-3",
        email="fresh@example.com",
        tier="free",
        email_verified=False,
        verification_token="good-token",
        verification_sent_at=datetime.now(timezone.utc),
    )
    session = FakeAsyncSession(lookup_result=user)

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/verify", params={"token": "good-token"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["tier"] == "free"

    decoded = jwt.decode(body["access_token"], cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    assert decoded["sub"] == "ext-3"
    assert decoded["tier"] == "free"

    assert user.email_verified is True
    assert user.verification_token is None
    assert session.committed is True


@pytest.mark.asyncio
async def test_verify_unknown_token_returns_400(app):
    session = FakeAsyncSession(lookup_result=None)
    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/verify", params={"token": "does-not-exist"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_expired_token_returns_400(app):
    stale = datetime.now(timezone.utc) - timedelta(
        minutes=cfg.verification_token_expiry_minutes + 10
    )
    user = User(
        external_id="ext-4",
        email="late@example.com",
        email_verified=False,
        verification_token="expired-token",
        verification_sent_at=stale,
    )
    session = FakeAsyncSession(lookup_result=user)

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/verify", params={"token": "expired-token"})

    assert resp.status_code == 400
    assert user.email_verified is False  # never flipped
