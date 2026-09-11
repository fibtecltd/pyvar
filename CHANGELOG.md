# Changelog

All notable changes to pyvar are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

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
