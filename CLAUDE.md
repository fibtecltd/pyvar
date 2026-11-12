# CLAUDE.md — pyvar.com project context
# Read this file in full before making any changes to this codebase.
# Last updated: April 2026 (assistant bank and typed-question gateway sections added November 2026)

---

## 1. Project overview

pyvar.com is an open-source financial and risk management computation platform.
It exposes regulatory-grade risk functions (VaR, ES, Greeks, stress testing, etc.)
as a REST API, accelerated via Numba JIT and served through a Celery/SQS async
job pipeline on AWS.

**Company:** Fibtec Limited (UK)
**Stack:** Python 3.11 · FastAPI · Numba · Celery · SQS · ECS Fargate · EC2 Spot · Aurora SV2
**Regulatory context:** Basel III/IV · FRTB SA & IMA · MiFID II · EMIR · ICAAP/ILAAP

---

## 2. Repository layout

```
pyvar/
├── CLAUDE.md                  ← you are here
├── config.py                  ← pydantic-settings, single source of env config
├── main.py                    ← FastAPI app factory (create_app pattern)
├── worker.py                  ← Celery worker entry point
│
├── engine/                    ← COMPUTE CORE — Numba JIT functions
│   ├── montecarlo.py          ← Monte Carlo VaR engine (@njit parallel)
│   ├── metrics.py             ← Derived metrics (CVaR, backtesting, percentiles)
│   ├── liquidity_ratios.py    ← LCR, NSFR, ASF, RSF, HQLA L1/2A/2B
│   ├── liquidity_cashflow.py  ← cash-flow ladders (30d/1y), gap, funding tenor (@njit)
│   ├── liquidity_stress.py    ← stress scenarios, survival horizon, intraday, LiqVaR (@njit)
│   ├── liquidity_funding.py   ← buffer, CFP, concentration, runoff, repo, encumbrance, LTP
│   ├── liquidity_internal.py  ← ILAAP metric, risk appetite, EWI, scorecard, cross-ccy bridge
│   ├── oprisk_lda.py          ← LDA: freq/severity fit, compound dist, MC OpVaR, AMA (@njit)
│   ├── oprisk_capital.py      ← SMA, allocation, diversification, economic capital
│   ├── oprisk_rcsa.py         ← RCSA scoring, control effectiveness, BEI/ICF, loss data
│   ├── oprisk_kri.py          ← KRI library, breach detection, trend analysis
│   ├── oprisk_scenario.py     ← scenario analysis, expert elicitation, severity/freq estimation
│   ├── oprisk_governance.py   ← cyber/conduct/model/IT/vendor/BCM, heat map, escalation
│   ├── deriv_options_exotic.py ← Asian/lookback/American+Bermudan LSM/rainbow/basket/compound
│   │                              MC option pricers; greeks=True opt-in (delta/gamma/vega/
│   │                              theta/rho via bump-and-reprice, task #15 Phase 4)
│   └── deriv_stoch_vol.py     ← Heston/SABR/Dupire/rBergomi/Variance Gamma/NIG; the 3 MC
│                                  pricers (rBergomi/VG/NIG) support greeks=True opt-in too
│
├── assistant/                 ← portal assistant (measured by scripts/assistant_eval/; only client.py may import `anthropic`)
│   ├── prompts.py             ← system prompt, per-action tasks, request builder (PROMPT_VERSION v4)
│   ├── graders.py             ← programmatic graders for menu answers and grade_typed
│   ├── cost.py                ← token prices and cost from the API's usage block
│   ├── body_schema.py         ← small JSON-Schema checker for request bodies
│   ├── records.py             ← trim_record: the part of a catalogue entry a model is shown
│   ├── scrub.py               ← removes pyvar keys, JWTs, long hex and base64 runs and email addresses from text before any model call
│   ├── client.py              ← ModelClient protocol + AnthropicClient (retries, served-model check, cost); the SDK is imported lazily here only
│   ├── gate.py                ← the Opus gate: JUDGE_SYSTEM, judge_message, parse_verdict, gate() -> Verdict
│   ├── static_text.py         ← the static answer built from the record (graders.oracle_text): the floor of the bank
│   ├── tools.py               ← the typed agent's 3 read-only tools (search_functions, get_function, propose_parameters) + ToolBox
│   ├── typed_prompts.py       ← the typed system prompt (t2-2026-11-12, pinned) and request builder
│   ├── typed_graders.py       ← graders.grade_typed with the two first-run false positives fixed (graders.py itself is hash-pinned)
│   ├── agent.py               ← the typed tool loop on ModelClient: <=4 tool turns, dollar and time caps, visitor text escaped as data
│   ├── guardrails.py          ← answer_question: scrub -> agent -> typed grade -> one retry -> static fallback from the bank; never raises for a model problem
│   └── bank.py                ← `python -m assistant.bank build|check`: writes and checks portal/assistant/bank/
│
├── schemas/                   ← Pydantic v2 request/response models
│   ├── var.py                 ← VaRRequest, VaRResult, JobResponse
│   ├── assistant.py           ← AskRequest / AskResponse for POST /api/v1/assistant/ask
│   ├── auth.py                ← sign-in and API key request/response models
│   └── derivatives.py         ← Request/response models for derivatives pricers, incl. Greek
│                                  fields (delta/gamma/vega/theta/rho) on greeks=True pricers
│
├── ingestion/                 ← Data loading (Polars lazy scan + PyArrow)
│   ├── loader.py
│   └── fixtures.py            ← Synthetic GBM returns for dev/test
│
├── tasks/                     ← Celery task definitions
│   └── var_task.py
│
├── api/                       ← FastAPI routes and middleware
│   ├── assistant_bank.py      ← cached manifest read for /public/config + BankStaticFiles (Cache-Control) for /assistant/bank/
│   ├── assistant/             ← typed-question gateway, POST /api/v1/assistant/ask (flag off): routes.py, deps.py (switches, spend cap, slots, model client), store.py (Redis spend + kill switch), metrics.py
│   ├── routes/var.py          ← POST /var/compute  GET /var/result/{id}  WS /var/stream/{id}  POST /var/stream-token/{id}
│   ├── routes/auth.py         ← register / sign-in link / verify / Google / API key routes
│   ├── middleware/auth.py     ← bearer validation: session JWT or pyvar_ API key
│   ├── middleware/api_keys.py ← key hashing, Redis-cached lookup, failed-attempt throttle
│   ├── middleware/usage.py    ← api_usage rows, allowlisted X-Pyvar-Client label
│   ├── middleware/rate_limit.py ← compute quota, public/register per-IP quotas, enforce_assistant_rate_limit (every tier)
│   ├── responses.py           ← orjson response class
│   └── errors.py              ← 422 handler that stays renderable for NaN/Infinity input
│
├── storage/                   ← Persistence layer
│   ├── models.py              ← SQLAlchemy async ORM (VaRJob audit table, users, API keys, usage)
│   └── s3.py                  ← PyArrow + boto3 Parquet writer to S3/MinIO
│
├── observability/             ← Monitoring and logging
│   └── setup.py               ← Prometheus + Sentry + structlog init
│
├── migrations/                ← Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/              ← migration scripts (never edit manually)
│
├── portal/assistant.js        ← widget in the Try-it panel (textContent only; loaded by pyvar.js only when /public/config says enabled)
├── portal/assistant/bank/     ← the answer bank: <bank_version>/<function>.json + manifest.json (written by the CLI only; absent until the first committed build)
│
├── ui/                        ← Streamlit parameter dashboard
│   └── app.py
│
└── tests/
    ├── test_engine.py         ← numerical correctness tests (no mocking)
    └── test_api.py            ← integration tests (httpx AsyncClient)
```

