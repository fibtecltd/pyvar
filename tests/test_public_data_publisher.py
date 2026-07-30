"""
tests/test_public_data_publisher.py — targeted regression test for the #146
companion fix in pyvar-cdk/lambda/public_data_publisher/handler.py.

Reasoning:
- pyvar-cdk/ has no existing Python test coverage (pytest.ini's testpaths is
  `tests` only, and there is no conftest.py / requirements wiring for it) —
  standing up a full test harness for one Lambda module to cover one JWT
  claim would be disproportionate. This imports the handler module directly
  by file path instead, with the three required env vars stubbed, and
  asserts only the one thing #146 changed: the service JWT's tier claim.
- No AWS calls happen: _sign_service_jwt is pure stdlib (hmac/hashlib/base64),
  and boto3.client(...) construction (module import time) does not touch the
  network — only real API calls would, and none are made here.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

HANDLER_PATH = (
    Path(__file__).parent.parent / "pyvar-cdk" / "lambda" / "public_data_publisher" / "handler.py"
)


def _load_handler_module(monkeypatch):
    monkeypatch.setenv("ENV_NAME", "test")
    monkeypatch.setenv("PUBLIC_BUCKET", "pyvar-test-public")
    monkeypatch.setenv("JWT_SECRET_ARN", "arn:aws:secretsmanager:eu-west-1:000000000000:secret:x")
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
