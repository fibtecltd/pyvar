"""
tests/test_market_data_registry_and_cache.py — MD-2 unit tests

Reasoning:
- registry.py and cache.py are exercised together since registry.get_provider()
  is the only way most callers will ever construct a CachingMarketDataProvider.
- Redis is never hit for real here (CLAUDE.md §5 Rule 3: "Never use real AWS
  services in tests" — extended to Redis by the exact same rationale this
  suite already applies to api/routes/caching.py and
  api/middleware/rate_limit.py: a real backing service must never be reached
  from a test run). cache.py's own module-level _cache_get/_cache_set are
  patched directly, matching tests/test_api.py's established pattern for
  api/routes/caching.py rather than mocking the redis client itself.
- Cache-hit tests assert the wrapped provider's method is NOT called at all
  (not just that the returned value matches) — that's the actual behavior
  MD-2 exists to deliver, so asserting only the return value would pass even
  if the cache accidentally always missed.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from ingestion.market_data.base import MarketDataProvider
from ingestion.market_data.cache import CachingMarketDataProvider, _cache_key
from ingestion.market_data.exceptions import InstrumentNotFoundError
from ingestion.market_data.providers.fake import FakeMarketDataProvider
from ingestion.market_data.registry import _PROVIDERS, get_provider
from ingestion.market_data.schemas import Instrument, PriceSeries, VolSurface, YieldCurve

KNOWN_ISIN = "ZZ0000000001"

# ── registry.py ───────────────────────────────────────────────────────────────


def test_get_provider_returns_a_caching_wrapper_by_default() -> None:
    provider = get_provider()

    assert isinstance(provider, CachingMarketDataProvider)
    assert isinstance(provider, MarketDataProvider)
    assert provider.name == "fake"


def test_get_provider_cached_false_returns_the_bare_provider() -> None:
    provider = get_provider(cached=False)

    assert isinstance(provider, FakeMarketDataProvider)
    assert not isinstance(provider, CachingMarketDataProvider)


def test_get_provider_rejects_an_unknown_provider_name() -> None:
    with patch("ingestion.market_data.registry.cfg") as mock_cfg:
        mock_cfg.market_data_provider = "not-a-real-provider"

        with pytest.raises(ValueError, match="Unknown market data provider"):
            get_provider()


def test_fake_is_the_only_registered_provider_until_md3() -> None:
    """MD-3 (providers/refinitiv.py) is the only thing expected to add a second entry."""
    assert set(_PROVIDERS) == {"fake"}


# ── cache.py ──────────────────────────────────────────────────────────────────


@pytest.fixture
def inner_provider() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(seed=42)


@pytest.fixture
def caching_provider(inner_provider: FakeMarketDataProvider) -> CachingMarketDataProvider:
    return CachingMarketDataProvider(inner_provider)


def test_caching_provider_implements_the_interface_and_keeps_inner_name(
    caching_provider: CachingMarketDataProvider,
) -> None:
    assert isinstance(caching_provider, MarketDataProvider)
    assert caching_provider.name == "fake"


@pytest.mark.asyncio
async def test_resolve_instrument_cache_miss_calls_inner_and_writes_cache(
    caching_provider: CachingMarketDataProvider,
) -> None:
    with (
        patch("ingestion.market_data.cache._cache_get", return_value=None),
        patch("ingestion.market_data.cache._cache_set") as mock_set,
    ):
        result = await caching_provider.resolve_instrument(KNOWN_ISIN)

    assert isinstance(result, Instrument)
    assert result.isin == KNOWN_ISIN
    mock_set.assert_awaited_once()
    args = mock_set.await_args.args
    assert args[0] == "fake"
    assert args[1] == "resolve_instrument"
    assert args[3] == result.model_dump_json()


@pytest.mark.asyncio
async def test_resolve_instrument_cache_hit_never_calls_inner_provider(
    inner_provider: FakeMarketDataProvider, caching_provider: CachingMarketDataProvider
) -> None:
    cached_instrument = Instrument(isin=KNOWN_ISIN, currency="GBP")
    inner_provider.resolve_instrument = AsyncMock(side_effect=AssertionError("must not be called"))  # type: ignore[method-assign]

    with patch(
        "ingestion.market_data.cache._cache_get",
        return_value=cached_instrument.model_dump_json(),
    ):
        result = await caching_provider.resolve_instrument(KNOWN_ISIN)

    assert result == cached_instrument
    inner_provider.resolve_instrument.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_instrument_provider_error_is_never_cached(
    caching_provider: CachingMarketDataProvider,
) -> None:
    with (
        patch("ingestion.market_data.cache._cache_get", return_value=None),
        patch("ingestion.market_data.cache._cache_set") as mock_set,
    ):
        with pytest.raises(InstrumentNotFoundError):
            await caching_provider.resolve_instrument("ZZ0000000404")

    mock_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_price_series_cache_miss_uses_the_configured_ttl(
    caching_provider: CachingMarketDataProvider,
) -> None:
    instrument = Instrument(isin=KNOWN_ISIN, currency="GBP")
    start, end = date(2026, 1, 5), date(2026, 1, 9)

    with (
        patch("ingestion.market_data.cache._cache_get", return_value=None),
        patch("ingestion.market_data.cache._cache_set") as mock_set,
        patch("ingestion.market_data.cache.cfg") as mock_cfg,
    ):
        mock_cfg.market_data_cache_ttl_price_series_seconds = 123
        await caching_provider.get_price_series(instrument, start, end)

    assert mock_set.await_args.args[1] == "get_price_series"
    assert mock_set.await_args.args[4] == 123


@pytest.mark.asyncio
async def test_get_price_series_cache_hit_returns_a_price_series(
    inner_provider: FakeMarketDataProvider, caching_provider: CachingMarketDataProvider
) -> None:
    instrument = Instrument(isin=KNOWN_ISIN, currency="GBP")
    cached_series = PriceSeries(instrument=instrument, points=[], source="fake")
    inner_provider.get_price_series = AsyncMock(side_effect=AssertionError("must not be called"))  # type: ignore[method-assign]

    with patch(
        "ingestion.market_data.cache._cache_get", return_value=cached_series.model_dump_json()
    ):
        result = await caching_provider.get_price_series(
            instrument, date(2026, 1, 5), date(2026, 1, 9)
        )

    assert result == cached_series
    inner_provider.get_price_series.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_yield_curve_cache_hit_returns_a_yield_curve(
    inner_provider: FakeMarketDataProvider, caching_provider: CachingMarketDataProvider
) -> None:
    cached_curve = YieldCurve(
        currency="GBP", as_of=date(2026, 1, 5), tenors={"1Y": 0.05}, source="fake"
    )
    inner_provider.get_yield_curve = AsyncMock(side_effect=AssertionError("must not be called"))  # type: ignore[method-assign]

    with patch(
        "ingestion.market_data.cache._cache_get", return_value=cached_curve.model_dump_json()
    ):
        result = await caching_provider.get_yield_curve("GBP", date(2026, 1, 5))

    assert result == cached_curve
    inner_provider.get_yield_curve.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_vol_surface_cache_hit_returns_a_vol_surface(
    inner_provider: FakeMarketDataProvider, caching_provider: CachingMarketDataProvider
) -> None:
    instrument = Instrument(isin=KNOWN_ISIN, currency="GBP")
    cached_surface = VolSurface(
        instrument=instrument, as_of=date(2026, 1, 5), points=[], source="fake"
    )
    inner_provider.get_vol_surface = AsyncMock(side_effect=AssertionError("must not be called"))  # type: ignore[method-assign]

    with patch(
        "ingestion.market_data.cache._cache_get", return_value=cached_surface.model_dump_json()
    ):
        result = await caching_provider.get_vol_surface(instrument, date(2026, 1, 5))

    assert result == cached_surface
    inner_provider.get_vol_surface.assert_not_awaited()


def test_cache_key_is_deterministic_regardless_of_dict_order() -> None:
    key_a = _cache_key("fake", "resolve_instrument", {"isin": KNOWN_ISIN, "x": 1})
    key_b = _cache_key("fake", "resolve_instrument", {"x": 1, "isin": KNOWN_ISIN})

    assert key_a == key_b
    assert key_a.startswith("pyvar:market_data:fake:resolve_instrument:")


@pytest.mark.asyncio
async def test_cache_get_fails_open_when_redis_client_is_unavailable() -> None:
    from ingestion.market_data.cache import _cache_get

    with patch("ingestion.market_data.cache._get_redis_client", return_value=None):
        result = await _cache_get("fake", "resolve_instrument", {"isin": KNOWN_ISIN})

    assert result is None


@pytest.mark.asyncio
async def test_cache_set_fails_open_when_the_redis_call_raises() -> None:
    from ingestion.market_data.cache import _cache_set

    broken_client = AsyncMock()
    broken_client.set.side_effect = ConnectionError("simulated Redis outage")

    with patch("ingestion.market_data.cache._get_redis_client", return_value=broken_client):
        # Must not raise — best-effort write, same fail-open contract as _cache_get.
        await _cache_set("fake", "resolve_instrument", {"isin": KNOWN_ISIN}, "{}", 60)
