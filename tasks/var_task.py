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

from celery import Celery, Task

from config import get_settings

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
        return result

    except Exception as exc:
        logger.exception("VaR computation failed", extra={"task_id": task_id})
        # Count the job (every outcome) and record the error. NOTE: this runs on
        # each failed attempt, so with retries a single job can emit more than one
        # JobCount/JobErrors (i.e. these count attempts, not distinct jobs). Kept
        # simple deliberately; terminal-only counting is a possible refinement.
        _emit_job_metric("JobCount", job_dimensions)
        _emit_job_metric("JobErrors", job_dimensions)
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc
