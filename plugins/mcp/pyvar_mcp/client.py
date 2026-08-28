"""plugins/mcp/pyvar_mcp/client.py — thin synchronous HTTP client for pyvar's API.

Reasoning:
- Stdlib urllib only, no requests/httpx dependency for the actual API calls --
  same convention pyvar-cdk/lambda/*/handler.py already uses for their own
  outbound calls (see those modules' own docstrings for why: this plugin's
  only hard dependency should be the `mcp` SDK itself, not a second HTTP
  stack). The `mcp` package pulls in its own httpx transitively for the
  MCP *protocol* wire format -- that's unrelated to this client, which only
  ever talks to pyvar's REST API.
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
from dataclasses import dataclass
from typing import Any

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


@dataclass
class PyvarClient:
    """Minimal synchronous client: one method, one job -- POST params to a
    function's endpoint, return the parsed JSON result."""

    api_key: str
    base_url: str = DEFAULT_API_BASE_URL

    @classmethod
    def from_env(cls) -> PyvarClient:
        """Reads PYVAR_API_KEY (required) and PYVAR_API_BASE_URL (optional,
        for pointing at a dev/staging deployment during testing) from the
        environment -- set by plugin.json's userConfig-backed mcpServers.env
        block at install time."""
        api_key = os.environ.get("PYVAR_API_KEY")
        if not api_key:
            raise RuntimeError(
                "PYVAR_API_KEY is not set. Get a free-tier key from "
                "https://www.pyvar.com#get-api-key and configure it when "
                "installing this plugin."
            )
        base_url = os.environ.get("PYVAR_API_BASE_URL", DEFAULT_API_BASE_URL)
        return cls(api_key=api_key, base_url=base_url)

    def call_function(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """POSTs params to {base_url}{path} and returns the parsed JSON
        response body.

        Raises PyvarApiError on any non-2xx response -- the caller (the MCP
        tool-call handler) decides how to surface that back to the model,
        this method never swallows an error into a fabricated result.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(params).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
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
