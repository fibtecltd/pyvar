# pyvar Full

The complete pyvar stack — API, Celery worker, Redis, Postgres — running
entirely on your own infrastructure via `docker compose up`. Built from
the exact same production `Dockerfile` the hosted `pyvar.com` API uses,
not a separate or lighter build.

See [`pyvar-local/README.md`](../pyvar-local/README.md) for the sibling,
narrower package this one extends: `pyvar-local` ships the compute
`engine/` and a CLI only, no API server. This package is for anyone who
wants the *whole* thing — the REST API, auth, rate limiting, async job
dispatch — running locally, not just the compute layer.

## What's in this stack

- **`pyvar-api`** — the real FastAPI app (`main.py`), all 8 domain
  routers, auth, rate limiting. Same image as `pyvar-prod-api`.
- **`worker`** — the real Celery worker (`worker.py`), same image.
- **`redis`** — Celery broker + result backend (replaces SQS/ElastiCache
  in the hosted deployment).
- **`postgres`** — the async job audit log and user/billing tables
  (replaces Aurora Serverless v2 in the hosted deployment).
- **`migrate`** — a one-shot service that runs `alembic upgrade head`
  before `pyvar-api`/`worker` start, so `docker compose up` alone is
  enough — no separate manual migration step.

## Getting started

```bash
cd pyvar-full/
docker compose up
```

Wait for `pyvar-api`'s healthcheck to pass (`docker compose ps`), then:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}'
```

From there it's the same REST API documented in
[`docs/publications/pyvar-rest-api-guide-medium-article.md`](../docs/publications/pyvar-rest-api-guide-medium-article.md)
— everything works identically to the hosted service, pointed at
`http://localhost:8000` instead of `https://pyvar.com`.

Scale workers: `docker compose up --scale worker=2`

## What's deliberately different from hosted pyvar.com

- **Stripe billing is inert by default.** `api/routes/billing.py` ships
  as part of the real API surface (this package includes the *whole*
  app, not a stripped-down one), but `local-eval.env` leaves the three
  Stripe settings blank, and the app's own
  `_require_billing_configured()` check 503s every billing route
  cleanly until real test-mode keys are supplied. Nothing to configure
  for local evaluation; supply your own Stripe test-mode keys in
  `local-eval.env` only if you specifically want to exercise Checkout
  locally.
- **No S3/result offload.** VaR jobs compute and return correctly.
  Only the large-result S3 offload path (`storage/s3.py`, triggered
  above a simulation-count threshold) is unconfigured — verified
  against `tasks/var_task.py`: that offload is wrapped in its own
  try/except with an explicit inline fallback ("an S3 outage must not
  fail an already-successful computation"), so a job above the
  threshold just returns its full result inline instead of offloading
  it, rather than failing.
- **No Sentry.** Left unconfigured; nothing breaks, error tracking is
  just off.
- **Credentials are fake, checked-in, and isolated.** `local-eval.env`
  ships real-looking-but-fake Postgres/JWT values, scoped entirely to
  this compose project's own network and volumes — fine for local
  evaluation, not meant to be internet-reachable. See that file's own
  header for specifics.

## Licensing note

Same note as `pyvar-local`: the code here is the same Apache-2.0-licensed
source already published in this repository. Nothing about running it
locally requires a purchase — this is the actual open-source stack,
packaged for a one-command local bring-up.

## Building and publishing

Not yet wired into a CI/CD pipeline the way `pyvar-local`'s
`local_package_stack.py` is — this first release is `docker compose up`
from a checked-out clone. Reusing that same manually-triggered
build/publish pattern (a standalone, on-demand CodePipeline stage) is
the natural next step if this needs to ship as a standalone downloadable
artifact rather than "clone the repo and run this directory," but that's
deliberately not built here yet.
