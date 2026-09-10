"""
ingestion/market_data/providers/fake.py — in-memory MarketDataProvider for tests/local dev

Reasoning:
- Per docs/plan-market-data-adapter.md §9: unit tests must run entirely
  against this provider — no network, no credentials, always runs in CI.
  It's also the first half of the MD-1..MD-3 contract test (§9/§13): once
  providers/refinitiv.py exists (MD-3), the same assertions run against
  both providers to guarantee this fake never drifts from the real
  interface's actual behavior.
- Deterministic by construction: every generated value derives from
  np.random.default_rng() seeded from (instance seed, ISIN/currency, data
  kind), the same "seed -> reproducible output" discipline as
  ingestion/fixtures.py's generate_gbm_returns. zlib.crc32 (not the
  built-in hash()) mixes the seed components, since str hashing is
  randomized per-process by default (PYTHONHASHSEED) and would make two
  runs of the same test produce different fixture data.
- A fixed, small ISIN universe is exposed so tests can exercise every
  branch of the interface: a normal instrument, one that raises
  EntitlementError (simulating a not-licensed instrument), and any ISIN
  outside the map raising InstrumentNotFoundError.
"""

from __future__ import annotations

import zlib
from datetime import date, timedelta

import numpy as np

from ingestion.market_data.base import MarketDataProvider
from ingestion.market_data.exceptions import EntitlementError, InstrumentNotFoundError
from ingestion.market_data.schemas import (
    Instrument,
    PricePoint,
    PriceSeries,
    VolPoint,
    VolSurface,
    YieldCurve,
)

# Deliberately synthetic ISINs ("ZZ" is not an assigned ISO 3166-1 country
# code) so fixture data can never be mistaken for a real instrument.
_FIXTURE_CURRENCIES: dict[str, str] = {
    "ZZ0000000001": "GBP",
    "ZZ0000000002": "USD",
    "ZZ0000000003": "EUR",
}
_ENTITLEMENT_RESTRICTED_ISIN = "ZZ0000000099"

_CURVE_TENORS = ("1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y")
_VOL_TENORS = ("1M", "3M", "6M", "1Y")
_VOL_STRIKES = (80.0, 90.0, 100.0, 110.0, 120.0)


class FakeMarketDataProvider(MarketDataProvider):
    """Deterministic in-memory provider — no network calls, ever."""

    name = "fake"

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def _rng_for(self, *parts: object) -> np.random.Generator:
        """Derive a deterministic RNG from the instance seed and arbitrary parts."""
        key = "|".join(str(p) for p in parts)
        derived_seed = (self._seed + zlib.crc32(key.encode())) % (2**32)
        return np.random.default_rng(derived_seed)

    async def resolve_instrument(self, isin: str) -> Instrument:
        isin = isin.upper()
        if isin == _ENTITLEMENT_RESTRICTED_ISIN:
            raise EntitlementError(
                self.name, f"Instrument {isin} is not licensed for this provider."
            )
        currency = _FIXTURE_CURRENCIES.get(isin)
        if currency is None:
            raise InstrumentNotFoundError(
                self.name, f"ISIN {isin} is not known to the fake provider."
            )
        return Instrument(isin=isin, currency=currency)

    async def get_price_series(self, instrument: Instrument, start: date, end: date) -> PriceSeries:
        if end < start:
            raise ValueError(f"end ({end}) must not be before start ({start}).")

        rng = self._rng_for(instrument.isin, "price")
        points: list[PricePoint] = []
        current = start
        price = 100.0
        while current <= end:
            if current.weekday() < 5:  # business days only, like real price feeds
                price = max(price + float(rng.normal(loc=0.0, scale=1.0)), 0.01)
                points.append(PricePoint(as_of=current, close=price, currency=instrument.currency))
            current += timedelta(days=1)

        return PriceSeries(instrument=instrument, points=points, source=self.name)

    async def get_yield_curve(self, currency: str, as_of: date) -> YieldCurve:
        currency = currency.upper()
        rng = self._rng_for(currency, "curve", as_of.isoformat())
        tenors = {tenor: float(rng.uniform(0.01, 0.06)) for tenor in _CURVE_TENORS}
        return YieldCurve(currency=currency, as_of=as_of, tenors=tenors, source=self.name)

    async def get_vol_surface(self, instrument: Instrument, as_of: date) -> VolSurface:
        rng = self._rng_for(instrument.isin, "vol", as_of.isoformat())
        points = [
            VolPoint(strike=strike, tenor=tenor, implied_vol=float(rng.uniform(0.10, 0.40)))
            for tenor in _VOL_TENORS
            for strike in _VOL_STRIKES
        ]
        return VolSurface(instrument=instrument, as_of=as_of, points=points, source=self.name)
