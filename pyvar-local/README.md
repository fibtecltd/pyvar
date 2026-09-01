# pyvar Local

An offline, no-API-key build of the pyvar compute engine — for institutions
whose data-governance policy doesn't permit sending position/portfolio data
to any third-party API, even a stateless one. See
[`docs/proposals/pyvar-local-package-proposal.docx`](../docs/proposals/pyvar-local-package-proposal.docx)
for the full rationale and business model, and
[`docs/p11-pre-launch-hardening.md`](../docs/p11-pre-launch-hardening.md) §2
for how this image is actually built and published.

## What's in this image

- `engine/` — the exact same compute engine that powers the hosted
  `pyvar.com` API. Generated/packaged from the same source on every release,
  never a manually-maintained fork.
- `tests/test_engine.py` — the same numerical-property test suite that gates
  every change to the hosted platform, shipped (not just referenced) so you
  can run it yourself:
  `docker run --rm --entrypoint pytest pyvar-local /app/tests/test_engine.py -v`
- A minimal CLI (`pyvar_local/cli.py`) — every public engine function is
  reachable by reflecting over the actual `engine/` modules at runtime, so
  it can't drift out of sync with what `engine/` actually contains.

```
$ docker run --rm pyvar-local list | head -3
alm_behavioural.behavioural_modelling_nmds(...)
alm_behavioural.core_deposit_duration(...)
alm_behavioural.loan_prepayment_rate_cpr(...)

$ docker run --rm pyvar-local call montecarlo run_monte_carlo_var \
    --params '{"returns": [0.001, -0.002, ...], "portfolio_value": 1000000, "n_simulations": 1000, "seed": 1}'
```

## What's deliberately NOT in this image (yet)

This first release is scoped to the engine and a CLI — not a full local
FastAPI server matching the hosted API's route surface (auth, per-function
REST endpoints, request/response schema validation). That's a real,
larger piece of work tracked as a fast-follow, not built here — see the
"what ships in the package" section of the local-package proposal document
for the originally-envisioned fuller scope.

## Licensing note

The code in this image is the same Apache-2.0-licensed `engine/` published in this
repository — nothing about running it locally requires a purchase. What a
`pyvar Local` subscription is proposed to actually cover (see the
monetization strategy document) is the signed/tested release itself, a
regulatory documentation bundle, update delivery, and support — not access
to code that's already public.

## Building and publishing

Not meant to be run by hand in normal operation — see
`pyvar-cdk/stacks/local_package_stack.py` for the manually-triggered
CodePipeline that builds and publishes this as a GitHub Release asset.
To build locally for testing:

```
docker build -f pyvar-local/Dockerfile -t pyvar-local:dev .
docker run --rm pyvar-local:dev list
docker run --rm --entrypoint pytest pyvar-local:dev /app/tests/test_engine.py -v
```
