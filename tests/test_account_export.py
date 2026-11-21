"""tests/test_account_export.py — the copy of an account's data, for a data-access request.

Reasoning:
- The privacy policy tells people they can ask for a copy of what we hold about them. There is no button:
  scripts/account_export.py calls /internal/admin/accounts/export, which calls api/account_export.py. The owner
  sends the file to the person, so what must hold is:
  * it is the WHOLE record of that one account (account row, keys, tier-change records, job records) and nothing of
    any other account, even one with a similar identifier;
  * it never carries a credential: the sign-in token, the legacy key digest and every key's digest stay out. A test
    lists every column of the four tables and fails when one is added without a decision (exported or secret);
  * it is paged, oldest first, so a heavy user's thousands of jobs do not need one huge answer;
  * an unknown address and an erased one are the same 404 (after an erasure there is nothing to find);
  * the address is the lookup key and the person's own data, but it appears in no log line and in no section but
    `account`; the log line names the operator, the account identifier, the section and a count;
  * the answer says what the copy does not cover, so it is not mistaken for everything we hold;
  * it needs an admin token (tests/test_education_admin.py carries the refused-credential matrix, which includes
    this route) and no education flag.
- Real rows in a real (in-memory SQLite) database and the real application; fixtures shared with
  tests/test_education_admin.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from structlog.testing import capture_logs

from api import account_export
from api.middleware.api_keys import generate_key
from storage.models import ApiKey, BillingEvent, User, VaRJob
from tests import test_education_admin as admin_tests
from tests.test_education_admin import ADMIN, ERASE, EXPORT

db = admin_tests.db
client = admin_tests.client
mail = admin_tests.mail
redis = admin_tests.redis

ADDRESS = "zz-sentinel-export@uni.ac.uk"
BASE = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


async def seed(db) -> None:
    """Ada (the account asked about), Bob (must never appear) and a lookalike identifier."""
    async with db() as session:
        ada = User(
            external_id="ext-ada",
            email=ADDRESS,
            tier="education",
            email_verified=True,
            verification_token="TOKEN-SENTINEL-ada",
            api_key_hash="LEGACY-DIGEST-SENTINEL",
            stripe_customer_id="cus_ada",
            total_jobs=3,
        )
        bob = User(external_id="ext-bob", email="bob-sentinel@uni.ac.uk", tier="free")
        lookalike = User(external_id="ext-ada-2", email="ada2-sentinel@uni.ac.uk", tier="free")
        session.add_all([ada, bob, lookalike])
        await session.flush()
        for owner, label in ((ada, "laptop"), (bob, "bob-laptop")):
            _, prefix, digest = generate_key()
            session.add(
                ApiKey(user_id=owner.id, name=label, prefix=prefix, key_hash="DIGEST-" + digest)
            )
        for index in range(5):
            session.add(
                VaRJob(
                    task_id=f"ada-{index}",
                    user_id="ext-ada",
                    tier="education",
                    status="completed",
                    created_at=BASE + timedelta(days=index),
                    portfolio_value=1e6,
                    n_simulations=1000,
                    confidence_level=0.99,
                    horizon_days=1,
                    var_pct=0.03,
                    result_s3_key=f"results/ada-{index}",
                )
            )
        session.add(
            VaRJob(
                task_id="bob-0",
                user_id="ext-bob",
                tier="free",
                status="completed",
                created_at=BASE,
                portfolio_value=5e5,
                n_simulations=500,
                confidence_level=0.95,
                horizon_days=1,
            )
        )
        session.add(
            VaRJob(
                task_id="lookalike-0",
                user_id="ext-ada-2",
                tier="free",
                status="completed",
                created_at=BASE,
                portfolio_value=7e5,
                n_simulations=500,
                confidence_level=0.95,
                horizon_days=1,
            )
        )
        session.add_all(
            [
                BillingEvent(
                    user_id="ext-ada",
                    event_type="education_granted",
                    old_tier="free",
                    new_tier="education",
                    reason="code=grant",
                    created_at=BASE,
                ),
                BillingEvent(
                    user_id="ext-ada",
                    event_type="education_tidied",
                    old_tier="education",
                    new_tier="free",
                    reason="code=tidy",
                    created_at=BASE + timedelta(days=400),
                ),
                BillingEvent(
                    user_id="ext-bob",
                    event_type="tier_downgraded",
                    old_tier="pro",
                    new_tier="free",
                    reason="bob-reason",
                    created_at=BASE,
                ),
            ]
        )
        await session.commit()


async def page(client, section: str, **extra):
    return await client.post(
        EXPORT, json={"email": ADDRESS, "section": section, **extra}, headers=ADMIN
    )


# ── what is in the copy ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_account_section_is_the_account_row_without_credentials(client, db) -> None:
    await seed(db)
    response = await page(client, "account")
    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == "ext-ada" and body["total"] == 1 and body["next_offset"] is None
    (row,) = body["rows"]
    assert (
        row["email"] == ADDRESS and row["external_id"] == "ext-ada" and row["tier"] == "education"
    )
    assert row["stripe_customer_id"] == "cus_ada" and row["total_jobs"] == 3
    assert "verification_token" not in row and "api_key_hash" not in row
    assert "SENTINEL" not in json.dumps(row).replace("zz-sentinel-export", "")


@pytest.mark.asyncio
async def test_the_keys_section_lists_keys_without_their_digests(client, db) -> None:
    await seed(db)
    body = (await page(client, "api_keys")).json()
    (key,) = body["rows"]
    assert (
        key["name"] == "laptop" and key["prefix"].startswith("pyvar_") and key["revoked_at"] is None
    )
    assert "key_hash" not in key and "DIGEST" not in json.dumps(body)
    assert "bob" not in json.dumps(body)


@pytest.mark.asyncio
async def test_the_record_sections_hold_only_this_accounts_rows(client, db) -> None:
    await seed(db)
    jobs = (await page(client, "var_jobs")).json()
    assert [r["task_id"] for r in jobs["rows"]] == [f"ada-{n}" for n in range(5)]
    assert jobs["total"] == 5 and jobs["next_offset"] is None
    assert (
        jobs["rows"][0]["result_s3_key"] == "results/ada-0" and jobs["rows"][0]["var_pct"] == 0.03
    )
    events = (await page(client, "billing_events")).json()
    assert [r["event_type"] for r in events["rows"]] == ["education_granted", "education_tidied"]
    for text in (json.dumps(jobs), json.dumps(events)):
        assert "bob" not in text and "lookalike" not in text and "ext-ada-2" not in text


@pytest.mark.asyncio
async def test_values_are_json_safe_and_the_address_is_in_the_account_section_only(
    client, db
) -> None:
    await seed(db)
    for section in ("account", "api_keys", "billing_events", "var_jobs"):
        body = (await page(client, section)).json()
        text = json.dumps(body)
        assert json.loads(text) == body
        assert (ADDRESS in text) == (section == "account"), section
    jobs = (await page(client, "var_jobs")).json()["rows"][0]
    assert datetime.fromisoformat(jobs["created_at"]) == BASE and isinstance(jobs["id"], str)


@pytest.mark.asyncio
async def test_every_answer_says_what_the_copy_does_not_cover(client, db) -> None:
    await seed(db)
    for section in ("account", "var_jobs"):
        notes = (await page(client, section)).json()["not_included"]
        assert notes == list(account_export.NOT_INCLUDED)
    text = " ".join(account_export.NOT_INCLUDED)
    assert "mailbox" in text and "Stripe" in text and "Sign-in tokens and key digests" in text


# ── paging ───────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pages_follow_one_another_oldest_first_and_cover_everything_once(client, db) -> None:
    await seed(db)
    seen: list[str] = []
    offset: int | None = 0
    pages = 0
    while offset is not None:
        body = (await page(client, "var_jobs", offset=offset, limit=2)).json()
        assert body["total"] == 5 and len(body["rows"]) <= 2
        seen += [row["task_id"] for row in body["rows"]]
        offset, pages = body["next_offset"], pages + 1
    assert seen == [f"ada-{n}" for n in range(5)] and pages == 3


@pytest.mark.asyncio
async def test_a_page_past_the_end_is_empty_not_an_error(client, db) -> None:
    await seed(db)
    body = (await page(client, "var_jobs", offset=50)).json()
    assert body["rows"] == [] and body["total"] == 5 and body["next_offset"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"section": "users"}, {"section": "api_usage"}],
)
async def test_a_bad_request_is_refused(client, db, extra) -> None:
    await seed(db)
    body = {"email": ADDRESS, "section": "account", **extra}
    assert (await client.post(EXPORT, json=body, headers=ADMIN)).status_code == 422


# ── who can be found ─────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_address_is_matched_whatever_its_case(client, db) -> None:
    await seed(db)
    body = {"email": ADDRESS.upper(), "section": "account"}
    response = await client.post(EXPORT, json=body, headers=ADMIN)
    assert response.status_code == 200 and response.json()["account_id"] == "ext-ada"


@pytest.mark.asyncio
async def test_an_unknown_address_is_a_404_that_does_not_echo_it(client, db) -> None:
    await seed(db)
    body = {"email": "nobody-sentinel@uni.ac.uk", "section": "var_jobs"}
    response = await client.post(EXPORT, json=body, headers=ADMIN)
    assert response.status_code == 404 and "nobody-sentinel" not in response.text


@pytest.mark.asyncio
async def test_after_an_erasure_there_is_nothing_to_export(client, db) -> None:
    await seed(db)
    erased = await client.post(ERASE, json={"email": ADDRESS, "apply": True}, headers=ADMIN)
    assert erased.status_code == 200
    assert (await page(client, "account")).status_code == 404
    async with db() as session:  # the rows stay (audit), they just cannot be reached through an address
        assert (
            len(
                list(
                    (
                        await session.execute(select(VaRJob).where(VaRJob.user_id == "ext-ada"))
                    ).scalars()
                )
            )
            == 5
        )


# ── logging ──────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_log_line_names_the_account_and_a_count_never_the_address_or_a_row(
    client, db
) -> None:
    await seed(db)
    with capture_logs() as logs:
        await page(client, "var_jobs", limit=2)
        await page(client, "account")
    lines = [entry for entry in logs if entry["event"] == "account_admin_export"]
    assert [(e["account_id"], e["section"], e["rows"]) for e in lines] == [
        ("ext-ada", "var_jobs", 2),
        ("ext-ada", "account", 1),
    ]
    assert all(e["operator"] == "operator" for e in lines)
    everything = repr(logs)
    assert "zz-sentinel" not in everything and "uni.ac.uk" not in everything
    assert "ada-0" not in everything and "results/" not in everything


@pytest.mark.asyncio
async def test_a_failed_lookup_logs_no_address(client, db) -> None:
    with capture_logs() as logs:
        await client.post(
            EXPORT, json={"email": "nobody-sentinel@uni.ac.uk", "section": "account"}, headers=ADMIN
        )
    assert "nobody-sentinel" not in repr(logs)


# ── nothing slips in unnoticed ───────────────────────────────────────────────────────────────────────────────

# One decision per column. A column added to any of these tables fails the test below until it is listed here,
# as exported or as a secret: a new field must not reach (or stay out of) a data-access copy by accident.
EXPECTED_EXPORTED = {
    User: {
        "id",
        "external_id",
        "tier",
        "tier_expires_at",
        "created_at",
        "last_active_at",
        "total_jobs",
        "total_simulations",
        "email",
        "email_verified",
        "verification_sent_at",
        "verified_at",
        "email_suppressed",
        "suppression_reason",
        "suppressed_at",
        "stripe_customer_id",
        "tier_downgrade_reason",
    },
    ApiKey: {
        "id",
        "user_id",
        "name",
        "prefix",
        "created_at",
        "expires_at",
        "last_used_at",
        "revoked_at",
    },
    BillingEvent: {
        "id",
        "user_id",
        "event_type",
        "old_tier",
        "new_tier",
        "reason",
        "stripe_event_id",
        "created_at",
    },
    VaRJob: {
        "id",
        "task_id",
        "user_id",
        "tier",
        "status",
        "created_at",
        "completed_at",
        "error_message",
        "duration_ms",
        "portfolio_value",
        "n_simulations",
        "confidence_level",
        "horizon_days",
        "var_pct",
        "var_abs",
        "cvar_pct",
        "cvar_abs",
        "result_s3_key",
    },
}
EXPECTED_SECRET = {"verification_token", "api_key_hash", "key_hash"}


def test_every_column_is_either_exported_or_a_named_secret() -> None:
    assert account_export.SECRET_COLUMNS == EXPECTED_SECRET
    for model, exported in EXPECTED_EXPORTED.items():
        columns = {c.key for c in model.__table__.columns}  # type: ignore[attr-defined]
        assert set(account_export._columns(model)) == exported, model.__name__
        assert columns == exported | (
            columns & EXPECTED_SECRET
        ), f"{model.__name__} has a column nobody decided on: {columns - exported - EXPECTED_SECRET}"


@pytest.mark.asyncio
async def test_no_credential_is_needed_but_an_admin_one_and_no_flag(client, db) -> None:
    await seed(db)  # education_tier_enabled is False here
    assert (await page(client, "account")).status_code == 200
    anonymous = await client.post(EXPORT, json={"email": ADDRESS, "section": "account"})
    assert anonymous.status_code in (401, 403)
