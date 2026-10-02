"""
tests/test_public_data_config.py — GET /public/config
(api/routes/public_data.py::get_public_config).

Reasoning:
- Unauthenticated, no DB, no S3 — the only external state is
  cfg.google_oauth_client_id, so this just monkeypatches that rather than
  mocking a backing service, same pattern test_billing.py uses for
  stripe_secret_key.
- portal/pyvar.js::initGoogleSignIn is the only caller; these tests pin the
  exact response shape it depends on (google_sign_in_enabled,
  google_client_id) so a field rename here fails loudly in CI instead of
  silently breaking the portal.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.routes import public_data as public_data_module
from main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_public_config_google_disabled_by_default(app, monkeypatch):
    monkeypatch.setattr(public_data_module.cfg, "google_oauth_client_id", None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/public/config")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"google_sign_in_enabled": False, "google_client_id": None}


@pytest.mark.asyncio
async def test_public_config_google_enabled_when_client_id_set(app, monkeypatch):
    monkeypatch.setattr(
        public_data_module.cfg,
        "google_oauth_client_id",
        "test-client-id.apps.googleusercontent.com",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/public/config")

    assert resp.status_code == 200
    body = resp.json()
    assert body["google_sign_in_enabled"] is True
    assert body["google_client_id"] == "test-client-id.apps.googleusercontent.com"
