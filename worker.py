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
  concurrency=1 may be appropriate on smaller machines.
- Sentry and structlog are initialised here separately from the FastAPI app
  so worker errors are also captured and logged.
"""

from observability.setup import setup_logging, setup_sentry
from tasks.var_task import celery_app  # noqa: F401 — imports registers all tasks

setup_logging()
setup_sentry()

if __name__ == "__main__":
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=info",
            "--concurrency=4",
            "--queues=default",
        ]
    )
