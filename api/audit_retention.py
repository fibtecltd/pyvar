"""api/audit_retention.py — the six-year clean-up of the audit tables (docs/plan-education-tier.md section 12).

Reasoning:
- The privacy policy says the records of computations (`var_jobs`) and of tier changes (`billing_events`) are
  kept six years and then deleted. CLAUDE.md 3.3 makes those two tables append-only AUDIT LOGS and says that only
  a clean-up job may delete rows, and only rows older than six years. This module is that job; the owner runs it
  through scripts/audit_cleanup.py and the /internal/admin/audit/cleanup route (no timer: the first rows reach six
  years in late 2032, and a deletion that nobody watches is the wrong default for an audit log).
- What it deletes: rows of `var_jobs` and `billing_events` whose `created_at` is older than six years. Nothing
  else: not `api_usage` (its own, shorter rules), not `users`, not `api_keys` (never deleted, CLAUDE.md 3.3).
- The six years are a constant, not an argument. The route and the script cannot be asked for a shorter period, so
  a typo cannot delete a record the policy promises to keep. Changing the period means changing this constant,
  the privacy page (tests/test_audit_cleanup.py pins the two together) and CLAUDE.md 3.3.
- A dry run counts. With `apply`, rows go in batches of at most `BATCH_ROWS`, at most `max_rows` per table per
  call, each batch committed on its own, so a long clean-up never holds one huge transaction and can be repeated
  until `remaining` is 0. The S3 result files need no step here: the results bucket's own lifecycle rule expires
  them after at most 365 days (pyvar-cdk/stacks/data_stack.py), long before the row that names them goes.
- Nothing about a person appears in the answer or in a log line: counts, the cutoff, the operator's label.
- Cost: neither table has an index on `created_at` alone (var_jobs has (user_id, created_at), CLAUDE.md 3.3), so each
  count and each batch scans its table. That is fine for a job run once a year; if it ever is not, the fix is an Alembic
  index, not a change here.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models import BillingEvent, VaRJob

logger = structlog.get_logger()

# [REGULATORY-ADJACENT] the retention promised on the privacy page ("kept for six years"), the Limitation Act 1980
# s.5 period the owner chose. Not an argument anywhere: see the module docstring.
AUDIT_RETENTION_YEARS = 6
BATCH_ROWS = 1000
DEFAULT_MAX_ROWS = 20000
MAX_ROWS_LIMIT = 200000

# The only tables this job may touch, by the name the answer uses.
TABLES = {"var_jobs": VaRJob, "billing_events": BillingEvent}


def retention_cutoff(now: datetime | None = None) -> datetime:
    """The instant `AUDIT_RETENTION_YEARS` before `now`; 29 February maps to 28 February in a common year."""
    moment = now or datetime.now(timezone.utc)
    year = moment.year - AUDIT_RETENTION_YEARS
    day = min(moment.day, calendar.monthrange(year, moment.month)[1])
    return moment.replace(year=year, day=day)


@dataclass(frozen=True)
class TableCleanup:
    """Per table: rows older than the cutoff when the call began, rows deleted by it, rows still older."""

    found: int
    deleted: int
    remaining: int


@dataclass(frozen=True)
class CleanupResult:
    cutoff: datetime
    tables: dict[str, TableCleanup]
    applied: bool


async def _count_older(
    session: AsyncSession, model: type[VaRJob] | type[BillingEvent], cutoff: datetime
) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(model).where(model.created_at < cutoff)
            )
        ).scalar_one()
    )


async def _delete_batches(
    session: AsyncSession,
    model: type[VaRJob] | type[BillingEvent],
    cutoff: datetime,
    max_rows: int,
) -> int:
    """Delete up to `max_rows` rows older than `cutoff`, oldest first, one committed batch at a time."""
    deleted = 0
    while deleted < max_rows:
        take = min(BATCH_ROWS, max_rows - deleted)
        ids = list(
            (
                await session.execute(
                    select(model.id)
                    .where(model.created_at < cutoff)
                    .order_by(model.created_at, model.id)
                    .limit(take)
                )
            ).scalars()
        )
        if not ids:
            break
        await session.execute(delete(model).where(model.id.in_(ids), model.created_at < cutoff))
        await session.commit()
        deleted += len(ids)
    return deleted


async def cleanup(
    session: AsyncSession,
    *,
    apply: bool = False,
    max_rows: int = DEFAULT_MAX_ROWS,
    now: datetime | None = None,
) -> CleanupResult:
    """Count (or, with `apply`, delete) audit rows older than six years. At most `max_rows` per table per call.

    Raises:
        ValueError: `max_rows` is not between 1 and `MAX_ROWS_LIMIT`.
    """
    if not 1 <= max_rows <= MAX_ROWS_LIMIT:
        raise ValueError(f"max_rows must be between 1 and {MAX_ROWS_LIMIT}")
    cutoff = retention_cutoff(now)
    tables: dict[str, TableCleanup] = {}
    for name, model in TABLES.items():
        found = await _count_older(session, model, cutoff)
        deleted = await _delete_batches(session, model, cutoff, max_rows) if apply else 0
        tables[name] = TableCleanup(found=found, deleted=deleted, remaining=found - deleted)
    if apply:
        logger.warning(
            "audit_cleanup",
            cutoff=cutoff.isoformat(),
            **{f"{name}_deleted": table.deleted for name, table in tables.items()},
            **{f"{name}_remaining": table.remaining for name, table in tables.items()},
        )
    return CleanupResult(cutoff=cutoff, tables=tables, applied=apply)
