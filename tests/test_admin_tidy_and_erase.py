"""tests/test_admin_tidy_and_erase.py — the two housekeeping admin routes: tidy lapsed grants, erase an account.

Reasoning:
- The privacy policy promises (portal/privacy.html, sections 2 and 4) that an expired education label goes back to
  plain "free" within 12 months, and that on request we "delete your e-mail address and switch off your API keys".
  api/education_grants.py::tidy and api/account_erasure.py are the two code paths behind those sentences, reached
  through /internal/admin/education/tidy and /internal/admin/accounts/erase, which accept only an admin token (the
  matrix of refused credentials is in tests/test_education_admin.py and now covers both routes).
- What is pinned, because each is a promise or a safety:
  * both are DRY RUNS unless the body says `apply`;
  * tidy touches only an education account whose grant ended more than `months` months ago, writes one
    billing_events row per account with a code and no cohort, and sends no e-mail;
  * erase removes the address, clears the tokens, revokes and blanks every key, resets an education label, keeps the
    row (so api_keys and the audit tables still join), writes one code=erase row, never names the address in its
    answer, and refuses a pro, enterprise or internal account;
  * neither needs the education flag.
- Real rows in a real (in-memory SQLite) database and the real application, like tests/test_education_admin.py,
  whose fixtures and helpers are reused.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from api.middleware.api_keys import generate_key, resolve_api_key
from storage.models import ApiKey, BillingEvent, User
from tests import test_education_admin as admin_tests
from tests.test_education_admin import ADMIN, ERASE, TIDY, add_user, aware, events, row

# The fixtures of tests/test_education_admin.py, shared by name (a plain assignment, so that using them as
# arguments below is not a redefinition of an unused import).
db = admin_tests.db
client = admin_tests.client
enabled = admin_tests.enabled
mail = admin_tests.mail
redis = admin_tests.redis

pytestmark = pytest.mark.asyncio

NOW = datetime.now(timezone.utc)


def ago(months: int) -> datetime:
    return NOW - timedelta(days=30 * months + 1)


# ── tidy ─────────────────────────────────────────────────────────────────────────────────────────────────────


async def seed_grants(db) -> None:
    await add_user(db, "old", tier="education", expires=ago(13))
    await add_user(db, "recent", tier="education", expires=ago(3))
    await add_user(db, "active", tier="education", expires=NOW + timedelta(days=60))
    await add_user(db, "free")


async def test_tidy_only_counts_unless_told_to_apply(client, db) -> None:
    await seed_grants(db)
    response = await client.post(TIDY, json={}, headers=ADMIN)
    assert response.status_code == 200 and response.json() == {"found": 1, "applied": False}
    assert (await row(db, "old")).tier == "education" and await events(db) == []


async def test_tidy_apply_resets_only_the_lapsed_label_and_says_nothing_to_the_holder(
    client, db, mail
) -> None:
    await seed_grants(db)
    response = await client.post(TIDY, json={"apply": True}, headers=ADMIN)
    assert response.json() == {"found": 1, "applied": True}
    old = await row(db, "old")
    assert old.tier == "free" and old.tier_expires_at is None
    assert (await row(db, "recent")).tier == "education"
    assert (await row(db, "active")).tier == "education"
    (event,) = await events(db)
    assert (event.event_type, event.old_tier, event.new_tier) == (
        "education_tidied",
        "education",
        "free",
    )
    assert event.user_id == "ext-old" and event.reason == "code=tidy; months=12"
    mail.assert_not_called()
    assert "@" not in json.dumps([event.user_id, event.reason])
    # nothing left on a second look
    again = await client.post(TIDY, json={"apply": True}, headers=ADMIN)
    assert again.json()["found"] == 0 and len(await events(db)) == 1


async def test_tidy_months_moves_the_cutoff(client, db) -> None:
    await seed_grants(db)
    response = await client.post(TIDY, json={"months": 2}, headers=ADMIN)
    assert response.json()["found"] == 2  # old and recent, not the active one


@pytest.mark.parametrize("months", [0, -1, 121])
async def test_tidy_refuses_a_silly_period(client, months) -> None:
    assert (await client.post(TIDY, json={"months": months}, headers=ADMIN)).status_code == 422


async def test_tidy_works_with_the_flag_off(client, db) -> None:
    await seed_grants(db)  # no `enabled` fixture: education_tier_enabled is False here
    assert (await client.post(TIDY, json={"apply": True}, headers=ADMIN)).status_code == 200


# ── erase ────────────────────────────────────────────────────────────────────────────────────────────────────


async def add_keys(db, name: str, count: int = 2) -> list[str]:
    secrets: list[str] = []
    async with db() as session:
        user = (
            await session.execute(select(User).where(User.external_id == f"ext-{name}"))
        ).scalar_one()
        for index in range(count):
            secret, prefix, digest = generate_key()
            session.add(
                ApiKey(
                    user_id=user.id, name=f"ada's laptop {index}", prefix=prefix, key_hash=digest
                )
            )
            secrets.append(secret)
        await session.commit()
    return secrets


async def keys_of(db) -> list[ApiKey]:
    async with db() as session:
        return list((await session.execute(select(ApiKey))).scalars())


async def test_erase_is_a_dry_run_unless_told_to_apply(client, db) -> None:
    await add_user(db, "ada")
    await add_keys(db, "ada")
    response = await client.post(ERASE, json={"email": "ada@uni.ac.uk"}, headers=ADMIN)
    assert response.status_code == 200
    assert response.json() == {
        "account_id": "ext-ada",
        "old_tier": "free",
        "keys_revoked": 2,
        "keys_renamed": 2,
        "stripe_linked": False,
        "google_sign_in": False,
        "applied": False,
    }
    assert (await row(db, "ada")).email == "ada@uni.ac.uk" and await events(db) == []
    assert all(key.revoked_at is None for key in await keys_of(db))


async def test_erase_removes_the_address_and_switches_the_keys_off_but_keeps_the_rows(
    client, db, redis, enabled
) -> None:
    await add_user(db, "ada", tier="education", expires=NOW + timedelta(days=30))
    secrets = await add_keys(db, "ada")
    async with db() as session:
        user = (await session.execute(select(User))).scalar_one()
        user.verification_token = "tok"
        user.api_key_hash = "legacy"
        await session.commit()
    assert (await resolve_api_key(secrets[0])).tier == "education"  # live and cached before

    response = await client.post(
        ERASE, json={"email": "Ada@Uni.ac.uk", "apply": True}, headers=ADMIN
    )
    assert response.status_code == 200 and response.json()["applied"] is True
    assert "ada@" not in response.text.lower()  # the answer names the account, never the address

    async with db() as session:
        user = (await session.execute(select(User))).scalar_one()
    assert user.email is None and user.email_verified is False
    assert user.verification_token is None and user.api_key_hash is None
    assert user.tier == "free" and user.tier_expires_at is None
    assert user.external_id == "ext-ada", "the row stays: the audit tables join on this identifier"

    keys = await keys_of(db)
    assert len(keys) == 2, "api_keys rows are never deleted (CLAUDE.md 3.3)"
    assert all(key.revoked_at is not None and key.name == "erased" for key in keys)
    assert await resolve_api_key(secrets[0]) is None, "a key stops working at once, cache included"

    (event,) = await events(db)
    assert (event.event_type, event.old_tier, event.new_tier) == (
        "account_erased",
        "education",
        "free",
    )
    assert event.user_id == "ext-ada" and event.reason == "code=erase"


async def test_erase_does_not_find_the_account_a_second_time(client, db) -> None:
    await add_user(db, "ada")
    await client.post(ERASE, json={"email": "ada@uni.ac.uk", "apply": True}, headers=ADMIN)
    again = await client.post(ERASE, json={"email": "ada@uni.ac.uk"}, headers=ADMIN)
    assert again.status_code == 404 and "ada" not in again.text


async def test_erase_reports_what_it_cannot_clear(client, db) -> None:
    async with db() as session:
        session.add(
            User(
                external_id="google:1234",
                email="g@uni.ac.uk",
                tier="free",
                email_verified=True,
                stripe_customer_id="cus_123",
            )
        )
        await session.commit()
    body = (await client.post(ERASE, json={"email": "g@uni.ac.uk"}, headers=ADMIN)).json()
    assert body["stripe_linked"] is True and body["google_sign_in"] is True


@pytest.mark.parametrize("tier", ["pro", "enterprise", "internal"])
async def test_erase_refuses_a_paid_or_service_account(client, db, tier) -> None:
    await add_user(db, "paid", tier=tier)
    response = await client.post(
        ERASE, json={"email": "paid@uni.ac.uk", "apply": True}, headers=ADMIN
    )
    assert response.status_code == 409 and tier in response.json()["detail"]
    assert (await row(db, "paid")).email == "paid@uni.ac.uk" and await events(db) == []


async def test_erase_works_with_the_flag_off_and_leaves_other_accounts_alone(client, db) -> None:
    await add_user(db, "ada")
    await add_user(db, "bea")
    await add_keys(db, "bea", count=1)
    await client.post(ERASE, json={"email": "ada@uni.ac.uk", "apply": True}, headers=ADMIN)
    assert (await row(db, "bea")).email == "bea@uni.ac.uk"
    assert all(key.revoked_at is None for key in await keys_of(db))


async def test_erase_logs_the_account_and_never_the_address(client, db) -> None:
    from structlog.testing import capture_logs

    await add_user(db, "ada")
    with capture_logs() as logs:
        await client.post(ERASE, json={"email": "ada@uni.ac.uk", "apply": True}, headers=ADMIN)
    assert "ada@" not in repr(logs) and "uni.ac.uk" not in repr(logs)
    assert any(line.get("account_id") == "ext-ada" for line in logs)


async def test_billing_events_rows_written_by_these_routes_carry_no_address(client, db) -> None:
    await add_user(db, "ada", tier="education", expires=ago(14))
    await client.post(TIDY, json={"apply": True}, headers=ADMIN)
    await add_user(db, "bea")
    await client.post(ERASE, json={"email": "bea@uni.ac.uk", "apply": True}, headers=ADMIN)
    async with db() as session:
        rows = (await session.execute(select(BillingEvent))).scalars().all()
    assert len(rows) == 2
    assert not any("@" in f"{r.user_id}{r.reason}{r.event_type}" for r in rows)
    assert aware(rows[0].created_at) <= aware(rows[1].created_at)
