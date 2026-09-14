"""
ingestion/market_data/registry.py — config-driven provider selection (MD-2)

Reasoning:
- The one place that knows about every concrete provider class. Callers
  (eventually tasks/var_task.py, per MD-4) ask get_provider() for "the
  configured provider" and never import a providers/*.py module directly —
  that's what keeps a vendor swap (fake -> refinitiv) a one-line config
  change (config.py's market_data_provider) instead of a code change at
  every call site.
- "fake" is the only registered provider until MD-3 lands
  providers/refinitiv.py — registering it here now, rather than waiting for
  MD-3, means MD-4's eventual wiring only has to add one dict entry, not
  build the registry mechanism from scratch under time pressure.
- Wraps the selected provider in CachingMarketDataProvider (MD-2's other
  half, cache.py) by default, since that's how every real caller should get
  it. cached=False exists for callers that genuinely need to bypass the
  cache (e.g. a future admin/debug endpoint, or the contract test comparing
  two providers directly per docs/plan-market-data-adapter.md §9) rather
  than forcing them to reach into cache.py themselves.
"""

from __future__ import annotations

from config import get_settings
from ingestion.market_data.base import MarketDataProvider
from ingestion.market_data.cache import CachingMarketDataProvider
from ingestion.market_data.providers.fake import FakeMarketDataProvider

cfg = get_settings()

_PROVIDERS: dict[str, type[MarketDataProvider]] = {
    "fake": FakeMarketDataProvider,
}


def get_provider(*, cached: bool = True) -> MarketDataProvider:
    """Construct the provider named by config.py's market_data_provider.

    Args:
        cached: When True (default), wraps the selected provider in
            CachingMarketDataProvider. Set False for a caller that needs
            uncached results directly from the provider.

    Returns:
        A ready-to-use MarketDataProvider.

    Raises:
        ValueError: cfg.market_data_provider names a provider not
            registered in _PROVIDERS.
    """
    provider_cls = _PROVIDERS.get(cfg.market_data_provider)
    if provider_cls is None:
        raise ValueError(
            f"Unknown market data provider {cfg.market_data_provider!r} "
            f"(config.py market_data_provider) — registered providers: "
            f"{sorted(_PROVIDERS)}."
        )

    provider = provider_cls()
    if cached:
        return CachingMarketDataProvider(provider)
    return provider