---

## 3. Critical architecture constraints

### 3.1 Numba JIT rules — READ CAREFULLY

These rules apply to ALL code inside `engine/`. Violating them causes silent
runtime errors or compilation failures that are hard to debug.

```
RULE 1: @njit functions must be STATELESS.
  - Accept only NumPy arrays, scalars, and Python primitives.
  - Never pass Python objects, dataclasses, Pydantic models, or dicts.
  - Never import inside an @njit function.

RULE 2: No dynamic dispatch inside @njit.
  - No Python-style polymorphism or duck typing.
  - All array dtypes must be float64 — never float32 or object.

RULE 3: Pre-draw random numbers BEFORE entering the JIT region.
  - np.random.randn(n_sims, horizon) is called in pure Python.
  - The pre-drawn array is passed as an argument to the @njit kernel.
  - Numba's random API is limited — do not use it inside @njit.

RULE 4: prange requires @njit(parallel=True, cache=True).
  - cache=True is mandatory — prevents recompilation on every worker restart.
  - Do not use regular range() in parallel kernels — use prange().

RULE 5: Return only NumPy arrays from @njit functions.
  - Convert to Python types (list, dict, float) in the public wrapper,
    NEVER inside the JIT kernel.

RULE 6: Numba JIT warmup happens in main.py lifespan handler.
  - This is intentional — ECS health check startPeriod=30s covers it.
  - Do NOT remove or skip the warmup call.
```

