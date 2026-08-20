"""pyvar_client._transport — the one HTTP call path every method goes through.

Reasoning:
- Single choke point for auth header injection, error-code-to-exception
  mapping, and retry/backoff -- every generated domain method and the
  hand-written VaR wrapper call `Client._request`, which calls
  `send_request` here. Nothing constructs its own httpx call.
- Retry is idempotency-aware, not blanket: `idempotent=True` (the default,
  used by every synchronous domain function -- pure compute, no side
  effects) retries on connection errors, timeouts, and 5xx. `idempotent=
  False` (used only by POST /var/compute's submission, in _var.py) never
  retries automatically -- a blind retry there risks double-submitting a
  Monte Carlo job, since the API has no idempotency-key mechanism to
  de-duplicate on. Polling GET /var/result/{task_id} is itself idempotent
  (it's a read), so it uses the default.
- Exponential backoff with a small fixed jitter-free schedule (not a
  dependency like tenacity) -- this client has one job and stays
  dependency-light; httpx is the only non-stdlib import.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from pyvar_client.exceptions import (
    PyvarAuthError,
    PyvarError,
    PyvarRateLimitError,
    PyvarValidationError,
)

_RETRYABLE_STATUS = {500, 502, 503, 504}
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.5


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    detail = body.get("detail") if isinstance(body, dict) else None

    if response.status_code == 401:
        raise PyvarAuthError(
            "Authentication failed -- token missing, invalid, or expired.",
            response_status=401,
            response_body=body,
        )
    if response.status_code == 422:
        # FastAPI's default validation error shape: detail is a list of
        # {"loc": [...], "msg": ..., "type": ...} entries.
        raise PyvarValidationError(
            "Request failed validation.",
            detail=detail if isinstance(detail, list) else None,
            response_status=422,
            response_body=body,
        )
    if response.status_code == 429:
        retry_after_header = response.headers.get("Retry-After")
        raise PyvarRateLimitError(
            detail if isinstance(detail, str) else "Rate limit exceeded.",
            retry_after=int(retry_after_header) if retry_after_header else None,
            response_status=429,
            response_body=body,
        )

    raise PyvarError(
        detail if isinstance(detail, str) else f"HTTP {response.status_code}",
        response_status=response.status_code,
        response_body=body,
    )


def send_request(
    http_client: httpx.Client,
    method: str,
    path: str,
    *,
    token: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    idempotent: bool = True,
) -> dict[str, Any]:
    """Send one request, mapping the response to a dict or a PyvarError subclass.

    Returns:
        The parsed JSON response body.

    Raises:
        PyvarAuthError: 401.
        PyvarValidationError: 422.
        PyvarRateLimitError: 429.
        PyvarError: any other 4xx/5xx after retries (if idempotent) are exhausted.
        httpx.HTTPError: a genuine network/timeout failure with no response at all.
    """
    headers = {"Authorization": f"Bearer {token}"}
    attempt = 0

    while True:
        try:
            response = http_client.request(
                method, path, json=json_body, params=params, headers=headers
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            if not idempotent or attempt >= _MAX_RETRIES:
                raise
            time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
            attempt += 1
            continue

        if idempotent and response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
            time.sleep(_BACKOFF_BASE_SECONDS * (2**attempt))
            attempt += 1
            continue

        _raise_for_status(response)
        result: dict[str, Any] = response.json()
        return result
