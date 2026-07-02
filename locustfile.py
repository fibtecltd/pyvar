"""
locustfile.py — pyvar.com dev-environment load test (P5b).

Target host (pass on the CLI or via --host):
    https://d1mqqddh8gu2qi.cloudfront.net

This file is DESIGNED to be inspected/parsed only in CI (``--list``); the actual
load test is run manually against the live dev CloudFront distribution.

------------------------------------------------------------------------------
Endpoints (see api/routes/var.py + main.py, prefix = /api/v1)
------------------------------------------------------------------------------
    POST /api/v1/var/compute        submit a Monte Carlo VaR job -> 202 {task_id}
    GET  /api/v1/var/result/{id}    poll job status/result
    GET  /api/v1/domains            catalogue browsing (domain listing)

------------------------------------------------------------------------------
Auth / edge headers
------------------------------------------------------------------------------
    Authorization: Bearer <PYVAR_TEST_JWT>      free-tier test JWT from env
    X-Origin-Verify: <PYVAR_ORIGIN_VERIFY>      CloudFront->ALB shared secret

The X-Origin-Verify header is the WAF/edge shared secret that proves the request
came through CloudFront; it is attached to EVERY request (including the
unauthenticated probe, which must still reach the origin to get a real 401).

------------------------------------------------------------------------------
User classes / weights
------------------------------------------------------------------------------
    70%  ComputeFlowUser        submit (n_simulations=10000) + poll to completion
    20%  CatalogueBrowseUser    GET /api/v1/domains
    10%  CachedResultUser       GET /api/v1/var/result/{OLD_TASK_ID}
     5%  UnauthenticatedUser    POST compute WITHOUT auth -> assert 401
    (val) FreeTierCapUser       POST compute with oversized n_simulations -> 422

------------------------------------------------------------------------------
Run config
------------------------------------------------------------------------------
    10 concurrent users, 10-minute ramp-up.
        locust -f locustfile.py \\
               --host https://d1mqqddh8gu2qi.cloudfront.net \\
               --users 10 --spawn-rate 0.0167 --run-time 15m --headless
    (spawn-rate 1 user / 60s => 10 users spawned over 10 minutes)

------------------------------------------------------------------------------
Performance target
------------------------------------------------------------------------------
    p95 END-TO-END latency for the compute flow (submit -> result ready) < 15s.
    This is checked programmatically in ComputeFlowUser.on_stop() (see below).

------------------------------------------------------------------------------
NOTE on the 422 validation case (schema vs. tier cap):
    api/routes/var.py enforces the per-tier simulation cap with HTTP 403, while
    schemas/var.py bounds n_simulations to [1_000, 1_000_000] and raises 422 on
    violation. The task asks a free-tier JWT to submit "n_simulations > 10000"
    and assert 422. A value just above 10_000 is BELOW both the free cap
    (100_000) and the schema max (1_000_000), so it would return 202 — not 422.
    To produce a deterministic 422 we submit a value ABOVE the schema maximum
    (n_simulations = 1_000_001). This exercises input-validation hardening
    exactly as intended. (A separate case could assert 403 for 100_001 sims.)
------------------------------------------------------------------------------
"""

from __future__ import annotations

import os
import time
import uuid

from locust import HttpUser, between, events, task

# ── Configuration from environment ──────────────────────────────────────────

HOST = "https://d1mqqddh8gu2qi.cloudfront.net"
API_PREFIX = "/api/v1"

JWT = os.environ.get("PYVAR_TEST_JWT", "")
ORIGIN_VERIFY = os.environ.get("PYVAR_ORIGIN_VERIFY", "")

# An OLD/known task id used by the cached-retrieval user class. Overridable via
# env so the test can point at a task that is guaranteed to exist in the backend.
OLD_TASK_ID = os.environ.get("PYVAR_OLD_TASK_ID", "00000000-0000-0000-0000-000000000000")

# End-to-end SLA for the compute flow.
P95_TARGET_SECONDS = 15.0

# Client-side polling budget for a single compute job (seconds).
POLL_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.5

# ── Shared header helpers ────────────────────────────────────────────────────


def _auth_headers() -> dict[str, str]:
    """Headers for an authenticated request through the CloudFront edge."""
    return {
        "Authorization": f"Bearer {JWT}",
        "X-Origin-Verify": ORIGIN_VERIFY,
        "Content-Type": "application/json",
    }


def _edge_headers() -> dict[str, str]:
    """Edge headers WITHOUT auth (used to probe the 401 path)."""
    return {
        "X-Origin-Verify": ORIGIN_VERIFY,
        "Content-Type": "application/json",
    }


def _sample_returns(n: int = 60) -> list[float]:
    """A small, deterministic, finite returns series (>= 30, <= 10_000)."""
    # Simple alternating small returns — schema only requires finite values.
    return [0.001 if i % 2 == 0 else -0.0012 for i in range(n)]


def _var_payload(n_simulations: int) -> dict:
    """Build a valid-shaped VaRRequest body with a given simulation count."""
    return {
        "portfolio_value": 1_000_000.0,
        "returns": _sample_returns(),
        "confidence_level": 0.99,
        "horizon_days": 1,
        "n_simulations": n_simulations,
        "seed": 42,
    }


# ── Global end-to-end latency accounting for the compute flow ────────────────

_compute_e2e_latencies: list[float] = []


def _record_e2e(latency_seconds: float) -> None:
    _compute_e2e_latencies.append(latency_seconds)


