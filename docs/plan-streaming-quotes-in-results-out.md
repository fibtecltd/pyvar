# Exploration: streaming quotes in, calculation results out

**Status: exploration, with two decisions recorded — no streaming-service code and no
new infrastructure yet.** (Phase 0 found and fixed four defects in the existing
job-completion route and its deployment: §9.0.) Requested 2026-10-22: a streaming in/out service for event-driven,
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
Two problems stay open: what a socket costs in memory and why that memory is not
returned (§9.5, §9.6), and the socket caps, which count per uvicorn worker, two per
task (§9.6).

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
| One WebSocket route exists: `WS /api/v1/var/stream/{task_id}` (job-completion push), session JWT in `?token=`, Redis Pub/Sub, 15-minute cap. It crashed on any job that was not finished yet until #396, raced the result store until #397, and kept abandoned sockets for 15 minutes with no limit until #398; **tested on dev through CloudFront, WAF and the ALB** (§9.4-9.6). Prod has not been probed directly | `api/routes/var.py`, `CHANGELOG.md`, Phase 0 reports |
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
   **Status (2026-10-24):** latency measured for all 385 functions, edge and WebSocket
   behaviour and the load one task carries measured on dev; see §9. What remains is
   listed in §9.7.
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
15. **Memory per socket, and memory that is not returned** (§9.5, §9.6): about 1.2-1.7 MiB
    per socket on a task that idles at 63-77% of 1 GiB, and about 84 MiB stayed allocated
    after 50 sockets closed. Autoscaling reacts to CPU and request count, not memory, so
    memory pressure does not add tasks; an out-of-memory kill restarts the task.
16. **Caps count per uvicorn worker** (§9.6): two budgets per task, so the effective
    limits are double what #398 stated.
17. **Tokens in logs:** `?token=<JWT>` lands in the API log group (30-day retention) as
    well as CloudFront's standard logs (§3.7).

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
6. **Authentication:** agree on short-lived stream tokens instead of keys in URLs.
7. **Where the code lives:** in this repository or a separate one (a separate package
   keeps the AI-assisted share of the main codebase easier to account for).

---

## 9. Phase 0 results

Five measurement runs by a delegated AWS agent against the dev stack: Phase 0
(2026-10-22), 0b and 0c (2026-10-23), 0d (late on 2026-10-23, UTC) and 0e (2026-10-24),
plus one `/health` sample on prod. The numbers are the agent's; the code readings are
mine.

### 9.0 Defects the measurements found

| # | Defect | Found by | Fixed |
|---|---|---|---|
| 1 | `WS /var/stream` crashed on any job not yet finished: it built its Redis client from the `localhost` default | Phase 0 | #396 |
| 2 | The worker publishes before Celery stores the result, so the route re-read "pending" and waited a whole poll (2.036 s) | 0b | #397 |
| 3 | Workers had no `S3_BUCKET`: every result above 10,000 simulations stayed inline (10.9 MB at 500,000), logged as a WARNING no alarm watches | 0c | #398 |
| 4 | Abandoned sockets stayed alive for the full 900 s wait, and nothing limited how many a process or user could hold | 0d | #398 |

Open: memory per socket and memory that is not returned (§9.5, §9.6); the caps count per
worker process (§9.6).

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
  finished. A job already finished when the socket opens is answered in 21 ms (22 kB).
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

### 9.7 Still to do

- A local reproduction with a TLS Redis: memory per socket, repeated cycles, leftover
  connections; then the candidate fixes.
- The rework: one shared Pub/Sub subscriber per process instead of a client per socket,
  per-worker cap defaults (25 and 5), corrected comments. Then a stepped re-run of 0d
  (25 sockets per step, held three minutes) with at least 15 service users, because the
  per-user cap is 10, and a dev-only cap override above 50.
- Eligibility flags in `portal/functions.json` from the CSV (§3.10); the 15 slower
  functions get coarse cadence.
- Optional: one WebSocket probe on prod. The pipeline's prod smoke test passed, but the
  route itself has not been probed there.

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
