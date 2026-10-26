# Changelog

All notable changes to pyvar are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Stream tokens: `POST /api/v1/var/stream-token/{task_id}`** — a client holding an API key
  can now open `WS /var/stream/{task_id}`. The WebSocket handshake cannot carry an
  `Authorization` header and URLs are logged (the API log, CloudFront), so until now the stream
  took only a 60-minute session token in `?token=`, which an API-key client does not have. The new
  route exchanges either credential, sent in a header, for a token that lasts
  `var_stream_token_ttl_seconds` (60 s), opens the stream of that one task and is refused by every
  other route (it carries an `aud` claim, so `decode_token_payload`, `get_current_user` and
  `require_session` reject it without a check of their own; it carries no tier). The stream still
  accepts a session JWT as before; an API key is still refused there. Like the poll endpoint, the
  route does no ownership check and is not metered against the compute quota. Tests in
  `tests/test_api.py`.

- **`pyvar Local` download page (item 2)** — `portal/local.html`, linked
  from the main nav and the footer's "Developers" column
  (`portal/pyvar.js`). Confirmed the `pyvar-local` build+publish pipeline
  had already run successfully (release `pyvar-local-v0-6682472c`,
  2026-09-12) but had no discoverable link anywhere on the site; this page
  describes what the image is and who it's for, links directly to the
  release asset, documents usage (`docker load` → `docker run ... list` →
  `docker run ... call ...`, plus running the shipped test suite
  yourself), and states explicitly what's in vs. not yet in this first
  release. Licensing mechanism (signed releases, a regulatory
  documentation bundle, an update SLA) stays deferred to item 5, unbuilt.

