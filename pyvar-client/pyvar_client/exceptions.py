"""pyvar_client.exceptions — typed exceptions mapped from the API's real status codes.

Reasoning:
- Callers want to know WHY a call failed, not just that httpx raised
  something. Regulatory-sensitive callers especially: a 422 on a
  confidence_level outside [0.90, 0.9999] is a very different situation
  from a 401 on an expired token, and code that catches these generically
  can't distinguish "fix my request" from "re-authenticate" from "back off
  and retry".
- Every exception here carries the raw response body/headers it was built
  from (response_body / response_status), so a caller that needs more than
  the typed fields can still get at the original data without re-parsing.
"""

from __future__ import annotations

from typing import Any


class PyvarError(Exception):
    """Base class for every error this client raises for an API response.

    Never raised directly -- always one of the subclasses below. A plain
    network/timeout failure (no response at all) surfaces as the
    underlying httpx exception, not a PyvarError -- there's no API status
    code to map in that case.
    """

    def __init__(
        self,
        message: str,
        *,
        response_status: int | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.response_status = response_status
        self.response_body = response_body


class PyvarAuthError(PyvarError):
    """401 -- the bearer token is missing, invalid, or expired.

    Registration/verification is a one-time human step (email link) this
    client does not automate -- see the Client docstring. There's nothing
    to retry here; the caller needs a fresh token.
    """


class PyvarValidationError(PyvarError):
    """422 -- the request failed Pydantic validation server-side.

    `detail` mirrors FastAPI's default validation error shape: a list of
    {"loc": [...], "msg": ..., "type": ...} entries, one per invalid field.
    """

    def __init__(
        self,
        message: str,
        *,
        detail: list[dict[str, Any]] | None = None,
        response_status: int | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message, response_status=response_status, response_body=response_body)
        self.detail = detail or []


class PyvarRateLimitError(PyvarError):
    """429 -- tier-based rate limit exceeded (api/middleware/rate_limit.py).

    retry_after is read directly from the response's Retry-After header
    (seconds) -- the API does not embed it in the JSON body.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None = None,
        response_status: int | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message, response_status=response_status, response_body=response_body)
        self.retry_after = retry_after


class PyvarComputeError(PyvarError):
    """A VaR job (POST /var/compute -> GET /var/result/{task_id}) reached
    status="failure". Not an HTTP-level error -- the submit/poll calls
    themselves returned 200/202 throughout; the compute job itself failed
    server-side (schemas/var.py's JobResultResponse.error carries why).
    """

    def __init__(self, message: str, *, task_id: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id
        self.detail = detail


class PyvarTimeoutError(PyvarError):
    """A VaR job never reached a terminal status within Client.var's
    configured poll timeout. Not the same as an HTTP timeout (httpx raises
    its own exception for that, unwrapped) -- this means the server kept
    responding "pending"/"started" past how long the caller was willing to
    wait.
    """

    def __init__(self, message: str, *, task_id: str) -> None:
        super().__init__(message)
        self.task_id = task_id
