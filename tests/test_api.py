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
- The var_jobs audit write (issue #118) is the other external dependency
  POST /var/compute now has — same never-hit-a-real-backing-service rule as
  Celery, mocked at api.routes.var.get_sessionmaker with a FakeAsyncSession,
  the same boundary/pattern tests/test_auth.py already established for
  api/routes/auth.py's DB writes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import create_access_token
from ingestion.fixtures import generate_gbm_returns
from main import create_app

# ── Fakes ──────────────────────────────────────────────────────────────────────


class FakeAsyncSession:
    """Enough of AsyncSession's interface for api/routes/var.py's audit write.

    fail_on_commit lets a test simulate a DB outage on the submission INSERT
    (or the compensating dispatch-failure UPDATE) without a real Postgres.
    """

    def __init__(self, fail_on_commit: bool = False):
        self.fail_on_commit = fail_on_commit
        self.added: list = []
        self.executed: list = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt):
        self.executed.append(stmt)
        return MagicMock()

    async def commit(self):
        if self.fail_on_commit:
            raise RuntimeError("simulated DB outage")
        self.committed = True


def patch_sessionmaker(fake_session: FakeAsyncSession):
    return patch("api.routes.var.get_sessionmaker", return_value=lambda: fake_session)


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
    fake_session = FakeAsyncSession()

    with (
        patch_sessionmaker(fake_session),
        patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task) as mock_apply,
    ):
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

    # The var_jobs audit row was written before dispatch, using the same
    # task_id that was then passed to apply_async — not a fresh Celery-side id.
    assert len(fake_session.added) == 1
    audit_row = fake_session.added[0]
    assert audit_row.status == "pending"
    assert audit_row.user_id == "test-user"
    assert audit_row.tier == "free"
    assert fake_session.committed is True
    assert mock_apply.call_args.kwargs["task_id"] == audit_row.task_id
    assert mock_task.id == "test-task-uuid-1234"


@pytest.mark.asyncio
async def test_submit_var_audit_insert_failure_returns_503(app, free_token, valid_payload):
    """If the var_jobs INSERT fails, the request fails loud and Celery is never touched."""
    fake_session = FakeAsyncSession(fail_on_commit=True)

    with (
        patch_sessionmaker(fake_session),
        patch("api.routes.var.compute_var_task.apply_async") as mock_apply,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 503
    mock_apply.assert_not_called()


@pytest.mark.asyncio
async def test_submit_var_dispatch_failure_compensates_and_returns_503(
    app, free_token, valid_payload
):
    """If apply_async raises after the audit row was written, the row is
    compensated (marked failure) rather than left stuck at pending."""
    fake_session = FakeAsyncSession()

    with (
        patch_sessionmaker(fake_session),
        patch(
            "api.routes.var.compute_var_task.apply_async",
            side_effect=RuntimeError("broker unavailable"),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 503
    # One INSERT (submission) plus one compensating UPDATE.
    assert len(fake_session.added) == 1
    assert len(fake_session.executed) == 1


@pytest.mark.asyncio
async def test_submit_var_requires_auth(app, valid_payload):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/var/compute", json=valid_payload)
    assert resp.status_code == 401


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

    with (
        patch_sessionmaker(FakeAsyncSession()),
        patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(pro_token),
            )
    assert resp.status_code == 202


# ── ElastiCache result caching ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_var_cache_hit_returns_200(app, free_token, valid_payload):
    """A cached result short-circuits Celery entirely and returns 200, not 202."""
    with (
        patch("api.routes.caching._cache_get", return_value=MOCK_VAR_RESULT),
        patch("api.routes.var.compute_var_task.apply_async") as mock_apply_async,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["result"]["var_abs"] == 28_000.0
    mock_apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_submit_var_cache_miss_dispatches_celery(app, free_token, valid_payload):
    """A cache miss falls through to the normal 202 + task_id Celery dispatch."""
    mock_task = MagicMock()
    mock_task.id = "cache-miss-task-uuid"

    with (
        patch("api.routes.caching._cache_get", return_value=None),
        patch_sessionmaker(FakeAsyncSession()),
        patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 202
    assert resp.json()["task_id"] == "cache-miss-task-uuid"


@pytest.mark.asyncio
async def test_get_result_success_writes_to_cache(app, free_token, valid_payload):
    """On SUCCESS, the result is written to cache keyed on the original dispatch payload."""
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"
    mock_async_result.result = MOCK_VAR_RESULT
    mock_async_result.kwargs = {"payload": valid_payload}

    with (
        patch("api.routes.var.AsyncResult", return_value=mock_async_result),
        patch("api.routes.caching._cache_set") as mock_cache_set,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/var/result/test-task-uuid-1234",
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    mock_cache_set.assert_awaited_once_with("var", valid_payload, MOCK_VAR_RESULT)


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
    # CloudFront's ApiCachePolicy (edge_stack.py) clamps TTL from this header —
    # a SUCCESS result is immutable, so it must be edge-cacheable.
    assert resp.headers["cache-control"] == "public, max-age=3600"


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
    # A still-running job must never be cached at the edge — it changes on
    # the next poll.
    assert resp.headers["cache-control"] == "no-store"


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
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["status"] == "failure"
    assert body["error"] is not None
    assert body["result"] is None