- **Pro-tier billing (Phase A)** — `POST /billing/checkout`,
  `POST /billing/webhook`, `GET /billing/checkout/complete`
  (`api/routes/billing.py`) wire up Stripe Checkout so a user can actually
  subscribe and have `users.tier` flip to `pro` automatically, closing the
  gap `docs/plan-monetization-implementation.md` identified: tier
  enforcement (`api/middleware/rate_limit.py`) was real, but nothing could
  ever set a user's tier to anything but `free`. Monthly-only, no trial,
  Stripe Checkout (hosted — pyvar's own infrastructure never touches card
  data), Enterprise remains a manual, sales-assisted path — all per
  confirmed decisions in that plan doc. `customer.subscription.deleted`
  and `invoice.payment_failed` both flip a user back to `free`, not just
  the happy path. New `users.stripe_customer_id` column
  (`0007_user_stripe_customer_id`), new `STRIPE_SECRET_KEY` /
  `STRIPE_WEBHOOK_SECRET` / `STRIPE_PRICE_ID_PRO` settings (all optional —
  billing routes return 503 rather than erroring when unset). Also closes
  a real gap the existing minimal auth system had no other way to close:
  `GET /billing/checkout/complete` issues a fresh JWT reflecting the
  user's current tier immediately after Checkout, since an already-issued
  JWT's embedded tier claim is never re-checked against the database (see
  that route's own docstring) — without it, a successful subscription
  would be real in the DB but invisible to actual rate-limit enforcement.
  AWS Secrets Manager wiring for the three Stripe values is deliberately
  NOT part of this change — see the plan doc's own follow-up section for
  why and the exact snippet to add once the secrets exist. **Since live-
  deployed**: wiring the three Stripe secrets took 4 follow-up PRs
  (#337–#341) to get the deploy right — see
  `docs/plan-monetization-implementation.md`'s update log for the full
  arc — landing on granting them to the ECS task role and fetching them
  in-app at startup (mirroring the existing `SENTRY_DSN` pattern) rather
  than via `execution_role` + `secrets={}`, so a new secret grant can
  never again gate whether the container is allowed to launch at all.

- **Monthly usage limits + billing-lifecycle audit trail (item 5 §8
  follow-on)** — Pro accounts now face two additional monthly caps beyond
  the existing daily quota: a request-count cap enforced generically
  across every `/api/v1` compute endpoint
  (`api/middleware/rate_limit.py`, `rate_limit_pro_monthly_requests`,
  default 5,000/month) and a VaR-specific simulation-count cap
  (`api/routes/var.py`, `rate_limit_pro_monthly_simulations`, default
  2,000,000/month — scoped to VaR since `VaRJob` is the only endpoint
  family with a per-user simulation-count record today). Breaching either
  hard-downgrades the account to Free for the rest of the current billing
  period (not overage billing) via the new
  `api/middleware/billing_lifecycle.py` module, shared by the Stripe
  webhook and both monthly-cap checks: every tier change now writes a
  durable, queryable audit row (new `billing_events` table,
  `0008_billing_events_downgrade`) and sends a best-effort SES
  notification — closing the "downgrade happens silently, only visible in
  CloudWatch" gap noted when Phase A first shipped. The Stripe webhook is
  now idempotent against redelivery (checked against
  `billing_events.stripe_event_id`) and additionally handles
  `invoice.paid`/`invoice.payment_succeeded` to automatically restore Pro
  access on the next successful payment — scoped narrowly to accounts
  downgraded by one of the two monthly caps, not a payment-failure or
  subscription-cancellation downgrade, which have their own explicit path
  back (a fresh Checkout). New `users.tier_downgrade_reason` column
  distinguishes "auto-downgraded for a monthly limit, should restore on
  next successful payment" from every other reason a tier is `free`.
  25 new tests (`tests/test_billing_lifecycle.py` + additions to
  `tests/test_rate_limit.py`, `tests/test_api.py`, `tests/test_billing.py`);
  full 1,738-test suite re-run clean.

- **Market data adapter infrastructure, MD-1 + MD-2 (item 6)** — first two
  phases of the vendor-agnostic market data adapter
  (`docs/plan-market-data-adapter.md`), no network calls anywhere yet.
  MD-1: `ingestion/market_data/base.py` (abstract `MarketDataProvider`
  interface — `resolve_instrument`/`get_price_series`/`get_yield_curve`/
  `get_vol_surface`, all async), `schemas.py` (canonical Pydantic v2
  `Instrument`/`PriceSeries`/`YieldCurve`/`VolSurface` models — the only
  shapes `engine/`/`api/`/`storage/` are ever meant to see once wired),
  `exceptions.py` (`ProviderError` family), and `providers/fake.py` (a
  deterministic in-memory provider for tests/local dev, seeded via
  `zlib.crc32` for cross-run reproducibility). MD-2: `registry.py`
  (config-driven provider selection via the new `market_data_provider`
  setting — `"fake"` is the only registered option until MD-3 adds
  `"refinitiv"`) and `cache.py` (`CachingMarketDataProvider`, a TTL Redis
  cache wrapping any provider per-method, reusing `api/routes/caching.py`'s
  fail-open philosophy and retry policy). New `market_data_cache_ttl_*`
  settings are explicit placeholder values pending a legal/contract check
  on Refinitiv's actual cache-TTL terms — not yet resolvable, per the plan
  doc's own §3. A static source-scan test enforces the compliance boundary:
  no file under `engine/`, `api/`, or `storage/` may import
  `market_data.providers`. 27 new tests across both phases; full suite
  re-run clean. MD-3 (the real Refinitiv adapter) and MD-4 (pipeline
  wiring) remain hard-gated behind decisions only Filippo can make.

### Fixed

- **Result reads built a Celery backend per pool thread, which showed as memory growing with
  socket churn** — found by profiling the 30-sockets-per-cycle soak locally (two uvicorn workers,
  a TLS Redis). Celery keeps one result backend per thread unless the backend class is
  thread-safe, and the Redis backend is not. `_read_celery_result` runs in Starlette's thread
  pool, whose threads are retired after 10 idle seconds, so each new pool thread built its own
  client, connection pool and TLS context (about 1 MiB), and a retired thread's backend stayed
  in a reference cycle until the next full garbage collection: up to 21 live `RedisBackend`
  objects per process against 2-3 threads, and a forced `gc.collect()` plus `malloc_trim` gave
  back 20 of the 46 MiB the processes had gained after 60 cycles. `_shared_result_backend()` now
  hands every read the same backend (its Redis client is thread-safe and the reads use nothing
  else of it). Applies to `GET /var/result/{task_id}` as well as the stream. Tests in
  `tests/test_result_backend.py`.

- **A closed `WS /api/v1/var/stream/{task_id}` client was noticed only when the safety timer ended** —
  found by Phase 0g on dev, the check of the fix below. With the subscriber up, the route waits up
  to `var_stream_safety_poll_seconds` (10 s) between state reads and looked at the disconnect
  reader only after that wait: 63 of 120 sockets in three 40-socket cycles were released more than
  4 s after the client closed, up to 10.04 s, where the 2 s timer of #398 had given 1.75 s at most.
  The slot and the registration of a closed client therefore lived until its next tick. The
  reader's completion now wakes the wait (a done-callback sets the wake event) and the route
  checks it right after the wait. Regression test with a 30 s timer: it fails when the callback is
  removed, and the earlier disconnect test fails when the check is. The same run found the push
  working on dev for the first time: 29, 125 and 156 ms after the worker stored the result, no
  failure lines in 70 live checks, and a flat 10-minute idle (memory slope 0.000 points a minute,
  CPU 1.1%, 37 cache connections) - while each socket cycle still left memory about 9 MiB higher
  (63.2 to 67.6% over four cycles) and about 7 more cache connections, which the entry does not
  explain.

- **The dev cache refuses `PSUBSCRIBE`, and the shared subscriber of #400 retried once a second for
  ever** — found by Phase 0f on dev. ElastiCache Serverless (Redis 7.1) answers `PSUBSCRIBE` with
  `ResponseError: unknown command 'psubscribe'`. Every socket then polled every 2 s (push lag
  1.69-1.87 s instead of 30-170 ms), the designed fallback. But the reader reset its back-off right
  after *sending* the command, and a server that refuses answers on the next read, so the reset
  happened every time: one retry a second per process, each with a new TLS connection. 3,022
  failures in 30 minutes, idle CPU 1.5% to about 8%, memory rising 0.3 to 0.8 points a minute with
  no sockets open (84.7% of 1 GiB at the end, still climbing). #400 had expected the fallback to
  cost nothing; the loop was what had not been tested, and its unit tests modelled a send that
  fails, not a refusal that arrives later. Reproduced locally against a Redis with the command
  renamed away (same error text): 234 failure lines in 120 s, +57 MiB, 6-10% of a core.
  The subscriber now sends `SUBSCRIBE` for each waiting job's own channel on one shared
  connection per process, the command the per-socket code used on dev (push measured at 30-172 ms
  in Phase 0e). It applies changes between 50 ms reads, so a new waiter wakes an idle reader at
  once, drops a channel when its last waiter leaves, gives its connection back after 60 s unused,
  and `healthy` turns on only when the server confirms a subscription. The back-off doubles from
  1 s to 30 s and resets only on that confirmation. `close()` no longer depends on a cancel
  arriving (`asyncio.wait_for` can swallow one before Python 3.12). Against the same refusing
  Redis: 8 failure lines in 120 s, +15 MiB and flat, about 0.7% CPU. Against a working Redis,
  two workers, five cycles of 50 sockets: memory held after the sockets close +19, +24, +26, +28,
  +29 MiB (the code of #398: +76 to +209), 9-10 Redis connections (73-87), 6 of 6 pushes 53-54 ms
  after the store, a result stored without a message delivered by the safety poll after 9.2 s,
  and new sockets pushed 52-55 ms after a Redis restart (one took 1.2 s, on a worker still
  reconnecting, polling at the short interval).
  A first version applied subscriptions only on a 500 ms tick: 50 sockets arrived at their second
  state read together, each on its own thread and Redis connection, and memory was worse (+42 to
  +64 MiB, 33-50 connections). Corrected before this entry.
  Fifteen guards were removed one at a time (the back-off reset after the send, `healthy` set
  after the send, stale channels kept, a reconnect that keeps the old subscription set, no wait
  for the subscription, a wait while the connection is down, no wake of an idle reader, a message
  that wakes every waiter, a reader that never gives its connection back, ignored confirmations,
  a wrong channel name, register after the second read, the disconnect check, the slot release,
  the interval choice) and each made a named test fail. Not measured on AWS: the new subscriber
  itself; Phase 0g should show the push lag and a flat memory.

- **`WS /api/v1/var/stream/{task_id}` built a Redis client and subscription for every socket; it now
  shares one subscription per worker process** — follow-up to the entry below, from Phase 0e on
  dev (50 sockets closed, about 84 MiB not returned, 37 Redis connections left against 6) and a
  local reproduction: the real app under uvicorn with the image's flags and two workers, a
  TLS-only Redis, 50 idle sockets per cycle, memory summed over both workers. Python-side object
  counts stayed flat after every cycle (no leaked tasks, clients or TLS contexts) and
  `malloc_trim` handed back most of the retained memory, so it was freed heap that the allocator
  keeps, not a leak. What made it large was the per-socket client: every Redis connection builds
  its own TLS context (0.83 MiB, measured on OpenSSL 3.0.13). With the code of #398 the first 50
  sockets cost 1.51 MiB each and the memory held after they closed grew with every cycle (+76,
  +118, +142, +174, +209 MiB over five cycles) with 73-87 Redis connections open. Now one
  `_JobDoneBus` per process holds a single pattern subscription on `pyvar:var-job-done:*` and
  wakes the sockets that wait: 0.62 MiB per socket, +31, +36, +37, +39, +41 MiB over the same
  five cycles, about 20 Redis connections. A socket registers with the subscriber before its
  first state read, so a completion in between is not lost. The state is still re-read after
  every wake-up, because Pub/Sub keeps nothing; the timer behind it is
  `var_stream_safety_poll_seconds` (10 s) while the subscriber is up and the old 2 s
  `var_stream_poll_interval_seconds` while it is down. The subscriber reconnects with a back-off
  from 1 s to 30 s and is closed at shutdown (`main.py` lifespan).
  Run end to end locally with the real code and two workers, playing the worker's part (publish,
  then store 50 ms later): 6 of 6 frames arrived 53-55 ms after the store; a result stored with
  no message was delivered 9.4 s later by the safety poll; with Redis restarted, the socket that
  was waiting was dropped (the result read raises, as before this change) and new sockets were
  pushed 52-54 ms after the store once the subscriber had reconnected.
  The caps are now per worker process with defaults of 25 and 5, which give the 50 and 10 per
  task #398 meant: the image runs two uvicorn workers (`Dockerfile`), and Phase 0e's 11th and
  51st sockets were not refused because each worker counted separately. #398's description and
  entry said "per task", which was wrong.
  `MALLOC_ARENA_MAX=2` is set in the image, as a separate change: without it the held memory kept
  creeping across cycles in the one-worker runs (+93 MiB after 15 cycles against +62 with it); in
  the two-worker five-cycle run the difference was small (+41 against +39).
  Not measured on AWS: `PSUBSCRIBE` on the ElastiCache Serverless cache (the route used
  `SUBSCRIBE` before). Phase 0f then showed that the dev cache refuses it, and that the retry
  loop made the refusal costly; see the entry above, which replaces the pattern subscription.
  Ten tests for the subscriber (`tests/test_job_done_bus.py`) and the stream-route tests in
  `tests/test_api.py`, rewritten around it. Twelve guards were removed one at a time (register
  before the read, unregister, the interval choice, the disconnect check, the slot release, the
  quick re-check, message type, routing, `healthy`, back-off growth, the pattern, client
  cleanup) and each made a named test fail.

- **`WS /api/v1/var/stream/{task_id}` kept abandoned sockets alive for 15 minutes and had no limit on
  how many it held** — found by the fourth Phase 0 run (0d) on dev, which opened sockets on one
  0.5 vCPU / 1 GiB task until its memory stop rule fired at 135 (92.8%). An idle task sits at
  787 MiB; the 135 sockets added about 1.2 MiB each on average (0.16 MiB over the first 50, 0.7 over
  the next 50, about 3 over the last 35). After the harness closed all 135, the handlers went on
  polling Redis (about 4,000 reads a minute) and holding 232 to 253 Redis connections until each
  one's own 900 s wait ended: the API logged 135 "Client disconnected" lines, 900 to 902 s after
  each socket opened. Memory reached 98.1% and stayed there with no sockets and 1% CPU. The route
  only ever sends, and Starlette reports a closed client only on a receive or a send, so it found
  out when the final timeout frame failed. Since the fix below made sockets for unfinished jobs stay
  open, prod runs the same route on the same task size; nothing there was measured. A reader task
  now ends the handler within one poll interval of the client leaving, which releases its Redis
  connection and subscription. Sockets that wait are capped per process
  (`var_stream_max_connections`, 50) and per user (`var_stream_max_connections_per_user`, 10);
  over a cap the route closes with 1013, and a job that is already finished is still answered
  first. The caps are counted per uvicorn worker process, not per task as first written here:
  the image runs two workers, so a task holds up to twice the figures (corrected in the entry
  above). 50 is the count at which dev read 77.7% memory; it is a stopgap, not a capacity figure.
  Not fixed here: the cost per socket. Every socket builds its own Redis client, and redis-py
  creates one TLS context per connection (0.83 MiB each, measured locally on OpenSSL 3.0.13, the
  same order as the 1.2 MiB seen), but the growth on dev was not linear, so that is a suspect, not
  a finding; nor is why memory stayed at 98.1% after the handlers ended. The next step is one
  shared Pub/Sub subscriber per process instead of a client per socket, then a re-run of the dev
  measurement to 150 sockets and beyond, stepped so CloudWatch's one to two minute lag cannot
  overshoot the stop rule. Five regression tests, each fails when its guard is removed.

- **Workers never offloaded large results to S3** — found by the third Phase 0 run on dev (jobs of
  500_000 simulations came back as 10.9 MB frames). `pyvar-cdk/stacks/compute_stack.py` wrote the
  worker's `celery.env` without `S3_BUCKET`, so `config.py`'s default `pyvar-results` was used, a
  bucket that does not exist: every job above `s3_result_offload_threshold` (10_000, so pro,
  enterprise and internal tiers only) logged `S3 result offload failed` (`NoSuchBucket` on
  `PutObject`) and fell back to an inline `loss_dist`, about 22 bytes per simulation, through the
  Redis result backend, every `GET /var/result` and every WebSocket frame. The fallback is a WARNING
  and the worker alarm counts ERROR and CRITICAL only, so nothing alerted. The worker role was already
  granted `PutObject` on the right bucket (`data.result_bucket.grant_put`); only the variable was
  missing. The env file now sets `S3_BUCKET` to the same bucket the API presigns from. The dev and
  prod compute templates differ from before only in the launch template's user data; the data stack's
  existing `ResultBucket` output is referenced, the one `api_stack.py` already uses. Takes effect when
  a worker next boots (the ASG scales to zero; its rolling-update policy replaces any running one).
  `tests/test_cdk_worker_env.py` parses the CDK source (no CDK import) and fails when the worker env
  file loses the line or the API and worker stop naming the same bucket expression. Whether prod
  workers logged the same failure was not checked; the code path is identical.

- **`WS /api/v1/var/stream/{task_id}` waited a whole poll interval after a push that arrived just
  before the result was stored** — follow-up to the fix below, found by the second Phase 0 run on
  dev. `tasks/var_task.py` publishes the completion marker from inside the task body (line 354) and
  returns on the next line; Celery stores the result only after the function returns (checked in the
  installed Celery 5.6.3: `mark_as_done` runs after the task function, and the `task_success` signal
  after the store). The marker therefore always reaches the route before the result exists. The route
  re-read the state, saw the job still pending, and waited a full `var_stream_poll_interval_seconds`
  (2.036 s on the one dev job that was pending when its socket opened; polling alone would have
  averaged about 1 s). After a push that still reads as pending, the route now re-checks
  `var_stream_wake_recheck_count` times (10), `var_stream_wake_recheck_seconds` apart (0.1 s), then
  goes back to waiting. The check sits on the API side so it does not depend on how fast workers pick
  up new code (they clone `master` at boot). Two regression tests; each fails when the re-check is
  removed, left unbounded or never triggered. How often the route lost the race before this change is
  not known: one pending sample. Measure with jobs that are still running when the socket opens.

- **`WS /api/v1/var/stream/{task_id}` crashed on any job that had not finished yet** — found by the
  Phase 0 measurements for the streaming exploration (`docs/plan-streaming-quotes-in-results-out.md`),
  which opened the socket on dev (HTTP 101 through CloudFront, WAF and the ALB) and watched the server
  close it 12 ms later. The route built its Redis client from `cfg.redis_url`, whose default is
  `localhost`; in AWS only `CELERY_RESULT_BACKEND` carries the ElastiCache address, so `subscribe`
  raised `ConnectionError` and, being outside the route's "fall back to polling" handling, took the
  socket down. Only jobs already finished at connect time (the fast path) worked, so the push the
  streaming document describes (`docs/plan-streaming-realtime-pricing.md` §7) was never seen working.
  The route now uses `storage.redis_client.redis_url()` like every other Redis caller; a Redis failure
  at subscribe time, or later, makes it poll every `var_stream_poll_interval_seconds` instead of
  failing, and it no longer spins against the result backend when a Pub/Sub read fails (the wait lived
  inside `get_message`, so a failing read skipped it). It also closes the Redis client it opens.
  The worker's publisher (`tasks/var_task.py`, `_publish_job_event`) had the same class of fault: it
  passed the raw `CELERY_RESULT_BACKEND` to `redis.Redis.from_url`, and its uppercase
  `ssl_cert_reqs=CERT_NONE` is rejected by redis-py (documented in `redis_url()`), which the
  publisher's catch-all swallowed. That was inferred from the code when this was fixed; the worker
  log group (`/pyvar/dev/worker`) has since confirmed it: 54 "Failed to publish job-completion
  event" warnings in the three days before the fix and none after. It now uses `redis_url()` too.
  Four regression tests; each fails when its fix is reverted.

- **The "Sign in with Google" button disappeared after a second page load** — the home page reads
  `GET /public/config` to learn whether Google sign-in is configured and hides the button on any
  non-200. `main.py` applied the per-IP limit (`rate_limit_unauth_per_hour`, 5 an hour) to the
  whole `/public` router, so `/public/config` shared one bucket with `status.json` and
  `demo-result.json`: a page load makes four of those calls, and from the second load in an hour
  `/public/config` answered 429 ("Rate limit exceeded. Please retry later."). The limit now sits
  on the two S3-backed files only (`api/routes/public_data.py`); `/public/config` reads settings,
  not S3, and is not limited. Tests pin both directions. The limit on those two files is now 60 an
  hour per IP (about 20 page loads): at 5, the status pill, the nav version and the terminal demo
  fell back to their static defaults from the second load.
- **The plugins page, the Claude-plugins guide and the `pyvar-mcp` README still told people to run
  `pip install -e plugins/mcp`** — the plugin has launched `uvx pyvar-mcp` from PyPI since 0.2.0.
  All three now say the server needs `uv` on the PATH (a missing `uv` is what a "command not
  found" error means now), and the README no longer says a PyPI release is still to come. The
  README is also the PyPI page, so `pyvar-mcp` 0.2.1 (next entry) carries the corrected text.
- **`pyvar-mcp` 0.2.1: the server now tells MCP clients which version it is** — the `initialize`
  reply carried an empty `serverInfo.version`. The version is read once from the package
  metadata (`pyvar_mcp.__version__`) and used for both that reply and the `X-Pyvar-Client`
  label, so they cannot differ; tests pin both. Ships as `pyvar-mcp` 0.2.1 (tag `pyvar-mcp-v0.2.1`;
  the plugin manifest moves to 0.2.1 too), which also republishes the PyPI page with the corrected
  install text. The plugin runs `uvx pyvar-mcp` without a version, so new installs get 0.2.1; a
  machine that already has 0.2.0 cached moves when uv refreshes its cache (`uvx --refresh
  pyvar-mcp` forces it).
- **`pyvar-client`: the 401 message named a token, and the `pyvar` command was counted as
  `pyvar-client`** — `PyvarAuthError` now reads "the API key is missing, invalid, revoked or
  expired" and says where to create a new one. `Client` takes an optional `client_name` for the
  `X-Pyvar-Client` label (validated as a short lowercase token), and the `pyvar` command passes
  `pyvar-cli`, the name the API's allowlist already had and nothing sent. Ships in `pyvar-client`
  0.3.0 (a new optional argument, so a minor version).
- **"Sign in with Google" rendered in the visitor's language ("Accedi con Google")** —
  #381 added `?hl=en` to the Google Identity Services script URL, but that parameter
  does not reach the button iframe (measured in headless Chromium with an it-IT locale:
  the iframe URL carried no `hl`, so the button followed the browser/Google-account
  language). The button's own `locale: 'en'` option in `portal/pyvar.js` does
  (the iframe URL then carries `hl=en`). `tests/test_portal_google_signin.py` fails
  on any `renderButton` call without it.
- **`pyvar-jupyter`: notebook traffic was recorded as `pyvar-client`** — the package
  wraps `pyvar_client.Client`, which stamps its own name on every request, so the
  `pyvar-jupyter` label in the API's client allowlist was never sent. The magics now
  relabel their requests (an httpx request hook, so `HTTP(S)_PROXY` still applies).
  Also: `pyvar-client>=0.2.0` as the dependency floor, and the example notebooks and the
  two portal guides show a `pyvar_...` key instead of a JWT-shaped or placeholder one.
- **API keys: a free "key" was a 60-minute JWT, and a verified account could not
  get another by email** — the credential every plugin user pasted once stopped
  working an hour later; its tier was a claim inside the token (a Stripe upgrade
  changed nothing until a new JWT was fetched); the emailed link was single use
  and `POST /auth/register` for a verified address sent nothing, so only Google
  sign-in could re-issue. New (`docs/plan-durable-api-keys.md`, migration
  `0009_api_keys`): durable, revocable API keys (`pyvar_...`, 1 year, SHA-256
  hashed, shown once, max 5 active) created from a signed-in session at
  `POST/GET/DELETE /auth/api-keys` and managed on the dashboard; the register
  form now doubles as sign-in for verified addresses (single-use 30-minute link,
  one per 5 minutes per address, identical 202 for every outcome); a key's tier
  is read from the database (Redis-cached 60 s) so upgrades apply, and a database
  outage is a 503, never a 401. Keys cannot create keys. `pyvar_client.Client()`
  reads `PYVAR_API_KEY` (client 0.2.0); `pyvar-mcp` 0.2.0 is launched with
  `uvx pyvar-mcp` and has a PyPI trusted-publishing workflow. `X-Pyvar-Client`
  is recorded (allowlisted) in the new `api_usage.client` column; no user
  identifier is stored there. Privacy and terms text updated. Existing JWTs keep
  working.

- **Claude plugins: the 8 domain skills could not actually be used** — Usage
  data for `pyvar-portfolio-analytics` (456 installs, 86 accounts ever active,
  103 skill uses, 2 of 83 new accounts back the next day) pointed at the skill
  itself. Each `SKILL.md` was a list of `pyvar.<domain>.<fn>(**params)` stubs:
  no parameter names, no API key or base URL, no example, and a `pyvar.*`
  Python namespace that does not exist (the real client is
  `pyvar_client.Client(...).<domain>.<fn>`). 26 of market-risk's 68 function
  names did not match a real endpoint, and 4 real ones were missing. The skills
  are now rendered by `scripts/sync_skills.py` from `portal/functions.json` and
  the live OpenAPI schema: a setup section (key, REST/client/MCP call shapes,
  errors, the 10-calls/day free quota), two worked examples per domain that
  `tests/test_skill_examples.py` re-runs against the real app, one-line
  signatures with defaults, and `references/functions.md` with every
  parameter's type and bounds. Hand-written domain caveats (regulatory
  constants, known limitations, citations) are carried over verbatim in
  `scripts/skill_specs/<skill>.tail.md`. `tests/test_skills_sync.py` fails when
  a skill drifts from the catalog. Plugin versions: 1.1.0 (regulatory 1.2.0).

- **Claude plugins: the 5 `arch-*` skills no longer present themselves as
  general-purpose** — their descriptions matched generic FastAPI/Redis/Numba
  questions, so Claude suggested them to people who were not working on pyvar.
  They are contributor guides; the descriptions and a "Who this is for" note now
  say so. Expect fewer installs of these five, not a regression.

- **Portal "Try it" panel: percentage-parameter labels** — 120 parameters
  across 107 functions that are entered as a decimal fraction representing
  a percentage (`confidence_level=0.99`, `recovery_rate=0.4`,
  `buffer_ratio=0.025`, ...) had no unit indicator on their form label at
  all. Verified against each parameter's own engine docstring (never
  guessed from the name alone — `beta`/`rho` are reused for a genuinely
  non-percentage quantity in one function each, and were excluded there).
  Labels now show a `(decimal, %)` hint; the input itself is unchanged —
  still takes `0.99`, never `99` — so no existing integration or saved
  request breaks. New `scripts/data/percentage_params.json` (hand-reviewed,
  same convention as `function_formulas.json`) feeds
  `scripts/generate_function_catalog.py`'s `is_percentage` field into
  `portal/functions.json`; `portal/pyvar.js` renders the hint.
