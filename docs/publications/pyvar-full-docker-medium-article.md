# pyvar Full: the Whole Platform, One `docker compose up` Away

*A companion to pyvar Local — same open-source engine, but this one ships the real API, auth, async job dispatch, and billing surface too, running entirely on your own infrastructure.*

> **Draft status:** not yet published. Every claim below — what's in the compose stack, what's deliberately inert, why the S3 offload path is safe to leave unconfigured — is verified against the actual `pyvar-full/` files and the `tasks/var_task.py`/`storage/s3.py` code they depend on, at drafting time. See **Sources** at the end.

---

Two weeks ago this publication covered [pyvar Local](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-local-release-medium-article.md) — an offline, no-API-key Docker image for institutions that can't send position data to any third-party endpoint, even a stateless one. It ships the compute engine and a CLI. Deliberately, it doesn't ship a server: no auth, no REST routes, no async job queue.

**pyvar Full** is the other half of that story: the same open-source stack, but the whole thing — the real FastAPI app, Celery worker, the actual route surface `pyvar.com` runs — brought up with one command, on infrastructure you control.

## What actually changed

Nothing in the application code. `pyvar-full/docker-compose.yml` builds from the exact same `Dockerfile` that produces the hosted `pyvar-prod-api` image — not a stripped-down variant, not a separate build target. If you've read `pyvar.com`'s own [technical deep-dive](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-technical-deepdive-medium-article.md) on how the compute engine and worker fleet are built, this is that same image, just orchestrated with `docker-compose` instead of ECS Fargate and EC2 Spot.

Five services, one command:

```bash
cd pyvar-full/
docker compose up
```

- **`pyvar-api`** — the real FastAPI app, all 8 domain routers, auth, rate limiting.
- **`worker`** — the real Celery worker, same image, `--scale worker=2` if you want more.
- **`redis`** — Celery broker and result backend, standing in for SQS/ElastiCache.
- **`postgres`** — the job audit log and user tables, standing in for Aurora Serverless v2.
- **`migrate`** — a one-shot service that runs `alembic upgrade head` before anything else starts, so there's no separate manual migration step. `docker compose up` alone is the whole setup.

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}'
```

From there it's the identical REST API [already documented](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-rest-api-guide-medium-article.md) for the hosted service — same auth flow, same 385 functions across 8 domains, same request/response shapes. Point your existing pyvar client code at `localhost:8000` instead of `pyvar.com` and it should just work.

## The billing question, answered by just checking

Shipping the whole app means shipping `api/routes/billing.py` too — the same Stripe-integrated route the hosted service uses for Pro-tier Checkout. The obvious question: does a publicly-distributed local image really need a commercial billing route baked in?

Rather than guess, this got checked directly. `_require_billing_configured()` — the function every billing route calls first — 503s cleanly whenever `STRIPE_SECRET_KEY` isn't set. `pyvar-full/local-eval.env` leaves it blank. So the answer turned out to be: nothing to strip out, nothing to configure. The route exists, does nothing without real keys, and costs zero setup either way. If you want to exercise Checkout locally, drop Stripe test-mode keys into `local-eval.env` yourself.

## What's actually different from running the hosted service

Almost nothing, by design — but two things are worth being upfront about, the same way pyvar Local's own writeup was upfront about what it doesn't include yet:

**No S3 result offload.** `tasks/var_task.py` only reaches for S3 above a simulation-count threshold, and that offload is wrapped in its own try/except with an explicit fallback: *"an S3 outage must not fail an already-successful computation."* Leave `S3_BUCKET` blank (the default in `local-eval.env`) and large jobs just return their full result inline instead of offloading it — more data back to you, not less, for local-scale testing. Nothing breaks; this was verified by reading the actual fallback logic, not assumed from the variable being optional.

**No Sentry.** Also left blank. Error tracking is off; nothing else changes.

Everything else — the Numba JIT-accelerated Monte Carlo kernels, the FRTB/Basel/MiFID II regulatory logic, the rate limiting and tier enforcement, the async job dispatch pattern — is the exact same code path the hosted platform runs in production, not a demo approximation of it.

## Why this, and why now

pyvar Local answered "I can't send data anywhere." This answers a narrower but common question: "I want to run the actual platform myself — evaluate it, integrate it into an existing pipeline, keep a copy that doesn't depend on pyvar.com's uptime — without standing up ECS, Aurora, and an ALB myself." Five `docker-compose` services and a checked-in set of safe local-eval defaults gets there in one command.

## Try it

```bash
git clone https://github.com/fibtecltd/pyvar
cd pyvar/pyvar-full
docker compose up
curl http://localhost:8000/health
```

---

## Sources

- [`pyvar-full/docker-compose.yml`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-full/docker-compose.yml) and [`pyvar-full/README.md`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-full/README.md) — the actual shipped artifact this article describes.
- [`Dockerfile`](https://github.com/fibtecltd/pyvar/blob/master/Dockerfile) — the same production image build both `pyvar-full` and the hosted `pyvar-prod-api` use.
- [`tasks/var_task.py`](https://github.com/fibtecltd/pyvar/blob/master/tasks/var_task.py) and [`storage/s3.py`](https://github.com/fibtecltd/pyvar/blob/master/storage/s3.py) — verified source for the S3-offload fallback-on-failure claim above.
- [`api/routes/billing.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/billing.py) — `_require_billing_configured()`, source for the billing-inert-by-default claim.
- [`docs/publications/pyvar-local-release-medium-article.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-local-release-medium-article.md) — the companion piece on the engine-only, no-API package this one extends.
- [`docs/plan-docker-all-in-one-image.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/plan-docker-all-in-one-image.md) — the original exploration this package was built from.
