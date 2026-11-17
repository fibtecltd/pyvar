"""
storage/reconcile.py — close the var_jobs rows that never reached a terminal state (C5).

Reasoning:
- var_jobs is the audit log of every VaR job. The API inserts a row as "pending" and the worker updates it to
  "success" or "failure" when the job ends (tasks/var_task.py). A job that never ends cleanly leaves its row
  "pending" for ever: its worker was lost before the retry rule existed (the W4 drill of 2026-11-14 left seven
  such rows), or, now that a lost worker is retried once, a job that kills its worker twice goes to the
  dead-letter queue, which updates nothing. A row that says "pending" for a job that will never run is a wrong
  statement in an audit log.
- The reconciler marks a row "failure", with a message that says why, once it has been "pending" for longer
  than `var_jobs_pending_timeout_seconds` (an hour by default: far beyond a job's queue wait, retry and run).
  It only touches "pending" rows, so a row the worker has finished is never changed, and rows are never deleted
  (CLAUDE.md 3.3). If the job was only slow and its worker finishes later, the worker's own terminal UPDATE
  (which sets status, completed_at and the results by task_id) overwrites the reconciler's mark: the record
  ends up true either way.
- It runs inside the API (api: main.lifespan), as a background loop in each API task, only in hosted
  environments. That needs no new infrastructure and survives scale-to-zero of the workers; the statement is
  one idempotent UPDATE, so several tasks running it is harmless. A failure is logged and retried at the next
  interval and never stops the API.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import cast

from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from storage.models import VaRJob

logger = logging.getLogger(__name__)

PENDING = "pending"
FAILED = "failure"
RECONCILED_MESSAGE = (
    "No terminal state was recorded within {seconds} s of submission (the worker was lost, the job was "
    "dead-lettered or it never ran); marked as failed by the var_jobs reconciler."
)


async def reconcile_pending_jobs(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    older_than_seconds: int,
    now: datetime | None = None,
) -> int:
    """Mark every var_jobs row still "pending" after `older_than_seconds` as failed.

    Args:
        session_factory: The async session factory (storage.session.get_sessionmaker()).
        older_than_seconds: Age, from created_at, beyond which a pending row counts as lost.
        now: The current time; injectable for tests.

    Returns:
        The number of rows changed.
    """
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(seconds=older_than_seconds)
    async with session_factory() as session:
        result = cast(
            CursorResult,
            await session.execute(
                update(VaRJob)
                .where(VaRJob.status == PENDING, VaRJob.created_at < cutoff)
                .values(
                    status=FAILED,
                    completed_at=moment,
                    error_message=RECONCILED_MESSAGE.format(seconds=older_than_seconds),
                )
            ),
        )
        await session.commit()
    return int(result.rowcount)


async def run_reconciler(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: int,
    older_than_seconds: int,
    sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
) -> None:
    """Reconcile every `interval_seconds` until cancelled; an error never ends the loop.

    The first run waits a random 30 to 90 seconds so that the API tasks of a deploy do not all start at once
    and the application has finished starting.
    """
    await sleep(
        random.uniform(30, 90)
    )  # noqa: S311  # nosec B311 - spreading start times, not security
    while True:
        try:
            changed = await reconcile_pending_jobs(
                session_factory, older_than_seconds=older_than_seconds
            )
            if changed:
                logger.warning(
                    "var_jobs reconciler marked rows as failed",
                    extra={"rows": changed, "older_than_seconds": older_than_seconds},
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — the loop must survive a database outage
            logger.error("var_jobs reconciler run failed", exc_info=True)
        await sleep(interval_seconds)