- **Stale "382 functions" figure in the live plugin marketplace listing** —
  `.claude-plugin/marketplace.json`'s top-level bundle description (what
  `/plugin marketplace add fibtecltd/pyvar` shows) still said 382, the
  exact number `docs/p9-function-catalogue-reconciliation.md` already
  flagged as not-current back in August. Corrected to 385, matching every
  other external-facing count (portal, submission content doc). Deliberately
  left `pyvar-market-risk`'s own "68 functions" figure alone — verified
  it's a considered, already-documented count (67 mapped real routes + 1
  non-route pipeline entry, 4 legacy duplicate routes intentionally
  uncovered), not an error; see that doc's new follow-up section for the
  full per-function mapping that resolves its own previously-open question.

## [0.2.0] — 2026-09-07

### Added

- **`pyvar-client` CLI** — `pip install pyvar-client` now also installs a
  `pyvar` command (stdlib `argparse` only, no new dependency). Generic
  JSON-params dispatch (`pyvar <domain> <function> --params file.json`) over
  the existing generated SDK namespaces, so it covers all 385 methods with
  no separate codegen step; `var` gets its own `submit`/`poll`/`compute`
  sub-subcommands mirroring `client.var`. See `pyvar-client/README.md`'s
  `## CLI` section. Published as `pyvar-client` v0.1.1.
