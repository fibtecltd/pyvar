# Onboarding guide

This guide gets a new engineer from a fresh checkout to a running local stack, a first API call and a first change. It points at the code and the project's own rules. For the design see [architecture-overview.md](architecture-overview.md); for the routes see [api-reference.md](api-reference.md).

## 1. What you are working on

pyvar is a risk-computation REST API: 385 functions in 8 domains served by a FastAPI app, plus Monte Carlo VaR as a queued job run by Celery workers (`README.md:12-15`). The compute code is in `engine/`, request and response models in `schemas/`, routes in `api/routes/`, persistence in `storage/`, infrastructure in `pyvar-cdk/`.

Read these first, in this order:

1. `README.md`: what it is, layout, quick start, disclaimer.
2. `CLAUDE.md`: the project's own context file. `CONTRIBUTING.md` says to read it in full and that it wins if the two disagree (`CONTRIBUTING.md:8-11`). It holds the Numba rules, the Celery and Alembic rules and the authentication rules.
3. `CONTRIBUTING.md`: how to add a function, the regulatory review rule and the PR checklist.
4. This documentation set.

The README includes a disclaimer you should know before touching formulas: output is not regulatory, financial or legal advice, and some functions carry a `caveat` in `portal/functions.json` (`README.md:249-264`).

## 2. Mental model in six lines

- One FastAPI app (`main.py:150-280`) serves the API under `/api/v1`, the static portal at `/`, and an assistant answer bank at `/assistant/bank`.
- Domain functions run inline in the request. The one exception is `POST /api/v1/var/compute`, which writes an audit row, enqueues a Celery task and returns 202 (`api/routes/var.py:179-331`).
- Credentials are a 60-minute session JWT or a durable `pyvar_` API key. Tier limits live in one table, `api/tiers.py`.
- Postgres holds accounts, keys and two audit logs. Redis holds Celery results, the result cache, rate-limit counters, job-done events and the trial and assistant state.
- The same Docker image runs the API and the worker (`docker-compose.yml:119`).
- Infrastructure is AWS CDK in `pyvar-cdk/`, deployed by a self-mutating pipeline (`pyvar-cdk/app.py:50-56`).

## 3. Prerequisites

| Need | Why | Source |
|---|---|---|
| Python 3.11 (CI also runs 3.12) | runtime | `CLAUDE.md:15`, `.github/workflows/ci.yml:88` |
| Docker | Redis, Postgres, or the whole stack | `README.md:115-124`, `docker-compose.yml` |
| Redis 7 and Postgres 16 | broker, cache and database | `README.md:118-124`, `.github/workflows/ci.yml:90-111` |
| Node and `aws-cdk` | only for infrastructure work | `README.md:197-200`, `.github/workflows/ci.yml:159-166` |

Dependency files: `requirements.txt`, `requirements-ci.txt`, `requirements-heavy.txt`. Environment variables are defined in `config.py` through pydantic-settings, with a template in `.env.example` (`README.md:49-54`).

## 4. Run it locally

### Option A: manual

These are the README's steps (`README.md:107-177`):

1. `pip install -r requirements.txt`
2. Start Redis 7 and Postgres 16 containers with database `pyvar` (the exact `docker run` commands, including the development password, are at `README.md:118-124`).
3. Apply migrations: `python scripts/db.py upgrade`. This creates `alembic_version`, `var_jobs`, `users`, `api_usage`, `api_keys` and `billing_events` (`README.md:129-133`). Ten migrations exist, `0001_initial` to `0010_user_tier_expires_at` (`migrations/versions/`).
4. Generate fixture data with `ingestion.fixtures.generate_fixture_parquet` (`README.md:138-139`).
5. Start the API: `uvicorn main:app --reload --port 8000`. Interactive docs appear at `/docs` (`README.md:145-146`).
6. In another terminal start the worker: `python worker.py` (`README.md:152`). It reads `CELERY_CONCURRENCY`, `SQS_QUEUE_NAME` and `CELERY_WORKER_POOL` from the environment (`worker.py:34-42`).
7. Optionally start the Streamlit dashboard: `streamlit run ui/app.py` (`README.md:158`).

### Option B: Docker Compose

`docker-compose.yml` defines `pyvar-api`, `pyvar-api-dev` (profile `dev`, with `--reload`), `worker`, `redis`, `postgres` and `flower` (profile `monitoring`) (`docker-compose.yml:34`, `:75`, `:114`, `:147`, `:163`, `:182`). Its header says to create the shared network once with `docker network create pyvar_net`, then `docker compose up`, and to run migrations with `docker compose run --rm pyvar-api python scripts/db.py upgrade` (`docker-compose.yml:17-26`). The services read a `.env` file (`docker-compose.yml:41`).

`pyvar-full/` is a packaged variant of the full stack that adds a one-shot `migrate` service, so `docker compose up` alone is enough (`pyvar-full/README.md:23-32`). `pyvar-local/` is the engine and a CLI only, with no API server (`pyvar-local/README.md:3-26`).

