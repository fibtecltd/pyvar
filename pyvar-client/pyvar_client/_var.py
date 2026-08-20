"""pyvar_client._var — the one hand-written (not generated) domain wrapper.

Reasoning:
- POST /var/compute is the single function, of 385, that's async: it
  returns a task_id immediately (schemas/var.py's JobResponse) instead of
  a result, and the caller polls GET /var/result/{task_id}
  (JobResultResponse) until status is "success" or "failure". Every other
  domain function is synchronous request/response -- see the codegen
  module docstring. That asymmetry is exactly why this one function gets
  a hand-written wrapper instead of a generated method: submit/poll/
  compute is a genuinely different call shape, not a mechanical variation
  on the generated pattern.
- Above cfg.s3_result_offload_threshold simulations, the API's own
  response strips loss_dist and populates presigned_url instead (#130) --
  compute() returns exactly what the API returned, loss_dist empty and
  presigned_url set in that case, rather than silently fetching the S3
  object itself. Fetching a presigned URL is a plain httpx.get the caller
  can do themselves if they want the raw distribution; this client
  doesn't guess at that on their behalf.
- submit() is NOT retried automatically by _transport (idempotent=False)
  -- a blind retry on submit risks double-submitting a real compute job,
  since the API has no idempotency-key mechanism. poll() IS retried (it's
  a read). compute() is the common case: submit once, poll until done.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from pyvar_client.exceptions import PyvarComputeError, PyvarTimeoutError

if TYPE_CHECKING:
    from pyvar_client._client import Client

_DEFAULT_POLL_INTERVAL_SECONDS = 2.0
_DEFAULT_POLL_TIMEOUT_SECONDS = 300.0


class VarNamespace:
    """`client.var` -- the one async-job domain, wrapped separately from
    the generated per-domain namespaces (see module docstring).
    """

    def __init__(self, client: "Client") -> None:
        self._client = client

    def submit(
        self,
        *,
        portfolio_value: float,
        returns: list[float],
        confidence_level: float = 0.99,
        horizon_days: int = 1,
        n_simulations: int | None = None,
        seed: int | None = 42,
    ) -> str:
        """POST /var/compute. Returns the task_id immediately -- does not wait.

        Field constraints mirror schemas/var.py's VaRRequest exactly:
        portfolio_value > 0; 30 <= len(returns) <= 10_000; 0.90 <=
        confidence_level <= 0.9999 (Basel III standard 0.99, FRTB ES
        0.975, internal-limit-monitoring floor 0.95); 1 <= horizon_days <=
        250; n_simulations >= 1_000 (omit for the tier's default).
        """
        body: dict[str, Any] = {
            "portfolio_value": portfolio_value,
            "returns": returns,
            "confidence_level": confidence_level,
            "horizon_days": horizon_days,
            "seed": seed,
        }
        if n_simulations is not None:
            body["n_simulations"] = n_simulations

        response = self._client._request(
            "POST", "/api/v1/var/compute", json_body=body, idempotent=False
        )
        return str(response["task_id"])

    def poll(self, task_id: str) -> dict[str, Any]:
        """GET /var/result/{task_id} once. Returns the raw JobResultResponse
        dict (status/result/error) -- does not block or retry on "pending".
        Use compute() for submit-and-wait; use this directly for your own
        polling loop.
        """
        return self._client._request("GET", f"/api/v1/var/result/{task_id}")

    def compute(
        self,
        *,
        portfolio_value: float,
        returns: list[float],
        confidence_level: float = 0.99,
        horizon_days: int = 1,
        n_simulations: int | None = None,
        seed: int | None = 42,
        poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
        poll_timeout_seconds: float = _DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """submit() + poll() until a terminal status, blocking.

        Returns:
            The VaRResult dict (schemas/var.py) on success.

        Raises:
            PyvarComputeError: the job reached status="failure" server-side.
            PyvarTimeoutError: still "pending"/"started" after
                poll_timeout_seconds -- the job may still complete later;
                this only means the caller stopped waiting. Use poll()
                with the same task_id to check again.
        """
        task_id = self.submit(
            portfolio_value=portfolio_value,
            returns=returns,
            confidence_level=confidence_level,
            horizon_days=horizon_days,
            n_simulations=n_simulations,
            seed=seed,
        )

        deadline = time.monotonic() + poll_timeout_seconds
        while time.monotonic() < deadline:
            result = self.poll(task_id)
            status = result.get("status")
            if status == "success":
                return dict(result["result"])
            if status == "failure":
                raise PyvarComputeError(
                    "VaR computation failed.",
                    task_id=task_id,
                    detail=result.get("error"),
                )
            time.sleep(poll_interval_seconds)

        raise PyvarTimeoutError(
            f"VaR job {task_id} did not complete within {poll_timeout_seconds}s.",
            task_id=task_id,
        )