### 3.2 Celery / SQS broker rules

```
LOCAL DEV:  CELERY_BROKER_URL = redis://localhost:6379/0
AWS:        CELERY_BROKER_URL = sqs://
            SQS_QUEUE_NAME    = pyvar-{env}-var-jobs.fifo

- The SQS queue is FIFO. task_acks_late=True is non-negotiable.
  If removed, interrupted Spot instances cause permanent job loss.
- visibility_timeout in SQS (60s) MUST exceed the max simulation runtime.
  If a new simulation type takes longer, update BOTH the Celery task
  timeout AND the SQS queue visibility timeout in the CDK stack.
- worker_prefetch_multiplier=1 — Monte Carlo is CPU-bound. Never increase.
- max_tasks_per_child=100 — prevents memory leaks from Numba compiled objects.
```

### 3.3 Database / Alembic rules

```
- ALL schema changes go through Alembic migrations. Never use
  Base.metadata.create_all() in production code.
- Migration scripts live in migrations/versions/.
  Never edit a committed migration — create a new one.
- Aurora SV2 uses async driver (asyncpg). Migration scripts use
  synchronous psycopg2 — this is intentional (Alembic runs offline).
- The VaRJob table is an AUDIT LOG. Never delete rows programmatically.
  Use the expiry lifecycle on S3 for large result cleanup instead.
- Index on (user_id, created_at) is intentional — do not remove.
```

### 3.4 AWS / CDK rules

```
- All secrets come from AWS Secrets Manager. Never hardcode credentials.
- VPC endpoints for SQS, ECR, S3, Secrets Manager are provisioned —
  do not add direct internet routes for these services.
- EC2 Spot workers use PRICE_CAPACITY_OPTIMIZED allocation. Do not
  change to LOWEST_PRICE — interruption risk is too high for financial compute.
- ECS tasks use FARGATE_SPOT + FARGATE mixed — do not remove the on-demand
  base capacity (api_min_tasks on FARGATE). This guarantees HA.
- IMDSv2 is required on all EC2 instances. Do not disable.
- CloudFront WAF WebACL MUST remain in us-east-1. The EdgeStack is
  deliberately deployed to us-east-1 — do not change this.
```

### 3.5 API keys and authentication

