"""GET /auth/me: which account a session belongs to (issue #454, docs/plan-dashboard-signed-in-account.md).

Reasoning:
- The dashboard shows "Signed in as <address>", so there has to be a route that returns the address to the holder of a
  session and to nobody else. These tests run against a REAL in-memory SQLite database, like tests/test_api_keys.py: what
  is being tested is which row is read and which credentials get that far, and a mock would only echo the code back.
- The rules are the plan's section 5: session token only (an API key, a stream token, a trial ticket and an admin token
  are all refused); the tier is the one that applies now, not the token's claim; an erased account is answered without an
  address, never with an error; the address is in no log record and no token claim, and the answer is not cacheable.
- Addresses are example.com / uni.example style. No real or tester address is written here.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
import structlog
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from structlog.testing import capture_logs

from api import account_erasure
from api.middleware import api_keys as keys_module
from api.middleware.auth import create_access_token, create_stream_token
from api.middleware.trial import mint_ticket
from main import create_app
from storage.models import ApiKey, Base, BillingEvent, User
from tests.test_api_keys import FakeRedis
from tests.test_education_admin import admin_token, bearer

ME = "/api/v1/auth/me"
ADDRESS = "ada.lovelace@uni.example"
OTHER_ADDRESS = "grace.hopper@uni.example"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[User.__table__, ApiKey.__table__, BillingEvent.__table__]
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    with (
        patch("api.routes.auth.get_sessionmaker", return_value=maker),
        patch("api.middleware.api_keys.get_sessionmaker", return_value=maker),
    ):
        yield maker
    await engine.dispose()


@pytest.fixture
def redis():
    fake = FakeRedis()
    with patch.object(keys_module, "_redis", return_value=fake):
        yield fake


@pytest_asyncio.fixture
async def client(db, redis):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


async def add_user(
    db,
    external_id: str,
    email: str | None = ADDRESS,
    tier: str = "free",
    verified: bool = True,
    tier_expires_at: datetime | None = None,
) -> None:
    async with db() as session:
        session.add(
            User(
                external_id=external_id,
                email=email,
                tier=tier,
                email_verified=verified,
                tier_expires_at=tier_expires_at,
            )
        )
        await session.commit()


def session_for(external_id: str, claimed_tier: str = "free") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(external_id, claimed_tier)}"}


# ── who gets an answer ──────────────────────────────────────────────────────────


async def test_a_session_gets_its_own_address_and_tier(client, db) -> None:
    await add_user(db, "u-1", ADDRESS, tier="pro")
    response = await client.get(ME, headers=session_for("u-1", "pro"))
    assert response.status_code == 200
    assert response.json() == {"email": ADDRESS, "tier": "pro"}


async def test_two_sessions_see_their_own_accounts_only(client, db) -> None:
    await add_user(db, "u-1", ADDRESS)
    await add_user(db, "u-2", OTHER_ADDRESS)
    first = await client.get(ME, headers=session_for("u-1"))
    second = await client.get(ME, headers=session_for("u-2"))
    assert first.json()["email"] == ADDRESS and second.json()["email"] == OTHER_ADDRESS
    assert OTHER_ADDRESS not in first.text and ADDRESS not in second.text


async def test_the_answer_is_not_cacheable(client, db) -> None:
    await add_user(db, "u-1")
    response = await client.get(ME, headers=session_for("u-1"))
    assert response.headers["cache-control"] == "no-store"


async def test_the_tier_comes_from_the_account_not_from_the_token(client, db) -> None:
    await add_user(db, "u-1", tier="free")
    response = await client.get(ME, headers=session_for("u-1", claimed_tier="enterprise"))
    assert response.json()["tier"] == "free"


async def test_a_lapsed_education_grant_counts_as_free(client, db) -> None:
    past = datetime.now(timezone.utc) - timedelta(days=1)
    await add_user(db, "u-1", tier="education", tier_expires_at=past)
    response = await client.get(ME, headers=session_for("u-1", claimed_tier="education"))
    assert response.json() == {"email": ADDRESS, "tier": "free"}


async def test_a_token_for_an_account_that_does_not_exist_is_refused_like_the_key_routes(
    client, db
) -> None:
    response = await client.get(ME, headers=session_for("nobody"))
    assert response.status_code == 403
    assert response.json()["detail"] == "No verified account for this session."


# ── an erased account ───────────────────────────────────────────────────────────


async def test_an_erased_account_is_answered_without_an_address_not_with_an_error(
    client, db, redis
) -> None:
    await add_user(db, "u-erased", ADDRESS)
    headers = session_for("u-erased")  # minted before the erasure, still valid for its 60 minutes
    assert (await client.get(ME, headers=headers)).json()["email"] == ADDRESS
    async with db() as session:
        await account_erasure.erase_account(session, email=ADDRESS, apply=True)
        row = (
            await session.execute(select(User).where(User.external_id == "u-erased"))
        ).scalar_one()
        assert row.email is None and row.email_verified is False  # what the real erasure leaves
    response = await client.get(ME, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"email": None, "tier": "free"}
    assert ADDRESS not in response.text


# ── which credentials get this far ──────────────────────────────────────────────


async def test_no_credential_is_refused(client, db) -> None:
    await add_user(db, "u-1")
    response = await client.get(ME)
    assert response.status_code in (401, 403)  # HTTPBearer's own refusal; the address is not in it
    assert ADDRESS not in response.text


async def test_an_api_key_is_refused_like_on_the_api_keys_routes(client, db) -> None:
    await add_user(db, "u-1")
    created = await client.post("/api/v1/auth/api-keys", json={}, headers=session_for("u-1"))
    assert created.status_code == 201, created.text
    key = {"Authorization": f"Bearer {created.json()['key']}"}
    response = await client.get(ME, headers=key)
    assert response.status_code == 403
    assert ADDRESS not in response.text


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: create_stream_token("u-1", "task-1"), id="stream token"),
        pytest.param(lambda: mint_ticket()[0], id="trial ticket"),
        pytest.param(lambda: admin_token(), id="admin token"),
        pytest.param(lambda: "not.a.jwt", id="garbage"),
    ],
)
async def test_every_other_kind_of_token_is_refused(client, db, token) -> None:
    await add_user(db, "u-1")
    response = await client.get(ME, headers=bearer(token()))
    assert response.status_code == 401, response.text
    assert ADDRESS not in response.text


# ── where the address must not appear ───────────────────────────────────────────


async def test_the_address_is_in_no_log_record(client, db, caplog) -> None:
    await add_user(db, "u-1", ADDRESS)
    caplog.set_level(logging.DEBUG)
    with capture_logs() as events:
        response = await client.get(ME, headers=session_for("u-1"))
        # canaries: prove both captures are live, so an empty capture cannot pass this test by itself
        logging.getLogger("canary").warning("canary-stdlib")
        structlog.get_logger().info("canary-structlog")
    assert response.status_code == 200 and response.json()["email"] == ADDRESS
    assert "canary-stdlib" in caplog.text
    assert any(event.get("event") == "canary-structlog" for event in events)
    seen = caplog.text + json.dumps(events, default=str)
    assert ADDRESS not in seen and "ada.lovelace" not in seen


def test_the_address_is_not_a_claim_of_the_session_token() -> None:
    token = create_access_token("u-1", "free")
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert set(payload) == {"sub", "tier", "exp"}
    assert "@" not in json.dumps(payload)


def test_the_response_model_has_exactly_the_two_fields_of_the_plan() -> None:
    from schemas.auth import AccountInfo

    assert list(AccountInfo.model_fields) == ["email", "tier"]
    assert AccountInfo(email=None, tier="free").model_dump() == {"email": None, "tier": "free"}
    odd: Any = "weird@uni.example"  # a stored address never turns the answer into a 500
    assert AccountInfo(email=odd, tier="free").email == odd
