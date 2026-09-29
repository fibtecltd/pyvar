# Exploration: a Docker image with full pyvar functionality

**Status: exploration only, no action taken.** Requested alongside five
other planning items (2026-09-29); this one and
`plan-streaming-realtime-pricing.md` were explicitly scoped as
"explore, without taking actions."

## 1. What already exists, and why it's not this

`pyvar-local/` (shipped, item 2 of the six-initiatives roadmap — see
`docs/plan-pyvar-local-package-generation.md`) is a single-container image,
but a deliberately narrow one: `engine/` plus a CLI wrapper
(`pyvar_local/cli.py`) that reflects over `engine/` at runtime, `python:3.11-slim`
base, `requirements-heavy.txt` only. Its own README states the exclusion
explicitly: **no FastAPI server, no Celery worker, no Postgres, no Redis,
no S3**. It answers "give me the compute engine to run offline," not
"give me pyvar."

**Correction to an earlier draft of this doc**: `docker-compose.yml` at
the repo root already runs the *full* stack — `pyvar-api` (FastAPI),
`worker` (Celery), `redis`, `postgres`, plus an optional `flower` task
monitor behind a `--profile monitoring` flag and a hot-reload
`pyvar-api-dev` service behind `--profile dev`. So "all pyvar
functionalities in Docker" isn't unbuilt — it's already how local API
development works today (`docker compose up`), reusing the repo's own
root `Dockerfile` (`target: runtime`). The actual gap is narrower than
"build a compose stack from scratch."

## 2. What the existing compose stack is, and isn't, for

It's built for **repo-cloned local development**, not **public
redistribution**:
- Bind-mounts the whole repo (`.:/app`) — assumes the source tree is
  already checked out, not something a third party downloads standalone.
- Reads `env_file: .env` — expects a developer's own local secrets file
  to already exist (`.env.example` documents the shape but isn't itself
  usable as-is).
- Hardcoded dev-only DB credentials (`pyvar:pyvar`) baked into the compose
  file itself — fine for a throwaway local Postgres container, not
  something to publish.
- Depends on an externally-created Docker network
  (`docker network create pyvar_net`, shared with a *separate*
  `~/claude-docker/docker-compose.yml`) — a convention specific to this
  project's own dev machine setup, not something a downloaded artifact
  should require.

None of this is a criticism of the compose file — it's doing its actual
job (fast local iteration) well. It just isn't the same artifact as "one
thing a prospect downloads and runs to see all of pyvar," which is what
"a Docker image containing all pyvar functionalities" (as a product,
distinct from a dev tool) actually implies.

## 3. What turning it into a distributable artifact would need

Given the compose topology already exists and is proven (this is what the
team's own local dev already runs on), the remaining gap is narrower than
originally scoped:
- Self-contained images: build with `COPY . .` (or a tighter subset, à la
  `pyvar-local/Dockerfile`'s explicit engine-only `COPY` list) instead of
  the dev bind-mount, so the image runs without a repo checkout.
- A generated, safe-default `.env` (or compose `environment:` block) baked
  in for evaluation use — real Postgres/Redis credentials for a
  throwaway local stack are fine to ship as defaults (they're not
  reachable from outside the compose network), unlike the current `.env`
  pattern which assumes a developer supplies their own.
- Drop the external-network dependency (`pyvar_net` shared with a sibling
  compose file) — a distributable artifact needs to be self-contained,
  not assume a co-located `claude-docker` checkout.
- Same Numba JIT warmup question `pyvar-local`'s own Dockerfile already
  answered (pre-warm at build time, baked into the image layer) — the
  root `Dockerfile`'s `runtime` target doesn't currently do this for the
  API/worker images the way `pyvar-local/Dockerfile` does for the engine
  image; worth carrying the same pattern over.
- The same license/distribution question already flagged for
  `pyvar-local` (per `docs/roadmap-six-open-initiatives.md`'s
  cross-cutting finding): `engine/` is Apache-2.0 and fine to ship
  broadly; whether `api/routes/billing.py` (a Stripe-integrated
  commercial billing module) belongs in a publicly-distributed "full
  pyvar" image is a real product decision, not an engineering one — and
  a live concern here specifically, since this is the first proposal
  that would actually package that module for outside distribution.

## 4. Revised complexity assessment

Materially lower than originally estimated: this isn't "design and build
a multi-service Docker topology," it's "take the already-working,
already-proven `docker-compose.yml` and harden it for distribution" —
self-contained builds instead of bind mounts, safe baked-in defaults
instead of a developer's own `.env`, and dropping the external-network
assumption. The one item that isn't mechanical is §3's billing-module
question, which needs a decision before any of this ships, not after.

## 5. Not evaluated here (deliberately, per "explore, no action" scope)

- Multi-arch builds (arm64/amd64) for the resulting images.
- Publishing destination (Docker Hub vs. GHCR vs. the existing GitHub
  Release-asset pattern `pyvar-local` uses) — a distribution-channel
  decision, not an architecture one.
- CI/pipeline wiring for building and testing the compose stack —
  `pyvar-local`'s existing `local_package_stack.py` (manually-triggered,
  not on every push) is the obvious template to reuse, not something to
  design from scratch here.

## 6. Recommendation if this moves forward

Scope it as "pyvar Local, extended" (a sibling/successor to the existing
`pyvar-local/` package) rather than a brand-new product — it reuses the
repo's own proven `docker-compose.yml` topology and root `Dockerfile`,
and `docs/plan-pyvar-local-package-generation.md`'s existing publish
pipeline (manually-triggered CodePipeline → GitHub Release asset) is a
reasonable template for shipping a hardened `docker-compose.yml` + image
tags instead of a single tarball. The billing-module inclusion question
(§3) is the one item that needs a decision before any of this is built,
not after.