```
- A key is "pyvar_" + 32 random bytes. Only its SHA-256 is stored. After creation never
  log, return or store a key in clear; log only the display prefix.
- api_keys rows are never deleted. Revoking sets revoked_at.
- A database error while resolving a key is a 503: never a 401, never a pass.
  Redis errors fail open to the database (Redis is only a cache).
- A key's tier is read from the database (cached api_key_cache_ttl_seconds). Do not move
  it into a token claim.
- Key management routes need a session JWT (require_session). An API key must not be
  able to create or revoke keys.
- POST /auth/register returns the identical 202 for every outcome, so it cannot be used
  to find out which addresses have accounts.
- WS /var/stream/{task_id} takes its credential in the URL (a handshake cannot carry a header,
  and URLs are logged), so an API key is never accepted there. POST /var/stream-token/{task_id}
  exchanges a key or session for a 60 s, one-task token with an `aud` claim and no tier; every
  other route must keep refusing it (decode_token_payload does, by that claim). Do not drop the
  `aud`, and do not accept it in get_current_user.
- Design, settings and failure modes: docs/plan-durable-api-keys.md.
```

### 3.6 Portal assistant answer bank

```
- portal/assistant/bank/ is BUILT, never written by hand. Rebuild it with
  `python -m assistant.bank build --max-usd N` and verify with `python -m assistant.bank check`
  (no API). Never edit a committed bank file or its manifest: `check` re-grades every answer and a
  hand edit is a different text from the one that was gated. Change the record, the prompt or the
  graders instead, then rebuild (incremental: only changed answers are rewritten).
- To correct chosen answers without a new prompt version, use `--redo-ids FILE` (answer id -> notes):
  it rewrites those answers once, keeps the old entry if the rewrite would be static, and touches
  nothing else (file example: docs/assistant-bank-redo-1.json).
- Inputs that invalidate the bank: portal/functions.json (per-answer record hash), prompts.py
  (PROMPT_VERSION and prompt_sha256) and graders.py (grader_sha256: any byte, formatting included).
  The drift tests in tests/test_assistant_bank.py fail until the bank is rebuilt, and SKIP while
  portal/assistant/bank/manifest.json is absent.
- Only assistant/client.py may import `anthropic`, and only inside AnthropicClient.__init__. The bank
  build never runs in the API. `anthropic==2.6.0` is in requirements.txt only for the typed gateway
  (3.7); keep it equal to scripts/assistant_eval/requirements.txt, the version the answers were measured with.
- The key is `anthropic_api_key` (SecretStr, config.py). Never log it; never log answer text.
- /assistant/bank/ is a static mount (api/assistant_bank.py), registered before the portal catch-all
  and NOT a reserved API prefix. The widget shows only if assistant_enabled AND the manifest is
  complete. portal/assistant.js must keep to textContent: no innerHTML, eval or inline handlers.
```

### 3.7 Portal assistant typed-question gateway

```
- POST /api/v1/assistant/ask (api/assistant/) is OFF by default: it answers only when BOTH
  assistant_enabled and assistant_typed_enabled are true. Do not turn the second on in any
  environment until the privacy and terms pages name the model provider (plan 4.6) and the second
  measurement run has been approved and read (docs/assistant-phase0-results.md).
- Dependency order is fixed (routes.py): require_available (switches, kill switch, daily spend cap)
  -> limit_concurrency -> enforce_assistant_rate_limit -> handler. A question refused at any step
  must cost the visitor no quota and cost no model call. Keep that order.
- Cost controls: the day's spend (Redis, micro-dollars, UTC day) and the kill switch key
  `pyvar:assistant:kill` are read before every question and FAIL CLOSED (503 assistant_unavailable).
  This is the opposite of the rate limiter, on purpose: it protects a paid external API. Recording
  the spend after an answer fails open and is counted. The quota applies to every tier, enterprise
  included.
- Never log, store or put in a metric a visitor's question, an earlier turn, an answer or a tool
  result. Logs and metrics carry ids, tiers, outcomes, dollars and seconds only. Never return a model
  id in a response (model_tier is the family only).
- Anonymous callers are allowed; a bearer credential that is present must validate (401, never a
  quiet downgrade). Typed replies are English-only (decided 2026-11-12).
- Tests use the scripted client (tests/assistant_typed_fakes.py) and dependency_overrides for the
  model client and the store; no test calls a model, Redis or AWS.
- Example input values are the gateway's, not the model's: the typed prompt (t4, t5) forbids writing them,
  strip_example_objects takes any JSON object out of the model's text before it is graded, and the
  last accepted propose_parameters call is attached as suggested_parameters. What is graded must be what
  is served. Any change to typed_prompts.py changes its pinned sha256 (tests) and what the next run measures.
  The t4 prompt also tells the model never to answer a capability question with a bare "No"; that is a prompt
  rule, not a grader gate (typed_graders.bare_denial is a harness diagnostic only: as a gate it fired on most
  category D answers and on honest declines, results 9.29).
- An answer that points at "the example below" while no propose_parameters call was accepted fails the check
  example_not_attached (the retry is told to call the tool or drop the reference); the mirror case, values
  written without an accepted call, fails example_without_check. Keep both in step with the t4 prompt wording.
- The t5 prompt (t4 plus one rule) tells the model to give propose_parameters realistic, mutually consistent
  values for every required parameter and never an empty object, an empty list or a placeholder; the validator
  checks types and bounds only. typed_graders.empty_required_values is a harness diagnostic, not a gate. Measured
  on a 77-case slice only (results 9.32 and 9.33), never on the full 260; the slice showed no empty example and no regression except more second tries.
- The measurement harness (scripts/assistant_eval/run_typed.py) calls answer_question itself, so any
  change under assistant/ changes what the next paid run measures. Do not re-implement the answer
  path in the harness; do not start a paid run from a session without being asked (caps are per
  command, see docs/assistant-plan-tier-measurement.md).
```

