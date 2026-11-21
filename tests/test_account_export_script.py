"""tests/test_account_export_script.py — scripts/account_export.py, the command behind "send me a copy of my data".

Reasoning:
- The harness (tests/script_world.py) replaces the script's HTTP call with a call into the REAL application over an
  in-memory database: the token the script signs is the token the API accepts, and the file it writes is checked
  against the rows in the database.
- The file holds one person's data, so what is pinned is how it is made and what stays out of everything else:
  * created 0600, never overwritten (an existing path is refused before any call), deleted if anything fails;
  * complete: every row of the account, across pages, and none of another account; the script itself checks the
    rows written against the totals the API reports and refuses to leave a short file behind;
  * no credential in it (sign-in token, key digests), the `not_included` list in it;
  * the address appears in the file's `account` section and nowhere else: not in stdout, stderr or the ledger.
- No AWS: the secret comes from stdin (`--secret-stdin`).
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from jose import jwt

from api.middleware.api_keys import generate_key
from storage.models import ApiKey, BillingEvent, User, VaRJob
from tests.script_world import SECRET, load_script, run_script, script_world

script = load_script("account_export")
ADDRESS = "zz-sentinel-copy@uni.ac.uk"
BASE_TIME = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    async with script_world(script, tmp_path, monkeypatch, "exports.jsonl") as w:
        w["out"] = tmp_path / "copy.json"
        yield w


async def seed(world, jobs: int = 5) -> None:
    async with world["maker"]() as session:
        ada = User(
            external_id="ext-ada",
            email=ADDRESS,
            tier="education",
            email_verified=True,
            verification_token="TOKEN-SENTINEL",
            api_key_hash="LEGACY-DIGEST-SENTINEL",
        )
        bob = User(external_id="ext-bob", email="bob-sentinel@uni.ac.uk")
        session.add_all([ada, bob])
        await session.flush()
        for owner in (ada, bob):
            _, prefix, digest = generate_key()
            session.add(
                ApiKey(
                    user_id=owner.id,
                    name=f"k-{owner.external_id}",
                    prefix=prefix,
                    key_hash="DIGEST-" + digest,
                )
            )
        for index in range(jobs):
            session.add(
                VaRJob(
                    task_id=f"ada-{index}",
                    user_id="ext-ada",
                    tier="education",
                    status="completed",
                    created_at=BASE_TIME + timedelta(days=index),
                    portfolio_value=1e6,
                    n_simulations=1000,
                    confidence_level=0.99,
                    horizon_days=1,
                )
            )
        session.add(
            VaRJob(
                task_id="bob-0",
                user_id="ext-bob",
                tier="free",
                status="completed",
                created_at=BASE_TIME,
                portfolio_value=1.0,
                n_simulations=1,
                confidence_level=0.95,
                horizon_days=1,
            )
        )
        session.add(
            BillingEvent(
                user_id="ext-ada",
                event_type="education_granted",
                old_tier="free",
                new_tier="education",
                reason="code=grant",
                created_at=BASE_TIME,
            )
        )
        session.add(
            BillingEvent(
                user_id="ext-bob",
                event_type="tier_downgraded",
                old_tier="pro",
                new_tier="free",
                reason="bob",
                created_at=BASE_TIME,
            )
        )
        await session.commit()


def run(world, *extra: str, email: str = ADDRESS):
    return run_script(
        script, world, "--env", "dev", "--email", email, "--out", str(world["out"]), *extra
    )


@pytest.mark.asyncio
async def test_it_writes_one_complete_file_and_prints_only_counts(world) -> None:
    await seed(world, jobs=5)
    code, out, err = await run(world, "--operator", "fibtec-ops", "--page-size", "2")
    assert code == 0, err
    assert "for account ext-ada: account 1, api_keys 1, billing_events 1, var_jobs 5" in out
    assert ADDRESS not in out + err and "zz-sentinel" not in out + err
    assert (
        "reply within one month" in out and "then delete it" in out and "the company mailbox" in out
    )

    data = json.loads(world["out"].read_text(encoding="utf-8"))
    assert set(data) == {
        "generated_at",
        "environment",
        "account_id",
        "not_included",
        "account",
        "api_keys",
        "billing_events",
        "var_jobs",
    }
    assert data["account_id"] == "ext-ada" and data["environment"] == "dev"
    assert data["account"]["email"] == ADDRESS
    assert [row["task_id"] for row in data["var_jobs"]] == [f"ada-{n}" for n in range(5)]
    assert [row["event_type"] for row in data["billing_events"]] == ["education_granted"]
    assert [row["name"] for row in data["api_keys"]] == ["k-ext-ada"]
    assert any("Stripe" in line for line in data["not_included"])
    assert oct(world["out"].stat().st_mode & 0o777) == "0o600"


@pytest.mark.asyncio
async def test_it_pages_with_the_requested_size(world) -> None:
    await seed(world, jobs=5)
    await run(world, "--page-size", "2")
    job_calls = [c["body"] for c in world["seen"] if c["body"]["section"] == "var_jobs"]
    assert [(c["offset"], c["limit"]) for c in job_calls] == [(0, 2), (2, 2), (4, 2)]


@pytest.mark.asyncio
async def test_no_credential_and_no_other_account_is_in_the_file(world) -> None:
    await seed(world)
    await run(world)
    text = world["out"].read_text(encoding="utf-8")
    for forbidden in (
        "TOKEN-SENTINEL",
        "LEGACY-DIGEST",
        "DIGEST-",
        "key_hash",
        "verification_token",
        "bob",
        "ext-bob",
    ):
        assert forbidden not in text, forbidden
    assert text.count(ADDRESS) == 1  # the account section only


@pytest.mark.asyncio
async def test_the_ledger_and_the_token_hold_no_address_and_no_secret(world) -> None:
    await seed(world)
    await run(world, "--operator", "fibtec-ops")
    raw = world["ledger"].read_text()
    (record,) = [json.loads(line) for line in raw.splitlines()]
    assert (
        record["action"] == "export"
        and record["account"] == "ext-ada"
        and record["by"] == "fibtec-ops"
    )
    assert record["var_jobs_rows"] == 5 and record["api_keys_rows"] == 1 and record["env"] == "dev"
    assert (
        "zz-sentinel" not in raw and "uni.ac.uk" not in raw and "@" not in raw and SECRET not in raw
    )
    assert oct(world["ledger"].stat().st_mode & 0o777) == "0o600"
    claims = jwt.decode(
        world["seen"][0]["token"], SECRET, algorithms=["HS256"], audience="pyvar-admin"
    )
    assert claims["aud"] == "pyvar-admin" and "tier" not in claims and claims["sub"] == "fibtec-ops"


@pytest.mark.asyncio
async def test_an_existing_file_is_never_overwritten_and_no_call_is_made(world) -> None:
    await seed(world)
    world["out"].write_text("precious")
    code, _, err = await run(world)
    assert code == 2 and "already exists" in err
    assert world["out"].read_text() == "precious" and world["seen"] == []


@pytest.mark.asyncio
async def test_an_unknown_address_makes_no_file_and_does_not_echo_it(world) -> None:
    await seed(world)
    code, out, err = await run(world, email="nobody-sentinel@uni.ac.uk")
    assert code == 5 and "HTTP 404" in err and "no account has this address" in err.lower()
    assert "nobody-sentinel" not in out + err
    assert not world["out"].exists() and not world["ledger"].exists()


@pytest.mark.asyncio
async def test_a_short_file_is_deleted_and_not_reported_as_done(world) -> None:
    await seed(world, jobs=5)

    def cuts_short(body):
        if (
            body["section"] == "var_jobs" and body["offset"] == 0
        ):  # "last page" after two of five rows
            return 200, {
                "account_id": "ext-ada",
                "section": "var_jobs",
                "total": 5,
                "next_offset": None,
                "rows": [{"task_id": "ada-0"}, {"task_id": "ada-1"}],
                "not_included": [],
            }
        return None

    world["state"]["hook"] = cuts_short
    code, out, err = await run(world)
    assert code == 5 and "wrote 2 rows but the API counts 5" in err
    assert not world["out"].exists() and not world["ledger"].exists() and "wrote " not in out


@pytest.mark.asyncio
async def test_a_failure_part_way_deletes_the_half_written_file(world) -> None:
    await seed(world, jobs=5)

    def breaks_on_the_second_page(body):
        if body["section"] == "var_jobs" and body["offset"] == 2:
            return 500, {"detail": "boom"}
        return None

    world["state"]["hook"] = breaks_on_the_second_page
    code, _, err = await run(world, "--page-size", "2")
    assert code == 5 and "HTTP 500" in err
    assert not world["out"].exists() and not world["ledger"].exists()


@pytest.mark.asyncio
async def test_a_server_that_never_advances_is_stopped(world) -> None:
    await seed(world, jobs=5)

    def loops(body):
        if body["section"] == "var_jobs":
            return 200, {
                "account_id": "ext-ada",
                "section": "var_jobs",
                "total": 5,
                "next_offset": body["offset"],
                "rows": [],
                "not_included": [],
            }
        return None

    world["state"]["hook"] = loops
    code, _, err = await run(world)
    assert code == 5 and "did not advance" in err and not world["out"].exists()


@pytest.mark.asyncio
async def test_an_account_with_nothing_but_its_row_gives_empty_lists(world) -> None:
    async with world["maker"]() as session:
        session.add(User(external_id="ext-ada", email=ADDRESS, tier="free"))
        await session.commit()
    code, out, err = await run(world)
    assert code == 0, err
    data = json.loads(world["out"].read_text(encoding="utf-8"))
    assert data["api_keys"] == data["billing_events"] == data["var_jobs"] == []
    assert "api_keys 0, billing_events 0, var_jobs 0" in out


@pytest.mark.asyncio
async def test_prod_needs_its_flag_and_no_call_is_made(world) -> None:
    code, _, err = await run_script(
        script, world, "--env", "prod", "--email", ADDRESS, "--out", str(world["out"])
    )
    assert code == 2 and "--yes-prod" in err and world["seen"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("size", ["0", "1001"])
async def test_a_silly_page_size_is_refused_before_any_call(world, size) -> None:
    code, _, err = await run(world, "--page-size", size)
    assert code == 2 and "--page-size" in err and world["seen"] == []


@pytest.mark.asyncio
async def test_a_missing_folder_is_refused(world) -> None:
    world["out"] = world["out"].parent / "nope" / "copy.json"
    code, _, err = await run(world)
    assert code == 2 and "is not a folder" in err and world["seen"] == []


@pytest.mark.asyncio
async def test_a_weak_secret_is_refused_and_never_echoed(world) -> None:
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO("weak-secret-xyz"))
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(
        script.main,
        ["--env", "dev", "--email", ADDRESS, "--out", str(world["out"]), "--secret-stdin"],
        stdout=out,
        stderr=err,
    )
    assert code == 3 and "weak-secret-xyz" not in out.getvalue() + err.getvalue()
    assert world["seen"] == [] and not world["out"].exists()
