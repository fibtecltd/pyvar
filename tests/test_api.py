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
#
# The route waits on the process-wide Pub/Sub subscriber (_JobDoneBus). These tests replace it
# with a stand-in, so none of them touches Redis or starts a reader task; the subscriber itself
# is tested in tests/test_job_done_bus.py.


class _FakeBus:
    """Stands in for _JobDoneBus: records registrations, wakes nobody, owns no Redis."""

    def __init__(self, healthy=False):
        self.healthy = healthy
        self.registered = []
        self.unregistered = []
        self.log = None  # an optional shared list, to check the order against other events

    async def register(self, task_id):
        import asyncio

        self.registered.append(task_id)
        if self.log is not None:
            self.log.append("register")
        return asyncio.Event()

    def unregister(self, task_id, event):
        self.unregistered.append(task_id)


@pytest.fixture
def stream_slots():
    """A fresh open-socket budget per test, so a failing test cannot leak slots into the next."""
    import api.routes.var as var_routes

    slots = var_routes._StreamSlots()
    with patch.object(var_routes, "_stream_slots", slots):
        yield slots


@pytest.fixture
def job_bus():
    import api.routes.var as var_routes

    bus = _FakeBus()
    with patch.object(var_routes, "_job_done_bus", bus):
        yield bus


@pytest.fixture
def ws_client(app, stream_slots, job_bus):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _pending_then_success():
    pending_result = MagicMock()
    pending_result.state = "PENDING"
    success_result = MagicMock()
    success_result.state = "SUCCESS"
    success_result.result = MOCK_VAR_RESULT
    success_result.kwargs = {}
    return pending_result, success_result


def _never_finishing_job():
    pending_result = MagicMock()
    pending_result.state = "PENDING"
    return pending_result


def test_stream_var_result_already_success_sends_immediately(ws_client, free_token, job_bus):
    """If the job is already terminal when the client connects, the fast path
    sends the result immediately without waiting on the subscriber at all."""
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"
    mock_async_result.result = MOCK_VAR_RESULT
    mock_async_result.kwargs = {}

    with patch("api.routes.var.AsyncResult", return_value=mock_async_result):
        with ws_client.websocket_connect(
            "/api/v1/var/stream/already-done-task?token=" + free_token
        ) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert data["result"]["var_abs"] == 28_000.0
    assert job_bus.registered == []  # the job was already terminal


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


def test_stream_var_result_waits_on_the_subscriber_then_sends_the_result(
    ws_client, free_token, job_bus
):
    """Pending on the fast path and on the read after registering, then stored by the time the
    wait ends: the result is pushed and the registration is undone."""
    from config import get_settings

    cfg = get_settings()
    pending_result, success_result = _pending_then_success()
    wait = AsyncMock(return_value=False)

    with (
        patch(
            "api.routes.var.AsyncResult",
            side_effect=[pending_result, pending_result, success_result],
        ),
        patch("api.routes.var._wait_for_wake", wait),
    ):
        with ws_client.websocket_connect(
            "/api/v1/var/stream/polling-task?token=" + free_token
        ) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert data["result"]["var_abs"] == 28_000.0
    assert job_bus.registered == ["polling-task"]
    assert job_bus.unregistered == ["polling-task"]
    # the subscriber is down (the fake's default), so the short interval applies
    assert wait.await_args.args[1] == cfg.var_stream_poll_interval_seconds


