"""tests/conftest.py -- no real HTTP calls anywhere in this suite.

Same rule pyvar-client/tests/conftest.py applies to itself: httpx.MockTransport
intercepts every request at the transport layer, so Client's real
retry/error-mapping/auth-header logic all still runs, just against a handler
this test controls instead of a live server.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pyvar_client import Client
from pyvar_jupyter._magics import PyvarMagics


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


@pytest.fixture
def magics() -> PyvarMagics:
    """A PyvarMagics instance with no shell attached. _invoke() guards every
    self.shell access, so this is fine for anything that doesn't need
    {expr} variable expansion -- see the `magics_with_shell` fixture for
    that."""
    return PyvarMagics(shell=None)


@pytest.fixture
def magics_with_shell() -> PyvarMagics:
    """A PyvarMagics instance attached to a real IPython InteractiveShell,
    for exercising {expr} variable expansion (self.shell.var_expand) --
    shell=None can't do this since there's no user namespace to expand
    against."""
    from IPython.testing.globalipapp import get_ipython

    # nosec B604 -- bandit flags any call with a `shell=` kwarg as a possible
    # subprocess shell-injection risk. This isn't one: `shell` here is
    # IPython's own Magics.__init__(self, shell=None, ...) parameter -- an
    # InteractiveShell instance, not a subprocess flag. No command execution
    # anywhere in this line.
    return PyvarMagics(shell=get_ipython())  # nosec B604
