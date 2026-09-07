"""
tests/test_internal.py — POST /internal/suppress-email (SES bounce/complaint
handling). Same mocking boundary as tests/test_auth.py: api.routes.internal.
get_sessionmaker is patched with a FakeAsyncSession backed by a real
storage.models.User instance, never a real Postgres connection.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import create_access_token
from main import create_app
from storage.models import User
from tests.test_auth import FakeAsyncSession, FakeResult


def patch_sessionmaker(fake_session: FakeAsyncSession):
    return patch("api.routes.internal.get_sessionmaker", return_value=lambda: fake_session)


class FakeSequentialSession:
    """Like FakeAsyncSession, but returns a distinct canned result per
    execute() call in order — needed for GET /internal/token-report, which
    issues two count queries (today, cumulative) in a single request."""

    def __init__(self, results: list[int]):
        self._results = list(results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return FakeResult(self._results.pop(0))


def patch_sequential_sessionmaker(session: "FakeSequentialSession"):
    return patch("api.routes.internal.get_sessionmaker", return_value=lambda: session)


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_suppress_email_requires_internal_tier(app):
    token = create_access_token(user_id="u1", tier="free")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/internal/suppress-email",
            json={"email": "a@example.com", "reason": "bounce_permanent"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_suppress_email_unauthenticated(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/internal/suppress-email",
            json={"email": "a@example.com", "reason": "complaint"},
        )
    assert resp.status_code in (401, 403)  # HTTPBearer's own missing-header code


@pytest.mark.asyncio
async def test_suppress_email_marks_matching_user(app):
    existing = User(external_id="ext-1", email="bounced@example.com", email_suppressed=False)
    session = FakeAsyncSession(lookup_result=existing)
    token = create_access_token(user_id="internal-svc", tier="internal")

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/internal/suppress-email",
                json={"email": "bounced@example.com", "reason": "bounce_permanent"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"matched": True, "already_suppressed": False}
    assert existing.email_suppressed is True
    assert existing.suppression_reason == "bounce_permanent"
    assert existing.suppressed_at is not None
    assert session.committed is True


@pytest.mark.asyncio
async def test_suppress_email_no_matching_user(app):
    session = FakeAsyncSession(lookup_result=None)
    token = create_access_token(user_id="internal-svc", tier="internal")

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/internal/suppress-email",
                json={"email": "unknown@example.com", "reason": "complaint"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    assert resp.json() == {"matched": False, "already_suppressed": False}
    assert session.committed is False  # no wasted write


@pytest.mark.asyncio
async def test_suppress_email_idempotent_on_already_suppressed(app):
    existing = User(
        external_id="ext-2",
        email="bounced2@example.com",
        email_suppressed=True,
        suppression_reason="complaint",
    )
    session = FakeAsyncSession(lookup_result=existing)
    token = create_access_token(user_id="internal-svc", tier="internal")

    with patch_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/internal/suppress-email",
                json={"email": "bounced2@example.com", "reason": "bounce_permanent"},
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    assert resp.json() == {"matched": True, "already_suppressed": True}
    assert existing.suppression_reason == "bounce_permanent"  # refreshed to latest reason


# ── GET /internal/token-report ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_report_requires_internal_tier(app):
    token = create_access_token(user_id="u1", tier="free")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/internal/token-report",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_token_report_unauthenticated(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/internal/token-report")
    assert resp.status_code in (401, 403)  # HTTPBearer's own missing-header code


@pytest.mark.asyncio
async def test_token_report_returns_today_and_cumulative_counts(app):
    # execute() is called today-count first, then cumulative-count — see
    # api/routes/internal.py::token_report().
    session = FakeSequentialSession(results=[3, 42])
    token = create_access_token(user_id="internal-svc", tier="internal")

    with patch_sequential_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/internal/token-report",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["issued_today"] == 3
    assert body["issued_cumulative"] == 42
    assert "date" in body and "env" in body


@pytest.mark.asyncio
async def test_token_report_defaults_null_counts_to_zero(app):
    session = FakeSequentialSession(results=[None, None])
    token = create_access_token(user_id="internal-svc", tier="internal")

    with patch_sequential_sessionmaker(session):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/internal/token-report",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    assert resp.json()["issued_today"] == 0
    assert resp.json()["issued_cumulative"] == 0
