# Exploration: streaming quotes in, calculation results out

**Status: exploration, with two decisions recorded — no streaming-service code and no
new infrastructure yet.** (Phase 0 found four defects in the existing
job-completion route and its deployment, and its checks found two more in the first fixes; all
six are fixed: §9.0.) Requested 2026-10-22: a streaming in/out service for event-driven,
quasi-real-time market quotes in → calculation and pricing results out, independent
of any market-data provider, keeping the current REST API JSON structure. This
document proposes approaches and compares them.

**Decisions recorded (Filippo, after review of PR #395):**
1. **WebSocket JSON is the default transport** (§5), with HTTP micro-batch as the
   documented fallback.
2. **The recommended path (§6) is accepted**, including its gates: Phase 0
   (measure and specify), then the stream core shipped as Approach D, Approach A as a
   capped prototype, Approach B only if the gates are met, Approach C only if replay
   is demanded.

**Still open** (§8): latency class (1), first asset classes (3), audience and tier
(4), legal review of customer-supplied vendor data (5), short-lived stream tokens
(6), and where the code lives (7). Phase 0 is measured (§9): per-function latency for
all 385 functions, the WebSocket path through CloudFront, and what one API task holds.
One problem stays open: on dev, every cycle of sockets still leaves 2-4 MiB more
memory in use, a step that has been shrinking but has not reached zero (§9.9).

**Provenance:** drafted with Claude Code (AI-assisted), like most documents in this
repository (see "Use of Generative AI" in `README.md`). It is not part of any grant
proposal. If this feature is ever funded, the funder's AI-use policy governs how the
funded work may be produced.

**Relationship to earlier documents.**
`docs/plan-streaming-realtime-pricing.md` split "real-time pricing" into three
shapes. This is its **shape #3** (continuously recomputed outputs), with one change
that removes the blocker that document attached to shape #2: quotes are **supplied by
the customer**, not ingested from a vendor by pyvar, so pyvar never redistributes
vendor data. `docs/plan-market-data-adapter.md` (a *pull* interface towards one
vendor) is unaffected and not a dependency.

---

## 1. The ask, restated

- **In:** a stream of market quotes (prices, rates, vols, spreads) pushed to pyvar by
  the customer, from whatever source they have.
- **Out:** calculation and pricing results, re-emitted when the inputs change, in the
  **same JSON shape the REST API returns today**.
- **Independent of any provider:** no vendor SDK, field names or identifiers in the
  core. Vendor-specific code, if any, lives outside it.
- **Quasi-real-time:** results within roughly seconds of a quote, not
  microseconds. This is not tick-to-trade and not an exchange connection.

**Non-goals:** being a market-data vendor; storing or replaying vendor data; changing
any `[REGULATORY]` formula or constant (the stream only wraps existing functions);
replacing the REST API.

---

## 2. Facts this design rests on

### 2.1 A correction to the earlier streaming document

`docs/plan-streaming-realtime-pricing.md` §2 says every compute endpoint is
"request → 202 + `task_id` → poll". That is true only of `/api/v1/var/compute`
(Monte Carlo VaR). The other **384 of 385 functions are synchronous**
request/response (`docs/publications/pyvar-iron-triangle-medium-article.md` line 18;
`api/routes/market_risk.py`: each handler is `async def` and returns the engine
result directly). This matters: a streaming layer can wrap synchronous calls and
needs no job queue for almost everything.

### 2.2 What exists today

| Fact | Source |
|---|---|
| Domain handlers call the engine **inline** in `async def` handlers; only `public_data.py` and `var.py` use `run_in_threadpool` | `api/routes/market_risk.py:272-287`, `grep run_in_threadpool api/` |
| Monte Carlo VaR (100,000 paths) takes 2–10 s and is the only async-job function | iron-triangle article, line 18 |
| Per-function latency: none existed in the repo docs; **Phase 0 measured all 385** (§9.1, `docs/data/streaming-phase0d-latency.csv`) | searched the iron-triangle article and `docs/p9-scenario-volume-cost-audit.md`; Phase 0 reports |
| The API image runs `uvicorn --workers 2`: two processes per task, and any in-process counter exists twice | `Dockerfile:166` |
| API tasks: 0.5 vCPU, 1 GiB, 2–10 tasks, comment "API is I/O-bound, not CPU-bound" | `pyvar-cdk/config.py:79-82` |
| Request path: CloudFront → WAF → ALB → Fargate, no API Gateway; ALB only accepts requests carrying CloudFront's secret header | `edge_stack.py:43`, `api_stack.py:464-499` |
| ALB idle timeout is 60 s: not set in CDK, so the AWS default, and read from the live ALB in Phase 0 | `grep idle_timeout pyvar-cdk/` finds nothing; Phase 0 report |
| Graceful shutdown window on deploy: 30 s, so open connections are cut at every rolling deploy | `api_stack.py:368` |
| One WebSocket route exists: `WS /api/v1/var/stream/{task_id}` (job-completion push), session JWT in `?token=`, Redis Pub/Sub, 15-minute cap. It crashed on any job that was not finished yet until #396, raced the result store until #397, kept abandoned sockets for 15 minutes with no limit until #398, and built a Redis client per socket until #400-#402 replaced it with one shared Pub/Sub connection per worker process (§9.7-9.9); **tested on dev through CloudFront, WAF and the ALB** (§9.4-9.6). Prod has not been probed directly | `api/routes/var.py`, `CHANGELOG.md`, Phase 0 reports |
| The dev cache (ElastiCache Serverless, Redis 7.1) refuses `PSUBSCRIBE` ("unknown command"); per-channel `SUBSCRIBE` and `PUBLISH` work | Phase 0f (§9.8) |
| Account-wide request quotas: free 10/day, pro 500/day and 5,000/month; one counter shared by all `/api/v1` compute endpoints, Redis-backed | `config.py:161-184`, `api/middleware/rate_limit.py` |
| API keys: `pyvar_…`, 365 days, SHA-256 stored; session JWT 60 min; key management needs a session | `docs/plan-durable-api-keys.md`, CLAUDE.md §3.5 |
| The Monte Carlo VaR kernel seeds NumPy's **global** RNG (`np.random.seed(seed)`), default seed 42 | `engine/montecarlo.py:92,121-122` |
| Several kernels use `@njit(parallel=True)`, which brings its own thread pool | `engine/credit_var.py`, `engine/deriv_options_exotic.py` |
| `pyvar-client` is synchronous (`httpx.Client`); no async or streaming surface | `pyvar-client/pyvar_client/_client.py` |
| Market-data MD-1/MD-2 merged: a vendor *pull* interface, schemas, TTL cache; MD-3 is blocked on a sandbox account | `docs/plan-market-data-adapter.md` §7 |

Two of these deserve emphasis. First, the REST API today serves the public site
(including the Google sign-in config); anything that can starve it is a risk beyond
the streaming feature itself. Second, because the engine is called inline on the
event loop, a streaming endpoint placed naively in the same process would block every
other request while it computes.

---

## 3. The contract every approach shares

The approaches in §4 differ in *where things run*. What clients see should not.

### 3.1 Principles

1. **Same functions, same bodies.** A stream calculation names a function by its REST
   path and carries the same request body. Its result is the same JSON the REST call
   returns.
2. **The core knows no vendor.** One canonical quote event; adapters are separate,
   optional, and mostly on the customer's side.
3. **Ephemeral by default.** Quotes are held in memory (at most Redis with a TTL of
   seconds). Nothing quote-derived is written to `storage/`. This matches the audit
   rule in the market-data plan: keep what we computed, not what we received.
4. **Newest wins.** If calculations cannot keep up, intermediate quotes are conflated.
   Queues never grow without bound.
5. **Every result is reproducible.** Each result carries a digest of its resolved
   inputs; the same digest means the same result (for deterministic functions).

### 3.2 Canonical quote event

```json
{"id": "EURUSD", "field": "mid", "value": 1.0842, "ts": "2026-10-22T14:03:07.412Z",
 "seq": 18231, "src": "desk-feed-1"}
```

- `id`: an opaque string chosen by the customer (optionally `scheme` such as ISIN or
  ticker, only for their own bookkeeping).
- `field`: `bid`, `ask`, `mid`, `last`, `rate`, `vol`, `spread`, or any lowercase
  token. The service does not interpret it.
- `ts`: the source time (RFC 3339). `seq`: optional counter per `src`, used to drop
  duplicates and out-of-order events.
- Values follow the REST API's units (decimals: 0.02 means 2%).
- Batches are allowed: `{"op": "quote", "events": [ ... ]}`.

### 3.3 Calculation subscriptions and bindings

A subscription is a function, a request body in which some values are *bindings* to
the quote cache, and a trigger. A body without bindings is just a REST call repeated.

- `{"$quote": "EURUSD.mid"}` is replaced by the latest scalar.
- `{"$window": {"ref": "EURUSD.mid", "n": 250, "transform": "log_return"}}` is
  replaced by an array from a rolling buffer. This exists because VaR functions take
  `returns` arrays, and it is the part that needs per-session state.
- Everything else in the body passes through untouched.

Resolution produces an ordinary REST body, validated by the **same Pydantic request
model** as the REST route. Invalid bodies fail with the same 422 detail.

### 3.4 Result envelope

```json
{"type": "result", "calc_id": "call-eurusd-1m", "seq": 17,
 "asof": {"inputs_ts": "2026-10-22T14:03:07.412Z", "computed_at": "2026-10-22T14:03:07.438Z"},
 "inputs_digest": "sha256:…", "dropped": 0,
 "result": { "…": "exactly what POST /api/v1/derivatives/black_scholes_european_option returns" }}
```

Errors mirror REST: `{"type": "error", "calc_id": …, "status": 422, "detail": "…"}`.
Warnings (`stale_input`, `window_not_full`) are separate frames so a result is never
silently computed on missing data.

### 3.5 Triggers, conflation, backpressure

- `{"on": "quote"}`: recompute when any bound input changes.
- `{"on": "interval", "interval_ms": 1000}`: fixed cadence, using latest values.
- Both accept `min_interval_ms` and `threshold` (for example, only when a bound value
  moves by at least a set amount).
- **One calculation in flight per subscription.** Quotes arriving meanwhile are
  conflated into the next run and counted in `dropped`.
- Per-connection ceilings: events per second in, subscriptions, window length, CPU
  budget. Exceeding one returns an error frame, then a close.

### 3.6 Reproducibility

Deterministic functions give the same output for the same digest, which makes
**replay-based validation** possible: record a session's events, feed them to a fresh
instance, and compare envelopes. For Monte Carlo functions, the seed must be part of
the digest. Note the global-seed point in §2.2: running such functions concurrently in
threads of one process could interleave draws (not tested here). Stochastic functions
should run in separate processes or with per-call generators.

### 3.7 Authentication

- Non-browser clients: `Authorization: Bearer pyvar_…` on the upgrade request.
- Browsers cannot set that header. The existing route puts a session JWT in the URL,
  which ends up in logs and proxies. **Do not allow 365-day `pyvar_` keys in URLs.**
  Instead, mint a short-lived stream token (for example `POST /api/v1/stream/token`,
  valid for tens of seconds, single use) with a session or key, and present it in the
  first frame.
- Confirmed in Phase 0: CloudFront standard logging is on, so a token in the URL is stored
  in S3 (§9.3).
- Built for the job-result stream (WS `/var/stream/{task_id}`): `POST /api/v1/var/stream-token/{task_id}`
  takes an API key or a session in the header and returns a token valid for 60 s
  (`var_stream_token_ttl_seconds`), bound to that one task and carrying an `aud` claim so every
  other route refuses it; the stream accepts it, or a session JWT, and never a key. It is not
  single use (that needs state in Redis). The quote stream would reuse the exchange with a
  different audience.
- The key's tier is read from the database, as for REST (CLAUDE.md §3.5).

### 3.8 Metering and tiers

The per-call daily quota does not fit a stream: one subscription can produce
thousands of computations an hour. A separate model is needed, with candidate units
**concurrent connections, subscriptions, events/s in, and computations/s out**,
and separate `stream_*` settings in `config.py`. Whether streaming is Enterprise-only,
a Pro add-on or metered is a monetization decision (see
`docs/plan-monetization-implementation.md`); it is not decided here.

### 3.9 Data handling and licensing

- Customers send **their own** quotes and receive results computed from them.
  pyvar redistributes nothing to third parties.
- If those quotes come from a market-data vendor, the **customer's** licence terms
  decide whether sending them to a hosted calculation service, and receiving derived
  values back, is permitted. Vendors commonly distinguish display from non-display
  use and treat derived data separately. This needs a legal review before any hosted
  offering; it is not legal advice, and it is the same class of question
  `docs/plan-market-data-adapter.md` §3 flags.
- Approach D (self-hosted, §4) avoids the question entirely because quotes never leave
  the customer's perimeter.
- The existing disclaimer applies to streamed results: computation on supplied data,
  not regulatory or financial advice.

### 3.10 Which functions are stream-eligible

- **Yes:** synchronous, deterministic functions with a measured p95 below the chosen
  budget — typically closed-form and tree pricing, Greeks, parametric and historical
  VaR, curve and ratio calculations.
- **Coarse cadence only:** Monte Carlo, LSM and exotic pricers (seconds per run). At
  most one in flight, with a minimum interval of several seconds.
- **Not eligible:** functions that need job-pipeline semantics (`/var/compute`
  already has its own completion push).
- The eligible set is data, not code: a flag per function in the catalogue
  (`portal/functions.json`), set from measurements (§6, Phase 0).

**Classes from the Phase 0 measurement** (warm p50, in-process on a 0.5 vCPU task, all
385 functions, `docs/data/streaming-phase0d-latency.csv`; §9.1):

- **Synchronous class, p50 under 50 ms: 371 of 386 rows.** Everything in ALM, liquidity,
  regulatory, and all but the functions named below.
- **50-250 ms (4):** `potential_future_exposure_pfe` 81 ms, `extreme_value_theory_var`
  69 ms, `scenario_analysis_oprisk` 215 ms, `resampled_efficient_frontier` 210 ms.
- **250 ms-1 s (9):** `lmm_bgm_rate_model`, `cox_ingersoll_ross_model`,
  `lookback_option_pricer`, `asian_option_pricer`, `volatility_surface_implied_vol`,
  `nelson_siegel_svensson_curve`, `bermudan_option_pricer`, `hull_white_short_rate_model`,
  `vasicek_interest_rate_model`.
- **1-5 s (2):** `american_option_lsm` (1.1 s), `rough_volatility_rbergomi_model` (4.0 s).
  Coarse cadence only, as above.
- **Variable tail:** `macro_scenario_generator` has p50 11 ms but p95 508 ms; give it a
  timeout rather than a plain "fast" label.

The flags themselves are **not yet in `portal/functions.json`** (a change there
triggers the pipeline); the classes above are derived from the CSV.

---

## 4. Four approaches

Effort labels are my relative judgement, not measured estimates.

### Approach A — stream façade inside the existing API service

```
customer ──WS/SSE──▶ CloudFront ▶ WAF ▶ ALB ▶ FastAPI task (REST + /stream)
                                              ├─ per-connection quote cache + buffers (memory)
                                              └─ engine calls (thread pool)
```

New WebSocket (or SSE) endpoints on the current service. State lives in the
connection's process.

**Pros**
- Smallest change: no new service, stack or pipeline stage.
- Reuses auth, request models, error handling and the existing WebSocket pattern.
- Fastest way to put a prototype in front of a few users.
- No extra always-on cost.

**Cons**
- **Blast radius:** stream load shares 0.5 vCPU tasks with the public REST API.
- Engine calls are inline today; they would need an executor, and thread pools plus
  `parallel=True` kernels on 0.5 vCPU risk oversubscription.
- State is lost on every deploy (30 s drain) and on scale-in; clients must reconnect
  and re-subscribe.
- Autoscaling (2–10 tasks) and the 1-hour sticky cookie decide where a connection
  lands; no replay.
- ALB idle timeout and CloudFront's behaviour for long-lived connections must be
  verified before anything is promised.

**Effort:** small to medium. **Best as:** a capped prototype, not a product.

### Approach B — dedicated stream service sharing the engine package

```
customer ──WS/SSE──▶ CloudFront ▶ WAF ▶ ALB ──/api/*──▶ REST service (unchanged)
                                         └──/stream/*──▶ pyvar-stream service
                                                          ├─ sessions, buffers (memory, optional Redis snapshot)
                                                          └─ worker processes (engine)
```

A second ECS service built from the same repository and engine, routed by path on the
same ALB so the CloudFront/WAF protections still apply.

**Pros**
- Isolation: a runaway stream cannot starve the REST API.
- Independent sizing (more CPU per task), scaling and deploys.
- Still no new technology; same schemas and auth code.
- Optional Redis snapshots let a session resume after a restart; Redis Streams can be
  added later for replay.

**Cons**
- New CDK stack and pipeline stage: more cost and operational surface, including
  connection draining on deploy.
- Routing must keep the ALB's CloudFront-header rule; a separate public load balancer
  would bypass the WAF design (see the SEC-1 comment in `api_stack.py`).
- Fan-out across instances (a quote producer on one task, consumers on another) needs
  either Redis Pub/Sub or session affinity.
- Always-on cost with no proven demand.

**Effort:** medium to large. **Best as:** the hosted product once demand is shown.

### Approach C — bus-centric streaming plane

```
customer ─▶ ingest gateway ─▶ [quotes log] ─▶ compute consumers ─▶ [results log] ─▶ fan-out gateways ─▶ customers
                               (Redis Streams / Kinesis / Kafka / NATS JetStream)
```

**Pros**
- Horizontal scale; producers and consumers decoupled.
- Durable log: replay, audit and **deterministic replay** for validation.
- Natural multi-consumer fan-out (one result stream, many readers).

**Cons**
- The heaviest option: several new components, each with an always-on cost
  (managed Kafka and per-shard billing are the usual culprits; I have not priced
  them here).
- At-least-once delivery needs idempotent consumers and sequence handling.
- More hops add latency; more services add attack surface.
- Poor fit for a self-funded, pre-revenue project with unproven demand.

**Effort:** large. **Best as:** a later step if replay or multi-consumer needs appear.

### Approach D — embedded / self-hosted streaming engine (library + daemon)

```
customer feed ──▶ pyvar-stream (library or daemon, runs on customer infra)
                    ├─ same bindings, triggers, envelope (§3)
                    ├─ engine imported locally (as pyvar-local does)
                    └─ optional calls to hosted REST for heavy functions
                  ◀── results as an async iterator, JSON lines, or a local WebSocket
```

Ships in the existing docker all-in-one image or as a PyPI package.

**Pros**
- Maximum provider independence: any feed that can yield quote events.
- **Quotes never leave the customer's perimeter**, which removes the licensing
  question in §3.9.
- No hosted infrastructure, no new always-on cost, no effect on the REST API.
- Fits the open-source and self-hosting positioning; the engine is already usable
  offline.
- Lets the contract in §3 be proven against real feeds before any hosted service.

**Cons**
- No hosted revenue or metering for this feature.
- Support burden for packaging and versions; customers must run it.
- Less attractive to smaller institutions without engineering capacity.
- The product story is a library, not "a service".

**Effort:** medium. **Best as:** the first deliverable and the reference
implementation.

### 4.1 Comparison

| | A façade | B dedicated | C bus | D self-hosted |
|---|---|---|---|---|
| New infrastructure | none | one service | several | none |
| Risk to the REST API | high | low | low | none |
| Provider independence | high | high | high | highest |
| Licensing exposure | hosted | hosted | hosted | none |
| Replay / audit | no | optional | yes | local only |
| Time to a prototype | shortest | medium | longest | short |
| Revenue path | yes | yes | yes | not directly |

---

## 5. Transport options

The transport is a separate choice from the approach.

| Transport | Pros | Cons |
|---|---|---|
| **WebSocket (JSON frames)** | Bidirectional (quotes in, results out on one connection); native in FastAPI; already used by `/var/stream`; browsers supported | Long-lived connections vs deploys and ALB idle timeout; token-in-URL temptation (§3.7) |
| **Server-Sent Events + HTTP POST** | Plain HTTP, simple through proxies; auto-reconnect with `Last-Event-ID` | One-way: quotes go in by separate POSTs; buffering by intermediaries can delay events |
| **gRPC bidirectional streaming** | Typed, efficient, strong tooling | Does not keep "the same JSON" unless payloads are JSON strings; poor browser support; more to operate behind CloudFront |
| **MQTT (broker)** | Built for pub/sub and flaky links; many feed adapters exist | A new broker and auth model; topics do not map neatly to function calls |
| **HTTP micro-batch** (`POST` events, receive results, or webhook out) | No long-lived connection; works with today's infrastructure | Not push; high call rates collide with request quotas and with the WAF's per-IP limit of 100 requests per 300 s (§9.3), which would need an exemption for any streaming path; webhook delivery reliability |

Suggested default: **WebSocket JSON**, with HTTP micro-batch as a documented
fallback for clients that cannot keep a socket open. Both would use the same
messages from §3 and Appendix A.

---

## 6. Recommended path

**Build the contract and a core once, then wrap it.**

0. **Phase 0 — measure and specify (documents and benchmarks only).**
   - Measure, per function, engine-only time and end-to-end HTTP time on the real
     task size. This is the gap in §2.2; every latency promise depends on it.
   - Fix the quote event, binding grammar, envelope and error frames as a versioned
     specification (§3, Appendix A), with a conformance test plan.
   - Set the eligible-function flags from measurements.
   - Verify ALB idle timeout, CloudFront and WAF behaviour for WebSockets with a
     throwaway echo endpoint.
   **Status (2026-10-26):** latency measured for all 385 functions; edge, WebSocket
   behaviour and the load one task carries measured on dev; the job-completion route fixed
   and re-checked on dev three times; see §9. What remains is listed in §9.10.
1. **Phase 1 — a stream core library with no AWS dependency:** bindings, rolling
   windows, triggers, conflation, digests. Ship it first as **Approach D**.
   Replay-determinism tests come with it.
2. **Phase 2 — Approach A as a capped prototype** behind a feature flag, with hard
   per-connection limits and an allow-list of accounts. Purpose: learn real demand
   and real load, not to launch.
3. **Phase 3 — Approach B** only if gates are met. **Approach C** only if replay or
   multi-consumer fan-out is demanded.

**Gates between phases** (thresholds to be set after Phase 0, not guessed now):
measured REST p95 impact while streams run; sustained concurrent connections against
CPU headroom; deploy-induced disconnects reported by users; written interest from
at least a few real users; legal position on §3.9.

---

## 7. Risks and open questions

1. **Demand is unproven.** The NLnet text itself says main users today are
   individual developers and researchers. Stage-gate spending accordingly.
2. **Latency is measured for all 385 functions** (§9.1); 15 are not fast enough for the
   synchronous class (§3.10).
3. **Data licensing** of customer quotes (§3.9) needs a legal check for any hosted
   variant.
4. **Abuse and cost control:** many subscriptions, long windows and heavy functions
   are a denial-of-service and cost vector. Per-connection CPU budgets and ceilings
   are required from day one, not later.
5. **Security:** no long-lived keys in URLs (§3.7); confirm WAF rules do not drop or
   inspect WebSocket frames in a way that breaks the protocol.
6. **Correctness of time:** late, duplicate and out-of-order quotes; clock skew
   between customer sources. `asof` semantics must be written down, and stale or
   incomplete inputs must produce warnings, not results.
7. **Operational:** deploys cut connections (30 s drain); clients need reconnect and
   `resume_from` behaviour; scale-in does too.
8. **Determinism claims:** only for functions that are deterministic; stochastic
   functions need seed handling and process isolation (§3.6).
9. **The WebSocket route is tested through the edge on dev** (§9.4-9.6), after three
   fixes; prod has not been probed directly.
10. **Pipeline cost:** when implementation starts, any change outside the eight
    excluded directories triggers a CodePipeline run (CLAUDE.md §8.1).
11. **Provenance:** the share of AI-assisted code in the repository will grow with
    this feature; keep the README's disclosure accurate.
12. **WAF per-IP limit:** 100 requests per 300 s, handshakes included; shared office
    IPs and reconnect storms can reach it (§9.3).
13. **Worker code follows `master` at boot** (§9.4), outside the pipeline's approval
    step; relevant to any stream function that runs on workers.
14. **Cold start:** about 2.5 minutes from zero workers (§9.4). A stream function that
    needs a worker inherits it; functions that run in the API process do not.
15. **Memory per socket, and memory that is not returned** (§9.5-9.9): the first design cost
    1.2-1.7 MiB per socket and left tens of MiB allocated after sockets closed. With one
    shared Pub/Sub connection per process it is about 0.6 MiB per socket in a local run, but
    on dev each 30-socket cycle still leaves 2-4 MiB more in use after six cycles; the steps
    shrink and have not reached zero. Autoscaling reacts to CPU and request count, not
    memory, so memory pressure does not add tasks; an out-of-memory kill restarts the task.
16. **Caps count per uvicorn worker** (§9.6, §9.8): the image runs two workers, so the
    defaults of 25 sockets and 5 per user per worker mean 50 and 10 per task. Refusals were
    seen on dev (4 and 6 in 0f); the per-user cap has not been probed.
17. **Tokens in logs:** `?token=<JWT>` lands in the API log group (30-day retention) as
    well as CloudFront's standard logs (§3.7). The result stream now has a 60 s, one-task token
    for this (§3.7), so a logged URL is dead a minute later; a session JWT is still accepted
    there and would still be logged for its hour. 0i confirmed the API access line holds the
    stream token in clear (§9.12), and 0k that CloudFront's standard logs do too: 27 of the 41
    request lines in one log object carried `token=` (§9.15). The token is dead a minute later; the
    lines are not redacted at either place.
18. **Pub/Sub on the cache:** the dev cache refuses pattern subscriptions (§9.8), so only
    per-channel `SUBSCRIBE` and `PUBLISH` are used. Pub/Sub keeps nothing, so every stream
    path keeps a state read behind the push (§9.9).
19. **Retry loops:** a subscriber that resets its back-off when it *sends* a command, not
    when the server confirms it, spins against a server that refuses (§9.8). Any stream
    component that reconnects needs the same rule.

---

## 8. Decisions needed from Filippo

1. **Latency class:** is "within a few seconds" right, or is sub-second needed? (Measured
   data is in §9.1: 371 of 386 rows have a p50 under 50 ms, 15 are slower, 2 take over
   a second.)
2. **Hosted, self-hosted, or both**, and in what order? (This document recommends D
   first.)
3. **First asset classes and functions** worth making stream-eligible.
4. **Audience and tier:** Enterprise-only, Pro add-on, or open?
5. **Legal review** of customer-supplied vendor data, before any hosted offering.
6. **Authentication:** agree on short-lived stream tokens instead of keys in URLs. (Built for
   the result stream, §3.7; the quote stream would reuse it.)
7. **Where the code lives:** in this repository or a separate one (a separate package
   keeps the AI-assisted share of the main codebase easier to account for).

---

## 9. Phase 0 results

Eleven measurement runs by a delegated AWS agent against the dev stack: Phase 0
(2026-10-22), 0b and 0c (2026-10-23), 0d (late on 2026-10-23, UTC), 0e (2026-10-24), 0f and
0g (2026-10-25), 0h (2026-10-26), 0i (after #403 was deployed, §9.12), 0j (§9.13) and 0k (after #405, §9.15), plus one
`/health` sample on prod. The numbers are the
agent's; the code readings are mine. §9.7 reports local reproductions in my sandbox (a
TLS-only Redis, the real app under uvicorn with two workers), which are not AWS numbers.

### 9.0 Defects the measurements found

| # | Defect | Found by | Fixed |
|---|---|---|---|
| 1 | `WS /var/stream` crashed on any job not yet finished: it built its Redis client from the `localhost` default | Phase 0 | #396 |
| 2 | The worker publishes before Celery stores the result, so the route re-read "pending" and waited a whole poll (2.036 s) | 0b | #397 |
| 3 | Workers had no `S3_BUCKET`: every result above 10,000 simulations stayed inline (10.9 MB at 500,000), logged as a WARNING no alarm watches | 0c | #398 |
| 4 | Abandoned sockets stayed alive for the full 900 s wait, and nothing limited how many a process or user could hold | 0d | #398 |
| 5 | The shared subscriber of #400 used `PSUBSCRIBE`, which the cache refuses, and its retry loop reset the back-off right after *sending* the command, so it retried once a second per process (3,022 failures in 30 minutes, idle CPU 1.5% to about 8%, memory creeping with no sockets) | 0f | #401 |
| 6 | With the subscriber up the route waited on a 10 s timer and noticed a closed client only when it ended (up to 10.04 s) | 0g | #402 |
| 7 | Every thread of the pool that reads results built its own Celery result backend (Redis client, connection pool, TLS context, about 1 MiB), and retired threads' backends stayed in reference cycles until the next full garbage collection: up to 21 live backends per process against 2-3 threads | local profiling (§9.11) | #403 |
| 8 | The shared subscriber rebuilt its whole Redis client every time it idled out (60 s with nobody waiting), leaving a new connection object and TLS context behind each time: about 1 MiB a socket cycle on dev | 0j (§9.13), reproduced locally (§9.14) | #405 |

Defects 5 and 6 were introduced by the fixes for 3 and 4 and found by re-measuring them.
Defect 7 (§9.11) was found by profiling the per-cycle memory step (§9.9) locally and is
fixed in #403 and re-measured on dev in 0i (§9.12). Defect 8 was found by 0j (§9.13), reproduced
locally (§9.14), fixed in #405 and re-measured on dev in 0k (§9.15): the step is gone.

### 9.1 Compute latency (in-process, 0.5 vCPU Fargate task, no network)

- Measured: **all 385 functions** (386 rows: `kri_threshold_breach_detection` has two
  example bodies), run 0d. Same image and task size, no environment, called in-process
  through the real app. 41 of the schema-built bodies needed hand-set parameters for
  cross-parameter rules. One discarded call, then 30 warm calls, at most 8 s per function;
  nine rows hit that budget with n between 2 and 23. All 386 returned a result. The data
  is `docs/data/streaming-phase0d-latency.csv`; the first run measured 283 and its 103
  422s are now measured.
- By warm p50: under 50 ms for 371; 50-250 ms for 4; 250 ms-1 s for 9; 1-5 s for 2; none
  above 5 s. Median p50 5.9 ms. By p95 the buckets read 6 / 366 / 12 / 2 / 0, which is
  the quota stall of §9.2, not function cost: use p50.
- The 15 rows with a p50 of 50 ms or more (p50 / p95, ms):
  rBergomi 4,021 / 4,097; `american_option_lsm` 1,091 / 1,186; `lmm_bgm_rate_model`
  785 / 816; `cox_ingersoll_ross_model` 689 / 693; `lookback_option_pricer` 688 / 700;
  `asian_option_pricer` 618 / 704; `volatility_surface_implied_vol` 419 / 658;
  `nelson_siegel_svensson_curve` 408 / 598; `bermudan_option_pricer` 376 / 381;
  `hull_white_short_rate_model` 282 / 294; `vasicek_interest_rate_model` 276 / 295;
  `scenario_analysis_oprisk` 215 / 292; `resampled_efficient_frontier` 210 / 275;
  `potential_future_exposure_pfe` 81 / 84; `extreme_value_theory_var` 69 / 109.
  `macro_scenario_generator` is fast at the median (11 ms) with a 508 ms p95.
- A fresh process takes 8.4-14.5 s to import the app (median 8.8 s). With an empty
  Numba cache the first call took a median 6 ms, six functions 0.65-2.2 s and the
  parallel kernels 1.7-2.6 s (first run). Stream workers must be long-lived and
  pre-warmed.

### 9.2 CPU budget

- The p95 plateau near 53-57 ms is the 0.5 vCPU quota. First run, closed loop (28
  examples, 100 calls each): p50 2.7 ms, p95 52.9 ms, CPU duty capped at 0.50. Paced at
  about 30% duty: p95 4.0 ms, plateau gone; it returns when the loop is closed again.
  The cgroup counters show nothing from inside the container, so the quota cannot be
  read directly. In 0d, 359 of the 363 rows with a p50 under 20 ms show a p95 of 45-75
  ms; the agent puts the stall at about 6% of back-to-back calls.
- Planning figure: below about 35% sustained duty at roughly 3.7 ms per call, on the
  order of 90 computations per second per task. Handler time only; it excludes socket
  I/O, quote binding and serialisation.
- Two Numba threads buy nothing at 0.5 vCPU; one thread was 16% faster on the heaviest
  of three functions tested (`asian_option_pricer`, 512 ms against 608 ms).

### 9.3 Edge and network

- Read from the live stack: CloudFront's default behaviour serves `/api/*` (all
  methods; all viewer headers except Host forwarded; origin read timeout 30 s, keepalive
  5 s). ALB idle timeout 60 s; stickiness cookie 3,600 s; deregistration delay 300 s but
  ECS stop timeout 30 s, so the effective drain is 30 s. CloudFront standard logging is
  on; ALB and WAF logging are off.
