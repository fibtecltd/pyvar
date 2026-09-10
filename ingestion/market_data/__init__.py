"""
ingestion/market_data — vendor-agnostic live market data adapters (MD-1)

Reasoning:
- Part of the market data adapter infrastructure (see
  docs/plan-market-data-adapter.md). This is MD-1 only: the abstract
  provider interface, canonical Pydantic schemas, the exception family, and
  an in-memory fake provider for tests/local dev. No network calls
  anywhere in this subtree yet — the real Refinitiv adapter (MD-3),
  config-driven registry + cache (MD-2), and wiring into tasks/var_task.py
  (MD-4) are deliberately out of scope until the open decisions in
  docs/plan-market-data-adapter.md §3 are answered.
- `engine/`, `api/`, and `storage/` must never import from
  `market_data.providers` directly — they consume the canonical schemas
  in `schemas.py` only, so a provider is fully swappable without touching
  those layers.
"""

from __future__ import annotations