### Smoke test

`GET /health` returns `status`, `app` and `env` (`main.py:254-256`). The compose healthcheck calls it (`docker-compose.yml:63-68`).

## 5. Make your first API call

1. **Register.** `POST /api/v1/auth/register` with `{"email": "you@example.com"}` (`pyvar-full/README.md:38-41`). The answer is always the same 202. If SES is unavailable, as in local development without AWS credentials, sending falls back to a log-only stub, so look in the API log for the link; what exactly is logged was not read (`api/routes/auth.py:19-22`).
2. **Verify.** Open the e-mailed link, which calls `GET /api/v1/auth/verify?token=...` and returns a 60-minute session token (`schemas/auth.py:41-49`).
3. **Create a key.** `POST /api/v1/auth/api-keys` with the session token as the bearer. The secret is shown once (`api/routes/auth.py:333-337`). `scripts/mint_api_key.py` also exists; its behaviour was not read.
4. **Call a function.** For example, from the client SDK:
   ```python
   from pyvar_client import Client
   client = Client()  # reads PYVAR_API_KEY
   client.market_risk.historical_simulation_var(returns=[...], portfolio_value=1_000_000, confidence_level=0.99)
   ```
   (`pyvar-client/README.md:17-29`). Or call `POST /api/v1/market-risk/historical_simulation_var` directly with a JSON body.
5. **Run a VaR job.** `POST /api/v1/var/compute` with `portfolio_value` and at least 30 `returns`, then poll `GET /api/v1/var/result/{task_id}` until `status` is `success` (`schemas/var.py:38-66`, `api/routes/var.py:179-183`, `:430-436`). `client.var.compute(...)` does the submit and poll for you (`pyvar-client/README.md:44-62`).

If you hit the free tier's daily compute quota, it is 20 requests a day by default (`config.py:180`).

## 6. Where to find things

| You want to... | Look in |
|---|---|
| change the app wiring, add a router | `main.py:196-251` |
| add or change a domain endpoint | `api/routes/<domain>.py`, `schemas/<domain>.py`, `engine/<prefix>_*.py` |
| change VaR submit or result behaviour | `api/routes/var.py`, `tasks/var_task.py`, `schemas/var.py` |
| change the Monte Carlo kernel | `engine/montecarlo.py` |
| change a tier's limits | the matching row in `api/tiers.py:75-142` |
| change authentication | `api/middleware/auth.py`, `api/middleware/api_keys.py` |
| change rate limits | `api/middleware/rate_limit.py` |
| change a table | `storage/models.py` plus a new file in `migrations/versions/` |
| change billing | `api/routes/billing.py`, `api/middleware/billing_lifecycle.py` |
| change the trial lane | `api/routes/trial.py`, `api/middleware/trial.py`, `api/trial_whitelist.py` |
| change the assistant | `assistant/`, `api/assistant/` |
| change infrastructure | `pyvar-cdk/stacks/` |
| see the canonical function list | `portal/functions.json`, `pyvar_functions.csv` |
| operator scripts | `scripts/` (database, keys, education grants, erasure, audit clean-up, benchmarks) |

## 7. Common tasks

### Add a new risk function

`CONTRIBUTING.md:27-45` lists eight steps: an `@njit` kernel in `engine/`, a typed public wrapper, Pydantic schemas in `schemas/`, a Celery task in `tasks/`, a FastAPI route in `api/routes/`, engine tests, API tests, and an update to the `CLAUDE.md` layout. Afterwards run `python3 scripts/generate_function_catalog.py` so `portal/functions.json` stays accurate.

Note the drift on step 4: `tasks/` contains only `var_task.py`, and the eight domain routers call the engine inline rather than through Celery (`main.py:217-219`, `api/routes/trial.py:15-18`). Follow the pattern of a neighbouring endpoint in the same domain rather than adding a task by default.

### Change the database

All schema changes go through Alembic. Never use `Base.metadata.create_all()` in production code and never edit a committed migration (`CLAUDE.md:184-187`). The wrapper commands are `python scripts/db.py upgrade`, `downgrade -1`, `revision "msg"`, `current`, `history`, `check` (non-zero when migrations are pending) and `sql` (`README.md:184-191`). The audit tables `var_jobs` and `billing_events` are append-only, kept six years, and only the clean-up command may delete from them (`CLAUDE.md:191-200`).

### Touch regulatory logic

Code marked `[REGULATORY]` implements specific Basel, FRTB, MiFID II or EMIR requirements. Use a `reg/*` branch, cite the document and section, update tests and `CHANGELOG.md`, and get a second reviewer (`CONTRIBUTING.md:78-97`). The fixed values include the `[0.90, 0.9999]` confidence range, the 250-day traffic-light test and the FRTB P&L attribution thresholds (`CLAUDE.md:402-442`).

### Add a tier or change a limit