- WAF (us-east-1): `RateLimitPerIp` 100 requests per 300 s per IP, block, all paths;
  `AggregateRateLimit` 6,000 per 300 s; no WebSocket-specific rule. Handshakes count;
  frames are believed not to (untested), and nothing was blocked while 135 sockets were
  open. The dev ACL (`pyvar-dev-waf`) has the same rules.
- `/health` through the edge on prod, from one vantage point (Paris POP): keep-alive
  TTFB p50 34.6 ms, p95 52.5 ms; a fresh connection 153 ms. In-process `/health` is
  2.4 ms at p50, so the edge adds about 32 ms.
- TLS: all 15 handshakes succeeded with no ALPN, `http/1.1`, and `h2,http/1.1`. Offering
  h2 gets h2 selected, and a WebSocket cannot upgrade over it, so clients must offer
  `http/1.1` only. One earlier attempt closed during the upgrade and is unexplained.
- 135 handshakes in 0d all returned 101: p50 83 ms, p95 97-122 ms, worst 615 ms.

### 9.4 WebSocket route

- The upgrade returned 101 in 79-115 ms through CloudFront, WAF and ALB. Three pending
  sockets (no client pings; a ping every 25 s; every 50 s) each held 901 s and ended with
  the server's timeout frame and close code 1000. uvicorn sent its own ping every 20 s,
  so the sockets were never idle on the wire: the ALB's 60 s idle timeout and
  CloudFront's idle limit were not exercised, and a client that does not answer pings
  was not tested. The ping interval should be set explicitly.
