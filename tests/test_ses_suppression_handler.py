"""
tests/test_ses_suppression_handler.py — targeted regression test for task #41
in pyvar-cdk/lambda/ses_suppression_handler/handler.py.

Reasoning:
- Same rationale as tests/test_public_data_publisher.py: pyvar-cdk/ has no
  existing Python test coverage, and this Lambda had none at all before this
  file — standing up a full test harness for one env-var check would be
  disproportionate. Imports the handler module directly by file path, with
  the required env vars stubbed, and asserts only the one thing task #41
  changed: API_BASE_URL comes from the environment, not a hardcoded literal.
- No AWS calls happen: boto3.client(...) construction (module import time)
  does not touch the network — only real API/Secrets Manager calls would,
  and none are made here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HANDLER_PATH = (
    Path(__file__).parent.parent / "pyvar-cdk" / "lambda" / "ses_suppression_handler" / "handler.py"
)


def _load_handler_module(monkeypatch):
    monkeypatch.setenv("ENV_NAME", "test")
    monkeypatch.setenv("JWT_SECRET_ID", "pyvar/test/jwt-secret")
    monkeypatch.setenv("API_BASE_URL", "https://test.pyvar.example")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")

    spec = importlib.util.spec_from_file_location("ses_suppression_handler", HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_base_url_comes_from_environment_not_hardcoded(monkeypatch):
    """task #41: API_BASE_URL was a hardcoded dev-CloudFront literal,
    unconditionally, in every environment's copy of this Lambda -- prod's
    suppression calls would fail outright (401, cross-environment
    JWT-secret mismatch) the moment a real bounce/complaint event ever
    triggered this handler. Must be read from the environment (set
    per-environment by ses_events_stack.py from cfg.api_base_url), not a
    fixed literal.
    """
    handler = _load_handler_module(monkeypatch)

    assert handler.API_BASE_URL == "https://test.pyvar.example"
    assert "d1mqqddh8gu2qi.cloudfront.net" not in handler.API_BASE_URL
