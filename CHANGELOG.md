# Changelog

All notable changes to pyvar are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing yet.

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
  flow. Source-available in this repo at launch; not yet published to
  PyPI (Trusted Publisher project bootstrap and the SDK's own
  `pyvar-client-v0.1.0` tag are still pending — see
  `docs/pyvar_release_plan.md`).

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