@events.quitting.add_listener
def _assert_p95_target(environment, **_kwargs) -> None:
    """
    On shutdown, compute the p95 end-to-end latency of the compute flow and
    fail the run (non-zero exit) if it exceeds the 15s SLA.
    """
    if not _compute_e2e_latencies:
        return
    ordered = sorted(_compute_e2e_latencies)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    p95 = ordered[idx]
    print(
        f"[P5b] compute-flow end-to-end p95 = {p95:.2f}s "
        f"(target < {P95_TARGET_SECONDS:.0f}s, n={len(ordered)})"
    )
    if p95 > P95_TARGET_SECONDS:
        environment.process_exit_code = 1


# ── 70%: full compute flow (submit + poll to completion) ─────────────────────


class ComputeFlowUser(HttpUser):
    """
    Submits a 10k-path VaR job and polls until it completes, recording the
    end-to-end latency (submit -> result ready) against the 15s p95 target.
    """

    weight = 70
    host = HOST
    wait_time = between(1, 3)

    @task
    def compute_var(self) -> None:
        start = time.perf_counter()

        with self.client.post(
            f"{API_PREFIX}/var/compute",
            json=_var_payload(n_simulations=10_000),
            headers=_auth_headers(),
            name="POST /var/compute",
            catch_response=True,
        ) as resp:
            if resp.status_code != 202:
                resp.failure(f"expected 202, got {resp.status_code}: {resp.text[:200]}")
                return
            try:
                task_id = resp.json()["task_id"]
            except (ValueError, KeyError) as exc:
                resp.failure(f"no task_id in submit response: {exc}")
                return
            resp.success()

        # Poll until success/failure or timeout.
        deadline = time.perf_counter() + POLL_TIMEOUT_SECONDS
        final_status: str | None = None
        while time.perf_counter() < deadline:
            with self.client.get(
                f"{API_PREFIX}/var/result/{task_id}",
                headers=_auth_headers(),
                name="GET /var/result/{id} (poll)",
                catch_response=True,
            ) as poll:
                if poll.status_code != 200:
                    poll.failure(f"expected 200, got {poll.status_code}")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                try:
                    status_value = poll.json().get("status")
                except ValueError as exc:
                    poll.failure(f"bad JSON on poll: {exc}")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                poll.success()

            if status_value in ("success", "failure"):
                final_status = status_value
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        elapsed = time.perf_counter() - start
        _record_e2e(elapsed)

        if final_status != "success":
            events.request.fire(
                request_type="FLOW",
                name="compute-flow end-to-end",
                response_time=elapsed * 1000.0,
                response_length=0,
                exception=RuntimeError(
                    f"compute flow did not succeed in {POLL_TIMEOUT_SECONDS}s "
                    f"(last status={final_status})"
                ),
            )
        else:
            events.request.fire(
                request_type="FLOW",
                name="compute-flow end-to-end",
                response_time=elapsed * 1000.0,
                response_length=0,
                exception=None,
            )


# ── 20%: catalogue browsing ──────────────────────────────────────────────────


class CatalogueBrowseUser(HttpUser):
    """Browses the domain catalogue — a cheap, read-only GET."""

    weight = 20
    host = HOST
    wait_time = between(1, 4)

    @task
    def list_domains(self) -> None:
        with self.client.get(
            f"{API_PREFIX}/domains",
            headers=_auth_headers(),
            name="GET /domains",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"expected 200, got {resp.status_code}")


# ── 10%: cached result retrieval ─────────────────────────────────────────────


class CachedResultUser(HttpUser):
    """Fetches a known/old task id to exercise the cached-retrieval path."""

    weight = 10
    host = HOST
    wait_time = between(1, 4)

    @task
    def fetch_old_result(self) -> None:
        with self.client.get(
            f"{API_PREFIX}/var/result/{OLD_TASK_ID}",
            headers=_auth_headers(),
            name="GET /var/result/{old_id} (cached)",
            catch_response=True,
        ) as resp:
            # A missing job still returns 200 with status=pending; only 5xx or
            # auth errors are failures here.
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"expected 200, got {resp.status_code}")


# ── 5%: unauthenticated probe — MUST be rejected with 401 ────────────────────


class UnauthenticatedUser(HttpUser):
    """Submits to the compute endpoint with NO auth; asserts a 401 response."""

    weight = 5
    host = HOST
    wait_time = between(2, 5)

    @task
    def compute_without_auth(self) -> None:
        with self.client.post(
            f"{API_PREFIX}/var/compute",
            json=_var_payload(n_simulations=10_000),
            headers=_edge_headers(),  # no Authorization header
            name="POST /var/compute (no auth -> 401)",
            catch_response=True,
        ) as resp:
            if resp.status_code in (401, 403):
                # 401 is the contract; 403 accepted if the edge blocks first.
                resp.success()
            else:
                resp.failure(f"expected 401 for unauthenticated compute, got {resp.status_code}")


# ── Validation: oversized n_simulations -> MUST be rejected with 422 ─────────


class FreeTierCapUser(HttpUser):
    """
    Submits an oversized simulation count with a free-tier JWT and asserts 422.

    See the module docstring: a value just above 10_000 is accepted (202), so we
    send a value ABOVE the schema maximum (1_000_001) to deterministically
    trigger Pydantic input validation (HTTP 422).
    """

    weight = 5
    host = HOST
    wait_time = between(2, 5)

    @task
    def oversized_simulation_request(self) -> None:
        with self.client.post(
            f"{API_PREFIX}/var/compute",
            json=_var_payload(n_simulations=1_000_001),
            headers=_auth_headers(),  # free-tier JWT
            name="POST /var/compute (oversized -> 422)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 422:
                resp.success()
            else:
                resp.failure(f"expected 422 for oversized n_simulations, got {resp.status_code}")


# Suppress an unused-import style warning for uuid if a fresh id is ever needed.
_ = uuid