- **Chatbot approve-button groundwork** — `pyvar-pipeline-approval-raw` (a
  new, narrowly-scoped SNS topic + `NotificationRule` carrying only
  `codepipeline-pipeline-manual-approval-needed`) and
  `pyvar-{env}-approval-action-relay` (a new Lambda reformatting that native
  event into a Chatbot `custom`-schema notification, republished onto the
  existing `pyvar-pipeline-notifications` topic). Groundwork for an actual
  Approve/Reject button in Slack via AWS Chatbot Custom Actions — attaching
  the button itself is a console-side step, not yet done. See
  `docs/p9-pipeline-approval-gate-status.md`'s 2026-08-24 update.
- **Daily JWT-issuance email report** (#328) — `users.verified_at` (0006
  migration) makes token issuance countable per-day; a
  `GET /internal/token-report` endpoint exposes today's and cumulative
  counts; a per-environment scheduled Lambda + SES email
  (`pyvar-cdk/stacks/token_report_stack.py`, 07:00 UTC) reports them to
  `info@pyvar.com`. Dev and prod each send their own report rather than one
  combined email, since the two environments are fully isolated (separate
  VPCs/SES identities).

### Fixed

- **`TokenReportStack` (#328) was never actually deployed by the pipeline** —
  it was added to `pyvar-cdk/app.py`'s standalone stack list but not to
  `PyvarDeployStage` (the pipeline's real deploy graph), so the pipeline
  never learned the stack existed and silently never created it in either
  environment. Added there too, `stack_name=` pinned to match the standalone
  stack exactly so this updates the existing stack in place.
- **Migrations introduced in the same commit as the code needing them were
  silently never applied** — the migration step ran
  `ecs run-task --task-definition <family-name>`, which resolves to
  whatever task-definition revision was already ACTIVE (the *previous*
  deploy's image), because this step runs *before* the same stage's
  `ApiStack` deploy registers a new revision pointing at the image this
  pipeline run just built. `0006_user_verified_at` (#328) hit exactly this:
  the pipeline reported a clean success while the column was never created
  in dev or prod. Fixed by cloning the family's current task-def with only
  the image swapped to this run's freshly-built one, registering that as a
  one-off revision, and running that specific revision ARN instead of the
  bare family name.
- **`TokenReportStack`'s Lambda couldn't actually send email** — confirmed
  live in dev: `ses:SendEmail` 403'd against the configuration-set resource
  despite `ses_identity.grant_send_email()` already being in place. AWS
  additionally authorizes `SendEmail` against the configuration-set itself
  whenever the identity has one attached as its default — the same gap
  `api_stack.py`'s own ECS task role grant had already hit and documented.
  Added the matching second grant here.

- **`crr2_large_exposure_limit`** — `is_institution` was accepted (its own
  docstring said it "affects the absolute alternative limit") but never
  actually applied: the function only ever ran the 25%-of-Tier-1 ratio
  test. CRR2 Art. 395(1) requires, for an institution counterparty (or a
  connected-client group including one), the limit to be the HIGHER of
  25% of Tier 1 capital or EUR 150m — now implemented. Default
  (`is_institution=False`) is unchanged. Verified against Art. 395(1) via
  two independent secondary sources after this environment's network
  egress proxy blocked direct fetches of every primary EU-legislation
  host tried.
- **`asset_swap_spread`** — `bond_price` was accepted but never used; the
  spread was always computed against `face_value` (par), silently wrong for
  any bond not trading at par relative to the standard market convention
  (O'Kane, 2000, "Introduction to Asset Swaps"). Added an opt-in
  `use_market_price: bool = False` parameter — default behaviour
  (par-referenced) is unchanged for every existing caller; passing
  `use_market_price=True` uses the bond's actual dirty price instead.
- **`bond_pricer_floating_rate`** — `maturity` was validated only as `> 0`
  and never reconciled against the actual number of coupon periods priced
  (`len(reference_rates) / frequency`), so an internally inconsistent call
  (e.g. 8 quarterly reference rates with `maturity=3.0`) silently priced the
  wrong schedule instead of failing. Now raises `ValueError` on mismatch;
  every previously-consistent call is unaffected.
- **`combined_stress_scenario`** — could not express BCBS 238's regulator-set
  retail deposit stability categories (stable/less-stable buckets, each with
  its own rate); only a single blended scalar retail run-off rate was
  possible. Added opt-in `retail_deposits_by_category`/`retail_runoff_rates`
  arrays (supplied together, validated to sum to `retail_deposits`) computing
  a BCBS-238-shaped categorised outflow instead. Default behaviour
  (arguments omitted) is unchanged.
- **`transaction_cost_analysis`** — even with `decision_price` supplied, the
  result was a delay+execution partial implementation shortfall, missing
  Perold's (1988) unexecuted-share opportunity-cost leg entirely (no
  cancellation price/quantity was modelled). Added opt-in
  `unexecuted_quantity`/`cancellation_price` parameters (supplied together,
  requiring a scalar `decision_price`) adding `opportunity_cost[_bps]` and
  `total_implementation_shortfall[_bps]` covering the full original order
  (executed and unexecuted). Default behaviour is unchanged.
- **`compute_rolling_var`'s caveat catalogue entry** — claimed the docstring
  called this an "expanding window" while the code used a trailing window;
  the docstring was already corrected in PR #301 and has said "fixed-length
  trailing window" ever since. The catalogue entry was never updated to
  match, so it described a mismatch that no longer exists. Corrected to
  reflect current reality — no code change, since none was needed.
- **`creditmetrics_portfolio_model`** — was a pure pass-through to
  `credit_var_monte_carlo`, not a distinct multi-state CreditMetrics model.
  Added `transition_matrix`/`current_rating`/`state_loss_pct` as an opt-in
  group implementing Gupton, Finger & Bhatia (1997)'s actual asset-return
  discretisation: each obligor's simulated asset return migrates through its
  own transition-matrix row to a rating state, not just default/survive.
  Verified two ways: an economic sanity check, and a bit-for-bit cross-check
  where a single-rating-per-obligor transition matrix reduces the new
  multi-state kernel to byte-identical output against the old two-state
  path given the same seed. Default (all three omitted) is the unchanged
  pass-through.
- **`downturn_lgd_adjustment`** — multiplicative scaling was the only
  implementation, even though the docstring already documented the
  EBA/GL/2019/03 additive fallback formula (the CRR Art. 181 alternative)
  without ever wiring it in. Added `method="additive"` using that exact
  documented formula. Default (`method` omitted) is unchanged.
- **`business_continuity_risk_score`** — `rpo_hours` was accepted and
  range-validated but had zero effect on the score: RPO risk had nothing to
  be measured against without a target. Added `rpo_target_hours` (the
  maximum tolerable data-loss window, ISO 22301 / DRI International BCM
  practice); when supplied, the pre-BCP-maturity risk becomes the worse of
  the RTO and RPO breach severities. Default is unchanged.
- **Redis clients hardened against ElastiCache Serverless idle-connection
  resets** (#322) — the result-cache and rate-limit-storage clients are
  long-lived singletons whose pooled connections sit idle between requests;
  ElastiCache Serverless's proxy layer silently drops idle connections,
  producing a bare `ConnectionResetError` on the next write (Sentry issue
  a5ebcb89, dev). Added `health_check_interval` to ping stale connections
  before reuse and a short-capped retry on `ConnectionError`/`TimeoutError`,
  without violating either client's fail-open "never slow a request" design.
- **Celery result-backend socket timeouts, and reads moved off the event
  loop** (#323) — `get_var_result` read `AsyncResult` state/result/kwargs
  synchronously inside an async handler, with no socket timeout configured
  on the Celery Redis result backend. A stalled write to a connection
  ElastiCache Serverless had silently dropped (same root cause as #322,
  Sentry issue cdb4c0e5, dev) blocked the *entire worker event loop* until
  the kernel's own TCP retransmission timeout gave up — freezing every
  other in-flight request on that process, not just the one polling. Added
  the same socket-timeout tuning as #322 to the Celery result backend, and
  moved the blocking reads into a threadpool via Starlette's
  `run_in_threadpool` so a stall is now bounded to the requesting thread.
- **Sentry no longer paged for the handled cache fail-open path** (#327) —
  the ElastiCache idle-connection reset (same root cause as #322/#323,
  Sentry issue 5d53be95, prod) was already caught and swallowed
  (fail-open, request still succeeds), but `logger.exception()` still
  promoted it to a Sentry ERROR event whenever the #322 retry budget lost
  the race against the proxy's own reconnect time. Downgraded to
  `logger.warning()` for this known/handled condition, and added
  `CacheReadError`/`CacheWriteError` CloudWatch metrics so frequency stays
  trackable without alert noise. No retry/functional behaviour changed.
- **`pyvar-client-publish.yml`** — declaring `permissions: { id-token: write }`
  zeroed every other default `GITHUB_TOKEN` scope, so `actions/checkout`
  couldn't read this private repo (`Repository not found`) on the first real
  `pyvar-client-v0.1.0` tag push. Added `contents: read`.
- **`pyvar-client` README** — the License section linked `[LICENSE](LICENSE)`,
  a relative path that resolves fine on GitHub but renders as a dead link on
  PyPI's project page (PyPI doesn't rewrite relative markdown links against
  the repo). Points at the GitHub blob instead. Published as `pyvar-client`
  v0.1.2.

### Security

- **Registration abuse gaps** — `POST /auth/register` had no disposable-email
  domain check and no rate limiting at all, unlike every other endpoint (which
  goes through slowapi via `enforce_compute_rate_limit`/
  `enforce_public_rate_limit`). Added a vendored, config-extensible
  disposable-email blocklist checked before any DB write or SES send, and a
  dedicated `enforce_register_rate_limit` (IP-keyed, its own
  `rate_limit_register_per_hour` config knob). Both follow the existing
  never-reveal-why-it-failed pattern: same generic 202 response either way.

## [0.1.0] — 2026-08-22

Initial public release. 385 risk functions across 8 domains, exposed as a
REST API and served through an async Celery/SQS job pipeline on AWS. See
`portal/functions.json` for the live, canonical function list and
`docs/pyvar_release_plan.md` for the full P1–P9 build history.

### Added

- 385 risk functions across 8 domains: Market Risk, Derivatives & Pricing,
  Credit Risk, Portfolio Analytics, Operational Risk, Liquidity Risk,
  ALM & Balance Sheet, and Regulatory & Compliance.
- Numba JIT-accelerated Monte Carlo VaR/ES engine, with antithetic-variate
  sampling and randomized-QMC (Sobol) pricing for low-dimensional
  derivatives kernels, and a Heston-companion control variate for the
  rBergomi Monte Carlo pricer.
- Bump-and-reprice Greeks (delta/gamma/vega/theta/rho), opt-in via
  `greeks=True`, for exotic option pricers and stochastic-volatility
  Monte Carlo pricers.
- Celery/SQS async job pipeline on AWS (ECS Fargate + EC2 Spot), with a
  `var_jobs` audit log recording every submission and completion.
- Minimum-viable account flow: email → verification → JWT, with tier-aware
  rate limiting (slowapi) and S3 result offload for large payloads.
- AWS CDK infrastructure: VPC + endpoints, Aurora Serverless v2, SQS FIFO
  + DLQ, ECS Fargate/Fargate Spot API, CloudFront + WAF, and a
  self-mutating CodePipeline for CI/CD.
- Cost-allocation tagging (`CostComponent=spot-worker-compute`) isolating
  Spot worker compute cost in AWS Cost Explorer from other EC2 line items.
- Reproducible benchmark harness (`scripts/p7_bench.py`) for the hottest
  Monte Carlo kernels, with fixed seeds/inputs — see
  `docs/p7-numba-profiling-results.md`.
- `tests/validation/` — cross-validation suite against QuantLib and
  published worked examples, with documented scope and limitations.
- `pyvar-client` — a typed Python SDK covering all 385 endpoints across the
  8 domains, with retry/backoff, typed exceptions, and a blocking
  `client.var.compute(...)` convenience wrapper over the one async job
  flow. Source-available in this repo at launch, and published to PyPI on
  2026-08-24 (https://pypi.org/project/pyvar-client/) — see
  `docs/pyvar_release_plan.md` for the PyPI Trusted Publisher bootstrap
  history.

### Fixed

Pre-launch regulatory corrections, found and fixed before any external
release:

- **Solvency II SCR credit-risk formula (Art. 200–201)** — corrected an
  error that understated required capital by roughly 79%.
- **rBergomi kernel** — added the missing fractional-Brownian
  autocovariance structure the model requires.
- **EMIR clearing obligation scope** — financial counterparties are now
  correctly in scope for all asset classes, not evaluated per-class.
- **IRRBB standard shocks** — recalibrated to the BCBS d578 (2024) values.

Pre-launch infrastructure corrections, found during a post-domain-cutover
audit — every deployed environment (dev and prod alike) had been calling
or linking to a hardcoded dev-only domain regardless of which environment
was actually running:

- **Lambda-to-API calls** — the scheduled demo-publisher and SES-
  suppression Lambdas called dev's API from every environment, causing
  prod's calls to fail outright on a guaranteed JWT signature mismatch
  (dev and prod sign with separate secrets).
- **Verification email links** — pointed at a stale, pre-cutover dev
  CloudFront domain in every environment instead of the environment's own
  real domain.
- **Portal client** — `portal/pyvar.js` hardcoded the same dev domain for
  every API call; replaced with a relative path, so the browser client
  always talks to whichever environment actually served the page and
  can't drift out of sync with it again.
- **Sentry trace sampling and structured-log rendering** — both compared
  the deployment environment against long-form values ("production"/
  "development") that never match what's actually injected (the short
  forms "prod"/"dev"), so prod silently over-sampled traces at 100%
  instead of the intended 10%, and the JSON-vs-console log renderer
  choice for deployed environments only worked by coincidence.

### Security

- **CORS allowlist reflected arbitrary Origins with credentials enabled**
  — the allowed-origins list picked between a wildcard and a single
  hardcoded domain based on a debug flag that was never actually `False`
  in any real deployment, so every environment reflected any request's
  Origin header back with `access-control-allow-credentials: true`.
  Replaced with an explicit per-environment allowlist, and dropped
  `allow_credentials` entirely — this API authenticates via Bearer JWT
  only, never cookies, so it protected nothing.

### Changed

- Removed misleading or false regulatory citations across engine
  docstrings and `CLAUDE.md`; documented genuine no-published-source
  limitations directly in the affected module docstrings rather than
  citing sources that don't actually support the implementation.
- Restructured circular/tautological validation tests that were asserting
  against themselves rather than an independent reference.