- **Push against poll.** Before #397 (0b): a job that was pending when its socket opened
  waited 2.036 s, one poll tick (defect 2). After #397 (0c, 8 jobs of 500,000
  simulations, in flight at open): the frame arrived 2.1-2.35 s after the open with a
  spread of 0.07 s, where polling alone would have given about 3.7 s and the old race
  about 4 s. The wake-up itself could not be resolved there, because defect 3 made each
  frame 10.9 MB (about 1.7 s to deliver). After #398 (0e, frames of 1.7 KB, three jobs):
  **30, 127 and 172 ms after the worker stored the result** (the worker log's
  "succeeded in" time, ±15 ms), with the socket opened 157-282 ms before each job
  finished. A job already finished when the socket opens is answered in 21 ms (22 kB). With the
  shared subscriber on dev: **29, 125 and 156 ms** (0g) and **128, 129 and 166 ms** (0h),
  ±10 ms, and **155, 126 and 128 ms** (0i, opened with a stream token, §9.12). In between,
  while the cache refused the pattern subscription and every socket polled every 2 s, 1.69,
  1.84 and 1.87 s (0f).
- Cold start: with the worker group at zero, a job waited 159 s from POST to worker
  pickup (an earlier run) and 162 s from POST to success (0e, including 6.2 s on the cold
  task).
  The scale-to-zero alarm removes an idle worker about four minutes after its last job.