Add a `TierPolicy` row in `api/tiers.py` and the name to `KNOWN_TIERS`. Its test fails until both agree, and no other module may read per-tier numbers (`api/tiers.py:11-16`, `api/tiers.py:44-46`).

### Rebuild the assistant answer bank

The bank under `portal/assistant/bank/` is built by `python -m assistant.bank build --max-usd N` and verified by `python -m assistant.bank check`, which needs no API. Never edit bank files by hand (`CLAUDE.md:311-315`, `assistant/README.md:40-59`). A build is paid and needs an Anthropic key in the environment (`assistant/README.md:41`).

## 8. Tests and CI

Run locally: `pytest -v --cov=. --cov-report=term-missing` (`README.md:164`). CI runs the same with `--cov-fail-under=80` on Python 3.11 and 3.12, against Redis 7 and Postgres 16 services, with `APP_ENV`, `REDIS_URL`, `POSTGRES_DSN`, `JWT_SECRET` and `CELERY_BROKER_URL` set for the job (`.github/workflows/ci.yml:83-139`).

Testing rules (`CONTRIBUTING.md:119-132`):

- Engine tests check numerical properties and never mock the engine. Examples: VaR above 0, CVaR at least VaR, the same seed giving the same result, linear scaling in portfolio value.
- API tests use `httpx.AsyncClient` against `create_app()` and mock Celery's `apply_async` and `AsyncResult`, not the engine. Cover 202, 401, 422 and 403 on the tier cap.
- Never use real AWS services; use `moto` if needed and `ingestion/fixtures.py` for synthetic returns.
- Assistant tests need no key and no network (`assistant/README.md:68-73`).

Test layout: `tests/test_*.py` is named by module, for example `test_var_task.py`, `test_rate_limit.py`, `test_billing.py`, `test_trial_routes.py` and many `test_assistant_*.py` files. Subdirectories `tests/security/` and `tests/validation/` also exist; the README describes `tests/validation/` as pyvar's own cross-validation suite (`README.md:20-21`). Rate-limit tests rely on a `tests/conftest.py` autouse fixture that patches `api.middleware.rate_limit._limiter` (`api/routes/var.py:229-232`).

CI jobs besides tests: lint with black, isort and ruff; Bandit with `-ll`; a CDK synth; a Docker build without push (`.github/workflows/ci.yml:33-61`, `:64-80`, `:148-179`, `:182-214`). The PR checklist adds mypy, a numerical test for any engine change, and the `type(scope): summary` commit style (`CONTRIBUTING.md:136-154`).

## 9. Rules that bite

These come from the project's own rules and are enforced by tests or review:

- **Numba kernels** are stateless, float64-only, take pre-drawn random numbers, return only NumPy arrays, and use `@njit(parallel=True, cache=True)` with `prange` (`CLAUDE.md:128-159`).
- **Celery and SQS:** `task_acks_late` and `task_reject_on_worker_lost` stay on, `worker_prefetch_multiplier` stays 1, and every SQS message keeps its own message group (`CLAUDE.md:161-180`, `tasks/var_task.py:278-291`, `:332-352`).
- **Keys:** only the SHA-256 is stored, nothing logs a key, and key routes need a session token (`CLAUDE.md:222-231`).
- **Tokens with `aud`** (stream, admin, trial) must keep being refused by `get_current_user` (`CLAUDE.md:233-244`, `:284-290`).
- **Fail open or closed** differs by component, so do not unify them (see the table in the architecture overview).
- **Never delete** `api_keys`, `var_jobs` or `billing_events` rows outside the clean-up command (`CLAUDE.md:191-200`, `:221-222`).
- **Assistant:** only `assistant/client.py` imports `anthropic`; visitor text is never logged or stored (`CLAUDE.md:323-326`, `:347-349`).
- **Secrets** come from AWS Secrets Manager; do not hard-code any (`CLAUDE.md:206-207`).

## 10. Gotchas

- The API process warms Numba at startup (`main.py:108-116`), so the first start is slow.
- A job still `pending` after an hour is marked failed by the reconciler, in hosted environments only (`storage/reconcile.py:11-19`, `main.py:126-137`).
- `GET /var/result/{task_id}` serves any authenticated caller who knows the id (`api/routes/var.py:738-741`).
- The README's layout block is partly stale: it names portal mock-ups that are not in `portal/` (`README.md:80-83`).
- Some referenced files were not read for this guide: `scripts/` contents, `ui/app.py`, `ingestion/loader.py` and `tests/conftest.py`. Not determined from the source here.

## Sources

README.md
CLAUDE.md
CONTRIBUTING.md
main.py
worker.py
config.py
docker-compose.yml
api/tiers.py
api/routes/var.py
api/routes/auth.py
api/routes/trial.py
storage/reconcile.py
tasks/var_task.py
schemas/auth.py
schemas/var.py
assistant/README.md
pyvar-client/README.md
pyvar-full/README.md
pyvar-local/README.md
pyvar-cdk/app.py
.github/workflows/ci.yml
