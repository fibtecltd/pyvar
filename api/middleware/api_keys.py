"""
api/middleware/api_keys.py — durable API keys: generation, hashing and lookup

Reasoning:
- The old "API key" was the session JWT: 60 minutes, tier baked in, shown once,
  not re-issuable by email. People paste a key into a plugin once, so it has to
  outlive a browser session, be revocable, and track the account's *current*
  tier (a Stripe upgrade must not wait for a new token).
- A key is "pyvar_" + 32 random bytes (urlsafe base64). Only its SHA-256 is
  stored: for a high-entropy random secret there is nothing to brute-force, and
  the per-request lookup is a single indexed equality (bcrypt/argon2 would add
  ~100 ms to every call for no security gain here).
- Per-request cost: auth used to be a stateless JWT decode. A key needs the user's
  tier, so the resolved (user, tier) is cached in Redis for
  cfg.api_key_cache_ttl_seconds. A cache hit costs one Redis GET and no database
  connection (the async pool is deliberately small, see storage/session.py).
  Revoking deletes the cache entry, so revocation is immediate on the same Redis;
  a tier change takes at most the TTL.
- Failure modes are asymmetric on purpose. Redis errors fail OPEN to the database
  (it is only a cache). A database error fails CLOSED: get_current_user turns it
  into a 503, never a 401 (a user with a good key must not be told it is bad) and
  never a pass.
- Unknown keys are negatively cached for a short time, and failures are counted
  per client IP, so spraying random keys cannot become unbounded database load.
- last_used_at is refreshed at most hourly, on the (rare) cache-miss path, so
  using a key causes no write per request.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select

from config import get_settings
from storage.models import ApiKey, User
from storage.session import get_sessionmaker

KEY_PREFIX = "pyvar_"
_PREFIX_DISPLAY_CHARS = 14  # "pyvar_" + 8 characters of the secret
_CACHE_PREFIX = "pyvar:apikey:"
_FAIL_PREFIX = "pyvar:apikey-fail:"
_NEGATIVE_TTL_SECONDS = 30
_LAST_USED_REFRESH = timedelta(hours=1)

cfg = get_settings()
logger = structlog.get_logger()


@dataclass(frozen=True)
class ResolvedKey:
    """What a valid key stands for: the account (JWT-style subject) and its tier."""

    key_id: str
    user_id: str
    tier: str


def looks_like_api_key(token: str) -> bool:
    return token.startswith(KEY_PREFIX)


def hash_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Return (secret, display prefix, sha256 hex). The secret is never stored."""
    secret = KEY_PREFIX + secrets.token_urlsafe(32)
    return secret, secret[:_PREFIX_DISPLAY_CHARS], hash_key(secret)


def _aware(value: datetime | None) -> datetime | None:
    """Postgres returns aware datetimes; other backends (tests) may not."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _redis() -> Any:
    # imported here, not at module level: api.routes.caching imports from api.middleware
    from api.routes.caching import _get_redis_client

    return _get_redis_client()


async def _cache_get(digest: str) -> dict[str, Any] | None:
    client = _redis()
    if client is None:
        return None
    try:
        raw = await client.get(_CACHE_PREFIX + digest)
    except Exception:  # noqa: BLE001 - the cache is best-effort, fall through to the database
        logger.warning("api_key_cache_read_failed")
        return None
    return None if raw is None else dict(json.loads(raw))


async def _cache_set(digest: str, value: dict[str, Any], ttl: int) -> None:
    client = _redis()
    if client is None or ttl <= 0:
        return
    try:
        await client.set(_CACHE_PREFIX + digest, json.dumps(value), ex=ttl)
    except Exception:  # noqa: BLE001 - best-effort
        logger.warning("api_key_cache_write_failed")


async def invalidate_cached_key(digest: str) -> None:
    """Drop a key from the cache (called on revoke so it takes effect at once)."""
    client = _redis()
    if client is None:
        return
    try:
        await client.delete(_CACHE_PREFIX + digest)
    except Exception:  # noqa: BLE001 - worst case the TTL bounds it
        logger.warning("api_key_cache_invalidate_failed")


async def too_many_failures(client_ip: str) -> bool:
    """Count one failed key lookup for this IP; True once it exceeds the per-minute limit."""
    client = _redis()
    if client is None:
        return False
    try:
        key = _FAIL_PREFIX + client_ip
        count = int(await client.incr(key))
        if count == 1:
            await client.expire(key, 60)
        return count > cfg.api_key_failed_attempts_per_minute
    except Exception:  # noqa: BLE001 - never lock people out because Redis is down
        return False


async def resolve_api_key(secret: str) -> ResolvedKey | None:
    """Resolve a presented key to its account, or None if unknown/revoked/expired.

    Raises on database failure (the caller maps that to 503, never to "invalid").
    """
    digest = hash_key(secret)
    now = datetime.now(timezone.utc)

    cached = await _cache_get(digest)
    if cached is not None:
        if cached.get("invalid"):
            return None
        expires = _aware(
            datetime.fromisoformat(cached["expires_at"]) if cached.get("expires_at") else None
        )
        if expires is None or expires > now:
            return ResolvedKey(cached["key_id"], cached["user_id"], cached["tier"])
        return None

    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                select(ApiKey, User)
                .join(User, User.id == ApiKey.user_id)
                .where(ApiKey.key_hash == digest, ApiKey.revoked_at.is_(None))
            )
        ).first()
        if row is None:
            await _cache_set(digest, {"invalid": True}, _NEGATIVE_TTL_SECONDS)
            return None
        key, user = row
        expires = _aware(key.expires_at)
        if (expires is not None and expires <= now) or not user.email_verified:
            await _cache_set(digest, {"invalid": True}, _NEGATIVE_TTL_SECONDS)
            return None

        last_used = _aware(key.last_used_at)
        if last_used is None or now - last_used > _LAST_USED_REFRESH:
            key.last_used_at = now
            await session.commit()

        resolved = ResolvedKey(str(key.id), user.external_id, user.tier)

    ttl = cfg.api_key_cache_ttl_seconds
    if expires is not None:
        ttl = min(ttl, int((expires - now).total_seconds()))
    await _cache_set(
        digest,
        {
            "key_id": resolved.key_id,
            "user_id": resolved.user_id,
            "tier": resolved.tier,
            "expires_at": expires.isoformat() if expires else None,
        },
        ttl,
    )
    return resolved