- Workers get their code by `git clone` of `master` at boot (`compute_stack.py`:
  "Hypothesis B", with a TODO to replace it with the baked AMI), not through the
  pipeline. A worker runs whatever `master` holds when it boots.
- The route is logged with its full URL, `?token=<JWT>` included: 135 lines for 135
  sockets in the API log group (30-day retention), on top of CloudFront's logs.

### 9.5 What one API task held (0d, before #398)

One dev API task (0.5 vCPU, 1 GiB; autoscaling 1-3 on CPU 60% and 500 requests per
target, which never triggered). Idle sockets on pending job ids, one new socket every
5 s, CloudWatch at one minute.

| Sockets | Memory | CPU avg | Redis connections | `/health` p50 / p95 |
|---|---|---|---|---|
| 0 | 76.9% (787 MiB) | 1.4% | 7 | 89 / 122 ms |
| 50 | 77.7% | 6.0% | 69 | 92 / 121 ms |
| 100 | 81.2% (max 83.0) | 23.8% | 136 | 100 / 147 ms |
| 135 | 92.8% (950 MiB) | 13.2% | 232 | 90 / 116 ms |

- The memory stop rule (above 85% for two consecutive minutes: 86.0% and 87.6%) fired at
  135 sockets. CloudWatch lags one to two minutes, so the ramp overshot by about 20
  sockets before it acted; 150 was never reached and the jobs at 150 did not run.