---

## 4. Regulatory constraints — DO NOT simplify

The following logic is regulatory-grade and must not be altered without
explicit approval. These are marked `[REGULATORY]` in the codebase.

### 4.1 VaR confidence levels
```python
# Basel III standard: 0.99 (1-day VaR)
# FRTB IMA: 0.975 (10-day ES)
# Internal: 0.95 acceptable for internal limit monitoring
# NEVER accept confidence_level outside [0.90, 0.9999]
# This is enforced in schemas/var.py — do not relax.
```

### 4.2 Expected Shortfall (CVaR)
```
ES is the Basel IV / FRTB standard risk measure — NOT VaR.
- ES at 97.5% over 10-day horizon is the FRTB IMA capital metric.
- ES must be computed as the MEAN of losses BEYOND the VaR threshold.
  Not the median. Not the max. The mean.
- CVaR decomposition uses Euler allocation — sum of components MUST
  equal total ES. Do not use approximations that break this property.
```

### 4.3 Backtesting
```
- Basel traffic-light test uses EXACTLY 250 trading days. Not 252. Not 260.
- Breach zones: Green < 5, Yellow 5-9, Red >= 10 (per Basel Committee).
- Capital add-on multiplier: 3.0 (green), 3.40-3.85 (yellow), 4.0 (red).
- Kupiec and Christoffersen tests must use chi-squared critical values
  at 95% confidence — do not change significance level.
```

### 4.4 FRTB P&L Attribution Test
```
- PAT uses Spearman rank correlation AND ratio test jointly.
- Green zone: |correlation| >= 0.80 AND 0.8 <= ratio <= 1.2.
- Amber zone: |correlation| >= 0.70 AND 0.6 <= ratio <= 1.5.
- Red zone (IMA disqualification): anything below Amber.
- These thresholds are set by the Basel Committee — never parameterise them.
```

---

## 5. Testing rules

```
RULE 1: Engine tests (test_engine.py) must verify NUMERICAL CORRECTNESS.
  - Never mock the Numba engine functions in engine tests.
  - Test VaR properties: VaR > 0, CVaR >= VaR, 99% VaR > 95% VaR.
  - Test determinism: same seed → same result (always).
  - Test scaling: absolute VaR scales linearly with portfolio_value.

RULE 2: API tests (test_api.py) use httpx.AsyncClient with app=create_app().
  - Mock Celery task dispatch (apply_async) — not the engine.
  - Mock AsyncResult for result polling.
  - Always test: 202 on submit, 401 without auth, 422 on bad params,
    403 on tier cap exceeded.

RULE 3: Never use real AWS services in tests.
  - Use moto for S3/SQS mocking if needed.
  - Use fixtures.py for synthetic returns — never real market data.

RULE 4: Coverage target is 80% minimum before any release.
  Run: pytest --cov=. --cov-report=term-missing
```

