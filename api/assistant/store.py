"""
api/assistant/store.py — the gateway's shared state in Redis: today's model spend and the kill switch

Reasoning:
- Two facts must be the same on every API task, so they live in the ElastiCache cluster the rate limiter and
  the result cache already use (storage/redis_client.py::redis_url()), under their own `pyvar:assistant:` keys:
  * the day's model spend, in millionths of a dollar (an integer, so INCRBY is exact and there is no float
    drift), one key per UTC day with a three-day expiry; the route adds each answer's cost after it is made;
  * a kill switch, the key `pyvar:assistant:kill`. Any value turns the route off at once on every task, with
    no deploy: `redis-cli SET pyvar:assistant:kill 1`; `DEL` turns it back on. (The deploy-time flag
    `assistant_typed_enabled` is the other half of the switch; this one is for an incident.)
- Both are read in ONE round trip (MGET) before every question.
- Unlike the rate limiter, reading this FAILS CLOSED. The limiter fails open because it is an anti-abuse
  measure and a cache blip must not lock everyone out of the compute API. This is the cost control for a
  paid external API: if the spend cannot be read, the route cannot know whether the cap has been reached, so
  it answers 503 and the portal's menu buttons (which need no model) keep working. Writing the spend after
  an answer fails OPEN (logged and counted): the visitor already has the answer, and the next question's read
  will fail closed if Redis is really down.
- The cap is a circuit breaker, not an exact meter: spend is added after an answer, so questions already in
  flight when the cap is reached still finish. The overshoot is bounded by `assistant_max_concurrent` x
  `assistant_max_usd_per_question` per API task.
- The client is built lazily and tuned like api/routes/caching.py's (idle-connection health checks and a
  short retry), because ElastiCache Serverless drops idle connections the same way.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import structlog

from api.assistant.metrics import SPEND_NOT_RECORDED
from storage.redis_client import redis_url

logger = structlog.get_logger()

KILL_KEY = "pyvar:assistant:kill"
SPEND_PREFIX = "pyvar:assistant:spend:"
MICRO = 1_000_000
SPEND_TTL_SECONDS = 3 * 86_400


class StoreUnavailable(Exception):
    """The spend and kill-switch keys could not be read."""


@dataclass(frozen=True)
class Gate:
    """What the store says before a question is answered.

    Attributes:
        killed: the kill switch is set.
        spent_usd: model dollars recorded so far today (UTC).
    """

    killed: bool
    spent_usd: float


def spend_key(now: dt.datetime) -> str:
    """The Redis key of the UTC day containing `now`."""
    return f"{SPEND_PREFIX}{now.astimezone(dt.timezone.utc).date().isoformat()}"


def seconds_until_utc_midnight(now: dt.datetime) -> int:
    """Whole seconds from `now` to the next 00:00 UTC (at least 1): when a spend cap resets."""
    utc = now.astimezone(dt.timezone.utc)
    midnight = (utc + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - utc).total_seconds()))


def _build_client() -> Any:
    """The async Redis client, tuned like api/routes/caching.py's (see the module docstring)."""
    import redis.asyncio as aioredis
    from redis.backoff import ExponentialBackoff
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError
    from redis.retry import Retry

    return aioredis.from_url(
        redis_url(),
        decode_responses=True,
        socket_keepalive=True,
        health_check_interval=30,
        retry=Retry(ExponentialBackoff(cap=0.2, base=0.02), retries=2),
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
    )


class AssistantStore:
    """Reads the gate and records spend. `client` is any async Redis-like object (a test passes a fake)."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _redis(self) -> Any:
        if self._client is None:
            self._client = _build_client()
        return self._client

    def client(self) -> Any:
        """The async Redis client, built on first use (the watchdog shares it)."""
        return self._redis()

    async def gate(self, now: dt.datetime | None = None) -> Gate:
        """The kill switch and today's spend, in one round trip.

        Raises:
            StoreUnavailable: the keys could not be read (fail closed, see the module docstring).
        """
        now = now or dt.datetime.now(dt.timezone.utc)
        try:
            killed, spent = await self._redis().mget([KILL_KEY, spend_key(now)])
            return Gate(killed is not None, int(spent or 0) / MICRO)
        except (
            Exception
        ) as exc:  # noqa: BLE001 — any storage or parsing failure means "cannot tell"
            raise StoreUnavailable(type(exc).__name__) from exc

    async def add_spend(self, usd: float, now: dt.datetime | None = None) -> None:
        """Add `usd` to today's spend. Fails open: an error is logged and counted, never raised."""
        micro = round(usd * MICRO)
        if micro <= 0:
            return
        key = spend_key(now or dt.datetime.now(dt.timezone.utc))
        try:
            async with self._redis().pipeline(transaction=True) as pipe:
                pipe.incrby(key, micro)
                pipe.expire(key, SPEND_TTL_SECONDS)
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001 — the visitor already has the answer
            SPEND_NOT_RECORDED.inc()
            logger.warning(
                "assistant_spend_not_recorded", error=type(exc).__name__, micro_usd=micro
            )


_store: AssistantStore | None = None


def get_store() -> AssistantStore:
    """The process-wide store (a FastAPI dependency, so a test overrides it)."""
    global _store
    if _store is None:
        _store = AssistantStore()
    return _store
