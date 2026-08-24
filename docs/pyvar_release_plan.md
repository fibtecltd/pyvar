# pyvar.com — Full Release Plan
## Using Claude Code as Primary Development Accelerator

**Version:** 1.0
**Date:** April 2026
**Target:** Public launch Q4 2026
**Prepared by:** Fibtec Limited

---

## Executive Summary

This document defines the complete release plan for pyvar.com — an open-source financial and risk computation platform exposing 382 regulatory-grade functions across 8 domains as a REST API. Claude Code is the primary development accelerator throughout, with each phase containing specific session prompts designed to produce production-ready output on first pass.

The plan spans 9 phases over approximately 28 weeks. The single most important investment is Phase 1: a complete CLAUDE.md. Every subsequent Claude Code session reads it first, and its quality directly determines the quality of the generated code.

**Total scope:** 382 Python functions · 8 REST API domains · AWS CDK deployment · Open-source GitHub launch

---

## Phase overview

| Phase | Name | Weeks | Gate |
|---|---|---|---|
| P1 | CLAUDE.md & project scaffolding | Wk 1–2 | CI green · CLAUDE.md locked |
| P2 | Engine implementation — all 382 functions | Wk 2–10 | 80% coverage · no Numba violations |
| P3 | API endpoints — all domains | Wk 8–13 | All endpoints 202 · OpenAPI complete |
| P4 | AWS deployment — CDK all stacks | Wk 11–15 | Dev smoke test passing · AMI baked |
| P5 | Testing & validation | Wk 14–18 | Numerical accuracy · load test p95 < 15s |
| P6 | Usage statistics & observability | Wk 16–19 | Grafana live · alarms configured |
| P7 | Cost & performance optimisation | Wk 18–22 | Monthly cost < £150 at 500 jobs/day |
| P8 | Portal finalisation | Wk 20–24 | pyvar.com live · search working |
| P9 | Public launch & GitHub | Wk 24–28 | 48h healthy prod · repo public |

---

## P1 — CLAUDE.md & Project Scaffolding
**Weeks 1–2**

### Goal
Before any Claude Code session touches pyvar, the CLAUDE.md must be complete and locked. This is the highest-leverage investment in the entire project — every subsequent session reads it first. A thorough CLAUDE.md prevents regulatory threshold errors, Numba compilation failures, and SQS misconfiguration that would otherwise cost hours to debug.

