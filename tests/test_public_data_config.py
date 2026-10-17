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
- initGoogleSignIn returns without a message on any non-200, so a 429 here
  hides the Google button. /public/config therefore must not draw on the
  per-IP bucket the S3-backed files use; the last two tests pin that, and that
  the files are still limited.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.middleware.rate_limit import cfg as rate_limit_cfg
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


@pytest.mark.asyncio
async def test_public_config_is_not_rate_limited(app, monkeypatch):
    monkeypatch.setattr(
        public_data_module.cfg, "google_oauth_client_id", "x.apps.googleusercontent.com"
    )

    with patch.object(rate_limit_cfg, "rate_limit_unauth_per_hour", 1):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            statuses = [(await client.get("/public/config")).status_code for _ in range(5)]

    assert statuses == [200] * 5


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/public/status.json", "/public/demo-result.json"])
async def test_s3_backed_files_stay_limited_and_do_not_take_config_down_with_them(
    app, monkeypatch, path
):
    monkeypatch.setattr(public_data_module, "_read_object", lambda key: b"{}")
    monkeypatch.setattr(
        public_data_module.cfg, "google_oauth_client_id", "x.apps.googleusercontent.com"
    )

    with patch.object(rate_limit_cfg, "rate_limit_unauth_per_hour", 1):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get(path)
            second = await client.get(path)
            config = await client.get("/public/config")

    assert first.status_code == 200
    assert second.status_code == 429
    assert config.status_code == 200
