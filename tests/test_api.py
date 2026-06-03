"""
tests/test_api.py — Integration tests for the FastAPI VaR endpoints

Reasoning:
- httpx AsyncClient with app=app bypasses the network entirely —
  tests run against the real FastAPI app without starting a server.
- Celery tasks are mocked with a synchronous stub so tests don't
  require Redis or a running worker. The stub returns a pre-built
  result dict that matches VaRResult schema.
- JWT tokens are generated via create_access_token() so auth
  middleware is exercised without a real identity provider.
- Tests cover: happy path, schema validation errors, tier enforcement,
  result polling with SUCCESS and FAILURE states.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import create_access_token
from ingestion.fixtures import generate_gbm_returns
from main import create_app

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def free_token():
    return create_access_token(user_id="test-user", tier="free")


@pytest.fixture
def pro_token():
    return create_access_token(user_id="pro-user", tier="pro")


@pytest.fixture
def valid_payload():
    returns = generate_gbm_returns(n_obs=252, seed=42).tolist()
    return {
        "portfolio_value": 1_000_000.0,
        "returns": returns,
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": 10_000,
        "seed": 42,
    }


MOCK_VAR_RESULT = {
    "var_pct": 0.028,
    "var_abs": 28_000.0,
    "cvar_pct": 0.035,
    "cvar_abs": 35_000.0,
    "loss_dist": [0.001 * i for i in range(10_000)],
    "mu": 0.0003,
    "sigma": 0.012,
    "n_simulations": 10_000,
    "confidence_level": 0.99,
    "horizon_days": 1,
}


# ── Helper ────────────────────────────────────────────────────────────────────


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Health check ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── POST /var/compute ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_var_returns_202(app, free_token, valid_payload):
    mock_task = MagicMock()
    mock_task.id = "test-task-uuid-1234"

    with patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"] == "test-task-uuid-1234"
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_submit_var_requires_auth(app, valid_payload):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/var/compute", json=valid_payload)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_invalid_confidence_level(app, free_token, valid_payload):
    """Confidence level outside [0.90, 0.9999] should be rejected by Pydantic."""
    valid_payload["confidence_level"] = 0.5
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/var/compute",
            json=valid_payload,
            headers=auth_headers(free_token),
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_too_few_returns(app, free_token, valid_payload):
    """Returns series shorter than 30 obs should be rejected."""
    valid_payload["returns"] = [0.001] * 10
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/var/compute",
            json=valid_payload,
            headers=auth_headers(free_token),
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_free_tier_simulation_cap(app, free_token, valid_payload):
    """Free tier allows max 100k simulations — request 200k should be rejected."""
    valid_payload["n_simulations"] = 200_000
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/var/compute",
            json=valid_payload,
            headers=auth_headers(free_token),
        )
    assert resp.status_code == 403
    assert "tier" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_pro_tier_allows_larger_simulations(app, pro_token, valid_payload):
    """Pro tier allows up to 500k simulations."""
    valid_payload["n_simulations"] = 200_000
    mock_task = MagicMock()
    mock_task.id = "pro-task-uuid-5678"

    with patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(pro_token),
            )
    assert resp.status_code == 202


# ── GET /var/result/{task_id} ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_result_success(app, free_token):
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"
    mock_async_result.result = MOCK_VAR_RESULT

    with patch("api.routes.var.AsyncResult", return_value=mock_async_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/var/result/test-task-uuid-1234",
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["result"]["var_abs"] == 28_000.0
    assert body["result"]["cvar_pct"] > body["result"]["var_pct"]


@pytest.mark.asyncio
async def test_get_result_pending(app, free_token):
    mock_async_result = MagicMock()
    mock_async_result.state = "PENDING"

    with patch("api.routes.var.AsyncResult", return_value=mock_async_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/var/result/pending-task-id",
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"
    assert resp.json()["result"] is None


@pytest.mark.asyncio
async def test_get_result_failure(app, free_token):
    mock_async_result = MagicMock()
    mock_async_result.state = "FAILURE"
    mock_async_result.result = Exception("Numba compilation error")

    with patch("api.routes.var.AsyncResult", return_value=mock_async_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/var/result/failed-task-id",
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failure"
    assert body["error"] is not None
    assert body["result"] is None
