"""tests/test_audit_cleanup.py — the six-year clean-up of `var_jobs` and `billing_events`.

Reasoning:
- The privacy policy (portal/privacy.html) says job records and tier-change records are kept six years from their
  date and then deleted; CLAUDE.md 3.3 says only a clean-up job may delete audit rows, and only those older than
  six years. api/audit_retention.py is that job (reached through /internal/admin/audit/cleanup and
  scripts/audit_cleanup.py). A deletion job is the one piece of code in the service that can destroy the compliance
  record, so what is pinned here is mostly what it must NOT do:
  * never delete a row younger than six years (boundary tested to the second, and 29 February);
  * never be asked for a shorter period (an extra `years` field in the body changes nothing);
  * never touch `users`, `api_keys` (CLAUDE.md 3.3: never deleted) or any other table;
  * count only, unless the body says `apply`; work in bounded batches and say what remains;
  * put no account identifier, address or row content in its answer or its log line;
  * work with the education flag off, and refuse every credential but an admin token (tests/test_education_admin.py
    carries the refused-credential matrix, which includes this route).
- The six years are one constant, pinned to the sentence on the privacy page.
- Real rows in a real (in-memory SQLite) database and the real application; fixtures shared with
  tests/test_education_admin.py.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select
from structlog.testing import capture_logs

from api import audit_retention
from storage.models import ApiKey, BillingEvent, User, VaRJob
from tests import test_education_admin as admin_tests
from tests.test_education_admin import ADMIN, CLEANUP, add_user

db = admin_tests.db
client = admin_tests.client
mail = admin_tests.mail
redis = admin_tests.redis

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2032, 6, 15, 12, 0, tzinfo=timezone.utc)
CUTOFF = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
SECOND = timedelta(seconds=1)


def job(task: str, created: datetime, user: str = "ext-ada") -> VaRJob:
    return VaRJob(
        task_id=task,
        user_id=user,
        tier="free",
        status="completed",
        created_at=created,
        portfolio_value=1_000_000.0,
        n_simulations=1000,
        confidence_level=0.99,
        horizon_days=1,
    )


def event(created: datetime, user: str = "ext-ada") -> BillingEvent:
    return BillingEvent(
        user_id=user,
        event_type="education_granted",
        old_tier="free",
        new_tier="education",
        reason="x",
        created_at=created,
    )


async def seed(db, jobs: list[tuple[str, datetime]], events: list[datetime] = ()) -> None:  # type: ignore[assignment]
    async with db() as session:
        session.add_all([job(task, created) for task, created in jobs])
        session.add_all([event(created) for created in events])
        await session.commit()


async def count(db, model) -> int:
    async with db() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def run(db, **kwargs):
    async with db() as session:
        return await audit_retention.cleanup(session, now=NOW, **kwargs)


# ── the rule itself ──────────────────────────────────────────────────────────────────────────────────────────


def test_the_period_is_six_years_and_the_privacy_page_says_so() -> None:
    assert audit_retention.AUDIT_RETENTION_YEARS == 6
    html = (ROOT / "portal" / "privacy.html").read_text(encoding="utf-8")
    assert "We keep each of these records for six years from its date and then delete it" in html
    assert (
        "Records of tier changes are kept for six years from their date, and so are job records"
        in html
    )


def test_the_cutoff_is_six_calendar_years_back() -> None:
    assert audit_retention.retention_cutoff(NOW) == CUTOFF


@pytest.mark.parametrize(
    "now,cutoff",
    [
        (
            datetime(2032, 2, 29, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 2, 28, 9, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2028, 2, 29, 9, 0, tzinfo=timezone.utc),
            datetime(2022, 2, 28, 9, 0, tzinfo=timezone.utc),
        ),
        (
            datetime(2031, 3, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2025, 3, 1, 0, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_29_february_maps_to_the_28th_not_to_an_error(now: datetime, cutoff: datetime) -> None:
    assert audit_retention.retention_cutoff(now) == cutoff


def test_only_the_two_audit_tables_can_be_cleaned() -> None:
    assert set(audit_retention.TABLES) == {"var_jobs", "billing_events"}


# ── counting and deleting ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_dry_run_counts_and_deletes_nothing(db) -> None:
    await seed(db, [("old", CUTOFF - SECOND), ("new", CUTOFF + SECOND)], [CUTOFF - SECOND])
    result = await run(db)
    assert not result.applied
    assert result.tables["var_jobs"] == audit_retention.TableCleanup(
        found=1, deleted=0, remaining=1
    )
    assert result.tables["billing_events"] == audit_retention.TableCleanup(
        found=1, deleted=0, remaining=1
    )
    assert await count(db, VaRJob) == 2 and await count(db, BillingEvent) == 1


@pytest.mark.asyncio
async def test_apply_deletes_exactly_the_rows_older_than_six_years(db) -> None:
    await seed(
        db,
        [
            ("seven-years", NOW - timedelta(days=365 * 7)),
            ("a-second-over", CUTOFF - SECOND),
            ("a-second-under", CUTOFF + SECOND),
            ("five-years", NOW - timedelta(days=365 * 5)),
            ("today", NOW),
        ],
        [NOW - timedelta(days=365 * 7), CUTOFF - SECOND, CUTOFF + SECOND, NOW],
    )
    result = await run(db, apply=True)
    assert result.applied
    assert result.tables["var_jobs"] == audit_retention.TableCleanup(
        found=2, deleted=2, remaining=0
    )
    assert result.tables["billing_events"] == audit_retention.TableCleanup(
        found=2, deleted=2, remaining=0
    )
    async with db() as session:
        kept = set((await session.execute(select(VaRJob.task_id))).scalars())
    assert kept == {"a-second-under", "five-years", "today"}
    assert await count(db, BillingEvent) == 2


@pytest.mark.asyncio
async def test_a_row_exactly_at_the_cutoff_is_kept(db) -> None:
    await seed(db, [("edge", CUTOFF)], [CUTOFF])
    result = await run(db, apply=True)
    assert result.tables["var_jobs"].found == 0 and result.tables["billing_events"].found == 0
    assert await count(db, VaRJob) == 1 and await count(db, BillingEvent) == 1


@pytest.mark.asyncio
async def test_it_never_touches_accounts_or_keys_however_old(db) -> None:
    old = NOW - timedelta(days=365 * 9)
    await add_user(db, "ada")
    async with db() as session:
        user = (await session.execute(select(User))).scalar_one()
        user.created_at = old
        session.add(
            ApiKey(user_id=user.id, name="k", prefix="pyvar_ab", key_hash="h" * 64, created_at=old)
        )
        await session.commit()
    await seed(db, [("old", old)], [old])
    await run(db, apply=True)
    assert await count(db, User) == 1 and await count(db, ApiKey) == 1


@pytest.mark.asyncio
async def test_it_works_in_bounded_batches_and_says_what_remains(db, monkeypatch) -> None:
    monkeypatch.setattr(audit_retention, "BATCH_ROWS", 2)
    old = CUTOFF - timedelta(days=30)
    await seed(db, [(f"old-{n}", old - timedelta(days=n)) for n in range(7)] + [("new", NOW)])
    first = await run(db, apply=True, max_rows=5)
    assert first.tables["var_jobs"] == audit_retention.TableCleanup(found=7, deleted=5, remaining=2)
    assert await count(db, VaRJob) == 3
    second = await run(db, apply=True, max_rows=5)
    assert second.tables["var_jobs"] == audit_retention.TableCleanup(
        found=2, deleted=2, remaining=0
    )
    async with db() as session:
        assert list((await session.execute(select(VaRJob.task_id))).scalars()) == ["new"]


@pytest.mark.asyncio
async def test_the_oldest_rows_go_first(db, monkeypatch) -> None:
    monkeypatch.setattr(audit_retention, "BATCH_ROWS", 1)
    await seed(
        db,
        [
            ("b", CUTOFF - timedelta(days=20)),
            ("a", CUTOFF - timedelta(days=40)),
            ("c", CUTOFF - timedelta(days=5)),
        ],
    )
    await run(db, apply=True, max_rows=2)
    async with db() as session:
        assert list((await session.execute(select(VaRJob.task_id))).scalars()) == ["c"]


@pytest.mark.parametrize("max_rows", [0, -1, audit_retention.MAX_ROWS_LIMIT + 1])
@pytest.mark.asyncio
async def test_a_silly_batch_size_is_refused(db, max_rows) -> None:
    with pytest.raises(ValueError):
        await run(db, max_rows=max_rows)


# ── the route ────────────────────────────────────────────────────────────────────────────────────────────────


def years_ago(years: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=366 * years)


@pytest.mark.asyncio
async def test_the_route_counts_unless_told_to_apply_and_answers_in_counts(client, db) -> None:
    await seed(db, [("old", years_ago(7)), ("new", years_ago(1))], [years_ago(8)])
    response = await client.post(CLEANUP, json={}, headers=ADMIN)
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["var_jobs"] == {"found": 1, "deleted": 0, "remaining": 1}
    assert body["billing_events"] == {"found": 1, "deleted": 0, "remaining": 1}
    assert set(body) == {"cutoff", "var_jobs", "billing_events", "applied"}
    assert await count(db, VaRJob) == 2


@pytest.mark.asyncio
async def test_the_route_applies_and_a_second_call_finds_nothing(client, db) -> None:
    await seed(db, [("old", years_ago(7)), ("new", years_ago(1))], [years_ago(8)])
    body = (await client.post(CLEANUP, json={"apply": True}, headers=ADMIN)).json()
    assert body["var_jobs"] == {"found": 1, "deleted": 1, "remaining": 0}
    assert body["billing_events"] == {"found": 1, "deleted": 1, "remaining": 0}
    again = (await client.post(CLEANUP, json={"apply": True}, headers=ADMIN)).json()
    assert again["var_jobs"]["found"] == 0 and again["billing_events"]["found"] == 0
    assert await count(db, VaRJob) == 1


@pytest.mark.asyncio
async def test_the_period_cannot_be_shortened_through_the_body(client, db) -> None:
    await seed(db, [("two-years", years_ago(2)), ("old", years_ago(7))], [years_ago(2)])
    for extra in ({"years": 1}, {"months": 1}, {"older_than_days": 1}, {"cutoff": "2099-01-01"}):
        response = await client.post(CLEANUP, json={"apply": True, **extra}, headers=ADMIN)
        assert response.status_code == 200
    async with db() as session:
        assert list((await session.execute(select(VaRJob.task_id))).scalars()) == ["two-years"]
    assert await count(db, BillingEvent) == 1


@pytest.mark.parametrize("max_rows", [0, -5, 200001])
@pytest.mark.asyncio
async def test_the_route_refuses_a_silly_batch_size(client, max_rows) -> None:
    response = await client.post(CLEANUP, json={"max_rows": max_rows}, headers=ADMIN)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_the_route_needs_no_flag_and_logs_counts_only(client, db) -> None:
    await seed(db, [("zz-sentinel-task", years_ago(7))], [years_ago(7)])  # the flag is off here
    with capture_logs() as logs:
        response = await client.post(CLEANUP, json={"apply": True}, headers=ADMIN)
    assert response.status_code == 200
    lines = [entry for entry in logs if entry["event"] in ("audit_cleanup", "audit_admin_cleanup")]
    assert {entry["event"] for entry in lines} == {"audit_cleanup", "audit_admin_cleanup"}
    text = repr(lines)
    assert "ext-ada" not in text and "@" not in text and "zz-sentinel-task" not in text
    assert re.search(r"var_jobs_deleted': 1", text) and "billing_events_deleted': 1" in text
    assert "operator': 'operator'" in text


@pytest.mark.asyncio
async def test_a_dry_run_writes_no_log_line(client, db) -> None:
    await seed(db, [("old", years_ago(7))])
    with capture_logs() as logs:
        await client.post(CLEANUP, json={}, headers=ADMIN)
    assert [entry for entry in logs if "audit" in entry["event"]] == []
