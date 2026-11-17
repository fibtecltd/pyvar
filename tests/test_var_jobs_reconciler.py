"""tests/test_var_jobs_reconciler.py — var_jobs rows that never ended are closed, and nothing else is touched (C5).

Reasoning:
- Real rows in a real (in-memory SQLite) table, not mocks: the question is which rows the UPDATE changes.
- Only "pending" rows older than the limit change; finished rows and recent rows are never touched, rows are never
  deleted, and a worker that finishes later still writes the true result over the reconciler's mark.
- The loop must survive an error, start only in hosted environments, and be stopped with the API.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import main as main_module
from storage import reconcile
from storage.models import VaRJob
from storage.reconcile import RECONCILED_MESSAGE, reconcile_pending_jobs, run_reconciler

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
HOUR = 3600


@pytest.fixture
async def factory() -> Any:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        await connection.run_sync(VaRJob.__table__.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def add(factory: Any, task_id: str, status: str, age_seconds: int) -> None:
    async with factory() as session:
        session.add(
            VaRJob(
                id=uuid.uuid4(),
                task_id=task_id,
                user_id="u",
                tier="free",
                status=status,
                created_at=NOW - timedelta(seconds=age_seconds),
                portfolio_value=1.0,
                n_simulations=10_000,
                confidence_level=0.99,
                horizon_days=1,
            )
        )
        await session.commit()


async def row(factory: Any, task_id: str) -> VaRJob:
    async with factory() as session:
        return (await session.execute(select(VaRJob).where(VaRJob.task_id == task_id))).scalar_one()


async def test_an_old_pending_row_is_closed_with_the_reason(factory) -> None:
    await add(factory, "old", "pending", 2 * HOUR)
    changed = await reconcile_pending_jobs(factory, older_than_seconds=HOUR, now=NOW)
    assert changed == 1
    closed = await row(factory, "old")
    assert closed.status == "failure"
    assert closed.error_message == RECONCILED_MESSAGE.format(seconds=HOUR)
    assert closed.completed_at is not None


async def test_only_old_pending_rows_change(factory) -> None:
    await add(factory, "recent-pending", "pending", HOUR - 60)
    await add(factory, "old-success", "success", 5 * HOUR)
    await add(factory, "old-failure", "failure", 5 * HOUR)
    await add(factory, "old-pending", "pending", HOUR + 60)
    changed = await reconcile_pending_jobs(factory, older_than_seconds=HOUR, now=NOW)
    assert changed == 1
    assert (await row(factory, "recent-pending")).status == "pending"
    assert (await row(factory, "old-success")).status == "success"
    assert (await row(factory, "old-failure")).error_message is None
    assert (await row(factory, "old-pending")).status == "failure"


async def test_nothing_is_ever_deleted(factory) -> None:
    for i in range(3):
        await add(factory, f"t{i}", "pending", 3 * HOUR)
    await reconcile_pending_jobs(factory, older_than_seconds=HOUR, now=NOW)
    async with factory() as session:
        assert len((await session.execute(select(VaRJob))).scalars().all()) == 3


async def test_a_second_run_changes_nothing(factory) -> None:
    await add(factory, "old", "pending", 2 * HOUR)
    assert await reconcile_pending_jobs(factory, older_than_seconds=HOUR, now=NOW) == 1
    assert await reconcile_pending_jobs(factory, older_than_seconds=HOUR, now=NOW) == 0


async def test_a_worker_that_finishes_later_overwrites_the_mark(factory) -> None:
    """The worker's own terminal UPDATE (by task_id) sets the true state, as tasks/var_task.py does."""
    await add(factory, "slow", "pending", 2 * HOUR)
    await reconcile_pending_jobs(factory, older_than_seconds=HOUR, now=NOW)
    async with factory() as session:
        await session.execute(
            update(VaRJob)
            .where(VaRJob.task_id == "slow")
            .values(status="success", completed_at=NOW, error_message=None, var_pct=0.02)
        )
        await session.commit()
    done = await row(factory, "slow")
    assert (done.status, done.error_message, done.var_pct) == ("success", None, 0.02)


async def test_the_loop_survives_an_error_and_keeps_going(caplog) -> None:
    calls = {"n": 0}

    async def flaky(*_a: Any, **_k: Any) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database down")
        return 0

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 4:
            raise asyncio.CancelledError

    with patch.object(reconcile, "reconcile_pending_jobs", flaky):
        with pytest.raises(asyncio.CancelledError):
            await run_reconciler(
                MagicMock(), interval_seconds=900, older_than_seconds=HOUR, sleep=fake_sleep
            )
    assert calls["n"] == 3, "the run after the failure still happens"
    assert 30 <= sleeps[0] <= 90, "the first run is delayed by a random 30 to 90 seconds"
    assert sleeps[1:] == [900, 900, 900]
    assert any("reconciler run failed" in r.getMessage() for r in caplog.records)


def test_the_defaults_are_an_hour_and_a_quarter_of_an_hour() -> None:
    cfg = main_module.cfg
    assert cfg.var_jobs_pending_timeout_seconds == 3_600
    assert cfg.var_jobs_reconcile_interval_seconds == 900
    assert cfg.var_jobs_reconcile_enabled is True


def run_lifespan(env: str, enabled: bool = True) -> list[Any]:
    """Run the API's lifespan with `env`; return the reconciler start-ups seen."""
    started: list[Any] = []

    async def fake_reconciler(*args: Any, **kwargs: Any) -> None:
        started.append(kwargs)
        await asyncio.Event().wait()

    async def go() -> None:
        async with main_module.lifespan(MagicMock()):
            await asyncio.sleep(0)

    with (
        patch.object(main_module.cfg, "app_env", env),
        patch.object(main_module.cfg, "jwt_secret", "x" * 40),
        patch.object(main_module.cfg, "var_jobs_reconcile_enabled", enabled),
        patch.object(main_module, "run_reconciler", fake_reconciler),
        patch.object(main_module, "get_sessionmaker", MagicMock()),
        patch("engine.montecarlo.run_monte_carlo_var"),
        patch.object(main_module, "close_job_done_bus", AsyncMock()),
    ):
        asyncio.run(go())
    return started


def test_the_api_starts_the_reconciler_in_a_hosted_environment_and_stops_it() -> None:
    started = run_lifespan("prod")
    assert started == [{"interval_seconds": 900, "older_than_seconds": 3_600}]


@pytest.mark.parametrize("env", ["test", "development"])
def test_no_reconciler_under_test_or_in_a_local_run(env: str) -> None:
    assert run_lifespan(env) == []


def test_the_reconciler_can_be_switched_off() -> None:
    assert run_lifespan("prod", enabled=False) == []