## 5a. Mandatory coding rules — enforced by pre-commit hooks

These rules apply to every Python file in `engine/`, `api/`, `tasks/`, and `schemas/`.
Violations will block commits. Apply them during implementation, not after.

### Variable naming (ruff E741)
**Never** use single-letter variable names `l`, `O`, or `I` — they are visually
indistinguishable from `1`, `0`, and `1` respectively.

```python
# WRONG
l = np.asarray(lgd, dtype=np.float64)

# CORRECT
lgd_arr = np.asarray(lgd, dtype=np.float64)
liab    = np.asarray(bucket_liabilities, dtype=np.float64)
```

### Return type annotations and numpy scalar returns (mypy no-any-return)
Any `@njit` function or numpy expression returning a declared `float`, `complex`,
or `np.ndarray` return type **must** be explicitly cast:

```python
# WRONG — numpy scalar is typed Any by mypy
def _my_kernel(...) -> float:
    return values[0]

# CORRECT
def _my_kernel(...) -> float:
    return float(values[0])

# WRONG — np.sqrt returns Any in strict mode
def _semi_deviation(...) -> float:
    return np.sqrt(acc / n)

# CORRECT
def _semi_deviation(...) -> float:
    return float(np.sqrt(acc / n))

# WRONG — complex return
def _cf_heston(...) -> complex:
    return np.exp(c_term + d_term * v0 + 1j * u * np.log(spot))

# CORRECT
def _cf_heston(...) -> complex:
    return complex(np.exp(c_term + d_term * v0 + 1j * u * np.log(spot)))
```

### dict type annotations (mypy type-arg)
Never use bare `dict` in type annotations. Always specify key/value types:

```python
# WRONG
def my_function(data: dict) -> dict:

# CORRECT — if types are known
def my_function(data: dict[str, float]) -> dict[str, Any]:

# ACCEPTABLE — when dict is genuinely heterogeneous
def my_function(data: dict) -> dict:  # type: ignore[type-arg]
```

### np.concatenate with mixed list and array (mypy arg-type)
`np.concatenate` requires all inputs to be arrays. Never mix a Python list
with a numpy array in the same tuple argument:

```python
# WRONG — mypy cannot infer type of ([0.0], arr)
surv_prev = np.concatenate(([0.0], surv[:-1]))

# CORRECT
surv_prev: np.ndarray = np.concatenate(
    (np.array([0.0], dtype=np.float64), surv[:-1])
)
```

### dict.get as max/min key (mypy arg-type)
`dict.get` is overloaded and mypy cannot resolve it as a key function.
Use an explicit lambda:

```python
# WRONG
best = max(scores, key=scores.get)

# CORRECT
best = max(scores, key=lambda k: scores[k])
```

### Unused variable suppression
If a variable is computed but genuinely unused (e.g. an intermediate step
preserved for clarity), prefix it with `_` to suppress ruff F841:

```python
# WRONG — ruff F841
lam = math.sqrt(mu * mu + 2.0 * rate / sigma**2)  # unused

# CORRECT
_lam = math.sqrt(mu * mu + 2.0 * rate / sigma**2)  # noqa: unused-intentional
```

---

## 6. Code style

```
- Python 3.11+ features are allowed (match/case, Self, X | Y unions).
- Type hints are REQUIRED on all public functions and class methods.
- Docstrings follow Google style with Args/Returns/Raises sections.
- Line length: 100 characters (Black compatible).
- Imports: isort + Black. Run before committing.
- No bare except: always catch specific exception types.
- Logging: use structlog, never print(). Always pass context as extra={}.
- f-strings preferred over .format() or % formatting.
```

---

## 7. Environment variables

