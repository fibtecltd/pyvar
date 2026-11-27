"""tests/test_education_admin.py — granting, extending, revoking and listing education accounts (A2 PR 1).

Reasoning:
- The /internal/admin/education routes change who may use 100,000-simulation requests, so two things are tested
  hard: WHO can call them (only a token with `aud` exactly "pyvar-admin": a session JWT, an "internal" JWT, an API
  key, a stream token, a trial ticket, and a token with no `aud` are all refused, and the admin token is refused
  by every other route) and WHAT they may do (a verified free account only; the cohort and per-domain caps; at
  most 12 months; every change writes its billing_events row in the same transaction, with a code and the cohort
  label and nothing an applicant wrote).
- Real rows in a real (in-memory SQLite) database and the real application, as tests/test_api_keys.py does; the
  Redis cache the key lookup uses is the same small in-process double, and SES is replaced by a recorder.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api import education_grants
from api.middleware import api_keys as keys_module
from api.middleware import trial as lane
from api.middleware.api_keys import generate_key, resolve_api_key
from api.middleware.auth import (
    ADMIN_TOKEN_AUDIENCE,
    create_access_token,
    create_stream_token,
    decode_admin_payload,
)
from config import get_settings
from main import create_app
from storage.models import ApiKey, Base, BillingEvent, User, VaRJob
from tests.test_api_keys import FakeRedis

cfg = get_settings()
SECRET = cfg.jwt_secret
LIST = "/api/v1/internal/admin/education/list"
GRANT = "/api/v1/internal/admin/education/grant"
EXTEND = "/api/v1/internal/admin/education/extend"
REVOKE = "/api/v1/internal/admin/education/revoke"
SUSPEND = "/api/v1/internal/admin/education/suspend-all"
TIDY = "/api/v1/internal/admin/education/tidy"
ERASE = "/api/v1/internal/admin/accounts/erase"
EXPORT = "/api/v1/internal/admin/accounts/export"
CLEANUP = "/api/v1/internal/admin/audit/cleanup"
CHECKOUT_ALLOW = "/api/v1/internal/admin/billing/checkout-allow"
ASSISTANT_ALLOW = "/api/v1/internal/admin/assistant/allow"


def admin_token(**overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": "operator",
        "aud": ADMIN_TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + 600,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return str(jwt.encode(claims, SECRET, algorithm=cfg.jwt_algorithm))


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _FreshAdminHeaders(Mapping[str, str]):
    """Request headers with an admin token minted at the moment they are read.

    This used to be `bearer(admin_token())` built once when the file is imported. An admin token lives 600 s, and
    pytest imports every test file before it runs any, so on a slow run (Python 3.12 in CI takes about 17 minutes)
    the tests that came after the 10-minute mark were refused with a 401. Four other test files import ADMIN
    too (account export, admin tidy and erase, audit clean-up, the billing allow list); all of them now get a
    token that is valid when the request is made.
    """

    def __getitem__(self, key: str) -> str:
        if key != "Authorization":
            raise KeyError(key)
        return bearer(admin_token())["Authorization"]

    def __iter__(self) -> Iterator[str]:
        return iter(("Authorization",))

    def __len__(self) -> int:
        return 1


ADMIN = _FreshAdminHeaders()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[User.__table__, ApiKey.__table__, BillingEvent.__table__, VaRJob.__table__],
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    with (
        patch("api.routes.internal.get_sessionmaker", return_value=maker),
        patch("api.middleware.api_keys.get_sessionmaker", return_value=maker),
    ):
        yield maker
    await engine.dispose()


@pytest.fixture
def redis():
    fake = FakeRedis()
    with patch.object(keys_module, "_redis", return_value=fake):
        yield fake


@pytest.fixture
def mail():
    with patch("api.education_grants.send_tier_change_email") as sent:
        yield sent


@pytest.fixture
def enabled():
    with patch.object(cfg, "education_tier_enabled", True):
        yield


@pytest_asyncio.fixture
async def client(db, redis, mail):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


async def add_user(
    db,
    name: str,
    *,
    tier: str = "free",
    domain: str = "uni.ac.uk",
    verified: bool = True,
    expires: datetime | None = None,
) -> User:
    async with db() as session:
        user = User(
            external_id=f"ext-{name}",
            email=f"{name}@{domain}",
            tier=tier,
            email_verified=verified,
            tier_expires_at=expires,
        )
        session.add(user)
        await session.commit()
        return user


async def row(db, name: str, domain: str = "uni.ac.uk") -> User:
    async with db() as session:
        return (
            await session.execute(select(User).where(User.email == f"{name}@{domain}"))
        ).scalar_one()


async def events(db) -> list[BillingEvent]:
    async with db() as session:
        return list(
            (await session.execute(select(BillingEvent).order_by(BillingEvent.created_at)))
            .scalars()
            .all()
        )


def body(name: str, **extra: Any) -> dict[str, Any]:
    return {"email": f"{name}@uni.ac.uk", "months": 6, "cohort": "ucl-2026", **extra}


def aware(moment: datetime | None) -> datetime:
    assert moment is not None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


# ── who may call: only an admin token ─────────────────────────────────────────────────────────────────────


def _refused_tokens() -> dict[str, str]:
    ticket, _ = lane.mint_ticket(time.time())
    api_key, _, _ = generate_key()
    return {
        "a session JWT": create_access_token("someone", "free"),
        "an enterprise JWT": create_access_token("someone", "enterprise"),
        "an internal JWT": create_access_token("svc", "internal"),
        "an API key": api_key,
        "a stream token": create_stream_token("someone", "task-1"),
        "a trial ticket": ticket,
        "a token with another audience": admin_token(aud="pyvar-stream"),
        "a token with no audience": admin_token(aud=None),
        "an expired admin token": admin_token(
            iat=int(time.time()) - 700, exp=int(time.time()) - 100
        ),
        "an admin token with no exp": admin_token(exp=None),
        "an admin token with no iat": admin_token(iat=None),
        "an admin token that lives 11 minutes": admin_token(exp=int(time.time()) + 660),
        "an admin token with a tier": admin_token(tier="internal"),
        "an admin token with no subject": admin_token(sub=None),
        "an admin token signed with another secret": str(
            jwt.encode(
                {
                    "sub": "x",
                    "aud": ADMIN_TOKEN_AUDIENCE,
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 60,
                },
                "another-secret-0123456789abcdefghijklmnopqrstuvwxyz",
                algorithm="HS256",
            )
        ),
        "gibberish": "not-a-token",
    }


@pytest.mark.parametrize("kind", sorted(_refused_tokens()))
async def test_every_other_credential_is_refused_on_every_admin_route(
    client, enabled, kind
) -> None:
    token = _refused_tokens()[kind]
    for method, path, payload in (
        ("GET", LIST, None),
        ("POST", GRANT, body("a")),
        ("POST", EXTEND, body("a")),
        ("POST", REVOKE, {"email": "a@uni.ac.uk", "cohort": "x"}),
        ("POST", SUSPEND, {}),
        ("POST", TIDY, {}),
        ("POST", ERASE, {"email": "a@uni.ac.uk"}),
        ("POST", EXPORT, {"email": "a@uni.ac.uk", "section": "account"}),
        ("POST", CLEANUP, {}),
        ("POST", CHECKOUT_ALLOW, {"action": "list"}),
        ("POST", ASSISTANT_ALLOW, {"action": "list"}),
    ):
        response = await client.request(method, path, json=payload, headers=bearer(token))
        assert response.status_code == 401, (kind, path, response.text)


async def test_no_credential_at_all_is_refused(client) -> None:
    assert (await client.get(LIST)).status_code in (401, 403)


async def test_a_valid_admin_token_is_accepted(client, db) -> None:
    response = await client.get(LIST, headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["accounts"] == []


def test_the_decoder_names_the_operator_and_nothing_else() -> None:
    payload = decode_admin_payload(admin_token(sub="fibtec-ops"))
    assert payload.operator == "fibtec-ops"
    assert vars(payload) == {"operator": "fibtec-ops"}


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/auth/api-keys", "GET"),  # require_session
        ("/api/v1/auth/me", "GET"),  # require_session; the one that returns the account's address
        ("/api/v1/market-risk/kupiec_pof_test", "POST"),  # a compute route
        ("/api/v1/internal/token-report", "GET"),  # the internal tier's own routes
        ("/api/v1/var/stream-token/abc", "POST"),
    ],
)
async def test_the_admin_token_is_refused_everywhere_else(client, path, method) -> None:
    response = await client.request(method, path, json={}, headers=ADMIN)
    assert response.status_code == 401, response.text


def test_the_stream_and_trial_decoders_refuse_it() -> None:
    from jose import JWTError

    from api.middleware.auth import decode_stream_payload

    with pytest.raises(JWTError):
        decode_stream_payload(admin_token(), "task-1")
    with pytest.raises(JWTError):
        lane.decode_ticket(admin_token())


# ── grant ─────────────────────────────────────────────────────────────────────────────────────────────────


async def test_a_grant_sets_the_tier_and_expiry_and_writes_the_event_in_the_same_commit(
    client, db, enabled, mail
) -> None:
    await add_user(db, "ada")
    response = await client.post(GRANT, json=body("ada"), headers=ADMIN)
    assert response.status_code == 200, response.text
    assert response.json()["tier"] == "education"

    user = await row(db, "ada")
    assert user.tier == "education"
    expected = education_grants.add_months(datetime.now(timezone.utc), 6)
    assert abs((aware(user.tier_expires_at) - expected).total_seconds()) < 60

    (event,) = await events(db)
    assert (event.event_type, event.old_tier, event.new_tier) == (
        "education_granted",
        "free",
        "education",
    )
    assert event.user_id == "ext-ada"
    # Exactly a code, the cohort label and a date: nothing an applicant wrote, no address, no domain.
    assert event.reason is not None
    assert re.fullmatch(r"cohort=ucl-2026; months=6; expires=\d{4}-\d{2}-\d{2}", event.reason)
    mail.assert_called_once()
    assert mail.call_args.args == ("ada@uni.ac.uk", "education_granted")
    # the e-mail is told the end date (it prints it) and the account id (the logs use it, never the address)
    assert mail.call_args.kwargs["account_id"] == "ext-ada"
    assert aware(mail.call_args.kwargs["end_date"]) == aware(user.tier_expires_at)


async def test_a_grant_for_a_single_month_and_for_twelve_is_allowed(client, db, enabled) -> None:
    await add_user(db, "one")
    await add_user(db, "twelve")
    assert (await client.post(GRANT, json=body("one", months=1), headers=ADMIN)).status_code == 200
    assert (
        await client.post(GRANT, json=body("twelve", months=12), headers=ADMIN)
    ).status_code == 200


@pytest.mark.parametrize("months", [0, 13, -1])
async def test_months_outside_one_to_twelve_are_refused(client, db, enabled, months) -> None:
    await add_user(db, "ada")
    response = await client.post(GRANT, json=body("ada", months=months), headers=ADMIN)
    assert response.status_code == 422
    assert (await row(db, "ada")).tier == "free"


@pytest.mark.parametrize("cohort", ["two words", "a@b.c", "x" * 41, "name: Ada Lovelace", ""])
async def test_a_cohort_label_must_be_a_short_token_so_no_applicant_text_reaches_the_audit_row(
    client, db, enabled, cohort
) -> None:
    await add_user(db, "ada")
    response = await client.post(GRANT, json=body("ada", cohort=cohort), headers=ADMIN)
    assert response.status_code == 422
    assert await events(db) == []


async def test_an_unknown_address_is_a_404(client, enabled) -> None:
    assert (await client.post(GRANT, json=body("nobody"), headers=ADMIN)).status_code == 404


async def test_an_unverified_account_is_refused(client, db, enabled) -> None:
    await add_user(db, "ada", verified=False)
    response = await client.post(GRANT, json=body("ada"), headers=ADMIN)
    assert response.status_code == 409
    assert (await row(db, "ada")).tier == "free"


@pytest.mark.parametrize("tier", ["pro", "enterprise", "internal"])
async def test_a_paid_or_service_account_is_never_granted(client, db, enabled, tier) -> None:
    await add_user(db, "ada", tier=tier)
    response = await client.post(GRANT, json=body("ada"), headers=ADMIN)
    assert response.status_code == 409
    user = await row(db, "ada")
    assert user.tier == tier and user.tier_expires_at is None
    assert await events(db) == []


async def test_an_account_that_is_already_education_is_pointed_to_extend(
    client, db, enabled
) -> None:
    await add_user(db, "ada")
    assert (await client.post(GRANT, json=body("ada"), headers=ADMIN)).status_code == 200
    again = await client.post(GRANT, json=body("ada"), headers=ADMIN)
    assert again.status_code == 409 and "extend" in again.json()["detail"].lower()


async def test_an_address_is_matched_whatever_its_case(client, db, enabled) -> None:
    await add_user(db, "ada")
    response = await client.post(
        GRANT, json={**body("ada"), "email": "ADA@Uni.AC.UK"}, headers=ADMIN
    )
    assert response.status_code == 200


# ── the flag ──────────────────────────────────────────────────────────────────────────────────────────────


async def test_with_the_flag_off_grant_and_extend_answer_503_and_change_nothing(client, db) -> None:
    assert cfg.education_tier_enabled is False
    await add_user(db, "ada")
    assert (await client.post(GRANT, json=body("ada"), headers=ADMIN)).status_code == 503
    assert (await client.post(EXTEND, json=body("ada"), headers=ADMIN)).status_code == 503
    assert (await row(db, "ada")).tier == "free"
    assert await events(db) == []


async def test_with_the_flag_off_revoke_list_and_suspend_still_work(client, db, enabled) -> None:
    await add_user(db, "ada")
    await client.post(GRANT, json=body("ada"), headers=ADMIN)
    with patch.object(cfg, "education_tier_enabled", False):
        listing = await client.get(LIST, headers=ADMIN)
        assert listing.status_code == 200 and listing.json()["enabled"] is False
        suspended = await client.post(SUSPEND, json={}, headers=ADMIN)
        assert suspended.json() == {"suspended": 1}
        revoked = await client.post(
            REVOKE, json={"email": "ada@uni.ac.uk", "cohort": "ucl-2026"}, headers=ADMIN
        )
        assert revoked.status_code == 200


# ── the caps ──────────────────────────────────────────────────────────────────────────────────────────────


async def test_the_cohort_cap_counts_active_accounts_only(client, db, enabled) -> None:
    with patch.object(cfg, "education_cohort_cap", 2), patch.object(
        cfg, "education_domain_cap", 99
    ):
        for name in ("a", "b", "c", "d"):
            await add_user(db, name, domain=f"{name}.ac.uk")
        ok = [
            await client.post(GRANT, json={**body(n), "email": f"{n}@{n}.ac.uk"}, headers=ADMIN)
            for n in ("a", "b")
        ]
        full = await client.post(GRANT, json={**body("c"), "email": "c@c.ac.uk"}, headers=ADMIN)
        assert [r.status_code for r in ok] == [200, 200]
        assert full.status_code == 409 and "full" in full.json()["detail"]

        # One grant ends: a place opens.
        await client.post(REVOKE, json={"email": "a@a.ac.uk", "cohort": "x"}, headers=ADMIN)
        again = await client.post(GRANT, json={**body("c"), "email": "c@c.ac.uk"}, headers=ADMIN)
        assert again.status_code == 200


async def test_a_lapsed_grant_does_not_take_a_place(client, db, enabled) -> None:
    past = datetime.now(timezone.utc) - timedelta(days=1)
    with patch.object(cfg, "education_cohort_cap", 1):
        await add_user(db, "old", tier="education", expires=past)
        await add_user(db, "new")
        response = await client.post(GRANT, json=body("new"), headers=ADMIN)
    assert response.status_code == 200


async def test_the_domain_cap_binds_unless_overridden_and_the_override_never_lifts_the_cohort_cap(
    client, db, enabled
) -> None:
    with patch.object(cfg, "education_domain_cap", 2), patch.object(cfg, "education_cohort_cap", 3):
        for name in ("a", "b", "c", "d"):
            await add_user(db, name)
        assert (await client.post(GRANT, json=body("a"), headers=ADMIN)).status_code == 200
        assert (await client.post(GRANT, json=body("b"), headers=ADMIN)).status_code == 200
        blocked = await client.post(GRANT, json=body("c"), headers=ADMIN)
        assert blocked.status_code == 409
        assert blocked.json()["detail"] == (
            "2 education accounts are already active for uni.ac.uk. "
            "Use allow_domain_over_cap for a class."
        )
        override = await client.post(
            GRANT, json=body("c", allow_domain_over_cap=True), headers=ADMIN
        )
        assert override.status_code == 200
        # Three active now: the cohort cap (3) is full, whatever the flag says.
        full = await client.post(GRANT, json=body("d", allow_domain_over_cap=True), headers=ADMIN)
        assert full.status_code == 409 and "full" in full.json()["detail"]


async def test_another_domain_is_not_counted_against_the_domain_cap(client, db, enabled) -> None:
    with patch.object(cfg, "education_domain_cap", 1):
        await add_user(db, "a", domain="one.ac.uk")
        await add_user(db, "b", domain="two.ac.uk")
        first = await client.post(GRANT, json={**body("a"), "email": "a@one.ac.uk"}, headers=ADMIN)
        second = await client.post(GRANT, json={**body("b"), "email": "b@two.ac.uk"}, headers=ADMIN)
    assert (first.status_code, second.status_code) == (200, 200)


async def test_a_domain_that_ends_the_same_way_is_not_the_same_domain(client, db, enabled) -> None:
    # "uni.ac.uk" must not count "notuni.ac.uk" (a suffix match on the domain, not on the string).
    with patch.object(cfg, "education_domain_cap", 1):
        await add_user(db, "a", domain="notuni.ac.uk")
        await add_user(db, "b")
        await client.post(GRANT, json={**body("a"), "email": "a@notuni.ac.uk"}, headers=ADMIN)
        second = await client.post(GRANT, json=body("b"), headers=ADMIN)
    assert second.status_code == 200


# ── extend ────────────────────────────────────────────────────────────────────────────────────────────────


async def test_extend_adds_months_to_the_current_end_date(client, db, enabled, mail) -> None:
    await add_user(db, "ada")
    await client.post(GRANT, json=body("ada", months=3), headers=ADMIN)
    before = aware((await row(db, "ada")).tier_expires_at)
    response = await client.post(EXTEND, json=body("ada", months=3), headers=ADMIN)
    assert response.status_code == 200
    after = aware((await row(db, "ada")).tier_expires_at)
    assert after == education_grants.add_months(before, 3)
    assert [e.event_type for e in await events(db)] == ["education_granted", "education_extended"]
    assert mail.call_args.args == ("ada@uni.ac.uk", "education_extended")
    assert aware(mail.call_args.kwargs["end_date"]) == after
    assert mail.call_args.kwargs["account_id"] == "ext-ada"


async def test_extend_never_goes_past_twelve_months_from_today(client, db, enabled) -> None:
    await add_user(db, "ada")
    await client.post(GRANT, json=body("ada", months=9), headers=ADMIN)
    too_far = await client.post(EXTEND, json=body("ada", months=6), headers=ADMIN)
    assert too_far.status_code == 409 and "12 months" in too_far.json()["detail"]
    fine = await client.post(EXTEND, json=body("ada", months=3), headers=ADMIN)
    assert fine.status_code == 200


async def test_extending_a_lapsed_grant_counts_from_today_and_checks_the_caps(
    client, db, enabled
) -> None:
    past = datetime.now(timezone.utc) - timedelta(days=40)
    await add_user(db, "lapsed", tier="education", expires=past)
    await add_user(db, "taken")
    with patch.object(cfg, "education_cohort_cap", 1):
        await client.post(GRANT, json=body("taken"), headers=ADMIN)  # fills the one place
        refused = await client.post(EXTEND, json=body("lapsed", months=2), headers=ADMIN)
        assert refused.status_code == 409 and "full" in refused.json()["detail"]
        await client.post(REVOKE, json={"email": "taken@uni.ac.uk", "cohort": "x"}, headers=ADMIN)
        revived = await client.post(EXTEND, json=body("lapsed", months=2), headers=ADMIN)
    assert revived.status_code == 200
    expires = aware((await row(db, "lapsed")).tier_expires_at)
    # Counted from today, not from the date it lapsed.
    assert abs((expires - education_grants.add_months(datetime.now(timezone.utc), 2)).days) <= 1


async def test_extend_refuses_an_account_that_is_not_education(client, db, enabled) -> None:
    await add_user(db, "ada")
    assert (await client.post(EXTEND, json=body("ada"), headers=ADMIN)).status_code == 409


# ── revoke and suspend-all ────────────────────────────────────────────────────────────────────────────────


async def test_revoke_returns_the_account_to_free_and_writes_the_event(
    client, db, enabled, mail
) -> None:
    await add_user(db, "ada")
    await client.post(GRANT, json=body("ada"), headers=ADMIN)
    response = await client.post(
        REVOKE, json={"email": "ada@uni.ac.uk", "cohort": "ucl-2026"}, headers=ADMIN
    )
    assert response.status_code == 200 and response.json()["tier"] == "free"
    user = await row(db, "ada")
    assert (user.tier, user.tier_expires_at) == ("free", None)
    last = (await events(db))[-1]
    assert (last.event_type, last.old_tier, last.new_tier) == (
        "education_revoked",
        "education",
        "free",
    )
    assert last.reason == "cohort=ucl-2026"
    assert mail.call_args.args == ("ada@uni.ac.uk", "education_revoked")
    assert mail.call_args.kwargs == {"account_id": "ext-ada"}


async def test_revoke_refuses_an_account_that_is_not_education(client, db) -> None:
    await add_user(db, "ada", tier="pro")
    response = await client.post(
        REVOKE, json={"email": "ada@uni.ac.uk", "cohort": "x"}, headers=ADMIN
    )
    assert response.status_code == 409
    assert (await row(db, "ada")).tier == "pro"


async def test_suspend_all_ends_every_active_grant_and_only_those(client, db, enabled) -> None:
    for name in ("a", "b"):
        await add_user(db, name)
        await client.post(GRANT, json=body(name), headers=ADMIN)
    await add_user(
        db, "old", tier="education", expires=datetime.now(timezone.utc) - timedelta(days=3)
    )
    await add_user(db, "plain")
    await add_user(db, "payer", tier="pro")

    response = await client.post(SUSPEND, json={}, headers=ADMIN)
    assert response.json() == {"suspended": 2}

    now = datetime.now(timezone.utc)
    for name in ("a", "b"):
        user = await row(db, name)
        assert user.tier == "education" and aware(user.tier_expires_at) <= now  # kept, but ended
    assert (await row(db, "payer")).tier == "pro"
    suspended = [e for e in await events(db) if e.event_type == "education_suspended"]
    assert len(suspended) == 2 and {e.reason for e in suspended} == {"code=suspend_all"}
    listing = (await client.get(LIST, headers=ADMIN)).json()
    assert listing["active"] == 0


async def test_a_suspended_account_can_be_brought_back_with_extend(client, db, enabled) -> None:
    await add_user(db, "ada")
    await client.post(GRANT, json=body("ada"), headers=ADMIN)
    await client.post(SUSPEND, json={}, headers=ADMIN)
    back = await client.post(EXTEND, json=body("ada", months=2), headers=ADMIN)
    assert back.status_code == 200
    assert (await client.get(LIST, headers=ADMIN)).json()["active"] == 1


# ── list ──────────────────────────────────────────────────────────────────────────────────────────────────


async def test_list_shows_state_cohort_and_the_caps(client, db, enabled) -> None:
    await add_user(db, "ada")
    await add_user(db, "bob")
    await client.post(GRANT, json=body("ada", cohort="first"), headers=ADMIN)
    await client.post(GRANT, json=body("bob", cohort="second"), headers=ADMIN)
    await client.post(EXTEND, json=body("bob", months=1, cohort="third"), headers=ADMIN)
    await add_user(
        db, "old", tier="education", expires=datetime.now(timezone.utc) - timedelta(days=2)
    )
    data = (await client.get(LIST, headers=ADMIN)).json()
    assert (data["active"], data["cohort_cap"], data["domain_cap"], data["enabled"]) == (
        2,
        25,
        10,
        True,
    )
    by_email = {a["email"]: a for a in data["accounts"]}
    assert by_email["old@uni.ac.uk"]["active"] is False
    assert by_email["ada@uni.ac.uk"]["cohort"] == "first"
    assert by_email["bob@uni.ac.uk"]["cohort"] == "third"  # the latest grant or extension wins
    assert [a["email"] for a in data["accounts"]][0] == "old@uni.ac.uk"  # soonest end first


# ── what a grant does to the account's API keys ──────────────────────────────────────────────────────────


async def add_key(db, user: User) -> tuple[str, str]:
    secret, prefix, digest = generate_key()
    async with db() as session:
        session.add(
            ApiKey(
                user_id=user.id,
                name="k",
                prefix=prefix,
                key_hash=digest,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=300),
            )
        )
        await session.commit()
    return secret, digest


async def test_a_live_grant_resolves_a_key_to_education_and_its_cache_never_outlives_the_grant(
    db, redis, enabled
) -> None:
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    user = await add_user(db, "ada", tier="education", expires=soon)
    secret, digest = await add_key(db, user)
    resolved = await resolve_api_key(secret)
    assert resolved is not None and resolved.tier == "education"
    assert 0 < redis.ttls[keys_module._CACHE_PREFIX + digest] <= 30


async def test_a_lapsed_or_dateless_grant_resolves_a_key_to_free(db, redis, enabled) -> None:
    lapsed = await add_user(
        db, "lapsed", tier="education", expires=datetime.now(timezone.utc) - timedelta(days=1)
    )
    dateless = await add_user(db, "dateless", tier="education", expires=None)
    for user in (lapsed, dateless):
        secret, digest = await add_key(db, user)
        resolved = await resolve_api_key(secret)
        assert resolved is not None and resolved.tier == "free"
        # A lapsed grant is cached like any free key; a zero TTL would send every call to the database.
        assert redis.ttls[keys_module._CACHE_PREFIX + digest] == cfg.api_key_cache_ttl_seconds


async def test_a_key_of_an_account_with_the_flag_off_is_free(db, redis) -> None:
    user = await add_user(
        db, "ada", tier="education", expires=datetime.now(timezone.utc) + timedelta(days=30)
    )
    secret, _ = await add_key(db, user)
    resolved = await resolve_api_key(secret)
    assert resolved is not None and resolved.tier == "free"


async def test_a_grant_and_a_revoke_drop_the_cached_key_at_once(client, db, redis, enabled) -> None:
    user = await add_user(db, "ada")
    secret, digest = await add_key(db, user)
    await resolve_api_key(secret)  # cached as free
    assert keys_module._CACHE_PREFIX + digest in redis.data
    await client.post(GRANT, json=body("ada"), headers=ADMIN)
    assert keys_module._CACHE_PREFIX + digest not in redis.data
    assert (await resolve_api_key(secret)).tier == "education"
    await client.post(REVOKE, json={"email": "ada@uni.ac.uk", "cohort": "x"}, headers=ADMIN)
    assert keys_module._CACHE_PREFIX + digest not in redis.data
    assert (await resolve_api_key(secret)).tier == "free"


async def test_suspend_all_drops_every_cached_key(client, db, redis, enabled) -> None:
    secrets_digests = []
    for name in ("a", "b"):
        user = await add_user(db, name)
        await client.post(GRANT, json=body(name), headers=ADMIN)
        secrets_digests.append(await add_key(db, user))
        await resolve_api_key(secrets_digests[-1][0])
    await client.post(SUSPEND, json={}, headers=ADMIN)
    for secret, digest in secrets_digests:
        assert keys_module._CACHE_PREFIX + digest not in redis.data
        assert (await resolve_api_key(secret)).tier == "free"


# ── a session token reflects the same rule ───────────────────────────────────────────────────────────────


def test_the_three_session_mints_read_the_tier_through_effective_tier() -> None:
    """The places that sign a session token read the tier through effective_tier (CLAUDE.md 3.5).

    Each of the three mints is checked by name, and the count is those three plus GET /auth/me: it signs nothing, it only
    shows the tier, but it must apply the same rule or a lapsed education grant would still read "education" on the
    dashboard. A new call site has to be added here on purpose."""
    import inspect
    import re

    from api.routes import auth, billing

    for mint in (auth.verify, auth.google_sign_in, billing.checkout_complete, auth.whoami):
        assert "effective_tier(" in inspect.getsource(mint), mint.__name__
    sources = [inspect.getsource(auth), inspect.getsource(billing)]
    assert sum(src.count("effective_tier(") for src in sources) == 4
    for src in sources:
        assert not re.search(r"^\s+tier = (user|row)\.tier\s*$", src, re.M)


@pytest.mark.parametrize(
    "offset_days,flag,expected",
    [(30, True, "education"), (-1, True, "free"), (30, False, "free")],
)
async def test_the_sign_in_link_mints_a_token_with_the_effective_tier(
    client, db, offset_days, flag, expected
) -> None:
    async with db() as session:
        session.add(
            User(
                external_id="ext-ada",
                email="ada@uni.ac.uk",
                tier="education",
                tier_expires_at=datetime.now(timezone.utc) + timedelta(days=offset_days),
                email_verified=True,
                verification_token="link-token",
                verification_sent_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    with (
        patch.object(cfg, "education_tier_enabled", flag),
        patch("api.routes.auth.get_sessionmaker", return_value=db),
    ):
        response = await client.get("/api/v1/auth/verify", params={"token": "link-token"})
    assert response.status_code == 200, response.text
    assert response.json()["tier"] == expected
    claims = jwt.decode(response.json()["access_token"], SECRET, algorithms=[cfg.jwt_algorithm])
    assert claims["tier"] == expected  # the token carries what the response says


async def test_a_billing_event_keeps_codes_and_labels_only(client, db, enabled) -> None:
    await add_user(db, "grace.hopper")
    await client.post(GRANT, json=body("grace.hopper", cohort="navy-2026"), headers=ADMIN)
    await client.post(
        EXTEND, json=body("grace.hopper", months=1, cohort="navy-2026"), headers=ADMIN
    )
    await client.post(
        REVOKE, json={"email": "grace.hopper@uni.ac.uk", "cohort": "navy-2026"}, headers=ADMIN
    )
    for event in await events(db):
        assert event.reason is not None
        assert "grace" not in event.reason and "@" not in event.reason
        assert event.stripe_event_id is None
