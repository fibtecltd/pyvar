"""
ingestion/market_data/exceptions.py — provider error family

Reasoning:
- Every MarketDataProvider method raises from this module so callers
  (eventually tasks/var_task.py, per MD-4) can catch one exception family
  regardless of which provider is active, instead of coding against
  vendor-specific exception types.
- ProviderError carries the provider name so a caught exception is
  attributable in logs/Sentry without the caller having to know which
  provider raised it.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all market data provider failures.

    Args:
        provider: Provider name (e.g. "fake", "refinitiv") — attached so a
            caller catching the base class can still tell which provider
            raised it.
        message: Human-readable failure description.
    """

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        self.message = message
        super().__init__(f"[{provider}] {message}")


class EntitlementError(ProviderError):
    """Raised when the requested instrument/data is not licensed for this provider."""


class RateLimitError(ProviderError):
    """Raised when the provider's rate limit has been exceeded."""


class InstrumentNotFoundError(ProviderError):
    """Raised when an instrument identifier (e.g. ISIN) cannot be resolved."""
