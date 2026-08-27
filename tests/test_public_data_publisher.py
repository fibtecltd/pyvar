"""
tests/test_public_data_publisher.py — targeted regression tests for
pyvar-cdk/lambda/public_data_publisher/handler.py.

Reasoning:
- pyvar-cdk/ has no existing Python test coverage (pytest.ini's testpaths is
  `tests` only, and there is no conftest.py / requirements wiring for it) —
  standing up a full test harness for one Lambda module would be
  disproportionate. This imports the handler module directly by file path
  instead, with the four required env vars stubbed.
- No AWS calls happen: _sign_service_jwt is pure stdlib (hmac/hashlib/base64),
  and boto3.client(...) construction (module import time) does not touch the
  network. Tests that exercise publish_demo_result patch _api_request and
  s3.put_object directly at the module object -- no real HTTP or AWS calls.
- The cache-hit-shape tests cover a real bug: DEMO_PAYLOAD is byte-identical
  on every 15-min cycle, so most cycles hit api/routes/caching.py's
  cache_check decorator and get back a JobResultResponse shape
  ({"result": {...}}) at POST time, not the normal 202 dispatch shape
  ({"task_id": <celery-id>}). Treating "cached" as a pollable task_id meant
  the poll loop always timed out and the cycle silently no-op'd -- see
  publish_demo_result's own comment for the full mechanism.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock

HANDLER_PATH = (
    Path(__file__).parent.parent / "pyvar-cdk" / "lambda" / "public_data_publisher" / "handler.py"
)


def _load_handler_module(monkeypatch):
    monkeypatch.setenv("ENV_NAME", "test")
    monkeypatch.setenv("PUBLIC_BUCKET", "pyvar-test-public")
    monkeypatch.setenv("JWT_SECRET_ARN", "arn:aws:secretsmanager:eu-west-1:000000000000:secret:x")
    monkeypatch.setenv("API_BASE_URL", "https://test.pyvar.example")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    spec = importlib.util.spec_from_file_location("public_data_publisher_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decode_claims(token: str) -> dict:
    _header, payload, _signature = token.split(".")
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def test_service_jwt_uses_internal_tier_not_free(monkeypatch):
    """#146: this Lambda calls POST /var/compute every 15 minutes. Under the
    new tier-based rate limiting, a "free" claim would exhaust the free-tier
    daily quota in ~2.5 hours and silently stop the demo from refreshing —
    the claim must be "internal" (unlimited, exempt) instead."""
    handler = _load_handler_module(monkeypatch)

    token = handler._sign_service_jwt("test-secret")
    claims = _decode_claims(token)

    assert claims["tier"] == "internal"
    assert claims["sub"] == "internal-demo-publisher"


def test_api_base_url_comes_from_environment_not_hardcoded(monkeypatch):
    """task #41: API_BASE_URL was a hardcoded dev-CloudFront literal,
    unconditionally, in every environment's copy of this Lambda -- prod's
    calls failed outright (401, cross-environment JWT-secret mismatch since
    dev's API verified against dev's own secret, not the one prod's Lambda
    signed with). Must be read from the environment (set per-environment by
    public_data_stack.py from cfg.api_base_url), not a fixed literal.
    """
    handler = _load_handler_module(monkeypatch)

    assert handler.API_BASE_URL == "https://test.pyvar.example"
    assert "d1mqqddh8gu2qi.cloudfront.net" not in handler.API_BASE_URL


_CACHE_HIT_RESULT = {
    "var_abs": 28_000.0,
    "var_pct": 0.028,
    "cvar_abs": 35_000.0,
    "cvar_pct": 0.035,
    "mu": 0.0003,
    "sigma": 0.012,
    "duration_ms": 2341,
}


def test_publish_demo_result_uses_cached_result_without_polling(monkeypatch):
    """A cache hit returns JobResultResponse shape ({"result": {...}}) at POST
    time -- must be used directly, never treated as a task_id to poll."""
    handler = _load_handler_module(monkeypatch)

    mock_api_request = MagicMock(
        return_value={"task_id": "cached", "status": "success", "result": _CACHE_HIT_RESULT}
    )
    monkeypatch.setattr(handler, "_api_request", mock_api_request)
    mock_put_object = MagicMock()
    monkeypatch.setattr(handler.s3, "put_object", mock_put_object)

    demo = handler.publish_demo_result("test-secret")

    # Exactly one call (the POST) -- no GET poll was ever attempted.
    mock_api_request.assert_called_once()
    assert mock_api_request.call_args[0][0] == "POST"
    assert demo is not None
    mock_put_object.assert_called_once()


def test_publish_demo_result_reports_engine_duration_not_round_trip(monkeypatch):
    """runtime_ms in the published JSON must be VaRResult.duration_ms (engine
    call only), not this function's own wall-clock timer -- the latter would
    also count SQS queue wait and any worker cold-start."""
    handler = _load_handler_module(monkeypatch)

    monkeypatch.setattr(
        handler,
        "_api_request",
        MagicMock(
            return_value={"task_id": "cached", "status": "success", "result": _CACHE_HIT_RESULT}
        ),
    )
    monkeypatch.setattr(handler.s3, "put_object", MagicMock())

    demo = handler.publish_demo_result("test-secret")

    assert demo["runtime_ms"] == _CACHE_HIT_RESULT["duration_ms"]


def test_publish_demo_result_skips_publish_when_duration_ms_missing(monkeypatch):
    """A VaRResult cached before duration_ms existed has no such key -- must
    skip publishing (leaving the previous good demo-result.json in place),
    never publish a broken/null runtime."""
    handler = _load_handler_module(monkeypatch)

    stale_result = {k: v for k, v in _CACHE_HIT_RESULT.items() if k != "duration_ms"}
    monkeypatch.setattr(
        handler,
        "_api_request",
        MagicMock(return_value={"task_id": "cached", "status": "success", "result": stale_result}),
    )
    mock_put_object = MagicMock()
    monkeypatch.setattr(handler.s3, "put_object", mock_put_object)

    demo = handler.publish_demo_result("test-secret")

    assert demo is None
    mock_put_object.assert_not_called()
