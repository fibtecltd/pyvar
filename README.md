# pyvar.com

Open-source financial and risk management computation platform.
Built by **Fibtec Limited (UK)** on top of NumPy, Numba, and the Anthropic Claude API.

---

## What is pyvar?

pyvar exposes **385 risk functions** across 8 domains — Monte Carlo VaR,
Expected Shortfall, Greeks, stress testing, P&L attribution and more — as a
REST API, served through an async Celery job pipeline. The most
compute-intensive kernels (Monte Carlo simulation and related hot loops —
84 of the 389 functions defined in `engine/`, 4 of which are internal
helpers not wired to any API route, 13 of them parallel) are Numba
JIT-compiled; the rest are plain NumPy/SciPy, where JIT compilation offers
little benefit. See `portal/functions.json` for the live, canonical function
list. Not independently validated for regulatory use — see
`tests/validation/` for pyvar's own cross-validation suite and its scope.

---

## Repository layout

```
pyvar/
├── CLAUDE.md                   ← Claude Code project context (read first)
├── Dockerfile                  ← multi-stage API container
├── alembic.ini                 ← database migration config
├── config.py                   ← pydantic-settings (all env vars here)
├── main.py                     ← FastAPI app factory
├── worker.py                   ← Celery worker entry point
├── requirements.txt
├── .env.example
├── pytest.ini
│
├── engine/                     ← Numba JIT compute core
│   ├── montecarlo.py           ← Monte Carlo VaR (@njit parallel)
│   └── metrics.py              ← CVaR, backtesting, percentiles
│
├── schemas/var.py              ← Pydantic v2 request/response models
├── ingestion/                  ← Polars lazy scan + PyArrow I/O
├── tasks/var_task.py           ← Celery task wrapping the engine
├── api/                        ← FastAPI routes + JWT middleware
├── storage/                    ← SQLAlchemy ORM + S3 Parquet writer
├── observability/              ← Prometheus + Sentry + structlog
├── ui/app.py                   ← Streamlit dashboard
├── tests/                      ← engine + API tests
│
├── migrations/                 ← Alembic migrations
│   └── versions/
│       ├── 0001_initial.py     ← var_jobs audit table
│       └── 0002_users_and_tier.py
│
├── scripts/
│   ├── db.py                   ← Alembic CLI wrapper
│   └── upgrade_head.sql        ← pre-generated migration SQL (for review)
│
├── portal/                     ← HTML portal mockups (open in browser)
│   ├── pyvar_portal.html
│   ├── pyvar_market_risk.html
│   └── pyvar_architecture.html
│
├── docs/                       ← project notes, release plans, adversarial reviews
│   ├── ENVIRONMENT_NOTES.md
│   ├── P4_ADVERSARIAL_REVIEW.md
│   ├── P4_ADVERSARIAL_POST_DEPLOY.md
│   ├── P5A_BLOCKERS.md
│   ├── pyvar_notes.md
│   └── pyvar_release_plan.md
│
└── pyvar-cdk/                  ← AWS CDK infrastructure
    └── stacks/
        ├── network_stack.py    ← VPC, subnets, SGs, VPC endpoints
        ├── data_stack.py       ← Aurora SV2, ElastiCache, S3
        ├── queue_stack.py      ← SQS FIFO + DLQ + CloudWatch alarms
        ├── compute_stack.py    ← EC2 Spot ASG + step scaling
        ├── api_stack.py        ← ECS Fargate + ALB
        ├── edge_stack.py       ← CloudFront + WAF + Route53
        ├── pipeline_stack.py   ← CodePipeline CI/CD (self-mutating)
        └── ami_stack.py        ← EC2 Image Builder (pre-baked Numba AMI)
```

---

## Quick start (local)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start infrastructure

```bash
docker run -d --name pyvar-redis    -p 6379:6379 redis:7-alpine
docker run -d --name pyvar-postgres -p 5432:5432 \
  -e POSTGRES_DB=pyvar \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=pyvar \
  postgres:16-alpine
```