All env vars are defined in `config.py` via pydantic-settings.
Do NOT read os.environ directly anywhere else in the codebase.

```python
from config import get_settings
cfg = get_settings()
```

Local dev: copy `.env.example` → `.env` and fill in values.
AWS: all secrets come from Secrets Manager, injected at ECS task start.

Key variables:
```
APP_ENV            development | staging | production
CELERY_BROKER_URL  redis://localhost:6379/0 (dev) | sqs:// (aws)
SQS_QUEUE_NAME     pyvar-{env}-var-jobs.fifo (aws only)
POSTGRES_DSN       postgresql+asyncpg://...
S3_BUCKET          pyvar-{env}-results-{account}
JWT_SECRET         from Secrets Manager in prod
SENTRY_DSN         leave blank in dev
```

---

## 8. Git workflow

```
Branch naming:
  feat/short-description      new features
  fix/short-description       bug fixes
  reg/short-description       regulatory logic changes (require review)
  infra/short-description     CDK / infrastructure changes

Commit message format:
  feat(engine): add filtered historical simulation VaR
  fix(api): correct tier cap enforcement for pro users
  reg(metrics): fix Kupiec test chi-squared degrees of freedom
  infra(cdk): add CodePipeline stack for CI/CD

- Never commit directly to main.
- reg/* branches require a second reviewer before merge.
- infra/* branches require cdk diff output in the PR description.
```

### 8.1 Mandatory pre-merge CodePipeline check

**Before merging ANY pull request to `master`, always check whether the
merge will trigger a real CodePipeline execution (Test/Build/Dev-deploy —
a real cost, not a no-op) — and say so explicitly, before merging, not
after.** This applies whether or not anyone asks.

The push trigger (`pyvar-cdk/stacks/pipeline_stack.py`'s
`_TRIGGER_EXCLUDED_PATHS`) excludes exactly 8 top-level directories —
AWS CodePipeline's own hard cap on push-filter exclude entries:

```
.claude  .claude-plugin  .github  docs  ingestion  pyvar-client  scripts  tests
```

