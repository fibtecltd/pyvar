"""
ingestion/market_data/base.py — MarketDataProvider abstract interface

Reasoning:
- One interface every provider (fake, and eventually refinitiv, per MD-3)
  implements identically, so engine/tasks code (once wired, per MD-4) never
  branches on which vendor is active.
- All methods are async: real providers (RDP, or any future vendor) are
  network I/O bound, and the fake provider's async methods let the same
  call sites work unchanged once a real provider is swapped in via the
  registry (MD-2) — no sync/async mismatch to paper over later.
- Every method's docstring states which exceptions.py error it raises so a
  caller can catch ProviderError (or a specific subclass) without reading
  each provider's implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ingestion.market_data.schemas import (
    Instrument,
    PriceSeries,
    VolSurface,
    YieldCurve,
)


class MarketDataProvider(ABC):
    """Vendor-agnostic market data provider interface.

    Attributes:
        name: Provider identifier used in schema `source` fields and in
            observability tags (structlog `provider` field, Prometheus
            `market_data_requests_total{provider}` counter — per MD-2/MD-3,
            not yet wired).
    """

    name: str

    @abstractmethod
    async def resolve_instrument(self, isin: str) -> Instrument:
        """Resolve a canonical ISIN to an Instrument.

        Args:
            isin: 12-character ISO 6166 instrument identifier.

        Returns:
            The resolved Instrument.

        Raises:
            InstrumentNotFoundError: The ISIN is not known to this provider.
            EntitlementError: The instrument exists but is not licensed
                under this provider's current entitlements.
        """

    @abstractmethod
    async def get_price_series(self, instrument: Instrument, start: date, end: date) -> PriceSeries:
        """Fetch a closing price time series for an instrument.

        Args:
            instrument: The instrument to fetch prices for.
            start: Inclusive start date.
            end: Inclusive end date.

        Returns:
            A PriceSeries covering [start, end], ordered ascending by date.

        Raises:
            EntitlementError: The instrument's price history is not
                licensed under this provider's current entitlements.
            RateLimitError: The provider's rate limit has been exceeded.
        """

    @abstractmethod
    async def get_yield_curve(self, currency: str, as_of: date) -> YieldCurve:
        """Fetch a yield curve snapshot for a currency.

        Args:
            currency: ISO 4217 currency code, e.g. "GBP".
            as_of: Curve snapshot date.

        Returns:
            The YieldCurve for that currency and date.

        Raises:
            EntitlementError: Yield curve data for this currency is not
                licensed under this provider's current entitlements.
            RateLimitError: The provider's rate limit has been exceeded.
        """

    @abstractmethod
    async def get_vol_surface(self, instrument: Instrument, as_of: date) -> VolSurface:
        """Fetch an implied volatility surface for an instrument.

        Args:
            instrument: The instrument to fetch the surface for.
            as_of: Surface snapshot date.

        Returns:
            The VolSurface for that instrument and date.

        Raises:
            EntitlementError: Volatility data for this instrument is not
                licensed under this provider's current entitlements.
            RateLimitError: The provider's rate limit has been exceeded.
        """