- Average cost at 135: 1.21 MiB per socket, and 0.44 milli-vCPU. Growth was steeper
  later: about 0.16 MiB per socket over the first 50, 0.7 over the next 50, about 3 over
  the last 35. A possible reason (not tested): the task had been used for 0c, whose
  10.9 MB frames had already stretched its heap, so the first sockets reused freed space.
  On a fresh task (0e) the baseline was 62.7-65.4%.
- **Abandoned sockets.** All 135 clients closed at 23:36:47. The handlers kept polling
  Redis, about 4,000 reads a minute (135 sockets x 30), and held 232-253 Redis
  connections until each one's own 900 s wait ended: the API logged 135 "Client
  disconnected" lines, 900-902 s after each socket opened. Memory reached 98.1% and
  stayed there with no sockets and 1.1% CPU. Cause: the route only sends, and Starlette
  reports a closed client only on a send or receive (defect 4, fixed in #398).
- Redis peaked at 4,761 ECPU per minute against the serverless cache's 5,000 per second
  cap. The ALB saw about 2 connections per socket and Redis about 1.7.
- No 429, 403 or 5xx; the WAF blocked nothing; ALB response time stayed under 60 ms on
  average.

### 9.6 After #398 (0e, dev)

- **S3 offload works.** Frames of 1.7 KB instead of about 11 MB; the presigned URL
  returned 5.19 MB of Parquet (`PAR1` at both ends); 4 "Result written to S3" log lines,
  none for the failure message.
- **Abandoned sockets are released.** Closing 50 sockets produced 50 "Client
  disconnected" lines 0.19-3.13 s later (median 1.9 s), against 900 s before.
- **The caps never refused anything.** An 11th socket for one user and a 51st on the
  server were both accepted. The image runs two uvicorn workers (`Dockerfile:166`) and
  #398 counts per process, so a task holds up to 100 sockets and 20 per user; the
  description of #398 said per task, which was wrong. Defaults of 25 and 5 per worker
  would give the intended 50 and 10 per task.
- **Memory is still not returned.** 65.43% before, 71.74% at 50 sockets, 73.63% after the
  close, unchanged for seven minutes: about 84 MiB, or 1.7 MiB per socket, retained
  although every handler had ended within 3 s. CPU and ALB connections were back to
  baseline within a minute; Redis connections stayed at 37 against about 6 before.
  Candidate causes, none proven: the synchronous result reads run on a thread pool, one
  Redis connection per concurrent thread, which grows and keeps its TLS contexts (0.83
  MiB each, measured locally on OpenSSL 3.0.13; every socket also builds its own async
  client with one); and freed heap that the allocator does not hand back. The test that
  separates a bounded high-water mark from a leak is repeated open-and-close cycles:
  a plateau or steady growth.

### 9.7 Local reproduction, and what the shared subscriber changed

A local run (my sandbox, not AWS): the real app under uvicorn with the image's flags and
two workers, a TLS-only Redis, 50 idle sockets per cycle, memory summed over both workers.
Python object counts stayed flat after every cycle (no leaked tasks, clients or contexts)
and `malloc_trim` handed back most of the retained memory: freed heap that the allocator
keeps, not a leak. What made it large was the per-socket Redis client; each Redis
connection builds its own TLS context (0.83 MiB, measured on OpenSSL 3.0.13).

| Memory held after the sockets close, change from start | cycle 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| a client per socket (#398) | +76 MiB | +118 | +142 | +174 | +209 |
| one pattern subscription (the version of #400) | +31 | +36 | +37 | +39 | +41 |
| one `SUBSCRIBE` per job on one connection (#401) | +19 | +24 | +26 | +28 | +29 |

Per socket, first cycle: 1.51 MiB, then 0.62, then 0.38. Redis connections at hold: 73-87,
then about 20, then 9-10. With the image's `MALLOC_ARENA_MAX=2` the difference was small with two
workers (+41 against +39) and larger in one-worker runs of 15 cycles (+93 against +62).
Playing the worker's part (publish, then store 50 ms later): pushed 53-54 ms after the
store; a result stored with no message was delivered by the safety poll after 9.2 s; after
a Redis restart new sockets were pushed 52-55 ms after the store (one took 1.2 s, on a
worker still reconnecting and polling at the short interval).

A first version of #401 applied subscriptions only on the reader's 500 ms tick. Sockets
arriving together then read the job state together, each on its own thread and Redis
connection, and memory was worse (+42 to +64 MiB, 33-50 connections). The reader now wakes
at once for a new waiter.

### 9.8 #400 on dev (0f): the cache refuses `PSUBSCRIBE`

- The shared subscriber of #400 got `ResponseError: unknown command 'psubscribe'` from the dev
  cache (ElastiCache Serverless, Redis 7.1) at its first use. Every socket then polled every
  2 s, as designed: lag 1,694, 1,871 and 1,837 ms.
- The retry loop made it costly. The back-off was reset after the command was *sent*; a
  server that refuses answers on the next read, so the reset happened every time. One
  retry a second per process, each with a new TLS connection: 199 failure lines in the
  first test window, 3,022 in 30 minutes, about 116 a minute. Idle CPU went from 1.5% to
  about 8%; memory rose 0.8, then 0.33 points a minute with no sockets open and reached
  84.7% of 1 GiB; cache connections went from 5 to 38. #400 had expected the fallback to
  cost nothing; its unit tests modelled a send that fails, not a refusal that arrives later.
- A local Redis with the command renamed away gave the same error text and reproduced it:
  234 failure lines in 120 s, +57 MiB and rising, 6-10% of a core. The fix (#401) gave 8
  lines, +15 MiB flat, about 0.7%.
- The same run showed the per-worker caps working: 4 and 6 refusals ("Too many open
  streams on this server") with 40 sockets per cycle, and every closed socket released within
  1.75 s while the timer was 2 s.
- Log gap: the refusal and disconnect lines carry only the event, level, logger and time;
  no task id, reason or open-stream count, so refusals can be counted but not attributed.

### 9.9 #401 and #402 on dev (0g, 0h)

- **0g (#401).** Push 29, 125 and 156 ms; 0 failure lines in 70 live checks; ten idle
  minutes flat (memory slope 0.000 points a minute, CPU 1.1%, 37 cache connections). But
  63 of 120 closed sockets were released more than 4 s after the close, up to 10.04 s: with
  the subscriber up the route waits on the 10 s timer and looked at the disconnect reader
  only when it ended (defect 6).
- **0h (#402).** The reader's completion now wakes the wait. 180 of 180 closed sockets were
  released within 0.22 s; push 128, 129 and 166 ms; 0 failure lines and 0 errors over 79
  minutes; handshakes 73-158 ms; no stop rule fired (memory peaked at 67.2%).
- **The step per cycle.** Memory "before" each of six 30-socket cycles rose by +1.94 (this
  one includes the jobs), +0.88, +0.59, +0.20, +0.39 and +0.39 points, i.e. 2-4 MiB in the
  last four; 0g had been about +0.9 points a cycle. A burst of 20 sockets in 0g cost the same
  as 40, so the step is per cycle, not per socket. Cache connections rose +8, +8, then held
  at 22-28 (4 at idle, 26 after the run). The plateau fits the thread-pool explanation
  (the synchronous result reads each take a connection with its own TLS context, up to a
  saturation point); the cause was not measured, and six cycles cannot show whether the
  memory step reaches zero. The idle level ended 6 points (about 60 MiB) above a fresh task.

### 9.10 Still to do

- Memory: settled by #405 on dev (0k, §9.15): 630 to 637 MiB over 24 cycles, flat from cycle 16 and
  while idle. A longer run (a few hours of mixed traffic) would show whether anything else creeps; the
  framework's own growth locally (§9.11) is the thing to watch.
- Redact `token=` in the API access line (§3.7, risk 17). CloudFront's standard logs hold it too and
  cannot be redacted at the edge; with a 60 s token that is a retention question, not a leak.
- The API-key path on dev: 0i could not create a test user (the dev database is private, with no
  Data API), so minting with a real key has only been tested locally.
- Give the refusal and disconnect log lines their context (task id, reason, open streams).
- Probe the caps above 25 sockets per worker and 5 per user on dev; the 30-socket cycles of
  0h never reached them.
- Eligibility flags in `portal/functions.json` from the CSV (§3.10); the 15 slower
  functions get coarse cadence.
- Stop accepting the session JWT on the stream once clients have moved to stream tokens
  (§3.7, risk 17), and decide whether a token should be single use.
- Optional: one WebSocket probe on prod. The pipeline's prod smoke test passed, but the
  route itself has not been probed there.

### 9.11 The memory step, profiled (local, my sandbox; not AWS)

Setup: the real app under uvicorn (two workers, uvloop, httptools, `MALLOC_ARENA_MAX=2`), a
TLS-only Redis on the same machine, 30 idle sockets opened and closed per cycle, memory summed
over both workers. The profiled runs also had each worker dump, every 10 cycles, its object counts
by type, its Redis connection pool and glibc `mallinfo2` (signal handlers in a wrapper module,
not in the repository).

- **What grew.** The 150-cycle soak of §9.9's open question (old code) rose to +77.2 MiB and was
  still climbing at 0.55 MiB a cycle, with the cache's connection count rising from 11 to 44. The
  dumps showed the cause: `RedisBackend`, `SSLContext` and `ConnectionPool` objects piled up, up
  to 21 `RedisBackend` per process against 2-3 live pool threads, and dropped in batches when the
  cyclic collector ran. Celery keeps a result backend per thread unless the backend class is
  thread-safe, and the Redis backend is not; the result reads run in Starlette's thread pool,
  whose threads are retired after 10 idle seconds (anyio). A forced `gc.collect()` plus
  `malloc_trim` after 60 cycles took the processes from +46.3 to +26.4 MiB.
- **The change.** `_shared_result_backend()` gives every read one backend (its Redis client is
  thread-safe and the reads use nothing else of it).

| | Old code | One shared backend |
|---|---|---|
| Memory gained, cycle 10 / 50 / 100 / 150 (MiB) | 21.8 / 40.2 / 53.1 / 77.2 | 22.9 / 32.2 / 35.8 / 47.9 |
| Slope over the last quarter (MiB a cycle) | 0.55 | 0.21 |
| Most cache connections | 44 | 10 |
| `RedisBackend` per process (60-cycle profile) | up to 21 | 2 |
| Returned by `gc.collect()` + `malloc_trim` at cycle 60 (MiB) | 19.9 | 3.1 |

- **What is left.** The soak still climbs, 0.2 MiB a cycle (about 7 KiB a socket), and 150 cycles
  do not show a plateau. A bare Starlette WebSocket route with no Redis and no pool threads, same
  flags, gained +12.8 MiB over 60 cycles at 0.06 (second half) to 0.12 (last quarter) MiB a cycle,
  so about half of what is left is the framework and the allocator, not this code. The rest is not
  in Python objects (counts flat over 50 cycles; lists grew by about ten a cycle) and was not
  located.
- **What this does not say.** On AWS the step was +0.2 to +0.4 points of 1 GiB a cycle (2-4 MiB),
  ten or more times the local figure for the same 30 sockets. The sandbox reproduces the mechanism
  and the direction, not the size. The dev run with #403 deployed is §9.12: the cache connections
  stopped stepping, the memory step fell to 0.27 points a cycle (about 2.8 MiB), still about
  fourteen times the local 0.2 MiB.

### 9.12 #403 on dev (0i)

Image `pyvar-dev-api:40893c3`, one task, rollout completed; an unauthenticated POST to the mint
route returned 401 (so the change is deployed).

- **Token flow, three jobs of 500,000 simulations.** Mint 76, 101 and 81 ms (200, `Cache-Control:
  no-store`, `x-cache: Miss from cloudfront`, `expires_in` 60); frames 1,753, 1,751 and 1,755
  bytes; push lag **155, 126 and 128 ms** (median 128; the agent's clock was 29-32 ms behind and
  was corrected, ±10 ms). The socket opened 55-126 ms before the worker's log line, so each job
  was in flight, with little margin: the mint sits between the POST and the socket and takes 76-101
  ms, and a faster job could finish first.
- **Claims** of one token: `aud` `pyvar-stream`, `tid` equal to the task id, `exp - iat` 60, no
  tier; the claims are `aud`, `exp`, `iat`, `sub`, `tid`.
- **Negative checks**, all as designed (every socket answered 101, then closed):

| Check | Result |
|---|---|
| Token minted for task X used on task Y | close 1008 "Invalid or expired token" |
| No token | 1008 "Missing token" |
| `pyvar_` plus 43 random characters as the token | 1008 "Invalid or expired token" |
| Mint, wait 65 s, open | 1008 "Invalid or expired token" |
| Stream token as Bearer on `GET /var/result/{id}`, `POST /auth/api-keys`, `POST /var/stream-token/{id}` | 401 "Invalid or expired token: Invalid audience", each |
| Service JWT as `?token=` on a finished job | the frame (1,753 bytes) |
| Mint with no Authorization / with id `a b` | 401 "Not authenticated" / 422 `string_pattern_mismatch` |

- **Not tested: the API-key path.** No test key under `pyvar/dev/`; the dev Aurora cluster is
  private (10.0.4.17, port 5432 times out from the agent's host) with no Data API; a verified user
  needs a database read or write, and ECS Exec or a one-off task would be service changes. Nothing
  was registered or created.
- **The stream token is in the API log in clear.** All three request lines read
  `WebSocket /api/v1/var/stream/{id}?token=<token> [accepted]`. It is good for 60 s and one task,
  but redacting `token=` in that line would close the gap. The CloudFront edge logs were not
  checked.
- **Six cycles of 30 sockets** (hold 30 s, watch 2 min). 180 of 180 handshakes returned 101
  (median 81-83 ms per cycle, worst 152 ms); no refusals; every closed socket was released within
  0.20 s (median 0.04-0.10 s per cycle); `/health` 88 calls, all 200, 72-140 ms.
- **Memory and cache connections** (1-minute CloudWatch; "before" is the last full minute before
  a cycle's first socket):

| Cycle | Memory % before / hold / T+1 / T+2 | Cache connections |
|---|---|---|
| 1 | 63.95 / 64.40 / 64.45 / 64.45 | 10 / 13 / 12 / 13 |
| 2 | 64.45 / 64.55 / 64.55 / 64.55 | 12 / 13 / 11 / 13 |
| 3 | 64.55 / 64.75 / 64.75 / 64.81 | 11 / 13 / 11 / 11 |
| 4 | 64.75 / 64.89 / 64.94 / 65.06 | 11 / 11 / 9 / 11 |
| 5 | 64.94 / 65.23 / 65.33 / 65.33 | 9 / 12 / 11 / 11 |
| 6 | 65.33 / 65.53 / 65.53 / 65.53 | 11 / 13 / 13 / 11 |

  The memory "before" stepped +0.50, +0.10, +0.20, +0.20, +0.39 points (mean 0.27, about 2.8 MiB;
  0h's cycles 2-6 averaged 0.49), with no decay to zero in six cycles. The cache connections did
  not step: 10, 12, 11, 11, 9, 11 before each cycle (0h reached 22-28). Five minutes after the
  last cycle: memory 65.53% (flat for the previous six minutes), cache 11, CPU 1.10%; the task
  had started at 61.82% and 5 connections, and the four jobs and eight sockets of Part 1 alone
  took it to 63.95%. CPU at hold was 1.7-3.2% (0h: 3.1-4.5%).
- **Failure lines.** None: 0 "Shared job-done subscriber failed" and 0 ERROR from the task's start
  to the end of the run (2 h 22 min, 58 live checks). The `ssl_cert_reqs` warning from Redis client
  creation appeared 4 times in the task's life, three at startup, against 67-74 a run before; the
  agent's inference is that this fits one shared backend.
- **Not shown.** Whether memory levels off (six cycles; at 0.27 points a cycle, 85% is about 70
  cycles away if the line is straight); the caps (30 sockets over two processes never reach 25 per
  process); a cold start (the warm-up took 6 s because a worker was warm); cycle 1's "before" falls
  inside the tail of Part 1.
- **Against the local run (§9.11).** 2.8 MiB a cycle on AWS against 0.2 MiB locally for the same 30
  sockets: the sandbox does not reproduce the size, and the difference has no explanation yet.

### 9.13 A longer run on dev (0j)

The same task as 0i (`pyvar-dev-api:40893c3`, started 2026-10-26 19:56 UTC); it began at 65.6%
(672 MiB) after 0i's six cycles. Container Insights had `MemoryUtilized` for the service (whole
MiB a minute); the percentage is that figure divided by 10.24, so MiB adds no resolution. Part 1:
10 cycles of 10 sockets (a socket every 4 s, hold 15 s, close all, watch 60 s). Part 2: 40 cycles of
30 sockets (a socket every 5 s, same hold and watch). Part 3: ten minutes with no sockets. The
per-cycle data is `docs/data/streaming-memory-cycles-dev.csv`.

| Span | Memory before, % (MiB) | Step per cycle |
|---|---|---|
| Part 1, cycles 1-10 (10 sockets) | 65.63 to 66.55 (672 to 681) | 0.117 points, 1.17 MiB |
| Part 2, cycles 1-10 (30 sockets) | 66.60 to 67.48 (682 to 691) | 0.110 points, 1.13 MiB |
| Part 2, cycles 31-40 | 68.95 to 69.63 (706 to 713) | 0.075 points, 0.77 MiB |
| Part 2, all 40 cycles | 66.60 to 69.63 | 0.075 points, 0.75 MiB |

- **Does it level off? No, it slows.** 672 to 715 MiB (+43 MiB, +4.2 points) over 50 cycles and
  1,300 sockets; the slope fell by about a third and is not near zero. The early-finish check (the
  value 8 cycles earlier within 0.15 points) never held: +0.78 at cycle 12, at least +0.29 at cycle
  27, +0.63 at cycle 40. On a straight line from the last ten cycles the 85% mark (870 MiB) is about
  200 cycles away.
- **Per socket or per cycle? Per cycle.** Part 1 stepped +0.098 to +0.103 points a cycle (about 1.0
  MiB) with 10 sockets and 111 s cycles; the first ten cycles of Part 2 stepped +0.098 with 30
  sockets and 220 s cycles. Per cycle they match; per socket they differ 3 times (0.010 against
  0.0033 points) and per minute 2 times. The step is about 1 MiB and the metric resolves 1 MiB, so
  this sits at the resolution limit.
- **Idle drift: none.** 715 MiB for the whole ten minutes of Part 3 (0.00 points); CPU 1.2-2.1%.
- **Cache connections:** 11-18 (per-minute maximum), 11-17 before a cycle; wandering, with steps of
  +2, +2, -2, +1, +1, +2, -1, -1; 11 at the start, 15 at the end.
- **Sockets and logs.** 1,300 handshakes, all 101 (median 80 ms, worst 638 ms); no refusals (30
  sockets over two processes never reach 25 each); every socket released within 0.65 s, none later
  than 2 s; `/health` 494 calls, all 200, 68-185 ms. 0 "Shared job-done subscriber failed", 0 ERROR
  (342 live checks). Memory peaked at 69.82%; no restart, no 429, 403 or 5xx.
- **Against 0i.** 0i's six cycles (hold 30 s, watch 2 min) stepped 0.27 points, 2.8 MiB, a cycle;
  0j's first ten stepped 1.1 MiB. The cycle shape differed and 0i's figure is six readings at 0.1
  point; neither is precise.
- **A hypothesis for the step** (the 0j agent's, tested locally in §9.14): every cycle's 60 s watch
  lets the shared subscriber idle-close its Redis connection (`_BUS_IDLE_CLOSE_SECONDS`, 60 s), and
  the next cycle rebuilds it.
- **Caveats.** Whole-MiB resolution makes single steps noisy (0 to 2.4 MiB); the conclusions rest on
  the 10- to 40-cycle means. A small CPU rise at the end of Part 3 is unexplained.

### 9.14 What each cycle leaves behind (local, my sandbox; not AWS)

My earlier local soaks never idle-closed the shared subscriber: a cycle there lasted about 5 s and the
close needs 60 s with nobody waiting. That is why they stepped about 0.2 MiB a cycle while 0j stepped
about 1 MiB. To test the 0j agent's hypothesis, the same soak (30 sockets a cycle, hold 3 s, watch
8 s, two workers, TLS Redis, 60 cycles) was run with the idle close set to 4 s, so that every cycle
closes the subscriber and the next one rebuilds it; against a control with the close off; and
against the change below. Memory gained, mean of each ten cycles (MiB):

| Run | Cycles 1-10 | 11-20 | 21-30 | 31-40 | 41-50 | 51-60 | Slope, second half | Most cache connections |
|---|---|---|---|---|---|---|---|---|
| Idle close every cycle (the code as it is) | 29.5 | 38.0 | 45.5 | 50.7 | 56.3 | 60.8 | 0.50 | 14 |
| No idle close (control) | 20.6 | 23.8 | 25.4 | 26.9 | 29.1 | 32.2 | 0.26 | 10 |
| Idle close every cycle, client kept | 16.4 | 18.8 | 19.9 | 22.1 | 24.5 | 26.6 | 0.23 | 8 |

- **The rebuild is the cost.** Closing and rebuilding every cycle added about 28 MiB over 60 cycles
  (about 0.5 MiB a rebuild at first, less later as garbage collection catches up). Each rebuild
  makes a new client, a new connection object and a new TLS context (0.8 MiB); the old ones are not
  freed until the cyclic collector runs.
- **The change.** `_JobDoneBus` keeps its Redis client for the life of the process. The idle close
  lets go only of the Pub/Sub object; the next subscription takes the same connection object, with
  the TLS context it already holds. A failed connection is still dropped and rebuilt, and the client
  is closed at shutdown. With it the soak with a close every cycle ended below the control
  (26.6 against 32.2 MiB; run-to-run spread is a few MiB) and the growth was the 0.2 MiB a cycle the
  framework alone shows (§9.11).
- **What this does not show.** The rebuild cost here, about 0.5 MiB, is half of 0j's 1 MiB a cycle,
  and nothing here has run on AWS. On AWS a rebuild happens whenever the subscriber sits unused for
  60 s, which any quiet minute between jobs causes, so real traffic pays it too. The change is in
  `_JobDoneBus` (`api/routes/var.py`, tests in `tests/test_job_done_bus.py`); 0k (§9.15) repeated the
  dev run after it was deployed, and the step is gone.

### 9.15 After #405, on dev (0k)

Image `pyvar-dev-api:2dd839f` (task definition :156, rollout completed, task up 43 min and never
restarted). Part 1: 24 cycles of 10 sockets (two accounts, 5 each; a socket every 4 s, hold 15 s,
close all, watch 70 s, so the subscriber idles out about 61 s after every close). Part 2: 5 idle
minutes. Memory is `MemoryUtilized` in whole MiB; the per-cycle data is
`docs/data/streaming-memory-cycles-dev-0k.csv`.

| Span | Memory before (MiB) | Step per cycle, 0k | Step per cycle, 0j |
|---|---|---|---|
| Cycles 1-10 | 630 to 634 | 0.35 MiB | 1.17 MiB |
| Cycles 15-24 | 636 to 637 | 0.05 MiB | 0.77 MiB |
| Cycles 17-24 | 637 throughout | 0.00 MiB | |

- **It levels off.** 630 to 637 MiB (+7 MiB), flat from cycle 16 and for the 5 idle minutes after
  (0.00 MiB of drift; CPU 1.1%). 0j gained 43 MiB over 50 cycles. The 24-cycle extension rule (a rise
  of more than 8 MiB between cycles 4 and 24) did not apply: 633 to 637.
- **The early steps** (+2, +1, 0, +1, then zeros, +1, +1, then zeros, +1, then eight zeros) probably
  include first-use work in the two server processes; at 1 MiB resolution that cannot be separated.
  Cycles 3-12 alone give 0.25 MiB a cycle.
- **Cache connections:** 5 to 12 a minute, 7 before cycle 1 and 11 from cycle 17; back to 7 within two
  minutes of the last cycle, against a baseline of 6-7, so no net step (0j: 11-18). Most "before"
  minutes overlap the previous cycle's hold, so the idle part is the clean reading.
- **Sockets and logs:** 240 handshakes, all 101 (median 80 ms, worst 159 ms); no refusals; 240 client
  closes with code 1000, every socket released within 0.063 s (median 0.052 s); `/health` 146 calls,
  all 200 (median 91 ms, worst 291 ms). 0 "Shared job-done subscriber failed", 0 "Failed to close
  the job-done subscriber", 0 ERROR, 0 refusals. Peak 46 requests in any 300 s window. No stop rule
  fired, no restart.
- **CloudFront logs.** In one standard-log object (delivered 15:43 UTC), 27 of 41 request lines
  contained `token=`, all of them stream-route lines (counted, never printed).
- **Caveats.** The baseline was not pristine: a VaR job queued at about 15:06 (memory 615 to 628
  MiB, cache connections 1 to 6) and another touch at 15:21 added 2 MiB and 1 connection before the
  first socket, so cycle 1's 630 includes them. The ALB connection metric is not a concurrency count
  and was not used. The agent rebuilt its harness (the 0j one was gone) and tested it only against a
  local mock before the first live request.
- **What this closes.** Defect 8 (§9.0): keeping the client across the idle close removed the per-cycle
  step on AWS as it did locally (§9.14). What 0k does not show is a long run under mixed traffic.

---

## Appendix A — example messages (WebSocket JSON)

Subscribe to an option price driven by a spot quote (parameter names are those of
`black_scholes_european_option` in `portal/functions.json`):

```json
{"op": "subscribe", "calc_id": "call-eurusd-1m",
 "function": "derivatives/black_scholes_european_option",
 "params": {"spot": {"$quote": "EURUSD.mid"}, "strike": 1.10, "rate": 0.03,
            "sigma": 0.08, "tau": 0.0833, "option_type": "call"},
 "trigger": {"on": "quote", "min_interval_ms": 250}}
```

Subscribe to a historical VaR from a rolling window of log returns (parameter names
from the REST function):

```json
{"op": "subscribe", "calc_id": "var-eurusd",
 "function": "market-risk/historical_simulation_var",
 "params": {"returns": {"$window": {"ref": "EURUSD.mid", "n": 250, "transform": "log_return"}},
            "portfolio_value": 10000000, "confidence_level": 0.99},
 "trigger": {"on": "interval", "interval_ms": 5000}}
```

Quote event frame and acknowledgement:

```json
{"op": "quote", "events": [{"id": "EURUSD", "field": "mid", "value": 1.0842,
  "ts": "2026-10-22T14:03:07.412Z", "seq": 18231, "src": "desk-feed-1"}]}
```

```json
{"type": "ack", "calc_id": "call-eurusd-1m", "status": "subscribed"}
```

A warning and an error frame:

```json
{"type": "warn", "calc_id": "var-eurusd", "code": "window_not_full", "have": 112, "need": 250}
```

```json
{"type": "error", "calc_id": "call-eurusd-1m", "status": 422,
 "detail": "sigma must be positive"}
```

## Appendix B — what would change in the repository (for later, not now)

Listed only so the size of each approach is visible. Nothing below is proposed for
immediate action.

- **All approaches:** a versioned specification document; a stream core module with
  no AWS imports; conformance and replay tests; per-function eligibility flags in the
  function catalogue; `stream_*` limits in `config.py`.
- **A:** a route module under `api/routes/`; executor settings; feature flag.
- **B:** a new CDK stack and pipeline stage; a path-based ALB rule behind CloudFront.
- **C:** the above plus a managed log service or broker and its IAM and networking.
- **D:** a package (or an addition to `pyvar-client`), a container entry point,
  documentation.
