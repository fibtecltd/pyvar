"""
tests/test_cors.py — regression test for task #42's CORS fix in main.py.

Reasoning:
- httpx AsyncClient + ASGITransport exercises the real CORSMiddleware chain
  (same pattern as tests/test_api.py) -- CORS is pure request/response
  header logic, nothing to mock.
- app_env isn't overridden here: pytest runs with whatever APP_ENV the test
  process was started with (CI sets APP_ENV=test; local dev usually has none
  set, falling back to "development"). Neither is a recognised deployed env,
  so config.py's _default_cors_origins leaves cors_allowed_origins at ["*"],
  the same wildcard local/test always had -- see tests/test_config.py for
  the per-environment allowlist values themselves. The point of this test
  isn't which origins are allowed, it's that a wildcard origin no longer
  arrives bundled with allow-credentials: true -- that combination is what
  made the previously-live bug (task #42) actually exploitable, and it must
  never come back regardless of which origin list is active.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from main import create_app


@pytest.mark.asyncio
async def test_cors_preflight_never_grants_credentials():
    """task #42: allow_credentials=True combined with a wildcard/reflected
    origin is exactly what made the previously-live CORS bug exploitable --
    this app authenticates via a Bearer header (api/middleware/auth.py),
    never cookies, so there's nothing legitimate for allow_credentials to
    protect. Must never be granted, for any origin."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/var/compute",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert "access-control-allow-credentials" not in response.headers
    # Literal "*", not a reflected copy of the request's Origin -- reflection
    # only happens when allow_credentials=True, which is exactly the bug.
    assert response.headers["access-control-allow-origin"] == "*"