### Tasks
- Finalise CLAUDE.md with all Numba JIT rules, regulatory constraints, SQS/broker notes, and session patterns (already drafted — review and lock)
- Set up GitHub repo: branch protection on main, required PR reviews for reg/* branches
- Configure pre-commit hooks: black, isort, ruff, bandit (--ll flag), mypy --strict on engine/ only
- Wire GitHub Actions CI: lint → security → tests (80% coverage gate) → CDK synth
- Add pytest-benchmark to requirements and baseline the empty engine functions
- Generate the pyvar Python SDK stub (thin REST wrapper) as the client-facing interface
- Set up Codecov and Sentry project — both free tiers sufficient at this stage

### Claude Code session prompts

**Session 1 — CLAUDE.md review:**
```
Read CLAUDE.md in full. Then audit every file in engine/, schemas/, tasks/, and api/
and tell me: (1) any existing code that violates the Numba JIT rules in section 3.1,
(2) any missing type hints on public functions, (3) any bare except clauses.
List findings by file.
```

**Session 2 — CI pipeline:**
```
Read CLAUDE.md section 8 (git workflow). Then read .github/workflows/ci.yml.
Extend the CI workflow to: add a mypy --strict check on engine/ only, add a
pytest-benchmark baseline run that posts results as a PR comment, and add a
cdk synth check that validates both dev and prod contexts.
```

### Exit gate
CI green on an empty push. CLAUDE.md reviewed by a second person. All hooks passing locally.

---

## P2 — Engine Implementation — All 382 Functions
**Weeks 2–10**

### Goal
The most substantial phase. Implement all 382 functions across 8 domains. Claude Code accelerates this dramatically — each domain is a self-contained session with the function list from pyvar_functions.csv as the prompt context. Numerical correctness tests are written alongside each function, not after.

### Domain allocation

| Domain | Functions | Key regulatory frameworks |
|---|---|---|
| Market Risk | 68 | FRTB SA/IMA · Basel III VaR |
| Credit Risk | 55 | IRB Foundation/Advanced · IFRS 9 · SA-CCR |
| Liquidity Risk | 40 | LCR/NSFR · ILAAP |
| Operational Risk | 44 | LDA · AMA · Basel SMA |
| Portfolio Analytics | 50 | UCITS · AIFMD |
| Regulatory & Compliance | 30 | Basel IV · FRTB · MiFID II · EMIR |
| Derivatives & Pricing | 62 | FRTB SBM · EMIR SIMM · IFRS 13 |
| ALM & Balance Sheet | 33 | IRRBB · EBA GL 2018 |

### Tasks
- Implement Market Risk domain (68 functions): start with montecarlo.py — already scaffolded. Add Historical ES, Greeks suite, FRTB SA/IMA, stress testing, backtesting
- Implement Credit Risk domain (55 functions): PD/LGD/EAD, IRB Foundation/Advanced, SA-CCR, CVA/DVA/XVA, IFRS 9 ECL
- Implement Liquidity Risk domain (40 functions): LCR/NSFR from first principles, intraday, survival horizon, ILAAP stress
- Implement Operational Risk domain (44 functions): LDA distribution fitting, RCSA scoring, KRI detection, Monte Carlo OpRisk VaR
- Implement Portfolio Analytics domain (50 functions): Markowitz, Black-Litterman, factor models, drawdown analytics
- Implement Regulatory domain (30 functions): Basel IV capital stack, FRTB PAT, MiFID II validators, EMIR checks
- Implement Derivatives domain (62 functions): Black-Scholes through Heston, full fixed income suite via QuantLib wrapper
- Implement ALM domain (33 functions): IRRBB six shocks, NII simulation, behavioural modelling, FTP curve
- Write numerical correctness tests alongside each function (not after) — engine tests must never mock the Numba kernel
- Achieve 80% engine test coverage before moving to P3

### Claude Code session prompts

**Domain session pattern — use for each of 8 domains:**
```
Read CLAUDE.md in full, paying particular attention to sections 3.1 (Numba rules),
4 (regulatory constraints), and 5 (testing rules).

I am going to give you the function list for the [DOMAIN] domain. For each function:
1. Implement it in engine/[module].py following the Numba JIT rules exactly
2. Write a corresponding test in tests/test_[module].py that verifies numerical
   correctness (not just types)
3. Add a Pydantic v2 schema in schemas/[domain].py

Functions to implement:
[paste relevant rows from pyvar_functions.csv]

Start with the simplest function and work up to the most complex. Flag any function
where the regulatory threshold is ambiguous before implementing it.
```

**Numba correctness audit — run after each domain session:**
```
Read CLAUDE.md section 3.1 (Numba JIT rules). Then audit all @njit functions
added in the last session:
1. Do any accept Python objects, dicts, or Pydantic models? (Rule 1)
2. Do any use dynamic dispatch or non-float64 arrays? (Rule 2)
3. Are random numbers drawn inside the JIT region? (Rule 3)
4. Do all parallel kernels use @njit(parallel=True, cache=True) with prange? (Rules 4/5)
Show me the exact line for any violation found.
```

**Regulatory threshold check:**
```
For all functions marked [REGULATORY] in engine/ and schemas/, verify that:
(1) VaR confidence levels are validated in [0.90, 0.9999],
(2) Basel backtesting uses exactly 250 days,
(3) FRTB PAT thresholds match section 4.4 of CLAUDE.md exactly.
Quote the relevant line of code for each check.
```

### Exit gate
All 382 functions implemented. Engine test coverage ≥80%. No Numba rule violations. All regulatory thresholds verified against CLAUDE.md section 4.

---

## P3 — API Endpoints — All Domains
**Weeks 8–13**

### Goal
One Celery task and one FastAPI route pair per domain (compute + result endpoints). The engine is the source of truth — the API layer must never contain business logic. JWT tier enforcement, orjson serialisation, and Alembic migrations for all new audit columns.

### Tasks
- Create tasks/[domain]_task.py for each domain — same pattern as var_task.py
- Create api/routes/[domain].py for each domain — POST compute + GET result endpoints
- Add Pydantic v2 request/response schemas for every function (partially done in P2)
- Run Alembic revision for any new audit columns added for non-VaR domains
- Wire all new routers into main.py (one include_router per domain)
- Add tier enforcement to all compute endpoints (free/pro/enterprise caps differ by domain)
- API integration tests for every domain: 202 on submit, 401 no auth, 422 bad params, 403 tier cap
- OpenAPI spec auto-generated — validate it renders cleanly at /docs
- Add slowapi rate limiting per domain (compute endpoints are more expensive than result polls)

### Claude Code session prompts

**Domain API session pattern:**
```
Read CLAUDE.md sections 3.2 (Celery/SQS rules) and section 10 (Adding a new domain).

For the [DOMAIN] domain, create:
1. tasks/[domain]_task.py — Celery task wrapping the engine functions. Must use
   bind=True, task_acks_late=True, worker_prefetch_multiplier=1
2. api/routes/[domain].py — POST /[domain]/compute and GET /[domain]/result/{task_id}
   with JWT auth and tier enforcement
3. Add the router to main.py

Follow the exact same pattern as tasks/var_task.py and api/routes/var.py.
Do not add any business logic to the API layer — call the engine function only.
```

**API test coverage session:**
```
Read CLAUDE.md section 5 (testing rules). For all domain routes added this session,
write integration tests using httpx.AsyncClient with app=create_app().

Every domain must test: (1) 202 on valid submit with mocked Celery, (2) 401 without JWT,
(3) 422 on invalid params, (4) 403 when n_simulations exceeds tier cap,
(5) 200 with SUCCESS and FAILURE states from mocked AsyncResult.
Do not test the engine functions here — mock apply_async and AsyncResult.
```

### Exit gate
All domain endpoints return 202 on valid submit. OpenAPI spec complete at /docs. API test coverage ≥80%. Alembic migrations clean.

---

## P4 — AWS Deployment — CDK All Stacks
**Weeks 11–15**

### Goal
Deploy to AWS dev environment. The CDK stacks are already written — this phase is about bootstrapping, first deployment, smoke testing, and wiring the AMI baking pipeline so Numba cold start is solved before prod.

### Stack deployment sequence
```
cdk bootstrap aws://ACCOUNT/eu-west-2
cdk bootstrap aws://ACCOUNT/us-east-1     # CloudFront WAF requires us-east-1

cdk deploy pyvar-dev-network
cdk deploy pyvar-dev-data
cdk deploy pyvar-dev-queue
cdk deploy pyvar-dev-compute
cdk deploy pyvar-dev-api
cdk deploy pyvar-dev-edge

# Then deploy CI/CD pipeline (manages itself from here)
cdk deploy pyvar-pipeline
```

### Tasks
- Bootstrap CDK in eu-west-2 and us-east-1
- Deploy dev environment in dependency order (network → data → queue → compute → api → edge)
- Run Alembic migrations against Aurora dev: `python scripts/db.py upgrade`
- Trigger AMI baking pipeline — verify Numba cache is pre-compiled in the AMI
- Smoke test all 8 domain endpoints: curl /health → 200, POST /api/v1/[domain]/compute → 202
- Verify SQS FIFO → Celery worker → S3 Parquet write path end-to-end
- Deploy pipeline stack — verify self-mutation on first push to main
- Set all secrets in Secrets Manager (JWT_SECRET, DB credentials, GitHub token)
- Configure CloudWatch dashboards: API latency, SQS queue depth, worker CPU, error rates

### Claude Code session prompts

**CDK diff review before deploy:**
```
Read CLAUDE.md sections 3.4 (AWS/CDK rules). Run cdk diff --context env=dev for all stacks.
Then tell me: (1) any changes that would cause downtime on an existing deployment,
(2) any security group rules that are too permissive (e.g. 0.0.0.0/0 on non-public ports),
(3) any missing VPC endpoint for the services used (SQS, ECR, Secrets Manager, S3 must
all have endpoints), (4) whether IMDSv2 is enforced on all EC2 instances.
```

**Post-deploy smoke test script:**
```
Write a bash smoke test script scripts/smoke_test.sh that:
(1) curls /health and asserts 200,
(2) obtains a test JWT token using the create_access_token utility,
(3) POSTs to /api/v1/var/compute with a synthetic returns payload,
(4) polls /api/v1/var/result/{task_id} every 2 seconds until status=success or timeout 120s,
(5) asserts var_abs > 0 and cvar_abs > var_abs.
Exit code 0 on pass, 1 on any failure. Use curl and jq only — no Python.
```

### Exit gate
All 6 application stacks deployed to dev. Smoke test passes. AMI with pre-compiled Numba cache in use (worker cold start < 30s). Pipeline self-mutates on push.

---

## P5 — Testing & Validation
**Weeks 14–18**

### Goal
Systematic validation of numerical correctness against reference implementations and regulatory compliance verification. Load testing to establish performance baselines before optimisation.

### Tasks
- Cross-validate VaR against QuantLib reference for same parameters — tolerance ≤0.1%
- Cross-validate Black-Scholes against analytical formula — tolerance ≤0.001%
- Cross-validate IRB capital against BIS published worked examples (BCBS d347)
- Cross-validate IFRS 9 ECL against published IASB illustrative examples
- Backtest VaR against 250-day Basel window — verify breach counts and traffic light zones
- Run FRTB PAT test with synthetic data — verify IMA eligibility thresholds
- Load test: 100 concurrent VaR requests at 100k paths — measure p50/p95/p99 latency
- Load test: scale-to-zero → first job cold start (target < 45s including AMI boot)
- Chaos test: terminate Spot worker mid-simulation — verify SQS re-queues and result eventually delivered
- Security scan: run bandit -r on full codebase, OWASP ZAP on the API
- Data residency verification: confirm no data leaves eu-west-2 in transit

### Claude Code session prompts

**Numerical validation suite:**
```
Read CLAUDE.md section 4 (regulatory constraints) in full. Write a validation module
tests/validation/test_reference_values.py that cross-validates pyvar outputs against
known reference values:

1. Monte Carlo VaR at 99%, 1d, N=1,000,000, seed=42: compare to
   scipy.stats.norm.ppf(0.99) × sigma (within 0.5% tolerance)
2. Black-Scholes call: S=100, K=100, T=1, r=0.05, sigma=0.2 → exact value 10.4506
   (within 0.001%)
3. IRB Foundation capital: PD=0.01, LGD=0.45, M=2.5 → verify against BIS BCBS d347 example
4. IFRS 9 12-month ECL: PD=0.02, LGD=0.40, EAD=1,000,000 → £8,000 exactly

Each test must print the reference value, the pyvar value, and the % deviation.
```

**Load test with Locust:**
```
Write a Locust load test file locustfile.py that simulates pyvar.com usage:
- 70% of virtual users: POST /var/compute (100k paths) → poll until success →
  record end-to-end latency
- 20%: GET /api/v1/domains (catalogue browsing)
- 10%: GET /api/v1/var/result/{old_task_id} (result retrieval from cache)

Target: 100 concurrent users, 10 minute ramp-up. Assert p95 end-to-end latency
< 15s for the compute flow. Use a test JWT token injected via environment variable.
```

### Exit gate
All numerical validations pass within tolerance. No regulatory threshold violations. Load test p95 < 15s at 100 concurrent users. Bandit shows 0 HIGH findings.

---

## P6 — Usage Statistics & Observability
**Weeks 16–19**

### Goal
Instrument everything before public launch so data flows from day one. Usage statistics inform pricing validation, cost modelling, and future roadmap prioritisation. Grafana dashboards must be ready before launch — not retrofitted.

### Key metrics to capture from day one
- Daily active users by tier (free/pro/enterprise)
- Functions called per domain (domain popularity ranking)
- Computation duration histogram by domain and function
- Cache hit rate per domain (ElastiCache efficiency)
- SQS queue depth over time (demand pattern analysis)
- Cost per simulation (tracks unit economics over time)
- Error rate by domain (identifies unstable functions)

### Tasks
- Publish custom CloudWatch metrics: computation duration per domain, n_simulations histogram, per-user tier distribution
- Wire Prometheus custom metrics (already coded in observability/setup.py) to Grafana Cloud
- Build Grafana dashboard: request rate, error rate, queue depth, worker count, p50/p95/p99
- Build usage dashboard: daily active users, functions per domain, tier distribution, ARR proxy
- Add request logging to VaRJob audit table: domain, function_name, duration_ms, tier
- Set up CloudWatch Alarms: error rate > 1% (page), queue age > 5min (page), DLQ depth > 0 (page)
- Weekly cost report: Lambda → S3 → email. Break down by service
- Add Sentry performance monitoring to Celery tasks — track slow simulations (> 30s)

### Claude Code session prompts

**Grafana dashboard as code:**
```
Write a Grafana dashboard JSON definition (to be imported into Grafana Cloud) that shows:
1. Row 1 — API health: request rate, error rate by status code, p50/p95/p99 latency
2. Row 2 — Compute: active workers, SQS queue depth, computation duration histogram by domain
3. Row 3 — Usage: unique users per day, function calls by domain (pie), tier distribution
4. Row 4 — Cost proxy: estimated daily cost (EC2 Spot hours × £0.04/hr + S3 PUTs),
   simulations per pound

Use CloudWatch as data source. Export as JSON dashboard definition.
```

**Usage analytics query library:**
```
Write a Python module analytics/queries.py with functions that query the var_jobs table:
1. daily_active_users(days=30) → DataFrame with date, user_count, tier_breakdown
2. top_functions(limit=20) → function_name, call_count, avg_duration_ms
3. domain_usage_heatmap() → domain × hour_of_day matrix (identifies market-open spikes)
4. tier_conversion_funnel() → starter→pro→enterprise conversion rates
5. cost_per_simulation() → date, avg_cost_pence

All queries must use SQLAlchemy Core. Include docstrings with business interpretation.
```

### Exit gate
Grafana dashboard live. CloudWatch alarms configured. Usage metrics flowing from day 0. Cost report generating weekly.

---

## P7 — Cost & Performance Optimisation
**Weeks 18–22**

### Goal
Optimise before launch — not after. Three levers: Numba kernel efficiency (profile and improve hot paths), API response time (cache hit rates), and AWS cost (Spot interruption rates, SQS batch sizes, S3 storage tiering).

### Cost targets

| Service | Target | Lever |
|---|---|---|
| EC2 Spot workers | ~£12/month | Scale-to-zero. c7i.xlarge Spot vs On-Demand |
| ECS Fargate (API) | ~£18/month | FARGATE_SPOT + on-demand base |
| Aurora SV2 | ~£45/month | 0.5 ACU minimum — scale only during batch writes |
| ElastiCache | ~£10/month | Serverless — pay per ECU consumed |
| Total | < £150/month | At 500 jobs/day |

### Tasks
- Profile the 10 slowest functions using pytest-benchmark — optimise any taking > 10s for 100k paths
- Add result caching in ElastiCache: cache key = SHA-256(request params). Target 40% cache hit rate
- Tune Celery worker concurrency on c7i.xlarge: benchmark at 1, 2, 4 — pick sweet spot
- Review SQS visibility timeout against actual p99 simulation time — adjust if needed
- Enable S3 Intelligent-Tiering — verify old Parquet files move to IA after 30 days
- Optimise Numba JIT warm-up: verify AMI cache covers all function signatures used in prod
- CloudFront cache hit rate for GET /result/{task_id} on SUCCESS — target > 60%
- Review AWS Cost Explorer: identify top 3 cost drivers and document mitigation

### Claude Code session prompts

**Performance profiling session:**
```
Read CLAUDE.md section 3.1 (Numba rules). Use pytest-benchmark to run the 10 most
compute-intensive functions with n_simulations=100_000. For any function taking > 5 seconds:
1. Profile with cProfile to identify the bottleneck
2. Check whether prange is used correctly (parallel, not sequential)
3. Check whether random numbers are pre-drawn before the JIT region (Rule 3)
4. Check whether all array dtypes are explicitly float64 (Rule 2)
5. Propose a specific code change with expected speedup

Show me the before/after benchmark for any change you make.
```

**Cache strategy implementation:**
```
Implement a result cache in api/routes/ as a cache_check decorator that:
1. Before dispatching to Celery: check ElastiCache for cached result using
   SHA-256 of canonical JSON request params as cache key
2. On cache hit: return 200 with the cached result immediately (not 202)
3. On cache miss: dispatch to Celery, on completion write result to cache TTL=3600
4. Cache key format: "pyvar:{domain}:{sha256_of_params}"
5. Log cache hits vs misses as CloudWatch custom metric

Test with the same params twice — second call must return instantly from cache.
```

### Exit gate
p99 latency < 10s at 100k paths for all domains. Cache hit rate > 30%. Monthly AWS cost forecast < £150 at 500 jobs/day. No Spot interruptions causing job loss in 72h soak test.

---

## P8 — Portal Finalisation
**Weeks 20–24**

### Goal
The pyvar.com portal must be complete and live before GitHub launch. All 8 domain pages must be production-ready with real function counts, working search, and live API integration. The homepage terminal animation must run against the actual API.

### Tasks
- Complete all 8 domain HTML pages — verify function counts match pyvar_functions.csv exactly
- Wire the homepage terminal demo to the real API (replace mock with live call)
- Add live status indicator: CloudWatch → Lambda → S3 → /status.json polled every 60s
- Build the API key registration flow: email → verified → JWT issued → shown in dashboard
- Add search across all 382 functions using Fuse.js — client-side, < 50ms response
- Add a 'Try it' panel on each domain page: parameter form → API call → result display
- Set up pyvar.com domain DNS: Route53 → CloudFront → ALB (separate from fibtec.co.uk)
- SSL certificate via ACM in us-east-1 — verify HTTPS and HTTP→HTTPS redirect
- SEO: meta descriptions, Open Graph tags, SoftwareApplication schema
- Accessibility audit: WCAG 2.1 AA — screen reader compatible, keyboard navigable

### Claude Code session prompts

**Live API integration in portal:**
```
The pyvar.com homepage has a terminal demo in index.html. Replace the static hardcoded
output with a live API call:
1. On page load, call GET /health — show a green status dot if OK
2. When user clicks 'Run demo': POST to /api/v1/var/compute with fixed demo params
   (portfolio_value=1000000, n_simulations=10000, confidence_level=0.99, seed=42)
3. Poll GET /result/{task_id} every 1.5s — show elapsed time in the terminal
4. On success: type out the result values character-by-character (30ms per char)
5. Handle API errors gracefully: show error message in terminal style (red text)

Use vanilla JS only — no frameworks. The demo API key is injected via a meta tag.
```

**Fuse.js search across all 382 functions:**
```
Build a client-side full-text search for pyvar.com that searches all 382 functions:
1. Fetch /api/v1/domains on page load to get the full function catalogue
2. Build a Fuse.js index with keys: ['function_name', 'domain', 'description']
   and threshold 0.3
3. Wire to the search input in the portal nav — results appear as a dropdown
   within 50ms of typing
4. Each result shows: domain colour dot, function name, domain name
5. Clicking a result navigates to the correct domain page and scrolls to +
   highlights that function card
6. Pressing Escape dismisses the dropdown

Load Fuse.js from https://cdn.jsdelivr.net/npm/fuse.js/dist/fuse.min.js
```

### Exit gate
pyvar.com live on its own domain with valid SSL. All 8 domain pages complete with correct function counts. Live API demo working. Search across 382 functions returning results in < 50ms. WCAG 2.1 AA passing.

---

## P9 — Public Launch & GitHub
**Weeks 24–28**

### Goal
Production deployment, launch communications, and GitHub open-source release. The prod CDK deploy goes through the CodePipeline (not manual). GitHub release includes pyvar_functions.csv, full README, and contributing guide.

### Launch sequence

```
Day -7:  Prod CDK deploy via CodePipeline (push to main → pipeline → prod)
Day -7:  Alembic upgrade head against Aurora prod
Day -5:  48h soak test on prod — verify no SEV-1 errors
Day -3:  Smoke test all 8 domains on prod
Day -3:  Review + enhance .claude/skills/ with this deployment's project
         experience (runs in parallel with the soak/smoke window above —
         no AWS dependency; hard gate before Day 0, since .claude/ is
         tracked in git and goes public with the repo)
Day -1:  DNS switch: pyvar.com → CloudFront prod distribution
Day  0:  GitHub repo public (tag v0.1.0)
Day  0:  Post to Hacker News (Show HN), r/quantfinance, r/algotrading
Day  0:  Email Anthropic partner programme — pyvar.com is live
Day +1:  Monitor: Sentry errors, CloudWatch cost, GitHub stars
Day +7:  Review usage metrics — identify most popular functions for v0.2.0 roadmap
```

### Tasks
- Prod CDK deploy via CodePipeline (push to main → pipeline self-mutates → deploys prod stage)
- Run Alembic upgrade head against Aurora prod before traffic arrives
- Verify prod smoke test passes: all 8 domain compute endpoints return 202
- Review and enhance all 13 `.claude/skills/*/SKILL.md` files with real project
  experience from this deployment, before the repo goes public — see the
  dedicated session prompt below
- Set prod min task count to 2 (one per AZ) — verify ALB health checks passing in both AZs
- GitHub release: tag v0.1.0, publish pyvar_functions.csv, attach architecture diagram
- Write CONTRIBUTING.md: how to add a new function, Numba rules summary, PR checklist
- Write CHANGELOG.md: v0.1.0 — 382 functions, 8 domains, AWS CDK deployment
- Post to Hacker News (Show HN), r/quantfinance, r/algotrading, LinkedIn
- Email Anthropic partner programme contact — pyvar.com is now live (referencing partner application)
- Set up GitHub Discussions as community forum — seed with 3 starter threads per domain
- Post-launch: monitor Sentry daily, review CloudWatch cost dashboard daily for first week

**Descoped from v0.1.0**: publishing a `pyvar-client` Python SDK to PyPI (originally
listed here as "configure GitHub Actions to auto-publish new releases to PyPI"). No
`pyvar-client` code exists anywhere in this repo — this was never a polish item, it's
a from-scratch package: auth/token handling, typed request/response models across
385 endpoints, retry/backoff, its own test suite, docs, and a release/versioning
strategy independent of the API's own. Launch ships the REST API directly (`README.md`'s
quick start is the local dev / API setup, not a client library) — rushing a published
SDK to hit a launch date risks locking in a bad public API surface. Moved to the
v0.2.0 roadmap below, consolidated with the CLI tool idea (a CLI is naturally built
on top of a client library, so they should be designed together, not the SDK first
and a CLI bolted on after).

**Update (2026-08-24)** — none of this held: `pyvar-client` was built anyway and
shipped source-available in this repo at v0.1.0 (PR #257, 385 methods across 8
domains — see `CHANGELOG.md`'s 0.1.0 entry), published to PyPI shortly after
(https://pypi.org/project/pyvar-client/, pending the one-time Trusted Publisher
bootstrap described in `.github/workflows/pyvar-client-publish.yml`'s own header
comment — that bootstrap has to be done by hand via the PyPI web UI, no API exists
for it), and the CLI itself then shipped too (PR #266, `pyvar-client` v0.1.1,
2026-08-24) rather than waiting for v0.2.0 as this note originally planned. Nothing
from this note is still outstanding — see the v0.2.0 roadmap bullet below, which is
updated to match.

### Claude Code session prompts

**CONTRIBUTING.md for open-source contributors:**
```
Read CLAUDE.md in full — it is the source of truth for contribution rules.
Write CONTRIBUTING.md that explains:
1. How to add a new function: the 8-step process from CLAUDE.md section 10
2. The Numba JIT rules (section 3.1) — explain WHY each rule exists
3. The regulatory constraint rules (section 4) — emphasise that reg/* branches
   need review
4. How to run the test suite locally (section 9)
5. PR checklist: CLAUDE.md compliance, numerical test included, coverage maintained,
   no Bandit HIGH findings
6. How to propose a new domain — link to GitHub Discussions

Tone: welcoming to quant developers and risk engineers.
```

**GitHub launch prep:**
```
Prepare the GitHub repository for public launch:
1. Write a README.md that leads with "382 risk functions. One API. Open source."
   — covers quick start (local dev setup: clone, install, run — no pyvar-client
   SDK exists; that's descoped to v0.2.0, see this doc's Tasks section above),
   8 domains with function counts, tech stack, and links to pyvar.com
2. Add GitHub topics: quantitative-finance, risk-management, var, monte-carlo, frtb,
   numba, fastapi, open-source
3. Write a GitHub release body for v0.1.0: what's included, known limitations,
   v0.2.0 roadmap
4. Add .github/ISSUE_TEMPLATE/bug_report.md and feature_request.md
5. Create 8 GitHub labels matching the 8 domains

The README must be compelling enough to earn 50 GitHub stars in the first week.
```

**Review + enhance .claude/skills/ with real project experience:**
```
13 skill files live in .claude/skills/*/SKILL.md — 8 domain/regulatory skills
(alm, credit-risk, derivatives, liquidity-risk, market-risk, operational-risk,
portfolio-analytics, regulatory) and 5 architecture skills (arch-api-gateway,
arch-compute, arch-data-ingestion, arch-observability, arch-storage). These
are tracked in git and become public documentation the moment the repo goes
public (Day 0) — review and correct them before then, not after.