### 3. Apply database migrations

```bash
python scripts/db.py upgrade
```

Creates: `alembic_version`, `var_jobs`, `users` tables.
To review SQL without applying: `cat scripts/upgrade_head.sql`

### 4. Generate fixture data

```bash
python -c "from ingestion.fixtures import generate_fixture_parquet; \
           generate_fixture_parquet('/tmp/pyvar_fixtures.parquet')"
```

### 5. Start the API

```bash
uvicorn main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 6. Start the worker (separate terminal)

```bash
python worker.py
```

### 7. Launch the UI (separate terminal)

```bash
streamlit run ui/app.py
```

### 8. Run tests

```bash
pytest -v --cov=. --cov-report=term-missing
```

### 9. Reproduce the published performance benchmarks

```bash
python scripts/p7_bench.py
```

Fully local and offline (no AWS credentials needed) — benchmarks the 10
hottest Monte Carlo kernels with fixed seeds/inputs, so the workload is
reproducible even though the absolute wall-clock numbers will vary by
machine. See `docs/p7-numba-profiling-results.md` for the last published
run and methodology.

---

## Migration commands

```bash
python scripts/db.py upgrade          # apply all pending migrations
python scripts/db.py downgrade -1     # roll back one migration
python scripts/db.py revision "msg"   # autogenerate from model changes
python scripts/db.py current          # show current revision
python scripts/db.py history          # full migration history
python scripts/db.py check            # CI gate: exits non-zero if pending
python scripts/db.py sql              # print SQL without applying
```

---

## AWS deployment

```bash
cd pyvar-cdk
pip install -r requirements.txt && npm install -g aws-cdk
cdk bootstrap aws://ACCOUNT/eu-west-1
cdk bootstrap aws://ACCOUNT/us-east-1
cdk deploy pyvar-pipeline --context account=ACCOUNT
# Push to main — pipeline handles all future deploys
```

---

## Tech stack summary

| Layer | Libraries |
|---|---|
| Compute | NumPy · Numba · SciPy · Polars · PyArrow · Dask · Ray |
| Finance | statsmodels · arch · QuantLib · empyrical |
| API | FastAPI · Pydantic v2 · orjson · slowapi |
| Queue | Celery · SQS FIFO (AWS) / Redis (local) |
| Storage | SQLAlchemy · Aurora PostgreSQL · S3 · Alembic |
| Infra | AWS CDK · ECS Fargate · EC2 Spot · CloudFront |
| AI | Anthropic Claude API |

Estimated AWS cost at ~500 jobs/day: **~£126/month**

---

## Disclaimer

pyvar computes risk metrics referenced by real regulatory frameworks (Basel
III/IV, FRTB, MiFID II, EMIR, ICAAP/ILAAP) — but **this is not regulatory,
financial, or legal advice, and pyvar's output is not a substitute for your
own institution's model validation, independent challenge, or regulatory
sign-off.** You are responsible for validating any function's output against
your own requirements before relying on it for a real risk, capital, or
compliance decision.

Where pyvar's implementation is a simplification of, or diverges from, the
textbook or regulatory-standard method, that is documented rather than
hidden: see each function's `caveat` field in `portal/functions.json`
(surfaced in the portal's Try-it panel) and `docs/p11-caveat-triage-plan.md`
for the full triage. As of this writing roughly a quarter of functions carry
such a caveat — read it before depending on that function.

Licensed under the [Apache License 2.0](LICENSE), which includes its own
express disclaimer of warranty and limitation of liability (§7–8) — the
above is a plain-English summary of what that means for this specific
project, not an additional or different legal term.

See [`SECURITY.md`](SECURITY.md) to report a security or numerical
correctness issue.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the function-implementation
process, Numba JIT rules, regulatory review requirements, and PR checklist.
[`CHANGELOG.md`](CHANGELOG.md) tracks notable changes by release.

---

Licensed under the [Apache License 2.0](LICENSE).

**Fibtec Limited** · hello@fibtec.co.uk
