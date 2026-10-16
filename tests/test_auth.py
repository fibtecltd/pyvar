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
- send_verification_email is patched out in the register()/verify() tests
  above: asserting it was called with the right token is the useful signal.
  It gets its own dedicated tests below (#149) — real SES is still never
  hit (get_ses_client is mocked), only send_verification_email's own
  success/fail-open behavior is exercised.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from api.routes import auth as auth_module
from api.routes.auth import send_verification_email
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
async def test_register_already_verified_sends_a_signin_link(app):
    """A returning user asks to sign in through the same form: they get a link."""
    existing = User(
        external_id="ext-2",
        email="verified@example.com",
        email_verified=True,
        verification_token=None,
    )
    session = FakeAsyncSession(lookup_result=existing)

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/register", json={"email": "verified@example.com"}
            )

    assert resp.status_code == 202
    assert existing.email_verified is True
    assert existing.verification_token  # a fresh single-use token was issued
    mock_send.assert_called_once_with(
        "verified@example.com", existing.verification_token, signin=True
    )


@pytest.mark.asyncio
async def test_register_verified_signin_link_is_throttled_per_address(app):
    """A second request inside the interval sends nothing and returns the same 202."""
    existing = User(
        external_id="ext-2",
        email="verified@example.com",
        email_verified=True,
        verification_token="already-sent",
        verification_sent_at=datetime.now(timezone.utc) - timedelta(seconds=30),
    )
    session = FakeAsyncSession(lookup_result=existing)

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/register", json={"email": "verified@example.com"}
            )

    assert resp.status_code == 202
    mock_send.assert_not_called()
    assert existing.verification_token == "already-sent"  # not rotated


@pytest.mark.asyncio
async def test_register_response_is_identical_for_every_outcome(app):
    """No account enumeration: new, verified and throttled addresses look the same."""
    bodies = []
    for existing in (
        None,
        User(external_id="a", email="a@example.com", email_verified=True),
        User(
            external_id="b",
            email="b@example.com",
            email_verified=True,
            verification_sent_at=datetime.now(timezone.utc),
        ),
    ):
        session = FakeAsyncSession(lookup_result=existing)
        with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post("/api/v1/auth/register", json={"email": "x@example.com"})
        bodies.append((resp.status_code, resp.json()))
    assert len({str(b) for b in bodies}) == 1


@pytest.mark.asyncio
async def test_register_suppressed_email_does_not_resend(app):
    existing = User(
        external_id="ext-3",
        email="bounced@example.com",
        email_verified=False,
        email_suppressed=True,
        suppression_reason="bounce_permanent",
        verification_token="stale-token",
    )
    session = FakeAsyncSession(lookup_result=existing)

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/register", json={"email": "bounced@example.com"})

    assert resp.status_code == 202
    mock_send.assert_not_called()
    assert existing.verification_token == "stale-token"  # untouched, no regeneration
    assert session.committed is False  # no DB write attempted


@pytest.mark.asyncio
async def test_register_disposable_email_does_not_create_user(app):
    session = FakeAsyncSession(lookup_result=None)

    with patch_sessionmaker(session), patch("api.routes.auth.send_verification_email") as mock_send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/auth/register", json={"email": "throwaway@mailinator.com"}
            )

    # Same response shape as a real registration — never reveal *why* a
    # request didn't go through (see api/routes/auth.py's module docstring).
    assert resp.status_code == 202
    assert session.added == []
    assert session.committed is False
    mock_send.assert_not_called()


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


# ── send_verification_email (#149) ───────────────────────────────────────────


def test_send_verification_email_calls_ses_with_correct_args():
    fake_client = MagicMock()
    with patch("api.routes.auth.get_ses_client", return_value=fake_client):
        send_verification_email("user@example.com", "tok-123")

    fake_client.send_email.assert_called_once()
    kwargs = fake_client.send_email.call_args.kwargs
    assert kwargs["Source"] == cfg.ses_sender_email
    assert kwargs["Destination"] == {"ToAddresses": ["user@example.com"]}
    body_text = kwargs["Message"]["Body"]["Text"]["Data"]
    assert "tok-123" in body_text
    assert cfg.public_base_url in body_text


def test_send_verification_email_falls_back_on_ses_failure():
    """A real SES failure (suppressed/bounced recipient, no credentials,
    transient error) must never raise into the caller — register() already
    committed the user row by the time this is called (see
    api/routes/auth.py's docstring)."""
    fake_client = MagicMock()
    fake_client.send_email.side_effect = RuntimeError("simulated SES failure")

    with patch("api.routes.auth.get_ses_client", return_value=fake_client):
        send_verification_email("user@example.com", "tok-456")  # must not raise


# ── POST /auth/google ────────────────────────────────────────────────────────

GOOGLE_CLAIMS = {
    "sub": "109876543210",
    "email": "new-google-user@example.com",
    "email_verified": True,
}


