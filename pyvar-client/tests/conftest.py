"""tests/conftest.py — no real HTTP calls anywhere in this suite.

Reasoning:
- Same rule the main pyvar repo applies to AWS in its own tests (CLAUDE.md
  §5 Rule 3: never use real external services) -- here the equivalent is
  never making a real HTTP call to pyvar.com. httpx.MockTransport
  intercepts every request at the transport layer, so Client's real
  retry/error-mapping/auth-header logic all still runs, just against a
  handler this test controls instead of a live server.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pyvar_client import Client


def make_client(handler: Callable[[httpx.Request], httpx.Response], **client_kwargs: Any) -> Client:
    return Client(
        api_key="test-token",
        transport=httpx.MockTransport(handler),
        **client_kwargs,
    )


@pytest.fixture
def json_response() -> Callable[..., Callable[[httpx.Request], httpx.Response]]:
    """Handler factory: always returns the given status/body, ignoring the request."""

    def _factory(status_code: int, body: Any) -> Callable[[httpx.Request], httpx.Response]:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json=body)

        return handler

    return _factory
