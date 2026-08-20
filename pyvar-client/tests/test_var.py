"""tests/test_var.py — client.var: the one hand-written async-job wrapper.

Covers submit/poll/compute against the real request/response shapes
(schemas/var.py's JobResponse/JobResultResponse), the failure ->
PyvarComputeError path, the timeout -> PyvarTimeoutError path, and that
submit() specifically is never auto-retried (idempotent=False).
"""

from __future__ import annotations

import httpx
import pytest

from pyvar_client.exceptions import PyvarComputeError, PyvarError, PyvarTimeoutError
from tests.conftest import make_client


def test_submit_returns_task_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/var/compute"
        return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})

    client = make_client(handler)
    task_id = client.var.submit(portfolio_value=1_000_000, returns=[0.01] * 60)
    assert task_id == "abc-123"


def test_submit_includes_n_simulations_when_given():
    seen_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_bodies.append(request.content)
        return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})

    client = make_client(handler)
    client.var.submit(portfolio_value=1_000_000, returns=[0.01] * 60, n_simulations=100_000)
    import json as _json

    body = _json.loads(seen_bodies[0])
    assert body["n_simulations"] == 100_000


def test_submit_omits_n_simulations_when_not_given():
    """n_simulations is Optional in submit()'s own signature (falls back to
    the tier default server-side) -- must not send it as a literal `null`
    that would fail VaRRequest's own ge=1_000 constraint."""
    seen_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_bodies.append(httpx.Request.read(request) and request.content)
        return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})

    client = make_client(handler)
    client.var.submit(portfolio_value=1_000_000, returns=[0.01] * 60)
    import json as _json

    body = _json.loads(seen_bodies[0])
    assert "n_simulations" not in body


def test_submit_is_never_retried_on_5xx():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"detail": "unavailable"})

    client = make_client(handler)
    with pytest.raises(PyvarError):
        client.var.submit(portfolio_value=1_000_000, returns=[0.01] * 60)
    assert calls["count"] == 1


def test_poll_returns_raw_result_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/var/result/abc-123"
        return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})

    client = make_client(handler)
    result = client.var.poll("abc-123")
    assert result["status"] == "pending"


def test_compute_polls_until_success_and_returns_result():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/var/compute":
            return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(200, json={"task_id": "abc-123", "status": "started"})
        return httpx.Response(
            200,
            json={
                "task_id": "abc-123",
                "status": "success",
                "result": {"var_pct": 0.05, "var_abs": 50_000.0},
            },
        )

    client = make_client(handler)
    result = client.var.compute(
        portfolio_value=1_000_000, returns=[0.01] * 60, poll_interval_seconds=0.0
    )
    assert result == {"var_pct": 0.05, "var_abs": 50_000.0}


def test_compute_raises_pyvar_compute_error_on_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/var/compute":
            return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})
        return httpx.Response(
            200,
            json={"task_id": "abc-123", "status": "failure", "error": "simulation diverged"},
        )

    client = make_client(handler)
    with pytest.raises(PyvarComputeError) as exc_info:
        client.var.compute(
            portfolio_value=1_000_000, returns=[0.01] * 60, poll_interval_seconds=0.0
        )
    assert exc_info.value.task_id == "abc-123"
    assert exc_info.value.detail == "simulation diverged"


def test_compute_raises_pyvar_timeout_error_when_never_terminal():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/var/compute":
            return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})
        return httpx.Response(200, json={"task_id": "abc-123", "status": "pending"})

    client = make_client(handler)
    with pytest.raises(PyvarTimeoutError) as exc_info:
        client.var.compute(
            portfolio_value=1_000_000,
            returns=[0.01] * 60,
            poll_interval_seconds=0.0,
            poll_timeout_seconds=0.01,
        )
    assert exc_info.value.task_id == "abc-123"