@pytest.mark.asyncio
async def test_google_sign_in_not_configured_returns_503(app):
    # cfg.google_oauth_client_id is unset by default (config.py) — no
    # monkeypatch needed, this is the out-of-the-box state.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/google", json={"id_token": "whatever"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_google_sign_in_new_user_creates_verified_account(app, monkeypatch):
    monkeypatch.setattr(auth_module.cfg, "google_oauth_client_id", "test-client-id")
    session = FakeAsyncSession(lookup_result=None)  # no existing row

    with (
        patch_sessionmaker(session),
        patch("api.routes.auth._verify_google_id_token", return_value=GOOGLE_CLAIMS),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/google", json={"id_token": "real-looking-jwt"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "free"

    assert len(session.added) == 1
    new_user = session.added[0]
    assert new_user.email == "new-google-user@example.com"
    assert new_user.external_id == "google:109876543210"
    assert new_user.email_verified is True
    assert session.committed is True

    decoded = jwt.decode(body["access_token"], cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    assert decoded["sub"] == "google:109876543210"


@pytest.mark.asyncio
async def test_google_sign_in_existing_verified_user_links_no_new_row(app, monkeypatch):
    monkeypatch.setattr(auth_module.cfg, "google_oauth_client_id", "test-client-id")
    existing = User(
        external_id="ext-existing-1",
        email="new-google-user@example.com",
        tier="pro",
        email_verified=True,
    )
    session = FakeAsyncSession(lookup_result=existing)

    with (
        patch_sessionmaker(session),
        patch("api.routes.auth._verify_google_id_token", return_value=GOOGLE_CLAIMS),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/google", json={"id_token": "real-looking-jwt"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "pro"
    assert session.added == []  # linked to the existing row, never re-inserted

    decoded = jwt.decode(body["access_token"], cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])
    assert decoded["sub"] == "ext-existing-1"  # the account's original identity, not Google's


@pytest.mark.asyncio
async def test_google_sign_in_existing_unverified_user_gets_verified(app, monkeypatch):
    """A row from an unfinished POST /auth/register (never clicked the SES
    link) — Google's verification is at least as strong, so this finishes
    what register() started instead of leaving the account stuck pending."""
    monkeypatch.setattr(auth_module.cfg, "google_oauth_client_id", "test-client-id")
    existing = User(
        external_id="ext-pending-1",
        email="new-google-user@example.com",
        tier="free",
        email_verified=False,
        verification_token="stale-token",
    )
    session = FakeAsyncSession(lookup_result=existing)

    with (
        patch_sessionmaker(session),
        patch("api.routes.auth._verify_google_id_token", return_value=GOOGLE_CLAIMS),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/google", json={"id_token": "real-looking-jwt"})

    assert resp.status_code == 200
    assert existing.email_verified is True
    assert existing.verification_token is None
    assert existing.verified_at is not None


@pytest.mark.asyncio
async def test_google_sign_in_invalid_token_returns_401(app, monkeypatch):
    monkeypatch.setattr(auth_module.cfg, "google_oauth_client_id", "test-client-id")
    session = FakeAsyncSession(lookup_result=None)

    with (
        patch_sessionmaker(session),
        patch(
            "api.routes.auth._verify_google_id_token",
            side_effect=ValueError("Token used too late"),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/google", json={"id_token": "garbage"})

    assert resp.status_code == 401
    assert session.added == []


@pytest.mark.asyncio
async def test_google_sign_in_unverified_email_claim_returns_401(app, monkeypatch):
    """Defense in depth: even though Google-issued tokens should always
    carry email_verified=True for a Gmail/Workspace account, this endpoint
    checks the claim itself rather than assuming it."""
    monkeypatch.setattr(auth_module.cfg, "google_oauth_client_id", "test-client-id")
    unverified_claims = {**GOOGLE_CLAIMS, "email_verified": False}
    session = FakeAsyncSession(lookup_result=None)

    with (
        patch_sessionmaker(session),
        patch("api.routes.auth._verify_google_id_token", return_value=unverified_claims),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/google", json={"id_token": "real-looking-jwt"})

    assert resp.status_code == 401
    assert session.added == []


# ── Sign-in links for already-verified accounts ────────────────────────────────


@pytest.mark.asyncio
async def test_verify_signin_link_works_once_and_keeps_original_verified_at(app):
    first_verified = datetime(2026, 9, 1, tzinfo=timezone.utc)
    user = User(
        external_id="ext-9",
        email="back@example.com",
        tier="pro",
        email_verified=True,
        verified_at=first_verified,
        verification_token="signin-token",
        verification_sent_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    session = FakeAsyncSession(lookup_result=user)

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/verify", params={"token": "signin-token"})

    assert resp.status_code == 200
    assert resp.json()["tier"] == "pro"
    assert user.verification_token is None  # single use
    # the daily "new verified accounts" count must not see a returning user as new
    assert user.verified_at == first_verified


@pytest.mark.asyncio
async def test_verify_signin_link_expires_after_minutes_not_a_day(app):
    user = User(
        external_id="ext-9",
        email="back@example.com",
        email_verified=True,
        verification_token="old-signin-token",
        verification_sent_at=datetime.now(timezone.utc)
        - timedelta(minutes=cfg.signin_link_expiry_minutes + 1),
    )
    session = FakeAsyncSession(lookup_result=user)

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/auth/verify", params={"token": "old-signin-token"})

    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"]


def test_signin_email_has_its_own_subject_and_short_expiry():
    fake_client = MagicMock()
    with patch("api.routes.auth.get_ses_client", return_value=fake_client):
        send_verification_email("back@example.com", "tok", signin=True)
    message = fake_client.send_email.call_args.kwargs["Message"]
    assert message["Subject"]["Data"] == "Sign in to pyvar.com"
    text = message["Body"]["Text"]["Data"]
    assert "dashboard.html?token=tok" in text
    assert f"{cfg.signin_link_expiry_minutes} minutes" in text