A PR whose changed files are **entirely** inside those 8 directories will
not trigger an execution. **Anything else does — including a single
root-level file like `README.md` or `CHANGELOG.md`.** Root-level files are
explicitly NOT coverable by this exclude list (no room left in the
8-entry cap — see the code's own comment at the trigger definition), so a
change that looks "docs-only" but touches `README.md` alongside `docs/`
files still starts a real pipeline run. Check every changed path in the
PR diff against the 8-directory list above — not just the PR's title or
description — before recommending or performing a merge, and state the
conclusion plainly: "this will trigger a CodePipeline run" or "this is
pipeline-safe."

---

## 9. Running locally

```bash
# 1. Infrastructure
docker run -d -p 6379:6379 redis
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pyvar postgres

# 2. Database migrations
alembic upgrade head

# 3. Generate fixture Parquet data
python -c "from ingestion.fixtures import generate_fixture_parquet; \
           generate_fixture_parquet('/tmp/pyvar_fixtures.parquet')"

# 4. Start API
uvicorn main:app --reload --port 8000

# 5. Start worker (separate terminal)
python worker.py

# 6. Start UI (separate terminal)
streamlit run ui/app.py

# 7. Run tests
pytest -v --cov=. --cov-report=term-missing
```

---

## 10. Common Claude Code tasks and patterns

### Adding a new risk function
1. Add the @njit kernel to engine/ (follow Numba rules in section 3.1)
2. Add a public wrapper function with full type hints and docstring
3. Add Pydantic request/response schemas in schemas/
4. Add a Celery task in tasks/
5. Add FastAPI route in api/routes/
6. Add engine tests verifying numerical properties
7. Add API tests verifying auth, validation, tier enforcement
8. Update this CLAUDE.md section 2 with the new files
9. Regenerate the published Claude skills so they list the new function with real
   parameters: `python3 scripts/generate_function_catalog.py`, then
   `python3 scripts/sync_skills.py` (assign the function to a group in
   `scripts/skill_specs/<domain>.json`), then `python3 scripts/generate_plugins.py`.
   `tests/test_skills_sync.py` fails until all three are done.

### Adding a new domain (e.g. Credit Risk endpoints)
1. Create schemas/credit.py, tasks/credit_task.py, api/routes/credit.py
2. Follow the exact same pattern as var.py in each layer
3. Register the new router in main.py
4. Add a new SQLAlchemy model in storage/models.py if new audit fields needed
5. Generate and apply an Alembic migration

### Modifying regulatory logic
1. Create a reg/* branch
2. Add a comment referencing the specific Basel/FRTB/MiFID II document and section
3. Update tests to cover the changed thresholds
4. Document the change in CHANGELOG.md with the regulatory reference

---

## 11. Known issues and workarounds

```
ISSUE: Numba first-call compilation takes ~2s on fresh worker.
FIX:   Warmup call in main.py lifespan handler (do not remove).
       In production: pre-bake AMI with compiled Numba cache.
       Cache location: ~/.cache/numba/ — preserved in EBS volume.

ISSUE: ElastiCache Serverless L2 construct not yet available in CDK.
FIX:   Using L1 CfnServerlessCache. When L2 lands, migrate.

ISSUE: SQS FIFO requires .fifo suffix in queue name.
FIX:   Always append .fifo when constructing queue names.
       Celery SQS transport reads CELERY_DEFAULT_QUEUE from config.

ISSUE: Aurora SV2 Alembic migrations must use sync driver (psycopg2).
FIX:   alembic.ini uses postgresql:// (not postgresql+asyncpg://).
       The application uses asyncpg — only migrations use psycopg2.

ISSUE: prod worker_use_baked_ami=True (config.py) requires a pyvar-prod-worker-*
       AMI to already exist. compute_stack.py resolves it via
       ec2.MachineImage.lookup(name=f"pyvar-{cfg.env_name}-worker-*", ...) at
       CDK synth time — this FAILS if no matching AMI has ever been built.
FIX:   AUTOMATED as of this entry — pyvar-cdk/stacks/pipeline_stack.py's
       shared Synth ShellStep now hashes ami_stack.py, and when it's changed
       since the last recorded bake (SSM /pyvar/prod/last-baked-ami-hash),
       triggers `aws imagebuilder start-image-pipeline-execution` against
       pyvar-prod-worker-pipeline and blocks (polling, 30min cap) until the
       new AMI reaches AVAILABLE — all BEFORE `cdk synth` runs, so
       ec2.MachineImage.lookup picks it up in the same pipeline run. Fails
       closed (exits 1) if the bake can't start or fails/times out — never
       silently deploys without a fresh bake. No-ops (one hash compare) on
       every push that doesn't touch ami_stack.py.
       ONE-TIME BOOTSTRAP: DONE. Confirmed 2026-08-31 against the real
       Fibtec prod account (347228921290): pyvar-prod-ami stack is
       UPDATE_COMPLETE (created 2026-08-08); its ImagePipeline
       (pyvar-prod-worker-pipeline) is ENABLED with 2 AVAILABLE image
       builds, and matching pyvar-prod-worker-* AMIs exist and are
       `available` in EC2 (so ec2.MachineImage.lookup resolves). The
       automated trigger-and-wait logic above has been proven end-to-end on
       real pipeline runs, both branches: SSM /pyvar/prod/last-baked-ami-hash
       was written once (2026-08-08T17:07:33Z, right after that day's bake
       reached AVAILABLE) confirming the bake branch; every Synth run since
       — including one on 2026-08-31 — has logged "No AMI-relevant changes
       since the last bake — skipping." confirming the skip branch. Full
       evidence trail in docs/p9-prod-ami-bootstrap-handoff.md's closure
       note. See docs/p9-scenario-volume-cost-audit.md for the original
       design writeup and tradeoffs considered before automating (incl. why
       the trigger has to run pre-synth, coupling a Prod-only AMI change to
       the Dev deploy in the same pipeline run).
```
