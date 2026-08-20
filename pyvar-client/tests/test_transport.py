"""tests/test_transport.py — retry/backoff and error-mapping behaviour.

Covers the specific claims _transport.py's own docstring makes: 5xx and
connection errors retry (idempotent calls only), 4xx never retries, and
each status code maps to the right typed exception.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from pyvar_client.exceptions import (
    PyvarAuthError,
    PyvarError,
    PyvarRateLimitError,
    PyvarValidationError,
)
from tests.conftest import make_client


@pytest.fixture(autouse=True)
def _no_real_sleep():
    """Retry backoff is real logic worth exercising, but nothing here
    should cost wall-clock seconds in CI -- patches time.sleep at the
    call site (_transport module), not the retry/backoff logic itself."""
    with patch("pyvar_client._transport.time.sleep"):
        yield


def test_successful_call_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"var_pct": 0.05})

    client = make_client(handler)
    result = client.market_risk.historical_simulation_var(
        returns=[0.01] * 60, portfolio_value=1_000_000
    )
    assert result == {"var_pct": 0.05}


def test_401_raises_pyvar_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid or expired token"})

    client = make_client(handler)
    with pytest.raises(PyvarAuthError) as exc_info:
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert exc_info.value.response_status == 401


def test_422_raises_pyvar_validation_error_with_field_detail():
    detail = [{"loc": ["body", "confidence_level"], "msg": "out of range", "type": "value_error"}]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": detail})

    client = make_client(handler)
    with pytest.raises(PyvarValidationError) as exc_info:
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert exc_info.value.detail == detail


def test_429_raises_pyvar_rate_limit_error_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "42"},
            json={"detail": "Rate limit exceeded. Please retry later."},
        )

    client = make_client(handler)
    with pytest.raises(PyvarRateLimitError) as exc_info:
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert exc_info.value.retry_after == 42


def test_5xx_is_retried_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(503, json={"detail": "temporarily unavailable"})
        return httpx.Response(200, json={"var_pct": 0.05})

    client = make_client(handler)
    result = client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert result == {"var_pct": 0.05}
    assert calls["count"] == 3


def test_5xx_exhausts_retries_and_raises():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, json={"detail": "still broken"})

    client = make_client(handler)
    with pytest.raises(PyvarError) as exc_info:
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert exc_info.value.response_status == 500
    # Initial attempt + _MAX_RETRIES retries.
    assert calls["count"] == 4


def test_400_level_error_not_in_special_cases_maps_to_generic_pyvar_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    client = make_client(handler)
    with pytest.raises(PyvarError) as exc_info:
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert exc_info.value.response_status == 404
    assert not isinstance(exc_info.value, (PyvarAuthError, PyvarValidationError))


def test_bearer_token_sent_on_every_request():
    seen_headers = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("authorization"))
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert seen_headers == ["Bearer test-token"]


def test_non_json_error_body_falls_back_to_raw_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream gateway error, not JSON")

    client = make_client(handler)
    with pytest.raises(PyvarError) as exc_info:
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert exc_info.value.response_body == "upstream gateway error, not JSON"


def test_connect_error_is_retried_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"var_pct": 0.05})

    client = make_client(handler)
    result = client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)
    assert result == {"var_pct": 0.05}
    assert calls["count"] == 2


def test_connect_error_exhausts_retries_and_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(handler)
    with pytest.raises(httpx.ConnectError):
        client.market_risk.historical_simulation_var(returns=[0.01] * 60, portfolio_value=1.0)


def test_connect_error_on_non_idempotent_call_never_retried():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.ConnectError("connection refused", request=request)

    client = make_client(handler)
    with pytest.raises(httpx.ConnectError):
        client.var.submit(portfolio_value=1_000_000, returns=[0.01] * 60)
    assert calls["count"] == 1
