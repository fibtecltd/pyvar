# Exploration: a streaming service for real-time-based pricing

**Status: exploration only, no action taken.** Requested alongside five
other planning items (2026-09-29), explicitly scoped as "explore, without
taking actions."

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