def test_stream_var_result_polls_slowly_only_while_the_subscriber_is_up(
    ws_client, free_token, job_bus
):
    from config import get_settings

    cfg = get_settings()
    job_bus.healthy = True
    pending_result, success_result = _pending_then_success()
    wait = AsyncMock(return_value=False)

    with (
        patch(
            "api.routes.var.AsyncResult",
            side_effect=[pending_result, pending_result, success_result],
        ),
        patch("api.routes.var._wait_for_wake", wait),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/up-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert wait.await_args.args[1] == cfg.var_stream_safety_poll_seconds
    assert cfg.var_stream_safety_poll_seconds > cfg.var_stream_poll_interval_seconds


def test_stream_var_result_registers_before_the_state_read_that_follows_the_fast_path(
    ws_client, free_token, job_bus
):
    """A completion between the fast-path read and the registration would otherwise be missed:
    the route must be registered before it reads the state a second time."""
    order = []
    job_bus.log = order
    pending_result, success_result = _pending_then_success()
    reads = iter([pending_result, pending_result, success_result])

    def next_read(*_args, **_kwargs):
        order.append("read")
        return next(reads)

    with (
        patch("api.routes.var.AsyncResult", side_effect=next_read),
        patch("api.routes.var._wait_for_wake", AsyncMock(return_value=False)),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/order-task?token=" + free_token) as ws:
            ws.receive_json()

    assert order[:3] == ["read", "register", "read"]


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
    # fast path, read after registering, read after the wake-up, one recheck pending, then stored
    results = [pending_result, pending_result, pending_result, pending_result, success_result]
    wait = AsyncMock(return_value=True)
    sleep = AsyncMock()

    with (
        patch("api.routes.var.AsyncResult", side_effect=results),
        patch("api.routes.var._wait_for_wake", wait),
        patch("api.routes.var.asyncio.sleep", sleep),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/race-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert wait.await_count == 1  # no second, full-length wait
    waits = [call.args[0] for call in sleep.await_args_list]
    assert waits == [cfg.var_stream_wake_recheck_seconds] * 2
    assert cfg.var_stream_poll_interval_seconds not in waits


def test_stream_var_result_wake_up_recheck_is_bounded_then_waiting_resumes(ws_client, free_token):
    """The quick re-check is a short grace window, not a spin: if the job is still pending
    after it, the route goes back to waiting."""
    from config import get_settings

    cfg = get_settings()
    pending_result, success_result = _pending_then_success()
    # fast path + read after registering + read after the wake-up + every recheck pending,
    # then success after the second, ordinary wait
    results = [pending_result] * (3 + cfg.var_stream_wake_recheck_count) + [success_result]
    wait = AsyncMock(side_effect=[True, False])
    sleep = AsyncMock()

    with (
        patch("api.routes.var.AsyncResult", side_effect=results),
        patch("api.routes.var._wait_for_wake", wait),
        patch("api.routes.var.asyncio.sleep", sleep),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/slow-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert sleep.await_count == cfg.var_stream_wake_recheck_count
    assert wait.await_count == 2  # woke, rechecked, then waited normally


# ── WS /var/stream/{task_id}: open-socket limits and abandoned clients ─────────
#
# Phase 0d on dev: 135 abandoned sockets kept polling Redis for the full 900 s wait (the route
# never read from the socket, so it could not see the client go) and the 1 GiB task, idling at
# 787 MiB, ended at 98% memory. These tests pin the two guards: the handler ends when the client
# leaves, and a process refuses sockets over its budget.


def _wait_until(predicate, timeout=2.0):
    """Poll `predicate` from the test thread; the handler runs on TestClient's own loop."""
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_stream_var_result_ends_when_the_client_disconnects(
    ws_client, free_token, stream_slots, job_bus
):
    """Regression: the handler waited out the whole max-wait before noticing a closed client."""
    from config import get_settings

    cfg = get_settings()

    with (
        patch.object(cfg, "var_stream_poll_interval_seconds", 0.05),
        patch.object(cfg, "var_stream_max_wait_seconds", 30),
        patch("api.routes.var.AsyncResult", return_value=_never_finishing_job()),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/gone-task?token=" + free_token) as ws:
            assert _wait_until(lambda: stream_slots.active == 1)
            ws.close()
            # Still inside the block: the harness cancels a handler that is left running when
            # the block exits, so only a handler that notices the close by itself gets here.
            assert _wait_until(lambda: stream_slots.active == 0)
            assert _wait_until(lambda: job_bus.unregistered == ["gone-task"])


def test_stream_var_result_releases_its_slot_when_the_job_completes(
    ws_client, free_token, stream_slots
):
    pending_result, success_result = _pending_then_success()

    with (
        patch(
            "api.routes.var.AsyncResult",
            side_effect=[pending_result, pending_result, success_result],
        ),
        patch("api.routes.var._wait_for_wake", AsyncMock(return_value=False)),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/slot-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert stream_slots.active == 0


def test_stream_var_result_refuses_sockets_over_the_process_cap(
    ws_client, free_token, pro_token, stream_slots
):
    from config import get_settings

    cfg = get_settings()

    with (
        patch.object(cfg, "var_stream_poll_interval_seconds", 0.05),
        patch.object(cfg, "var_stream_max_wait_seconds", 3),  # a wrongly admitted socket ends
        patch.object(cfg, "var_stream_max_connections", 1),
        patch("api.routes.var.AsyncResult", return_value=_never_finishing_job()),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/first?token=" + free_token):
            assert _wait_until(lambda: stream_slots.active == 1)
            with pytest.raises(WebSocketDisconnect) as exc_info:
                # another user, so only the process-wide cap can refuse it
                with ws_client.websocket_connect(
                    "/api/v1/var/stream/second?token=" + pro_token
                ) as ws:
                    ws.receive_text()
            assert exc_info.value.code == status.WS_1013_TRY_AGAIN_LATER
            assert "server" in exc_info.value.reason
            assert stream_slots.active == 1  # a refused socket takes no slot

    assert stream_slots.active == 0


def test_stream_var_result_caps_sockets_per_user(ws_client, free_token, pro_token, stream_slots):
    from config import get_settings

    cfg = get_settings()

    with (
        patch.object(cfg, "var_stream_poll_interval_seconds", 0.05),
        patch.object(cfg, "var_stream_max_wait_seconds", 3),  # a wrongly admitted socket ends
        patch.object(cfg, "var_stream_max_connections_per_user", 1),
        patch("api.routes.var.AsyncResult", return_value=_never_finishing_job()),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/mine?token=" + free_token):
            assert _wait_until(lambda: stream_slots.active == 1)
            # a different user still gets a socket
            with ws_client.websocket_connect("/api/v1/var/stream/theirs?token=" + pro_token):
                assert _wait_until(lambda: stream_slots.active == 2)
                with pytest.raises(WebSocketDisconnect) as exc_info:
                    with ws_client.websocket_connect(
                        "/api/v1/var/stream/mine-too?token=" + free_token
                    ) as ws:
                        ws.receive_text()
                assert exc_info.value.code == status.WS_1013_TRY_AGAIN_LATER
                assert "account" in exc_info.value.reason

    assert stream_slots.active == 0


def test_stream_var_result_answers_a_finished_job_even_at_the_cap(
    ws_client, free_token, stream_slots
):
    """The cap guards sockets that wait. A job that is already done is answered and closed at
    once, so it must not be refused however full the process is."""
    from config import get_settings

    cfg = get_settings()
    mock_async_result = MagicMock()
    mock_async_result.state = "SUCCESS"
    mock_async_result.result = MOCK_VAR_RESULT
    mock_async_result.kwargs = {}

    with (
        patch.object(cfg, "var_stream_max_connections", 0),
        patch("api.routes.var.AsyncResult", return_value=mock_async_result),
    ):
        with ws_client.websocket_connect("/api/v1/var/stream/done-task?token=" + free_token) as ws:
            data = ws.receive_json()

    assert data["status"] == "success"
    assert stream_slots.active == 0
