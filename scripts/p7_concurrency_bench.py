"""scripts/p7_concurrency_bench.py — P7 Task 3 rerun: Celery concurrency
benchmark at a load where compute, not submission latency, dominates.

CORRECTNESS NOTE (Tier 3, independent strategic assessment, 2026-08):
the original P7 Task 3 benchmark (docs/p7-celery-concurrency-results.md)
submitted a batch of only 10 jobs SEQUENTIALLY (one `curl` after another in
a shell loop) before polling for completion. At that batch size, the
sequential submission loop itself (network round-trip + TLS handshake +
auth per request) took ~1.2-1.4s of a ~4.2-5.8s total — the doc's own
caveat says as much. That means the measurement was dominated by how long
it takes a shell loop to fire 10 HTTP requests one after another, not by
how the Celery/worker pipeline actually behaves under load. It supports no
speed or concurrency-tuning claim at all, by its own admission.

Two changes fix this, both necessary:

1. Submit the whole batch CONCURRENTLY (a thread pool firing all requests
   at once), not sequentially. This decouples "time to get N jobs into the
   queue" from N — with concurrent submission, submit wall-clock stays
   roughly flat regardless of batch size, instead of scaling linearly with
   it the way a sequential loop does.
2. Use a batch large enough that total processing time is dominated by the
   queue actually draining at the configured concurrency, not by one-time
   connection/auth overhead. Default here is 50 jobs (5x the original 10) —
   configurable via --n-jobs for an even larger run.

This script does NOT eyeball the result the way the original doc's prose
did ("total wall-clock is dominated by SQS/HTTP round-trip latency" as an
assertion). It measures submit_wallclock and total_wallclock separately and
prints the submission share explicitly, so whichever concurrency levels get
run, the report can state — not assume — whether the run was actually
compute/queue-bound rather than submission-bound. If the submission share
is still large at the chosen batch size, that's a signal to re-run with
--n-jobs raised further, not a result to publish as-is.

PREREQUISITES: AWS creds (Secrets Manager read for the JWT signing secret),
the pyvar-{env}-workers ASG must already be forced up with the desired
CELERY_CONCURRENCY applied (see scripts/force-worker-instance.sh and the
SSM steps documented in docs/p7-celery-concurrency-results.md's Method
section, which this script does not replace).

Usage:
    python3 scripts/p7_concurrency_bench.py --concurrency-label 2 --n-jobs 50

Prints one CSV-ish line per run to stdout for later collation into a
results doc; does not itself touch the ASG or SSM.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

RETURNS = [
    -0.012, 0.008, -0.005, 0.015, -0.003, 0.011, -0.007, 0.004, -0.009, 0.013,
    -0.002, 0.006, -0.014, 0.009, -0.001, 0.007, -0.011, 0.003, -0.006, 0.012,
    -0.004, 0.008, -0.010, 0.005, -0.008, 0.014, -0.003, 0.009, -0.006, 0.011,
]  # fmt: skip


def _b64url(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def mint_jwt(env_name: str, region: str) -> str:
    """Mints a 24h service JWT the same way scripts/chaos_test.sh does —
    'internal' tier, so --n-simulations can go up to the internal/enterprise
    cap (500,000) rather than pro's 100,000 (see api/middleware/auth.py)."""
    secret = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            f"pyvar/{env_name}/jwt-secret",
            "--region",
            region,
            "--query",
            "SecretString",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")))
    payload = _b64url(
        json.dumps(
            {"sub": "p7-concurrency-bench", "tier": "internal", "exp": int(time.time()) + 86400},
            separators=(",", ":"),
        )
    )
    sig = _b64url(
        hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{sig}"


def _request(url: str, headers: dict[str, str], data: bytes | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310  # fixed benchmark endpoint
        return json.loads(resp.read())


def submit_job(endpoint: str, headers: dict[str, str], n_simulations: int) -> str:
    body = json.dumps(
        {
            "n_simulations": n_simulations,
            "confidence_level": 0.99,
            "horizon_days": 1,
            "portfolio_value": 1_000_000,
            "returns": RETURNS,
        }
    ).encode()
    resp = _request(f"{endpoint}/api/v1/var/compute", headers, body)
    task_id = resp.get("task_id")
    if not task_id:
        raise RuntimeError(f"no task_id in response: {resp!r}")
    return task_id


def poll_until_done(endpoint: str, headers: dict[str, str], task_id: str, timeout_s: float) -> str:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = _request(f"{endpoint}/api/v1/var/result/{task_id}", headers)
        status = resp.get("status", "unknown")
        if status in ("success", "failure"):
            return status
        time.sleep(1.0)
    return "timeout"


def run_batch(endpoint: str, headers: dict[str, str], n_jobs: int, n_simulations: int) -> dict:
    t0 = time.monotonic()
    task_ids: list[str] = []
    with ThreadPoolExecutor(max_workers=n_jobs) as pool:
        futures = [pool.submit(submit_job, endpoint, headers, n_simulations) for _ in range(n_jobs)]
        for fut in as_completed(futures):
            task_ids.append(fut.result())
    t_submit_done = time.monotonic()
    submit_wallclock = t_submit_done - t0

    statuses: list[str] = []
    with ThreadPoolExecutor(max_workers=n_jobs) as pool:
        futures = [pool.submit(poll_until_done, endpoint, headers, tid, 600.0) for tid in task_ids]
        for fut in as_completed(futures):
            statuses.append(fut.result())
    t_all_done = time.monotonic()
    total_wallclock = t_all_done - t0

    n_success = sum(1 for s in statuses if s == "success")
    n_failed = sum(1 for s in statuses if s == "failure")
    n_timeout = sum(1 for s in statuses if s == "timeout")

    return {
        "n_jobs": n_jobs,
        "n_simulations": n_simulations,
        "submit_wallclock_s": round(submit_wallclock, 3),
        "total_wallclock_s": round(total_wallclock, 3),
        "submit_share_pct": (
            round(100 * submit_wallclock / total_wallclock, 1)
            if total_wallclock > 0
            else float("nan")
        ),
        "n_success": n_success,
        "n_failed": n_failed,
        "n_timeout": n_timeout,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default="dev")
    parser.add_argument("--region", default="eu-west-1")
    parser.add_argument("--endpoint", default="https://d1mqqddh8gu2qi.cloudfront.net")
    parser.add_argument("--n-jobs", type=int, default=50)
    parser.add_argument("--n-simulations", type=int, default=100_000)
    parser.add_argument(
        "--concurrency-label",
        default="unspecified",
        help="CELERY_CONCURRENCY value currently applied on the worker (for the report only — "
        "this script does not set it; see docs/p7-celery-concurrency-results.md's Method).",
    )
    args = parser.parse_args()

    jwt = mint_jwt(args.env, args.region)
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json",
    }

    print(
        f"# concurrency={args.concurrency_label} n_jobs={args.n_jobs} "
        f"n_simulations={args.n_simulations} endpoint={args.endpoint}",
        file=sys.stderr,
    )
    result = run_batch(args.endpoint, headers, args.n_jobs, args.n_simulations)
    result["concurrency_label"] = args.concurrency_label
    print(json.dumps(result))

    if result["n_failed"] or result["n_timeout"]:
        print(
            f"WARNING: {result['n_failed']} failed, {result['n_timeout']} timed out "
            "— do not use this run's timings, investigate first",
            file=sys.stderr,
        )
    if result["submit_share_pct"] > 15.0:
        print(
            f"WARNING: submission took {result['submit_share_pct']}% of total wall-clock — "
            "still submission-bound at this batch size, re-run with a larger --n-jobs before "
            "treating this as a compute/queue-bound measurement",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
