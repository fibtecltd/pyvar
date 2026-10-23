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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from starlette.websockets import WebSocketDisconnect

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
async def test_wrong_method_on_api_route_is_not_shadowed_by_static_mount(app):
    """Regression test: main.py mounts the static portal at "/" last, and a
    plain Starlette Mount matches any HTTP method for its path prefix. A GET
    against the POST-only /var/compute previously fell through to that
    mount's file lookup instead of the real route's own method handling,
    returning a misleading 404 (`{"detail": "Not Found"}`, indistinguishable
    from a genuinely unknown path) instead of 405. main.py's
    _PortalStaticMount excludes reserved API/system prefixes from the
    portal mount's matching so this now surfaces correctly.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/var/compute")
    assert resp.status_code == 405


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
    """Free tier allows max 10k simulations — request 200k should be rejected."""
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
    """Pro tier allows up to 100k simulations — more than free's 10k cap."""
    valid_payload["n_simulations"] = 50_000
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


# ── Rate limiting (#146) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_var_returns_429_once_daily_quota_exhausted(app, free_token, valid_payload):
    """Proves the real main.py/var.py wiring (route-level `dependencies=[...]`),
    not just the isolated dependency function — see tests/test_rate_limit.py
    for the rest of the tier/scope/fail-open coverage.

    The rate limiter itself is already swapped for an isolated in-memory
    instance by tests/conftest.py's autouse fixture (no real Redis, no
    cross-test quota leakage) — this test only needs to lower the quota low
    enough to exceed it in two requests.
    """
    from api.middleware import rate_limit as rate_limit_module

    mock_task = MagicMock()
    mock_task.id = "quota-task-uuid"

    with (
        patch.object(rate_limit_module.cfg, "rate_limit_free_daily", 1),
        patch_sessionmaker(FakeAsyncSession()),
        patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                "/api/v1/var/compute", json=valid_payload, headers=auth_headers(free_token)
            )
            second = await client.post(
                "/api/v1/var/compute", json=valid_payload, headers=auth_headers(free_token)
            )

    assert first.status_code == 202
    assert second.status_code == 429
    assert "Retry-After" in second.headers


# ── Monthly simulation-count cap, Pro only (item 5 §8 follow-on) ────────────


@pytest.mark.asyncio
async def test_submit_var_pro_monthly_simulation_cap_downgrades_and_raises_403(
    app, pro_token, valid_payload
):
    """valid_payload requests 10,000 simulations (under Pro's 100,000
    per-request cap either time) — two submissions push the cumulative
    monthly total past a lowered 15,000 cap, on the second call only."""
    from api.middleware import rate_limit as rate_limit_module

    mock_task = MagicMock()
    mock_task.id = "sim-cap-task-uuid"

    with (
        patch.object(rate_limit_module.cfg, "rate_limit_pro_daily", 1000),
        patch.object(rate_limit_module.cfg, "rate_limit_pro_monthly_simulations", 15_000),
        patch_sessionmaker(FakeAsyncSession()),
        patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task),
        patch("api.routes.var.downgrade_for_monthly_limit") as mock_downgrade,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.post(
                "/api/v1/var/compute", json=valid_payload, headers=auth_headers(pro_token)
            )
            second = await client.post(
                "/api/v1/var/compute", json=valid_payload, headers=auth_headers(pro_token)
            )

    assert first.status_code == 202
    assert second.status_code == 403
    mock_downgrade.assert_called_once()
    call_kwargs = mock_downgrade.call_args.kwargs
    assert call_kwargs["user_id"] == "pro-user"
    assert call_kwargs["downgrade_reason"] == "monthly_simulation_limit_exceeded"


