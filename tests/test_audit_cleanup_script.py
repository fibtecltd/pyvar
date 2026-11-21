"""tests/test_audit_cleanup_script.py — scripts/audit_cleanup.py, the command behind "kept six years, then deleted".

Reasoning:
- The harness (tests/script_world.py) replaces the script's HTTP call with a call into the REAL application over an
  in-memory database, so the token the script signs is the token the API accepts, and "deleted" is only said when
  the API itself no longer counts a row older than the cutoff.
- Deletion of audit rows is irreversible, so: a dry run unless `--yes`; prod needs `--yes-prod`; there is no option
  that changes the six years (argparse refuses `--years`); a stuck or lying API stops the command with exit 5
  rather than a loop or a false "done"; and nothing about a person reaches the output or the ledger (the tables
  hold account identifiers, which the test data fills with a sentinel).
- No AWS: the secret comes from stdin (`--secret-stdin`).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy import func, select

from api import audit_retention
from storage.models import BillingEvent, VaRJob
from tests.script_world import SECRET, load_script, run_script, script_world

script = load_script("audit_cleanup")
SENTINEL = "zz-sentinel-account"


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    async with script_world(script, tmp_path, monkeypatch, "audit-cleanups.jsonl") as w:
        yield w


def run(world, *argv: str):
    return run_script(script, world, *argv)


def ago(years: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=365.25 * years)


async def seed(
    world, old_jobs: int, new_jobs: int = 1, old_events: int = 0, new_events: int = 1
) -> None:
    async with world["maker"]() as session:
        for index in range(old_jobs + new_jobs):
            session.add(
                VaRJob(
                    task_id=f"t-{index}",
                    user_id=SENTINEL,
                    tier="free",
                    status="completed",
                    created_at=ago(7 if index < old_jobs else 1) - timedelta(minutes=index),
                    portfolio_value=1e6,
                    n_simulations=1000,
                    confidence_level=0.99,
                    horizon_days=1,
                )
            )
        for index in range(old_events + new_events):
            session.add(
                BillingEvent(
                    user_id=SENTINEL,
                    event_type="education_granted",
                    old_tier="free",
                    new_tier="education",
                    reason="x",
                    created_at=ago(8 if index < old_events else 1) - timedelta(minutes=index),
                )
            )
        await session.commit()


async def count(world, model) -> int:
    async with world["maker"]() as session:
        return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


ARGS = ["--env", "dev"]


@pytest.mark.asyncio
async def test_it_is_a_dry_run_unless_told_otherwise(world) -> None:
    await seed(world, old_jobs=3, old_events=2)
    code, out, err = await run(world, *ARGS)
    assert code == 0, err
    assert "dry run: rows older than" in out and "var_jobs 3, billing_events 2" in out
    assert "Add --yes to delete them" in out
    assert await count(world, VaRJob) == 4 and await count(world, BillingEvent) == 3
    assert not world["ledger"].exists()


@pytest.mark.asyncio
async def test_with_yes_it_deletes_confirms_and_records(world) -> None:
    await seed(world, old_jobs=3, old_events=2)
    code, out, err = await run(world, *ARGS, "--yes", "--operator", "fibtec-ops")
    assert code == 0, err
    assert "deleted rows older than" in out and "var_jobs 3, billing_events 2" in out
    assert "confirmed by the API" in out
    assert await count(world, VaRJob) == 1 and await count(world, BillingEvent) == 1

    claims = jwt.decode(
        world["seen"][0]["token"], SECRET, algorithms=["HS256"], audience="pyvar-admin"
    )
    assert claims["aud"] == "pyvar-admin" and "tier" not in claims and claims["sub"] == "fibtec-ops"

    (record,) = [json.loads(line) for line in world["ledger"].read_text().splitlines()]
    assert (
        record["action"] == "audit_cleanup"
        and record["by"] == "fibtec-ops"
        and record["env"] == "dev"
    )
    assert record["var_jobs_deleted"] == 3 and record["billing_events_deleted"] == 2
    assert oct(world["ledger"].stat().st_mode & 0o777) == "0o600"
    raw = world["ledger"].read_text()
    assert SENTINEL not in raw and "@" not in raw and SECRET not in raw


@pytest.mark.asyncio
async def test_it_repeats_rounds_until_nothing_is_left(world) -> None:
    await seed(world, old_jobs=5, old_events=0)
    code, out, err = await run(world, *ARGS, "--yes", "--max-rows", "2")
    assert code == 0, err
    assert "in 3 round(s)" in out and "round 1: left" in out
    assert await count(world, VaRJob) == 1
    applies = [c for c in world["seen"] if c["body"].get("apply")]
    assert len(applies) == 3 and all(c["body"]["max_rows"] == 2 for c in applies)


@pytest.mark.asyncio
async def test_nothing_to_delete_says_so_with_the_cutoff_and_writes_no_ledger(world) -> None:
    await seed(world, old_jobs=0, old_events=0)
    code, out, err = await run(world, *ARGS, "--yes")
    assert code == 0, err
    assert out.startswith("nothing to delete: no row is older than ") and "(six years)" in out
    assert not world["ledger"].exists() and await count(world, VaRJob) == 1
    assert [c["body"] for c in world["seen"]] == [{"apply": False}]


@pytest.mark.asyncio
async def test_there_is_no_way_to_change_the_period(world, capsys) -> None:
    await seed(world, old_jobs=0, old_events=0)
    for flag in ("--years", "--months", "--older-than", "--days"):
        with pytest.raises(SystemExit) as stopped:
            script.main([*ARGS, flag, "1"])
        assert stopped.value.code == 2
    capsys.readouterr()
    assert world["seen"] == []
    assert audit_retention.AUDIT_RETENTION_YEARS == 6


@pytest.mark.asyncio
async def test_it_stops_when_rows_remain_but_a_round_deletes_none(world) -> None:
    await seed(world, old_jobs=3, old_events=0)

    def stuck(body):
        if body.get("apply"):
            return 200, {
                "cutoff": "2026-01-01T00:00:00+00:00",
                "var_jobs": {"found": 3, "deleted": 0, "remaining": 3},
                "billing_events": {"found": 0, "deleted": 0, "remaining": 0},
                "applied": True,
            }
        return None

    world["state"]["hook"] = stuck
    code, out, err = await run(world, *ARGS, "--yes")
    assert code == 5 and "a round deleted none" in err
    assert "deleted rows" not in out and not world["ledger"].exists()
    assert len([c for c in world["seen"] if c["body"].get("apply")]) == 1


@pytest.mark.asyncio
async def test_it_does_not_say_deleted_when_the_api_still_counts_rows(world) -> None:
    await seed(world, old_jobs=3, old_events=0)

    def lies(body):
        if body.get("apply"):  # says all gone, deletes nothing
            return 200, {
                "cutoff": "2026-01-01T00:00:00+00:00",
                "var_jobs": {"found": 3, "deleted": 3, "remaining": 0},
                "billing_events": {"found": 0, "deleted": 0, "remaining": 0},
                "applied": True,
            }
        return None

    world["state"]["hook"] = lies
    code, out, err = await run(world, *ARGS, "--yes")
    assert code == 5 and "still counts some older than the cutoff" in err
    assert "deleted rows" not in out and not world["ledger"].exists()
    assert await count(world, VaRJob) == 4


@pytest.mark.asyncio
async def test_prod_needs_its_flag_and_no_call_is_made(world) -> None:
    code, _, err = await run(world, "--env", "prod")
    assert code == 2 and "--yes-prod" in err and world["seen"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("max_rows", ["0", "-1", "200001"])
async def test_a_silly_round_size_is_refused_before_any_call(world, max_rows) -> None:
    code, _, err = await run(world, *ARGS, "--max-rows", max_rows)
    assert code == 2 and "--max-rows" in err and world["seen"] == []


@pytest.mark.asyncio
async def test_a_weak_secret_is_refused_and_never_echoed(world) -> None:
    import asyncio
    import io

    world["monkeypatch"].setattr(sys, "stdin", io.StringIO("weak-secret-xyz"))
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(script.main, [*ARGS, "--secret-stdin"], stdout=out, stderr=err)
    assert code == 3 and "weak-secret-xyz" not in out.getvalue() + err.getvalue()
    assert world["seen"] == []


@pytest.mark.asyncio
async def test_a_refused_token_is_reported_without_deleting_anything(world) -> None:
    await seed(world, old_jobs=2, old_events=0)

    def refused(body):
        return 401, {"detail": "Invalid or expired token"}

    world["state"]["hook"] = refused
    code, out, err = await run(world, *ARGS, "--yes")
    assert code == 5 and "HTTP 401" in err and out == ""
    assert await count(world, VaRJob) == 3
