# pyvar Local: the compute engine, offline, no API key required

*A GitHub Release, not a SaaS signup — for institutions whose data-governance policy won't let position or portfolio data leave the building, even to a stateless API.*

> **Draft status:** not yet published. Every fact below — the release tag, the build date, the asset size, the CLI output shape — is verified against the actual `fibtecltd/pyvar` GitHub Release and repo source at drafting time. See **Sources** at the end.

---

pyvar.com's regulatory-grade risk functions — VaR, Expected Shortfall, credit PD/LGD/EAD, liquidity ratios, operational risk, the rest of the eight domains — are built to be called over a REST API. That's the right shape for most users. It's the wrong shape for a specific, real category of institution: one whose data-governance policy simply doesn't permit sending position or portfolio data to *any* third-party endpoint, stateless or not, encrypted or not. For that case, the answer isn't "trust us, nothing is logged" — it's "don't send it anywhere."

**pyvar Local** is that answer: the exact same compute engine that powers the hosted API, packaged as a Docker image you run entirely on your own infrastructure, with no network call to pyvar.com required to get a result.

## What's actually in the box

Three things, deliberately:

1. **`engine/`** — the same compute engine that runs the hosted `pyvar.com` API. Not a fork, not a re-implementation kept loosely in sync by hand — packaged from the same source on every release, so it can't drift.
2. **The real test suite, shipped, not just referenced.** `tests/test_engine.py` — the same numerical-property tests (VaR > 0, CVaR ≥ VaR, 99% VaR > 95% VaR, determinism under a fixed seed) that gate every change to the hosted platform — is inside the image, runnable by anyone who receives it:

   ```
   docker run --rm --entrypoint pytest pyvar-local /app/tests/test_engine.py -v
   ```

   That's a genuine "don't take our word for it" mechanism, not a marketing claim. If you don't trust that the engine does what it says, you can verify it yourself, offline, without asking us for anything.

3. **A minimal CLI** (`pyvar_local/cli.py`) that reflects over the actual `engine/` modules at runtime — every function `engine/` exposes is automatically reachable through the CLI, which means the CLI's function list can't silently fall behind what the engine actually contains. There's no manually-maintained registry to forget to update.

```
$ docker run --rm pyvar-local list | head -3
alm_behavioural.behavioural_modelling_nmds(...)
alm_behavioural.core_deposit_duration(...)
alm_behavioural.loan_prepayment_rate_cpr(...)

$ docker run --rm pyvar-local call montecarlo run_monte_carlo_var \
    --params '{"returns": [0.001, -0.002, ...], "portfolio_value": 1000000, "n_simulations": 1000, "seed": 1}'
```

## What's deliberately *not* in the box yet

Worth being direct about scope, since half of what makes a release trustworthy is saying plainly what it doesn't do. This first release does not include a local FastAPI server matching the hosted API's full route surface — no auth layer, no per-function REST endpoints, no request/response schema validation server-side. That's real, larger work, tracked as a fast-follow rather than shipped here. If your workflow needs an HTTP interface rather than a CLI, this release isn't there yet — the CLI is the whole interface today.

## Getting it

This isn't a `docker pull` from a registry — it's a GitHub Release asset, a `docker save | gzip` of the built image:

- **Tag:** `pyvar-local-v0-6682472c`
- **Built:** 2026-09-12
- **Asset:** `pyvar-local.tar.gz`, ~555 MB
- **Download:** [github.com/fibtecltd/pyvar/releases/tag/pyvar-local-v0-6682472c](https://github.com/fibtecltd/pyvar/releases/tag/pyvar-local-v0-6682472c)

```
$ docker load -i pyvar-local.tar.gz
Loaded image: pyvar-local:<full-sha>

$ docker run --rm pyvar-local:<full-sha> list | head -3
```

`docker load` prints the exact tag it loaded — use that tag (not a bare `pyvar-local` with no tag) for every command after. Worth re-tagging to something shorter first: `docker tag pyvar-local:<sha> pyvar-local:local`.

It uses its own tag namespace (`pyvar-local-v<version>-<short-sha>`), separate from the application's own version tags (`v0.1.0`, `v0.2.0`), and ships as a *prerelease* — a deliberate signal that this is a first cut of a distribution mechanism, not a promise of API/CLI stability yet.

## Why a tarball, not a container registry

The build pipeline behind this (`pyvar-cdk/stacks/local_package_stack.py`) is a manually-triggered, two-stage CodePipeline — Build+Test (docker build, pre-warm the Numba JIT cache into the image layer, run `tests/test_engine.py` inside the *built* image as a release gate, not just the source) then Publish. It's wired into the CDK app as a standalone stack, deliberately *not* part of the auto-deploying pipeline that ships every push to the hosted API — this only runs when someone actually triggers it.

Publishing as a GitHub Release asset rather than pushing to a container registry in AWS was a deliberate choice: it avoids a data-residency constraint the project had already hit once elsewhere in its infrastructure (a public-data stack that needed to stay in a specific AWS region), and a GitHub Release requires no new AWS storage or new IAM surface at all — the GitHub token this needs already existed for the main pipeline.

## The licensing point, stated plainly

The code in this image is the same Apache-2.0-licensed `engine/` already published in the main repository. Nothing about running it locally requires a purchase — you could build this exact image yourself from the public source. What a commercial `pyvar Local` offering would actually be selling, if and when one exists, is the *signed, tested release itself*, a regulatory documentation bundle, update delivery, and support — not access to code that's already public. This release is the "build once, share once" slice of that idea, not the commercial product.

## Try it

```bash
docker load -i pyvar-local.tar.gz
docker run --rm pyvar-local:<loaded-tag> list
docker run --rm --entrypoint pytest pyvar-local:<loaded-tag> /app/tests/test_engine.py -v
```

No API key. No network call. No account. Just the engine, verifiable by running its own test suite yourself.

---

## Sources

- [GitHub Release `pyvar-local-v0-6682472c`](https://github.com/fibtecltd/pyvar/releases/tag/pyvar-local-v0-6682472c) — the actual published asset this article describes.
- [`pyvar-local/README.md`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-local/README.md) — scope, usage, and licensing note, verified verbatim against the current repo.
- [`pyvar-local/Dockerfile`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-local/Dockerfile) — build steps, JIT pre-warm, base image.
- [`pyvar-cdk/stacks/local_package_stack.py`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-cdk/stacks/local_package_stack.py) — the manually-triggered build/publish pipeline.
- [`portal/local.html`](https://github.com/fibtecltd/pyvar/blob/master/portal/local.html) — the live download page on pyvar.com, source of the exact tag/date/size figures used here.
- [`docs/plan-pyvar-local-package-generation.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/plan-pyvar-local-package-generation.md) — the full build/verification history behind this release.
