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
        return result

    except Exception as exc:
        logger.exception("VaR computation failed", extra={"task_id": task_id})
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc
