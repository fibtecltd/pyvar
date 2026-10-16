"""Durable API keys: creation, authentication, revocation, tier, failure modes.

Reasoning:
- These run against a REAL (in-memory SQLite) database, not a fake session: what is
  being tested is SQL behaviour (unique hash, revoked/expired filters, the join to the
  user's tier) and a mock would only echo the implementation back. Redis is replaced by
  a tiny in-process fake, since the cache is the only thing the code uses it for.
- The free-tier quota test proves the point of the design: a key and a session JWT for
  the same account draw from ONE bucket, so keys are not a way around the 10/day cap.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.middleware import api_keys as keys_module
from api.middleware.api_keys import KEY_PREFIX, generate_key, hash_key, resolve_api_key
from api.middleware.auth import create_access_token
from api.middleware.usage import _client_name
from config import get_settings
from main import create_app
from storage.models import ApiKey, Base, User

cfg = get_settings()
COMPUTE = "/api/v1/market-risk/kupiec_pof_test"
COMPUTE_BODY = {"n_breaches": 6, "n_observations": 250}


class FakeRedis:
    """Just the commands api_keys.py uses."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> Any:
        return self.data.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)

    async def incr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key, 0)) + 1
        return int(self.data[key])

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[User.__table__, ApiKey.__table__])
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


async def _add_user(
    db, external_id: str = "u-1", tier: str = "free", verified: bool = True
) -> User:
    async with db() as session:
        user = User(
            external_id=external_id,
            email=f"{external_id}@example.com",
            tier=tier,
            email_verified=verified,
        )
        session.add(user)
        await session.commit()
        return user


def _session(external_id: str = "u-1", tier: str = "free") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(external_id, tier)}"}


def _bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def _create(client: AsyncClient, name: str = "default", who: str = "u-1") -> dict[str, Any]:
    resp = await client.post("/api/v1/auth/api-keys", json={"name": name}, headers=_session(who))
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# ── key material ───────────────────────────────────────────────────────────────


def test_generated_keys_are_prefixed_high_entropy_and_hash_to_sha256():
    secret, prefix, digest = generate_key()
    assert secret.startswith(KEY_PREFIX)
    assert len(secret) >= len(KEY_PREFIX) + 43  # 32 random bytes, urlsafe base64
    assert secret.startswith(prefix) and len(prefix) == 14
    assert digest == hashlib.sha256(secret.encode()).hexdigest() == hash_key(secret)
    assert generate_key()[0] != secret


# ── creation ───────────────────────────────────────────────────────────────────


async def test_create_returns_the_secret_once_and_stores_only_its_hash(client, db):
    await _add_user(db)
    created = await _create(client, "ci pipeline")

    secret = created["key"]
    assert secret.startswith(KEY_PREFIX) and created["prefix"] == secret[:14]
    assert created["name"] == "ci pipeline"

    async with db() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
    stored = " ".join(str(v) for v in vars(row).values())
    assert secret not in stored  # the secret is not persisted anywhere
    assert row.key_hash == hashlib.sha256(secret.encode()).hexdigest()
    expected_expiry = datetime.now(timezone.utc) + timedelta(days=cfg.api_key_default_expiry_days)
    expires = row.expires_at.replace(tzinfo=timezone.utc)
    assert abs((expires - expected_expiry).total_seconds()) < 60

    listing = await client.get("/api/v1/auth/api-keys", headers=_session())
    assert listing.status_code == 200
    assert secret not in listing.text and "key_hash" not in listing.text
    assert listing.json()["keys"][0]["prefix"] == created["prefix"]


async def test_create_needs_a_signed_in_session(client, db):
    await _add_user(db)
    assert (await client.post("/api/v1/auth/api-keys", json={})).status_code in (401, 403)
    forged = {"Authorization": "Bearer not-a-token"}
    assert (await client.post("/api/v1/auth/api-keys", json={}, headers=forged)).status_code == 401


async def test_an_api_key_cannot_create_or_revoke_keys(client, db):
    await _add_user(db)
    created = await _create(client)
    key_auth = _bearer(created["key"])

    resp = await client.post("/api/v1/auth/api-keys", json={}, headers=key_auth)
    assert resp.status_code == 403
    resp = await client.delete(f"/api/v1/auth/api-keys/{created['id']}", headers=key_auth)
    assert resp.status_code == 403
    assert (await client.get("/api/v1/auth/api-keys", headers=key_auth)).status_code == 403


async def test_unverified_accounts_cannot_create_keys(client, db):
    await _add_user(db, "u-unverified", verified=False)
    resp = await client.post("/api/v1/auth/api-keys", json={}, headers=_session("u-unverified"))
    assert resp.status_code == 403


async def test_active_key_cap_and_revoking_frees_a_slot(client, db):
    await _add_user(db)
    made = [await _create(client, f"k{i}") for i in range(cfg.api_key_max_active_per_user)]
    over = await client.post("/api/v1/auth/api-keys", json={}, headers=_session())
    assert over.status_code == 409

    revoke = await client.delete(f"/api/v1/auth/api-keys/{made[0]['id']}", headers=_session())
    assert revoke.status_code == 204
    assert (
        await client.post("/api/v1/auth/api-keys", json={}, headers=_session())
    ).status_code == 201


async def test_blank_key_name_is_rejected(client, db):
    await _add_user(db)
    resp = await client.post("/api/v1/auth/api-keys", json={"name": "   "}, headers=_session())
    assert resp.status_code == 422


# ── authentication ─────────────────────────────────────────────────────────────


async def test_a_key_authenticates_a_compute_endpoint(client, db):
    await _add_user(db)
    created = await _create(client)
    resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(created["key"]))
    assert resp.status_code == 200, resp.text
    assert "p_value" in resp.json()


async def test_key_and_session_share_one_daily_quota(client, db):
    """Keys are not a way around the free tier's daily cap."""
    await _add_user(db)
    created = await _create(client)
    calls = [_session(), _bearer(created["key"])]
    for i in range(cfg.rate_limit_free_daily):
        resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=calls[i % 2])
        assert resp.status_code == 200, (i, resp.text)
    for headers in calls:
        resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=headers)
        assert resp.status_code == 429


async def test_unknown_key_is_401_with_a_pointer_to_get_a_new_one(client, db):
    resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(KEY_PREFIX + "x" * 43))
    assert resp.status_code == 401
    assert "Create a new one" in resp.json()["detail"]
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_revoking_takes_effect_immediately_and_keeps_the_row(client, db):
    await _add_user(db)
    created = await _create(client)
    key_auth = _bearer(created["key"])
    assert (await client.post(COMPUTE, json=COMPUTE_BODY, headers=key_auth)).status_code == 200

    revoke = await client.delete(f"/api/v1/auth/api-keys/{created['id']}", headers=_session())
    assert revoke.status_code == 204
    # the key was cached a moment ago, yet is refused straight away
    assert (await client.post(COMPUTE, json=COMPUTE_BODY, headers=key_auth)).status_code == 401
    # revoking twice is fine; the audit row is kept
    again = await client.delete(f"/api/v1/auth/api-keys/{created['id']}", headers=_session())
    assert again.status_code == 204
    async with db() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
    assert row.revoked_at is not None


async def test_an_expired_key_is_refused(client, db, redis):
    await _add_user(db)
    created = await _create(client)
    async with db() as session:
        row = (await session.execute(select(ApiKey))).scalar_one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()
    redis.data.clear()
    resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(created["key"]))
    assert resp.status_code == 401


async def test_keys_of_unverified_accounts_are_refused(client, db):
    user = await _add_user(db, "u-2", verified=False)
    secret, prefix, digest = generate_key()
    async with db() as session:
        session.add(ApiKey(user_id=user.id, name="x", prefix=prefix, key_hash=digest))
        await session.commit()
    resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(secret))
    assert resp.status_code == 401


async def test_users_cannot_see_or_revoke_each_others_keys(client, db):
    await _add_user(db, "u-1")
    await _add_user(db, "u-2")
    mine = await _create(client, who="u-1")
    theirs = await _create(client, who="u-2")

    listing = (await client.get("/api/v1/auth/api-keys", headers=_session("u-1"))).json()["keys"]
    assert [k["id"] for k in listing] == [mine["id"]]
    resp = await client.delete(f"/api/v1/auth/api-keys/{theirs['id']}", headers=_session("u-1"))
    assert resp.status_code == 404
    assert (
        await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(theirs["key"]))
    ).status_code == 200


# ── tier, caching and last use ─────────────────────────────────────────────────


async def test_tier_comes_from_the_account_and_refreshes_within_the_cache_ttl(db, redis):
    user = await _add_user(db, tier="free")
    secret, prefix, digest = generate_key()
    async with db() as session:
        session.add(ApiKey(user_id=user.id, name="x", prefix=prefix, key_hash=digest))
        await session.commit()

    first = await resolve_api_key(secret)
    assert first is not None and first.tier == "free" and first.user_id == "u-1"

    async with db() as session:  # a Stripe upgrade lands
        row = (await session.execute(select(User))).scalar_one()
        row.tier = "pro"
        await session.commit()

    assert (await resolve_api_key(secret)).tier == "free"  # still cached
    redis.data.clear()  # ...until the (<= cache TTL) entry lapses
    assert (await resolve_api_key(secret)).tier == "pro"
    assert 0 < max(redis.ttls.values()) <= cfg.api_key_cache_ttl_seconds


async def test_last_used_is_set_on_first_use_and_not_rewritten_on_cache_hits(db, redis):
    user = await _add_user(db)
    secret, prefix, digest = generate_key()
    async with db() as session:
        session.add(ApiKey(user_id=user.id, name="x", prefix=prefix, key_hash=digest))
        await session.commit()

    await resolve_api_key(secret)
    async with db() as session:
        first = (await session.execute(select(ApiKey))).scalar_one().last_used_at
    assert first is not None

    await resolve_api_key(secret)  # cache hit: no database write
    async with db() as session:
        assert (await session.execute(select(ApiKey))).scalar_one().last_used_at == first


async def test_redis_being_down_falls_back_to_the_database(client, db):
    await _add_user(db)
    created = await _create(client)
    with patch.object(keys_module, "_redis", return_value=None):
        resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(created["key"]))
    assert resp.status_code == 200


async def test_a_database_outage_is_503_never_401(client, db):
    await _add_user(db)
    created = await _create(client)

    def broken() -> Any:
        raise RuntimeError("aurora unreachable")

    with (
        patch("api.middleware.api_keys.get_sessionmaker", side_effect=broken),
        patch.object(keys_module, "_redis", return_value=None),
    ):
        resp = await client.post(COMPUTE, json=COMPUTE_BODY, headers=_bearer(created["key"]))
    assert resp.status_code == 503


async def test_spraying_invalid_keys_is_throttled_per_client(client, db, monkeypatch):
    monkeypatch.setattr(cfg, "api_key_failed_attempts_per_minute", 3)
    codes = []
    for i in range(5):
        resp = await client.post(
            COMPUTE, json=COMPUTE_BODY, headers=_bearer(f"{KEY_PREFIX}{i:043d}")
        )
        codes.append(resp.status_code)
    assert codes[:3] == [401, 401, 401]
    assert codes[3:] == [429, 429]


# ── usage telemetry helpers ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("", None),
        ("pyvar-mcp/0.1.0", "pyvar-mcp"),
        ("PyVar-Client/0.2.0", "pyvar-client"),
        ("pyvar-jupyter", "pyvar-jupyter"),
        ("curl/8.0", "other"),
        pytest.param("x" * 500, "other", id="oversized-garbage"),
    ],
)
def test_client_header_is_allowlisted(header, expected):
    assert _client_name(header) == expected
