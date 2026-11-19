"""plugins/mcp/pyvar_mcp/client.py — thin synchronous HTTP client for pyvar's API.

Reasoning:
- Stdlib urllib only, no requests/httpx dependency for the actual API calls --
  same convention pyvar-cdk/lambda/*/handler.py already uses for their own
  outbound calls (see those modules' own docstrings for why: this plugin's
  only hard dependency should be the `mcp` SDK itself, not a second HTTP
  stack). The `mcp` package pulls in its own httpx transitively for the
  MCP *protocol* wire format -- that's unrelated to this client, which only
  ever talks to pyvar's REST API.
- With no API key configured the client does not fail at start-up any more: it runs the 30 functions on the
  no-sign-up trial list through pyvar.com's trial routes (trial.py), asking for an anonymous installation ticket
  at the first call that needs one. A configured key always wins, and the key path below is unchanged.
- Every function catalogued in functions.json (see
  scripts/generate_mcp_tools.py's own docstring for how this was confirmed)
  is a plain synchronous POST -> JSON response -- no submit/poll job pattern.
  Only /api/v1/var/compute (not itself one of the 385 catalogued functions)
  uses that pattern, so this client doesn't need to implement it.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from . import __version__
from .trial import TrialError, TrialHttpError, TrialSession, unavailable_message

DEFAULT_API_BASE_URL = "https://www.pyvar.com"
REQUEST_TIMEOUT_SECONDS = 30


class PyvarApiError(Exception):
    """Raised for any non-2xx response from the pyvar API.

    Carries the HTTP status code and whatever body the API returned (usually
    a FastAPI {"detail": ...} shape) so the MCP tool-call handler can relay
    something a model can actually act on, rather than a bare exception
    string.
    """

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"pyvar API returned HTTP {status_code}: {body}")


class PyvarSetupError(Exception):
    """No key is configured and the no-sign-up trial cannot help; `message` says what to do next.

    Raised from call_function, never at start-up, so the server still starts and lists its tools.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def clean_api_key(value: str | None) -> str | None:
    """The configured key, or None when it is empty or an unsubstituted ${user_config...} placeholder."""
    if value is None:
        return None
    value = value.strip()
    if not value or value.startswith("${"):
        return None
    return value


# "pyvar-mcp/<version>", sent as X-Pyvar-Client so the API can attribute calls to this server
# (an allowlisted label, never tied to a user). The version is the one the server reports to
# MCP clients when they connect: pyvar_mcp.__version__.
CLIENT_ID = f"pyvar-mcp/{__version__}"


@dataclass
class PyvarClient:
    """Minimal synchronous client: one method, one job -- POST params to a
    function's endpoint, return the parsed JSON result.

    With `api_key` set every function works. Without one, the 30 functions on the no-sign-up trial list work
    through pyvar.com's trial routes (trial.py), and anything else is an explanatory PyvarSetupError.
    """

    api_key: str | None = None
    base_url: str = DEFAULT_API_BASE_URL
    _trial: TrialSession | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_env(cls) -> PyvarClient:
        """Reads PYVAR_API_KEY (optional now) and PYVAR_API_BASE_URL (optional,
        for pointing at a dev/staging deployment during testing) from the
        environment -- set by plugin.json's userConfig-backed mcpServers.env
        block at install time. An empty key, or the literal `${user_config...}`
        an unset option may leave behind, counts as no key."""
        return cls(
            api_key=clean_api_key(os.environ.get("PYVAR_API_KEY")),
            base_url=os.environ.get("PYVAR_API_BASE_URL", DEFAULT_API_BASE_URL),
        )

    @property
    def has_key(self) -> bool:
        return self.api_key is not None

    def call_function(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """POSTs params to {base_url}{path} and returns the parsed JSON
        response body.

        Raises PyvarApiError on any non-2xx response -- the caller (the MCP
        tool-call handler) decides how to surface that back to the model,
        this method never swallows an error into a fabricated result. Raises
        PyvarSetupError when there is no key and the trial cannot run the
        function (not on its list, CI is set, or not inside Claude Code's
        plugin runtime), or the trial is busy or spent.
        """
        if self.api_key is None:
            return self._call_trial(path, params)
        url = f"{self.base_url}{path}"
        data = json.dumps(params).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("X-Pyvar-Client", CLIENT_ID)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(
                req, timeout=REQUEST_TIMEOUT_SECONDS
            ) as resp:  # nosec B310 -- fixed https base_url, not user-controlled
                body = resp.read().decode()
        except urllib.error.HTTPError as exc:
            raise PyvarApiError(exc.code, exc.read().decode()) from exc
        except urllib.error.URLError as exc:
            raise PyvarApiError(0, f"network error: {exc.reason}") from exc
        result: dict[str, Any] = json.loads(body)
        return result

    def _call_trial(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """The no-key path: the trial routes, for the functions on the trial list."""
        reason = unavailable_message()
        if reason is not None:
            raise PyvarSetupError(reason)
        if self._trial is None:
            try:
                self._trial = TrialSession.from_env(self.base_url)
            except TrialError as exc:
                raise PyvarSetupError(exc.message) from exc
        try:
            return self._trial.call(path.rsplit("/", 1)[-1], params)
        except TrialHttpError as exc:
            raise PyvarApiError(exc.status_code, exc.body) from exc
        except TrialError as exc:
            raise PyvarSetupError(exc.message) from exc
