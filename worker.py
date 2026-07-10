"""
worker.py — Celery worker entry point

Run with:
    python worker.py
    # or directly via celery CLI:
    celery -A worker.celery_app worker --loglevel=info --concurrency=4

Reasoning:
- worker_prefetch_multiplier=1 ensures each worker takes one task at a time.
  Monte Carlo is CPU-bound and long-running — prefetching multiple tasks
  would cause head-of-line blocking.
- concurrency should match the number of physical CPU cores. Numba's
  parallel=True already uses all cores within a single task, so
  concurrency=1 may be appropriate on smaller machines. Defaults to
  os.cpu_count() so it follows worker_instance_type automatically instead
  of needing to be hardcoded per instance family; CELERY_CONCURRENCY in
  celery.env overrides it if ever needed.
- pool reads CELERY_WORKER_POOL from celery.env (falls back to 'prefork')
  so the env var actually takes effect instead of being silently unused.
- Sentry and structlog are initialised here separately from the FastAPI app
  so worker errors are also captured and logged.
"""

import os

from observability.setup import setup_logging, setup_sentry
from tasks.var_task import celery_app  # noqa: F401 — imports registers all tasks

setup_logging()
setup_sentry()

if __name__ == "__main__":
    concurrency = os.environ.get("CELERY_CONCURRENCY") or str(os.cpu_count() or 4)
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            f"--concurrency={concurrency}",
            f"--queues={os.environ.get('SQS_QUEUE_NAME', 'celery')}",
            f"--pool={os.environ.get('CELERY_WORKER_POOL', 'prefork')}",
        ]
    )
