"""
ingestion/market_data/cache.py — TTL-configurable cache wrapping any MarketDataProvider (MD-2)

Reasoning:
- CachingMarketDataProvider implements the same MarketDataProvider interface
  it wraps, so registry.py can hand callers a cached provider transparently —
  nothing downstream needs to know caching is happening at all.
- Redis client construction/retry policy mirrors api/routes/caching.py's
  _get_redis_client() exactly (same fail-open philosophy: any Redis error —
  including the client being unavailable — is treated as a cache miss, never
  as a reason to fail a lookup or raise). Deliberately its OWN client and key
  prefix ("pyvar:market_data:..."), not a reuse of caching.py's module-level
  singleton: that module lives in api/ and caches whole job results keyed on
  request hashes; this one lives in ingestion/ and caches individual
  per-provider-method market data lookups. ingestion/ has no existing
  dependency on api/, and this keeps it that way.
- Only successful lookups are cached — a ProviderError (or any other
  exception) from the wrapped provider propagates straight through, since
  _cache_get/_cache_set are only consulted around the wrapped provider call,
  never around the exception path itself.
- TTLs are read from config.py's market_data_cache_ttl_* settings at call
  time (not baked into this module) — see config.py's own comment on why
  they're placeholders pending a legal/contract check on Refinitiv's actual
  cache-TTL terms (docs/plan-market-data-adapter.md §3).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from typing import Any

from config import get_settings
from ingestion.market_data.base import MarketDataProvider
from ingestion.market_data.schemas import Instrument, PriceSeries, VolSurface, YieldCurve
from storage.redis_client import redis_url

cfg = get_settings()
logger = logging.getLogger(__name__)

_redis_client: Any = None  # lazily created — see _get_redis_client()


def _get_redis_client() -> Any:
    """Lazily create the async Redis client. Returns None if redis is unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            from redis.backoff import ExponentialBackoff
            from redis.exceptions import ConnectionError as RedisConnectionError
            from redis.exceptions import TimeoutError as RedisTimeoutError
            from redis.retry import Retry

            _redis_client = aioredis.from_url(
                redis_url(),
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30,
                retry=Retry(ExponentialBackoff(cap=0.2, base=0.02), retries=2),
                retry_on_error=[RedisConnectionError, RedisTimeoutError],
            )
        except Exception:  # noqa: BLE001 — cache must never block a lookup
            logger.warning("Redis cache client unavailable — market data caching disabled")
            return None
    return _redis_client


def _cache_key(provider_name: str, method: str, params: dict[str, Any]) -> str:
    """Deterministic key: SHA-256 of the canonical (sort_keys) JSON of params."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"pyvar:market_data:{provider_name}:{method}:{digest}"


async def _cache_get(provider_name: str, method: str, params: dict[str, Any]) -> str | None:
    client = _get_redis_client()
    if client is None:
        return None
    try:
        raw = await client.get(_cache_key(provider_name, method, params))
    except Exception:  # noqa: BLE001 — best-effort, never fail the lookup
        logger.warning(
            "Market data cache read failed — treating as cache miss",
            extra={"provider": provider_name, "method": method},
        )
        return None
    return raw  # type: ignore[no-any-return]


async def _cache_set(
    provider_name: str,
    method: str,
    params: dict[str, Any],
    raw_json: str,
    ttl_seconds: int,
) -> None:
    client = _get_redis_client()
    if client is None:
        return
    try:
        await client.set(_cache_key(provider_name, method, params), raw_json, ex=ttl_seconds)
    except Exception:  # noqa: BLE001 — best-effort, never fail the lookup
        logger.warning(
            "Market data cache write failed — result not cached",
            extra={"provider": provider_name, "method": method},
        )


class CachingMarketDataProvider(MarketDataProvider):
    """Wraps another MarketDataProvider with a TTL Redis cache, per method.

    TTLs (config.py market_data_cache_ttl_*) are placeholders pending the
    legal/contract check on Refinitiv's actual cache-TTL terms (see
    docs/plan-market-data-adapter.md §3) — safe to use with the fake
    provider now; MUST be revisited before MD-3 wires up a real vendor.
    """

    def __init__(self, inner: MarketDataProvider) -> None:
        self._inner = inner
        self.name = inner.name

    async def resolve_instrument(self, isin: str) -> Instrument:
        params = {"isin": isin}
        cached = await _cache_get(self.name, "resolve_instrument", params)
        if cached is not None:
            return Instrument.model_validate_json(cached)

        result = await self._inner.resolve_instrument(isin)
        await _cache_set(
            self.name,
            "resolve_instrument",
            params,
            result.model_dump_json(),
            cfg.market_data_cache_ttl_instrument_seconds,
        )
        return result

    async def get_price_series(self, instrument: Instrument, start: date, end: date) -> PriceSeries:
        params = {"isin": instrument.isin, "start": start.isoformat(), "end": end.isoformat()}
        cached = await _cache_get(self.name, "get_price_series", params)
        if cached is not None:
            return PriceSeries.model_validate_json(cached)

        result = await self._inner.get_price_series(instrument, start, end)
        await _cache_set(
            self.name,
            "get_price_series",
            params,
            result.model_dump_json(),
            cfg.market_data_cache_ttl_price_series_seconds,
        )
        return result

    async def get_yield_curve(self, currency: str, as_of: date) -> YieldCurve:
        params = {"currency": currency, "as_of": as_of.isoformat()}
        cached = await _cache_get(self.name, "get_yield_curve", params)
        if cached is not None:
            return YieldCurve.model_validate_json(cached)

        result = await self._inner.get_yield_curve(currency, as_of)
        await _cache_set(
            self.name,
            "get_yield_curve",
            params,
            result.model_dump_json(),
            cfg.market_data_cache_ttl_yield_curve_seconds,
        )
        return result

    async def get_vol_surface(self, instrument: Instrument, as_of: date) -> VolSurface:
        params = {"isin": instrument.isin, "as_of": as_of.isoformat()}
        cached = await _cache_get(self.name, "get_vol_surface", params)
        if cached is not None:
            return VolSurface.model_validate_json(cached)

        result = await self._inner.get_vol_surface(instrument, as_of)
        await _cache_set(
            self.name,
            "get_vol_surface",
            params,
            result.model_dump_json(),
            cfg.market_data_cache_ttl_vol_surface_seconds,
        )
        return result
