"""
tests/test_market_data_fake_provider.py — MD-1 unit tests

Reasoning:
- Runs entirely against FakeMarketDataProvider per
  docs/plan-market-data-adapter.md §9 — no network calls, no credentials,
  always green in CI. This IS the "no network calls anywhere" contract
  test suite the plan's §13 definition of done for MD-1 requires; once
  providers/refinitiv.py exists (MD-3) the shared assertions below should
  be parametrized to run against both providers (the plan's own
  "contract test" requirement), not duplicated.
- Exercises every exceptions.py branch the fake provider can raise
  (InstrumentNotFoundError, EntitlementError) so a caller relying on the
  ProviderError family (once tasks/var_task.py is wired, per MD-4) can
  trust these are reachable, not just declared in base.py's docstrings.
- Determinism is asserted directly (same seed -> identical output across
  two independent provider instances) since MD-2's cache and MD-3's
  contract test both depend on the fake provider being reproducible.
"""

from __future__ import annotations

from datetime import date

import pytest

from ingestion.market_data.base import MarketDataProvider
from ingestion.market_data.exceptions import (
    EntitlementError,
    InstrumentNotFoundError,
    ProviderError,
)
from ingestion.market_data.providers.fake import FakeMarketDataProvider
from ingestion.market_data.schemas import Instrument

KNOWN_ISIN = "ZZ0000000001"
UNKNOWN_ISIN = "ZZ0000000404"
RESTRICTED_ISIN = "ZZ0000000099"


@pytest.fixture
def provider() -> FakeMarketDataProvider:
    return FakeMarketDataProvider(seed=42)


# ── Interface conformance ────────────────────────────────────────────────────


def test_fake_provider_implements_the_interface(provider: FakeMarketDataProvider) -> None:
    assert isinstance(provider, MarketDataProvider)
    assert provider.name == "fake"


# ── resolve_instrument ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_instrument_returns_a_known_instrument(
    provider: FakeMarketDataProvider,
) -> None:
    instrument = await provider.resolve_instrument(KNOWN_ISIN)

    assert isinstance(instrument, Instrument)
    assert instrument.isin == KNOWN_ISIN
    assert instrument.currency == "GBP"


@pytest.mark.asyncio
async def test_resolve_instrument_is_case_insensitive(provider: FakeMarketDataProvider) -> None:
    instrument = await provider.resolve_instrument(KNOWN_ISIN.lower())

    assert instrument.isin == KNOWN_ISIN


@pytest.mark.asyncio
async def test_resolve_instrument_raises_not_found_for_unknown_isin(
    provider: FakeMarketDataProvider,
) -> None:
    with pytest.raises(InstrumentNotFoundError) as exc_info:
        await provider.resolve_instrument(UNKNOWN_ISIN)

    assert isinstance(exc_info.value, ProviderError)
    assert exc_info.value.provider == "fake"


@pytest.mark.asyncio
async def test_resolve_instrument_raises_entitlement_error_for_restricted_isin(
    provider: FakeMarketDataProvider,
) -> None:
    with pytest.raises(EntitlementError):
        await provider.resolve_instrument(RESTRICTED_ISIN)


# ── get_price_series ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_price_series_covers_the_requested_range(
    provider: FakeMarketDataProvider,
) -> None:
    instrument = await provider.resolve_instrument(KNOWN_ISIN)
    start, end = date(2026, 1, 5), date(2026, 1, 9)  # Mon-Fri, one full business week

    series = await provider.get_price_series(instrument, start, end)

    assert series.source == "fake"
    assert series.instrument == instrument
    assert len(series.points) == 5
    assert all(p.currency == instrument.currency for p in series.points)
    assert all(p.close > 0 for p in series.points)
    assert series.points[0].as_of == start
    assert series.points[-1].as_of == end


@pytest.mark.asyncio
async def test_get_price_series_excludes_weekends(provider: FakeMarketDataProvider) -> None:
    instrument = await provider.resolve_instrument(KNOWN_ISIN)
    # Sat 2026-01-10 to Sun 2026-01-11 — no business days in range.
    series = await provider.get_price_series(instrument, date(2026, 1, 10), date(2026, 1, 11))

    assert series.points == []


@pytest.mark.asyncio
async def test_get_price_series_rejects_end_before_start(
    provider: FakeMarketDataProvider,
) -> None:
    instrument = await provider.resolve_instrument(KNOWN_ISIN)

    with pytest.raises(ValueError, match="must not be before"):
        await provider.get_price_series(instrument, date(2026, 1, 9), date(2026, 1, 5))


@pytest.mark.asyncio
async def test_get_price_series_is_deterministic_for_the_same_seed(
    provider: FakeMarketDataProvider,
) -> None:
    other = FakeMarketDataProvider(seed=42)
    instrument = await provider.resolve_instrument(KNOWN_ISIN)
    start, end = date(2026, 1, 5), date(2026, 1, 9)

    series_a = await provider.get_price_series(instrument, start, end)
    series_b = await other.get_price_series(instrument, start, end)

    assert series_a.points == series_b.points


# ── get_yield_curve ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_yield_curve_returns_all_expected_tenors(
    provider: FakeMarketDataProvider,
) -> None:
    curve = await provider.get_yield_curve("gbp", date(2026, 1, 5))

    assert curve.currency == "GBP"
    assert set(curve.tenors) == {"1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y"}
    assert all(0.0 < rate < 1.0 for rate in curve.tenors.values())
    assert curve.source == "fake"


# ── get_vol_surface ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_vol_surface_returns_points_for_every_strike_and_tenor(
    provider: FakeMarketDataProvider,
) -> None:
    instrument = await provider.resolve_instrument(KNOWN_ISIN)

    surface = await provider.get_vol_surface(instrument, date(2026, 1, 5))

    assert surface.instrument == instrument
    assert len(surface.points) == 4 * 5  # 4 tenors x 5 strikes
    assert all(p.implied_vol > 0 for p in surface.points)


# ── Compliance boundary (plan §13 definition of done) ────────────────────────


def test_no_engine_api_or_storage_module_imports_a_provider() -> None:
    """No file under engine/, api/, or storage/ may import market_data.providers.

    This is the compliance-adjacent guarantee from
    docs/plan-market-data-adapter.md §13: the engine stays data-agnostic and
    a provider is fully swappable without touching those layers. Enforced
    here as a static source scan rather than an import-time assertion, so
    it fails loudly in CI even if nothing currently exercises the import.
    """
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    offending: list[str] = []
    for layer in ("engine", "api", "storage"):
        for path in (repo_root / layer).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "market_data.providers" in text or "market_data import providers" in text:
                offending.append(str(path.relative_to(repo_root)))

    assert offending == [], f"market_data.providers imported from a forbidden layer: {offending}"
