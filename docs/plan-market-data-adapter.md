# Plan: market data adapter infrastructure (Refinitiv first)

**Item 6 of 6** in `docs/roadmap-six-open-initiatives.md`. Ranked hardest:
the largest engineering effort of the six, the only one touching a genuine
compliance boundary (vendor data-redistribution restrictions), and the
only one where a complete design already exists as an attachment
(`pyvarmarketdataadapterplan.md`) rather than needing one written from
scratch here. This plan verifies that design against the current repo and
separates what's genuinely unblocked from what isn't.

## 1. Verified against the repo — the attached plan's assumptions hold up

- **Nothing here exists yet.** Unlike item 2 (`pyvar-local`), this is
  real, unbuilt work — no `ingestion/market_data/` directory, no
  Refinitiv reference anywhere in the codebase.
- **The retry/backoff pattern the plan says to reuse is real**:
  `tasks/var_task.py` already has `max_retries=2`,
  `default_retry_delay=5`, and a working `self.retry(exc=exc)` pattern on
  transient failures — a genuine template for the Refinitiv adapter's own
  rate-limit backoff (§6 of the attached plan), not something to invent.
- **`httpx>=0.27.0` and `pydantic>=2.6.0` are already in `requirements.txt`**
  — the plan's async `MarketDataProvider` interface and Pydantic v2
  canonical schemas fit the existing dependency set with no new core
  libraries needed (only `refinitiv-data`, scoped to `providers/refinitiv.py`
  alone, per the plan's own module-boundary discipline).
- **The compliance boundary the plan insists on (no raw vendor data in
  `storage/`) is consistent with how this repo already treats sensitive
  data** — `storage/s3.py`'s Parquet writer and `var_jobs`'s audit-log
  design (CLAUDE.md §3.3: "never delete rows programmatically") already
  reflect a similar "audit what we computed, not what we received"
  discipline. This isn't a new pattern being introduced, it's consistent
  with the existing one.

## 2. What's genuinely unblocked and could start now — MD-1

Per the attached plan's own milestone table, **MD-1 has zero external
dependencies**: `base.py` (the abstract interface), `schemas.py`
(canonical Pydantic models), `exceptions.py`, `providers/fake.py` (the
in-memory test double), and unit tests against the fake provider only —
"no network calls anywhere." None of this needs a Refinitiv sandbox
account, a cache-TTL legal answer, or any of the open decisions in §3
below. This is real, buildable code today.

## 3. What's blocked on Filippo — the attached plan's own §12, unchanged

These were already correctly identified as open in the attached document,
and nothing found this session resolves them:

1. **RDP access tier / app registration scope** — which instrument
   classes and history depth the sandbox actually grants.
2. **Snapshot (REST) vs. streaming (RDP WebSocket) for v1** — materially
   changes MD-3's scope; the plan recommends starting REST-only but this
   is your call.
3. **Cache TTL policy** — the plan is explicit this needs "a legal/contract
   check against the actual Refinitiv sandbox and eventual production
   terms, not just an engineering guess." I have no way to obtain
   Refinitiv's actual terms from this session.
4. **Whether the ISIN→RIC mapping table may be persisted** — affects
   whether `resolve_instrument()` results can be cached beyond a single
   session; same "needs the actual sandbox terms" blocker as #3.

None of these block MD-1. All of them block MD-3 (the real Refinitiv
adapter) and, transitively, MD-4 (wiring into the production compute
pipeline) — which the attached plan already correctly treats as "a hard
gate behind MD-1–3 being merged and reviewed."

## 4. One thing to flag before proceeding, not found in the other five items

The attached plan's own header says: **"Audience: delegated coding agent
operating on the `pyvar` repository."** That's a different framing than
items 1–5, where the ask was "plan and document." Worth confirming
directly: do you want MD-1 implemented in this session now (it's genuinely
unblocked, per §2), or was this plan written to be handed to a separate
delegated agent/session — e.g. a fresh Claude Code Remote session, per the
document's own stated audience? Either works; asking rather than assuming,
since starting to write new `ingestion/market_data/` code is a materially
different kind of action than the docs-only work items 1–5 involved.

## 5. Recommended sequencing once that's answered

1. MD-1 first, regardless of who builds it — it's the only phase with no
   external blockers, and MD-2's cache-TTL work benefits from MD-1's
   schemas already existing.
2. MD-2 (`registry.py`, `cache.py`) can follow MD-1 immediately for the
   *mechanism* (config-driven provider selection, a TTL-configurable
   cache), but the actual TTL *values* stay placeholders pending
   decision #3 in §3.
3. MD-3 (the real Refinitiv adapter) waits on decisions #1 and #2 in §3 —
   there's no way to write a sandbox-specific adapter without knowing what
   the sandbox actually grants.
4. MD-4 (wiring into `tasks/var_task.py`) stays hard-gated behind MD-1–3
   being merged and reviewed, exactly as the attached plan specifies —
   not something to shortcut even once MD-3 exists.
5. MD-5 (docs) happens alongside each phase, not as an afterthought at the
   end — same discipline as every other item this session.

## 6. Definition of done (for MD-1, the actionable slice)

Per the attached plan's own §13, verified as the right bar:
- `providers/fake.py` passes a real (not placeholder) contract test suite.
- No file under `engine/`, `api/`, or `storage/` imports anything from
  `market_data/providers/`.
- `ruff check` and `pytest` clean, consistent with existing CI conventions.

## 7. Built and shipped

**MD-1 — merged** (PR #332, 2026-09-11): `base.py` (the abstract
`MarketDataProvider` interface), `schemas.py` (`Instrument`/`PriceSeries`/
`YieldCurve`/`VolSurface`, Pydantic v2), `exceptions.py` (`ProviderError`
family), `providers/fake.py` (deterministic in-memory provider, seeded via
`zlib.crc32` for cross-run reproducibility), and 12 unit tests including
the compliance-boundary static scan from §6. No network calls anywhere in
the subtree.

**MD-2 — mechanism shipped** (this session, following §5's sequencing):
- `registry.py` — `get_provider()` reads `config.py`'s new
  `market_data_provider` setting (`"fake"` is the only registered option
  until MD-3 adds `"refinitiv"`) and returns the configured provider,
  wrapped in the TTL cache by default (`cached=False` opts out).
- `cache.py` — `CachingMarketDataProvider` wraps any `MarketDataProvider`
  and caches each of the 4 interface methods independently in Redis
  (`pyvar:market_data:{provider}:{method}:{sha256}` keys), reusing the
  exact fail-open philosophy and retry policy `api/routes/caching.py`
  already established (`_get_redis_client()` construction, 2-retry
  exponential backoff, any Redis error treated as a cache miss/no-op —
  never a reason to fail a lookup). A `ProviderError` from the wrapped
  provider is never cached — only successful lookups are.
- TTLs (`market_data_cache_ttl_instrument_seconds` = 1h,
  `..._price_series_seconds` / `..._yield_curve_seconds` /
  `..._vol_surface_seconds` = 5m each) are **explicitly placeholder
  values**, per §3 decision #3 — still unresolved, still blocking MD-3,
  unchanged by this work. They're deliberately short so a wrong guess
  fails safe (cheap to go stale and refresh) rather than risking serving
  data past whatever Refinitiv's real terms eventually allow.
- 15 new tests (`tests/test_market_data_registry_and_cache.py`) — registry
  provider selection/rejection, cache hit (asserts the wrapped provider is
  never called, not just that the return value matches), cache miss
  (asserts the correct per-method TTL is used), errors never cached, and
  both `_cache_get`/`_cache_set` fail open on a Redis error. 27/27 across
  both MD-1 and MD-2 test files; full suite re-run clean.

**Still blocked on Filippo, unchanged from §3**: MD-3 (the real Refinitiv
adapter) needs decisions #1 (RDP access tier), #2 (snapshot vs. streaming),
and the cache-TTL legal check (#3, which also unblocks turning MD-2's
placeholder TTLs into real values) and the ISIN→RIC persistence call (#4).
MD-4 (wiring into `tasks/var_task.py`) stays hard-gated behind MD-1–3 being
merged and reviewed, exactly as §5 specifies.
