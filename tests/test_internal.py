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
from tests.test_auth import FakeAsyncSession


def patch_sessionmaker(fake_session: FakeAsyncSession):
    return patch("api.routes.internal.get_sessionmaker", return_value=lambda: fake_session)


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