@pytest.mark.asyncio
async def test_submit_var_free_tier_not_subject_to_monthly_simulation_cap(
    app, free_token, valid_payload
):
    """Free has nowhere to downgrade to — the monthly simulation check must
    not even run for it."""
    mock_task = MagicMock()
    mock_task.id = "free-tier-task-uuid"

    with (
        patch("api.middleware.rate_limit.cfg.rate_limit_free_daily", 1000),
        patch("api.routes.var.cfg.rate_limit_pro_monthly_simulations", 1),
        patch_sessionmaker(FakeAsyncSession()),
        patch("api.routes.var.compute_var_task.apply_async", return_value=mock_task),
        patch("api.routes.var.downgrade_for_monthly_limit") as mock_downgrade,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute", json=valid_payload, headers=auth_headers(free_token)
            )

    assert resp.status_code == 202
    mock_downgrade.assert_not_called()


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
async def test_submit_var_cache_hit_with_s3_offload_includes_presigned_url(
    app, free_token, valid_payload
):
    """#130: a cache hit for a large-simulation result carries s3_key —
    hydrate_presigned_url must be called on the cache-hit path too, not just
    the live GET /var/result path, so a cached large result never comes back
    with a stale/missing presigned_url."""
    large_result = {**MOCK_VAR_RESULT, "loss_dist": [], "s3_key": "results/xyz/xyz.parquet"}
    with (
        patch("api.routes.caching._cache_get", return_value=large_result),
        patch("api.routes.var.compute_var_task.apply_async"),
        patch(
            "api.routes.caching.hydrate_presigned_url",
            return_value={**large_result, "presigned_url": "https://s3.example.com/signed"},
        ) as mock_hydrate,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/var/compute",
                json=valid_payload,
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["s3_key"] == "results/xyz/xyz.parquet"
    assert body["result"]["presigned_url"] == "https://s3.example.com/signed"
    mock_hydrate.assert_called_once_with(large_result)


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
    assert body["result"]["s3_key"] is None
    assert body["result"]["presigned_url"] is None
    # CloudFront's ApiCachePolicy (edge_stack.py) clamps TTL from this header —
    # a SUCCESS result is immutable, so it must be edge-cacheable.
    assert resp.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.asyncio
async def test_get_result_success_with_s3_offload_includes_presigned_url(app, free_token):
    """#130: when the Celery result carries an s3_key (large simulation),
    the response includes a freshly-generated presigned_url and empty
    loss_dist — hydrate_presigned_url is mocked at its api.routes.var import
    site, never a real boto3/S3 call."""
    large_result = {**MOCK_VAR_RESULT, "loss_dist": [], "s3_key": "results/abc/abc.parquet"}
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"
    mock_async_result.result = large_result
    mock_async_result.kwargs = {}

    with (
        patch("api.routes.var.AsyncResult", return_value=mock_async_result),
        patch(
            "api.routes.var.hydrate_presigned_url",
            return_value={**large_result, "presigned_url": "https://s3.example.com/signed"},
        ) as mock_hydrate,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/var/result/large-task-id",
                headers=auth_headers(free_token),
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["s3_key"] == "results/abc/abc.parquet"
    assert body["result"]["presigned_url"] == "https://s3.example.com/signed"
    assert body["result"]["loss_dist"] == []
    mock_hydrate.assert_called_once_with(large_result)


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


# ── WS /var/stream/{task_id} ──────────────────────────────────────────────────
#
# fastapi.testclient.TestClient (sync, Starlette's own WS test harness) rather
# than httpx.AsyncClient — httpx has no WebSocket support. Uses the same `app`
# fixture (create_app()) as every async test above; a plain FastAPI instance
# works identically with either client.


@pytest.fixture
def ws_client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_stream_var_result_already_success_sends_immediately(ws_client, free_token):
    """If the job is already terminal when the client connects, the fast path
    sends the result immediately with no Redis Pub/Sub subscription at all."""
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"
    mock_async_result.result = MOCK_VAR_RESULT
    mock_async_result.kwargs = {}

    with (
        patch("api.routes.var.AsyncResult", return_value=mock_async_result),
        patch("api.routes.var.aioredis.Redis.from_url") as mock_redis_from_url,
    ):
        with ws_client.websocket_connect(
            "/api/v1/var/stream/already-done-task?token=" + free_token
        ) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert data["result"]["var_abs"] == 28_000.0
    # The fast path never touches Redis — the job was already terminal.
    mock_redis_from_url.assert_not_called()


def test_stream_var_result_already_failure_sends_immediately(ws_client, free_token):
    mock_async_result = MagicMock()
    mock_async_result.state = "FAILURE"
    mock_async_result.result = Exception("Numba compilation error")

    with patch("api.routes.var.AsyncResult", return_value=mock_async_result):
        with ws_client.websocket_connect(
            "/api/v1/var/stream/failed-task?token=" + free_token
        ) as ws:
            data = ws.receive_json()

    assert data["status"] == "failure"
    assert data["error"] is not None
    assert data["result"] is None


def test_stream_var_result_missing_token_closes_policy_violation(ws_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/api/v1/var/stream/some-task") as ws:
            ws.receive_text()
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_stream_var_result_invalid_token_closes_policy_violation(ws_client):
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/api/v1/var/stream/some-task?token=not-a-real-jwt") as ws:
            ws.receive_text()
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_stream_var_result_polls_until_job_completes(ws_client, free_token):
    """Job is PENDING on the first check, SUCCESS on the second — exercises
    the Pub/Sub-subscribe-and-poll loop, not just the immediate fast path."""
    pending_result = MagicMock()
    pending_result.state = "PENDING"
    success_result = MagicMock()
    success_result.state = "SUCCESS"
    success_result.result = MOCK_VAR_RESULT
    success_result.kwargs = {}

    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(return_value=None)
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_redis_client.aclose = AsyncMock()

    with (
        patch(
            "api.routes.var.AsyncResult",
            side_effect=[pending_result, success_result],
        ),
        patch(
            "api.routes.var.aioredis.Redis.from_url",
            return_value=mock_redis_client,
        ),
    ):
        with ws_client.websocket_connect(
            "/api/v1/var/stream/polling-task?token=" + free_token
        ) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert data["result"]["var_abs"] == 28_000.0
    mock_pubsub.subscribe.assert_awaited_once_with("pyvar:var-job-done:polling-task")
    mock_pubsub.unsubscribe.assert_awaited_once()


def _pending_then_success():
    pending_result = MagicMock()
    pending_result.state = "PENDING"
    success_result = MagicMock()
    success_result.state = "SUCCESS"
    success_result.result = MOCK_VAR_RESULT
    success_result.kwargs = {}
    return pending_result, success_result


def test_stream_var_result_builds_its_redis_client_from_the_shared_url(ws_client, free_token):
    """Regression: the route used cfg.redis_url, which defaults to localhost, so in AWS
    (where only CELERY_RESULT_BACKEND carries the ElastiCache address) every pending job
    crashed the socket. It must use storage.redis_client.redis_url(), like every other
    Redis caller, which also rewrites the ssl_cert_reqs flag redis-py cannot parse."""
    pending_result, success_result = _pending_then_success()
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(return_value=None)
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_redis_client.aclose = AsyncMock()
    shared_url = "rediss://elasticache.example:6379/0?ssl_cert_reqs=none"

    with (
        patch("api.routes.var.AsyncResult", side_effect=[pending_result, success_result]),
        patch("api.routes.var.redis_url", return_value=shared_url),
        patch(
            "api.routes.var.aioredis.Redis.from_url", return_value=mock_redis_client
        ) as mock_from_url,
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/url-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    mock_from_url.assert_called_once_with(shared_url)
    mock_redis_client.aclose.assert_awaited_once()


def test_stream_var_result_falls_back_to_polling_when_subscribe_fails(ws_client, free_token):
    """Regression: a Redis failure at subscribe time was not covered by the route's
    'fall back to polling' handling, so it crashed the socket instead. The job result
    must still arrive on the poll, and the half-built client must still be closed."""
    import redis.exceptions

    pending_result, success_result = _pending_then_success()
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock(side_effect=redis.exceptions.ConnectionError("down"))
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_redis_client.aclose = AsyncMock()
    sleep = AsyncMock()

    with (
        patch("api.routes.var.AsyncResult", side_effect=[pending_result, success_result]),
        patch("api.routes.var.aioredis.Redis.from_url", return_value=mock_redis_client),
        patch("api.routes.var.asyncio.sleep", sleep),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/down-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert data["result"]["var_abs"] == 28_000.0
    sleep.assert_awaited()  # it waited between polls instead of spinning
    mock_pubsub.unsubscribe.assert_not_awaited()  # never subscribed, so nothing to undo
    mock_pubsub.aclose.assert_awaited_once()
    mock_redis_client.aclose.assert_awaited_once()


def test_stream_var_result_waits_between_polls_when_pubsub_read_fails(ws_client, free_token):
    """Regression: when get_message raised straight away the loop fell through to the
    next poll with no wait (the wait lived inside get_message), so a Pub/Sub outage
    turned the route into a busy loop against the result backend."""
    import redis.exceptions

    pending_result, success_result = _pending_then_success()
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(side_effect=redis.exceptions.ConnectionError("dropped"))
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_redis_client.aclose = AsyncMock()
    sleep = AsyncMock()

    with (
        patch(
            "api.routes.var.AsyncResult",
            side_effect=[pending_result, pending_result, pending_result, success_result],
        ),
        patch("api.routes.var.aioredis.Redis.from_url", return_value=mock_redis_client),
        patch("api.routes.var.asyncio.sleep", sleep),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/drop-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert mock_pubsub.get_message.await_count == 1  # tried once, then stopped using Pub/Sub
    assert sleep.await_count >= 1
    mock_pubsub.unsubscribe.assert_awaited_once()


def _wake_up_pubsub(messages):
    """A Pub/Sub double whose get_message yields `messages` in order (None = poll timeout)."""
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(side_effect=messages)
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()
    mock_redis_client = MagicMock()
    mock_redis_client.pubsub = MagicMock(return_value=mock_pubsub)
    mock_redis_client.aclose = AsyncMock()
    return mock_pubsub, mock_redis_client


def test_stream_var_result_rechecks_quickly_after_a_wake_up_that_beats_the_result_store(
    ws_client, free_token
):
    """Regression: the worker publishes before returning, and Celery stores the result only
    after the return, so the first read after a push can still see the job as pending. The
    route then waited a whole poll interval (2.036 s measured on dev). It must re-check
    within a fraction of a second instead."""
    from config import get_settings

    cfg = get_settings()
    pending_result, success_result = _pending_then_success()
    # fast-path check, read after the wake-up, one recheck still pending, then stored
    results = [pending_result, pending_result, pending_result, success_result]
    mock_pubsub, mock_redis_client = _wake_up_pubsub([{"type": "message", "data": b"success"}])
    sleep = AsyncMock()

    with (
        patch("api.routes.var.AsyncResult", side_effect=results),
        patch("api.routes.var.aioredis.Redis.from_url", return_value=mock_redis_client),
        patch("api.routes.var.asyncio.sleep", sleep),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/race-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert mock_pubsub.get_message.await_count == 1  # no second, full-length wait
    waits = [call.args[0] for call in sleep.await_args_list]
    assert waits == [cfg.var_stream_wake_recheck_seconds] * 2
    assert cfg.var_stream_poll_interval_seconds not in waits


def test_stream_var_result_wake_up_recheck_is_bounded_then_polling_resumes(ws_client, free_token):
    """The quick re-check is a short grace window, not a spin: if the job is still pending
    after it, the route goes back to waiting on Pub/Sub or the poll interval."""
    from config import get_settings

    cfg = get_settings()
    pending_result, success_result = _pending_then_success()
    # fast path + read after the wake-up + every recheck pending, then success on the next poll
    results = [pending_result] * (2 + cfg.var_stream_wake_recheck_count) + [success_result]
    mock_pubsub, mock_redis_client = _wake_up_pubsub([{"type": "message", "data": b"x"}, None])
    sleep = AsyncMock()

    with (
        patch("api.routes.var.AsyncResult", side_effect=results),
        patch("api.routes.var.aioredis.Redis.from_url", return_value=mock_redis_client),
        patch("api.routes.var.asyncio.sleep", sleep),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/slow-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert sleep.await_count == cfg.var_stream_wake_recheck_count
    assert mock_pubsub.get_message.await_count == 2  # woke, rechecked, then waited normally
