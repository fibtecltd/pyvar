# Exploration: a streaming service for real-time-based pricing

**Status: shape #1 implemented (2026-09-30).** Originally requested
alongside five other planning items (2026-09-29), explicitly scoped then
as "explore, without taking actions." Filippo has since explicitly decided
to build shape #1 (§3) — see §7 below for what shipped. Shapes #2 and #3
remain unexplored beyond this doc's original analysis; nothing below
changes their status.

## 1. Disambiguation — this is a different question from MD-3's streaming decision

`docs/plan-market-data-adapter.md` §3 already has an open decision labeled
"snapshot (REST) vs. streaming (RDP WebSocket)" — but that's about how
pyvar **ingests** Refinitiv market data, an upstream data-sourcing
question. This doc is about a different, downstream question: should
pyvar **serve** its own customers real-time/streaming computed pricing
and risk outputs, as a product capability. The two are related (a
streaming ingestion feed makes a streaming output product more valuable)
but not the same decision, and this doc doesn't assume MD-3's outcome
either way.

## 2. What the current architecture actually does today

Verified against `api/routes/var.py` and the equivalent routers for the
other 7 domains: every compute endpoint is **request → 202 + `task_id` →
client polls `GET /.../result/{task_id}`** against a Celery/Redis result
backend (CLAUDE.md §3.2). This is correct for the workload — Monte Carlo
VaR, LSM option pricing, and the rest are seconds-to-minutes CPU-bound
jobs, not sub-second lookups — but it means there is **no existing
push/streaming primitive anywhere in `api/`**: no WebSocket route, no
Server-Sent Events, no long-lived connection handling at all. A streaming
product would be new infrastructure, not an extension of something
half-built.

## 3. What "real-time-based data pricing" could mean — three different products, worth separating