For each skill: read it in full, check every claim against what actually
shipped in this codebase (not what the skill assumes), and enhance it with
concrete lessons from real project experience — not generic advice a skill
could have said on day one.

Domain/regulatory skills — cross-check against the actual regulatory fixes
made during this project (see CLAUDE.md section 4 and git history): the
Solvency II SCR credit-risk formula correction (Art. 200-201), the rBergomi
kernel's fractional-Brownian autocovariance fix, the IRRBB standard shock
recalibration to BCBS d578, and the EMIR clearing scope correction
(all-asset-class, not per-class). Also check the module docstrings this
project already cleaned up for false/self-authored citations — the skill
files should point to the same real published sources, not repeat whatever
they said before that cleanup.

Architecture skills — this is where the bulk of new material is, since
almost all of this project's hard-won infrastructure lessons happened during
the P9 prod bootstrap: the ImageBuilder DistributionConfiguration schema
requiring literal PascalCase keys (not the typed CDK property class, which
has the same bug); CloudFront and SES both enforcing alias/identity
uniqueness ACCOUNT-WIDE, not per-distribution or per-stack, which blocked
prod's edge and SES stacks from ever deploying until given their own
domains; Aurora engine version pinning going stale when AWS deprecates a
specific point version; EC2 ASG Warm Pools being flatly incompatible with
Spot-based MixedInstancesPolicy; a self-mutating CDK pipeline silently
reverting any deployed-but-uncommitted fix on its next run; and the
RunDbMigration-before-the-app-stack-exists bootstrap ordering trap. Check
each architecture skill actually reflects these constraints where relevant,
not just the original design intent.

