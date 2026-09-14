"""
ingestion/market_data — vendor-agnostic live market data adapters (MD-1 + MD-2)

Reasoning:
- Part of the market data adapter infrastructure (see
  docs/plan-market-data-adapter.md). MD-1 (base.py, schemas.py,
  exceptions.py, providers/fake.py) and MD-2 (registry.py's config-driven
  provider selection, cache.py's TTL Redis cache) are both here now. No
  network calls anywhere in this subtree yet — the real Refinitiv adapter
  (MD-3) and wiring into tasks/var_task.py (MD-4) stay out of scope until
  the open decisions in docs/plan-market-data-adapter.md §3 are answered
  (MD-2's cache TTLs are placeholder values for the same reason — see
  config.py's own comment on them).
- `engine/`, `api/`, and `storage/` must never import from
  `market_data.providers` directly — they consume the canonical schemas
  in `schemas.py` only (and, once MD-4 wires it up, `registry.get_provider()`),
  so a provider is fully swappable without touching those layers.
"""

from __future__ import annotations