1. **Streaming job-completion push** (smallest lift): instead of the
   client polling `GET /var/result/{task_id}`, push the result over a
   WebSocket or SSE connection the moment the Celery task completes.
   Doesn't require any new *pricing* capability — same compute, same
   Monte Carlo/LSM kernels, just a different result-delivery transport.
   Real infra cost: FastAPI supports WebSockets natively, but ALB
   (CLAUDE.md §3.4's Fargate topology) needs sticky sessions or a
   pub/sub fan-out (Redis Pub/Sub, which is already in the stack) for a
   WebSocket connection to receive a push from whichever worker actually
   finishes the job — solvable, not free.

2. **Streaming market-data passthrough**: re-expose whatever Refinitiv
   RDP WebSocket feed MD-3 eventually ingests (if snapshot vs. streaming
   is decided in streaming's favor) directly to pyvar's own customers —
   effectively becoming a redistribution point for vendor tick data. This
   is the one that most directly collides with `docs/plan-market-data-adapter.md`'s
   own flagged compliance boundary: **vendor data-redistribution
   restrictions are exactly what that plan says needs a legal check before
   any caching, let alone re-streaming to third parties.** This shape is
   the highest-risk of the three and the most dependent on MD-3's
   still-open legal questions.

3. **Continuously-recomputed risk metrics** (the most genuinely new
   product): re-run VaR/Greeks/sensitivities on a schedule or on every
   underlying price tick and push the *recomputed risk output* (not raw
   market data) to subscribers — e.g., a live-updating VaR figure as the
   portfolio's underlying prices move intraday. This avoids the
   redistribution problem in #2 entirely (subscribers receive pyvar's own
   computed output, not resold vendor data) but is real, new compute
   architecture: continuous Monte Carlo re-runs are expensive if done
   naively (CLAUDE.md §3.1's Numba kernels are fast per-run, not free at
   tick frequency), so this would likely need either a cheaper
   incremental-update method (e.g., delta-based re-pricing rather than a
   full fresh Monte Carlo draw) or a deliberately coarser refresh cadence
   (seconds, not ticks) — an actual quant-design question, not just infra.

## 4. Rough complexity ordering of the three shapes

Push-based job completion (#1) < continuously-recomputed metrics (#3) <
market-data passthrough (#2) — #2 is listed last despite sounding
simplest because its blocker isn't engineering effort, it's the same
unresolved vendor-contract question already blocking MD-3, and building
ahead of that answer risks having to unbuild it.

## 5. What this doc deliberately does not do

- Recommend a transport (WebSocket vs. SSE vs. gRPC streaming) — a real
  choice, but premature before which of #1/#2/#3 is actually wanted.
- Size AWS infra changes (ALB WebSocket support, Redis Pub/Sub wiring,
  CloudFront's WebSocket pass-through behavior) — meaningful work, but
  downstream of the product-shape decision, not a blocker to making it.
- Touch pricing/billing implications (would streaming access be a new
  tier, an Enterprise-only add-on, metered separately from the existing
  request/simulation caps in `config.py`?) — a monetization-strategy
  question (item 5 of the six-initiatives roadmap), not an architecture
  one, and explicitly out of scope for a no-action exploration.

## 6. If this moves forward — recommended next step

Get a decision on which of the three shapes (§3) is actually wanted before
any design work, since they have almost nothing in common: #1 is a
transport change to existing compute, #2 is a legal/compliance question
first and an engineering one second, #3 is a new quant-design problem
first and an infra one second. Treating "real-time pricing" as one
initiative when it's really three would make scoping and estimating
unreliable from the start.

## 7. Shape #1 implementation (2026-09-30)

Decision made: shape #1 ("streaming job-completion push," §3.1), VaR only,
same scope this doc's own complexity ordering already flagged as the
smallest lift. Shapes #2 and #3 untouched — nothing here resolves their
open blockers (§4/§5).

**New endpoint:** `WS /api/v1/var/stream/{task_id}`, alongside the existing
`GET /api/v1/var/result/{task_id}` poll — the poll endpoint is unchanged
and still works exactly as before; this is an additive alternative
transport, not a replacement.

**Design decisions actually made (the ones this doc deliberately deferred
in §5):**

- **Transport: WebSocket**, not SSE or gRPC — FastAPI/Starlette support it
  natively (already in `uvicorn[standard]`, no new dependency), and it's
  bidirectional-capable if a future shape needs client→server messages
  (this one doesn't use that, but doesn't foreclose it either).
- **Fan-out mechanism: Redis Pub/Sub**, on the same Redis instance Celery
  already uses as broker/backend (`cfg.redis_url`) — exactly the
  "already in the stack" option this doc's §3.1 flagged. `tasks/var_task.py`
  publishes a minimal marker (`"success"`/`"failure"`, not the result
  payload) to channel `pyvar:var-job-done:{task_id}` on terminal state,
  best-effort (never fails the job if Pub/Sub is unavailable — same
  "must never break compute" posture as the existing CloudWatch metric
  helpers in that file).
- **Reliability — the one real gap this doc's §3.1 called out
  ("solvable, not free"):** Redis Pub/Sub has no persistence or replay —
  a message published with no subscriber listening is lost forever. Rather
  than build ALB sticky-sessions/ELB-level fan-out (the infra-layer
  solution this doc's §5 explicitly deferred), the WebSocket route itself
  never trusts Pub/Sub alone: it re-reads the authoritative Celery result
  backend state on every wake-up (a pushed message OR a plain
  `cfg.var_stream_poll_interval_seconds` timeout tick), so a lost message
  costs at most one poll interval of latency, never a hung connection.
  This sidesteps needing the ALB/Redis-fan-out infra work at all for a
  single-worker-process deployment — revisit if/when true multi-instance
  WS fan-out becomes necessary.
- **Auth: JWT as a `?token=` query parameter**, not the Authorization
  header — browser WebSocket clients cannot set arbitrary headers on the
  opening handshake, so this is the standard pattern. Validated by the
  same `decode_token_payload()` logic `get_current_user` uses for every
  HTTP route (extracted into `api/middleware/auth.py` so the two transports
  share one validation path, not two).
- **Authorization scope: deliberately matches `GET /var/result/{task_id}`
  exactly** — no new per-user task-ownership check was added, since the
  existing poll endpoint doesn't have one either; adding it to only one of
  the two transports for the same resource would create an inconsistent
  security model. Tightening both together is a separate, not-yet-made
  decision.
- **Bounded connection lifetime:** `cfg.var_stream_max_wait_seconds` (15
  minutes default) caps how long a single WS connection can be held open,
  so a job that never reaches a terminal state can't pin a worker slot
  indefinitely.
- **Billing/tiering: untouched**, per this doc's own §5 scoping — streaming
  access is not gated or metered differently from the existing poll
  endpoint for any tier. A monetization decision here, if wanted, is item
  5's territory, not this change's.

**Not done:** shapes #2 and #3, any AWS/CDK-level change (this doc's §5 already
flagged ALB WebSocket pass-through and CloudFront's WS behavior as
downstream infra work — the Redis Pub/Sub design above was specifically
chosen to defer that, not to require it), and streaming for the other 7
domains (only VaR — the reference implementation this session's `plugins/`
marketplace work already treats as the flagship domain).
