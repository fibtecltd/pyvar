"""
tasks/var_task.py — Celery task wrapping the Monte Carlo VaR engine

Reasoning:
- Monte Carlo with 100k paths takes 1-10 seconds depending on CPU.
  Running this inline in a FastAPI handler would block the event loop
  and hit HTTP timeout limits for slow clients.
- Celery offloads computation to worker processes. The API handler
  returns a task_id immediately; the client polls for the result.
- bind=True gives the task access to self.request.id (the task UUID)
  so it can store results keyed by task_id without passing IDs around.
- task_track_started=True transitions state to STARTED as soon as the
  worker picks up the job — gives the frontend a "running" state to show.
- Errors are caught and re-raised as Celery Failure so the result backend
  stores the exception rather than leaving the task in PENDING forever.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, cast

from celery import Celery, Task
from sqlalchemy import CursorResult, update

from config import get_settings
from storage.models import VaRJob
from storage.session import get_sync_sessionmaker

cfg = get_settings()
logger = logging.getLogger(__name__)

# ── Interim job metrics (Path B) ───────────────────────────────────────────────
# CloudWatch is the INTERIM destination for job success/failure counts so P6 does
# not ship with zero observability. The proper Grafana Cloud / Amazon Managed
# Prometheus pipeline is a separate task before P9 launch — this is not the final
# architecture. Metrics land in the "pyvar" namespace, which worker_role's
# cloudwatch:PutMetricData grant is already scoped to (compute_stack.py).
_JOB_METRIC_NAMESPACE = "pyvar"
_cw_client = None  # lazily created; creation needs a region (set on workers via env)


def _emit_job_metric(metric_name: str, dimensions: list[dict[str, str]]) -> None:
    """Emit a single-count CloudWatch metric for job accounting.

    Best-effort and fully isolated: a CloudWatch outage or missing credentials
    (e.g. local docker-compose dev) must NEVER fail or slow a VaR computation, so
    every error — including lazy client creation — is swallowed with a warning.

    Args:
        metric_name: Metric name within the pyvar namespace (e.g. "JobCount").
        dimensions: CloudWatch dimension list, e.g. [{"Name": "TaskName", ...}].
    """
    global _cw_client
    try:
        if _cw_client is None:
            import boto3

            _cw_client = boto3.client("cloudwatch")
        _cw_client.put_metric_data(
            Namespace=_JOB_METRIC_NAMESPACE,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Dimensions": dimensions,
                    "Value": 1.0,
                    "Unit": "Count",
                }
            ],
        )
    except Exception:  # noqa: BLE001 — metric emission must never break the task
        logger.warning(
            "Failed to emit CloudWatch job metric",
            extra={"metric": metric_name},
        )


# ── var_jobs audit completion write (Path B, issue #118) ───────────────────────
# The submission-side INSERT (api/routes/var.py) already created a `pending`
# var_jobs row for this task_id before dispatch — see that module's docstring
# for why that write is fail-loud. This is the other half: an UPDATE, by
# task_id, to the row's terminal state. It is intentionally best-effort (unlike
# the submission write): by the time this runs the original HTTP request has
# already returned 202, so there is no caller left to fail loud to, and raising
# here would only make the Celery task itself fail/retry over a pure
# persistence problem. A failed update leaves the row parked at "pending"
# rather than losing it, which is why the submission write existing is what
# makes this safe to treat as best-effort. Logged loudly (structlog captures
# this via the root logger config in observability/setup.py; Sentry is wired
# into the worker too) so a stuck row is visible, not silent.
#
# Uses the SYNCHRONOUS sessionmaker (storage/session.py::get_sync_sessionmaker)
# — this task runs in a plain sync Celery worker process, not an event loop.
#
# UPDATE-only, never a second INSERT on the normal path: task_id is unique and
# Celery preserves self.request.id across self.retry() calls, so every retry
# of one job targets the same row — no duplicate audit rows are possible by
# construction. The INSERT fallback below only fires if the row is missing
# (defensive; should not happen once the submission write path is live).


def _write_terminal_audit(
    task_id: str,
    status: str,
    *,
    duration_ms: int,
    result: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    """Best-effort UPDATE of the var_jobs row for task_id to its terminal state.

    Called exactly once per job — on success, or on failure once retries are
    exhausted — never on a mid-retry attempt (a transient retry is not a
    terminal outcome and must not flap the audit status).

    Args:
        task_id: Celery task id — the var_jobs dedup key.
        status: Terminal status to record ("success" or "failure").
        duration_ms: Wall-clock compute time (engine call only, not queue
            wait) — timed by the caller so this stays a single UPDATE with no
            need to read the row's created_at back first.
        result: VaRResult dict (success only) — scalar fields are persisted,
            loss_dist is not (see VaRJob's inline-scalars-only design).
        error_message: Exception string (failure only).
    """
    values: dict[str, Any] = {
        "status": status,
        "completed_at": datetime.now(timezone.utc),
        "duration_ms": duration_ms,
        "error_message": error_message,
    }
    if result is not None:
        values.update(
            var_pct=result["var_pct"],
            var_abs=result["var_abs"],
            cvar_pct=result["cvar_pct"],
            cvar_abs=result["cvar_abs"],
        )

    try:
        with get_sync_sessionmaker()() as session:
            updated = cast(
                CursorResult,
                session.execute(update(VaRJob).where(VaRJob.task_id == task_id).values(**values)),
            )
            if updated.rowcount == 0:
                # No submission row found (should not happen on the normal
                # path) — insert one rather than silently losing the record.
                # user_id is unknown here (the task payload carries compute
                # inputs only, not the caller identity — see the module note
                # on why tier isn't propagated either); "unknown" flags this
                # as the defensive fallback path, not a real audit gap.
                session.add(VaRJob(task_id=task_id, user_id="unknown", **values))
            session.commit()
    except Exception:  # noqa: BLE001 — audit write must never crash the worker
        logger.error(
            "var_jobs completion audit write failed — row left at prior status",
            extra={"task_id": task_id, "status": status},
            exc_info=True,
        )


# ── Celery app ────────────────────────────────────────────────────────────────
# Broker and backend are read from environment variables so ECS task definitions
# can inject the correct SQS/ElastiCache endpoints without changing code.
# Falls back to cfg.redis_url (localhost:6379) for local dev.

celery_app = Celery(
    "pyvar",
    broker=os.environ.get("CELERY_BROKER_URL", cfg.redis_url),
    backend=os.environ.get("CELERY_RESULT_BACKEND", cfg.redis_url),
)

celery_app.conf.update(
    task_default_queue=os.environ.get("SQS_QUEUE_NAME", "celery"),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_extended=True,  # stores task args/kwargs in result
    result_expires=cfg.celery_result_ttl,
    worker_prefetch_multiplier=1,  # one task at a time per worker (CPU-bound)
    task_acks_late=True,  # only ack after task completes (safe retry)
    worker_max_tasks_per_child=100,  # recycle workers to prevent memory leak
)


# ── Task ──────────────────────────────────────────────────────────────────────


@celery_app.task(
    bind=True,
    name="pyvar.tasks.compute_var",
    max_retries=2,
    default_retry_delay=5,
)
def compute_var_task(self: Task, payload: dict) -> dict:
    """
    Celery task: receives a validated VaRRequest payload dict,
    runs the Monte Carlo engine, and returns a VaRResult dict.

    The result is stored in Redis by the Celery result backend.
    Clients retrieve it via GET /var/result/{task_id}.

    Args:
        payload: dict matching VaRRequest schema fields.

    Returns:
        dict matching VaRResult schema fields.
    """
    import numpy as np

    from engine.montecarlo import run_monte_carlo_var

    task_id = self.request.id
    logger.info("Starting VaR computation", extra={"task_id": task_id})

    # VaRRequest carries no Domain field and tier lives only in the API-layer JWT
    # (not propagated into the task payload), so we dimension by TaskName only.
    # See the PR notes for why Domain/Tier are omitted.
    job_dimensions = [{"Name": "TaskName", "Value": self.name}]

    started = time.perf_counter()

    try:
        returns = np.array(payload["returns"], dtype=np.float64)

        result = run_monte_carlo_var(
            returns=returns,
            portfolio_value=payload["portfolio_value"],
            confidence_level=payload.get("confidence_level", 0.99),
            horizon_days=payload.get("horizon_days", 1),
            n_simulations=payload.get("n_simulations", 100_000),
            seed=payload.get("seed", 42),
        )

        logger.info(
            "VaR computation complete",
            extra={
                "task_id": task_id,
                "var_pct": result["var_pct"],
                "n_sims": result["n_simulations"],
            },
        )
        # Completed successfully — count the job.
        _emit_job_metric("JobCount", job_dimensions)
        # var_jobs is the compliance record of the job's terminal outcome —
        # write it once, here, on the one path that actually succeeds.
        _write_terminal_audit(
            task_id,
            "success",
            duration_ms=int((time.perf_counter() - started) * 1000),
            result=result,
        )
        return result

    except Exception as exc:
        logger.exception("VaR computation failed", extra={"task_id": task_id})
        # Count the job (every outcome) and record the error. NOTE: this runs on
        # each failed attempt, so with retries a single job can emit more than one
        # JobCount/JobErrors (i.e. these count attempts, not distinct jobs). Kept
        # simple deliberately; terminal-only counting is a possible refinement.
        _emit_job_metric("JobCount", job_dimensions)
        _emit_job_metric("JobErrors", job_dimensions)

        retries_exhausted = self.request.retries >= self.max_retries
        if retries_exhausted:
            # Terminal failure — unlike the CloudWatch counters above, the
            # audit record must reflect the job's final state exactly once,
            # not flap on every transient retry attempt.
            _write_terminal_audit(
                task_id,
                "failure",
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_message=str(exc),
            )
            raise exc
        raise self.retry(exc=exc)