Where a skill is still accurate, leave it. Where it's wrong, fix it. Where
it's silent on something this project already learned the hard way, add it
— specific and falsifiable, not generic restatement of what the skill
already said.
```

### Exit gate
Prod deployment healthy for 48h. All 8 domain smoke tests passing. All 13 `.claude/skills/*/SKILL.md` files reviewed and enhanced with real project experience. GitHub repo public. No SEV-1 Sentry errors in 48h post-launch.

---

## Additional considerations

### What Claude Code does best on this project
- Domain engine implementation (P2): given CLAUDE.md + function list → produces numerically correct, Numba-compliant code with tests
- API boilerplate (P3): given one working domain as a pattern → replicates cleanly across 7 more
- CDK code generation (P4): verbose and repetitive — Claude Code shines here
- Test suites (P5): given the regulatory constraints in CLAUDE.md → writes correct threshold checks
- Portal JS (P8): self-contained, no external state — produces clean vanilla JS on first pass

### What requires human review regardless of Claude Code output
- Any function touching FRTB PAT thresholds (reg/* branch — two reviewers)
- Any Numba kernel with a new `@njit` signature (first-call compilation risk)
- Any Alembic migration that touches the var_jobs audit table (irreversible in prod)
- The CDK pipeline stack before first deployment (self-mutation means errors propagate)

### v0.2.0 roadmap (post-launch)
The following additions are scoped for v0.2.0, informed by usage statistics from P6:
- Real-time market data ingestion (Bloomberg/Refinitiv API connector via IntegratePro)
- Jupyter notebook integration (pyvar-jupyter kernel)
- Additional functions based on GitHub Discussions demand
- ~~`pyvar-client` CLI, built on top of the SDK~~ — **done, not v0.2.0 scope
  anymore.** Both halves of this item shipped ahead of schedule instead of
  waiting for v0.2.0 as originally planned here (see the P9 update note
  above): the SDK at v0.1.0 (PR #257, published to PyPI 2026-08-24) and the
  CLI at v0.1.1 (PR #266, published to PyPI the same day). See
  `pyvar-client/README.md`'s own `## CLI` section for actual usage — that's
  now the source of truth for this item, not the design sketch this bullet
  used to carry (package shape, exception types, retry semantics, etc. all
  landed as designed; the generated-methods codegen approach also landed,
  in `codegen/generate.py`, resolving the drift concern this sketch raised
  about hand-maintaining 385 methods).
- Streamlit dashboard as a hosted pyvar.com feature (not just local)

### Dependency on Fibtec services
pyvar.com's existence validates all four Fibtec services in production:
- **IntegratePro** — generates the Bloomberg/Refinitiv data connectors for v0.2.0
- **OptimizePro** — profiles and optimises the Numba kernels in P7
- **DocuGen** — generates the API reference documentation from the FastAPI routes
- **SecureAudit** — runs the pre-launch security review in P5

This is a genuine dogfooding opportunity — use Fibtec's own services on pyvar.com and document the results as case studies for the Anthropic partner application.

---

*pyvar.com release plan · Fibtec Limited · April 2026*
*Review cycle: weekly during P2–P4, fortnightly during P5–P9*
