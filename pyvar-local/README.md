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

## Getting the image (GitHub Release download)

If you received this as a `pyvar-local.tar.gz` from a GitHub Release
(`pyvar-local-v0-<short-sha>` — see `pyvar-cdk/stacks/local_package_stack.py`'s
Publish stage), it's a `docker save | gzip` of the built image, not something
`docker run` can use directly. Load it first:

```
$ docker load -i pyvar-local.tar.gz
Loaded image: pyvar-local:<full-sha>

$ docker run --rm pyvar-local:<full-sha> list | head -3
```

`docker load` prints the exact tag it loaded — use that tag (not a bare
`pyvar-local` with no tag) for every command below. Optionally re-tag it to
something shorter first: `docker tag pyvar-local:<full-sha> pyvar-local:local`.

## Running it as another user, or on a read-only filesystem

The image runs as root, and the engine's compiled-code cache (Numba's) is baked into `/app`. Run as any other user
(`--user ...`, Kubernetes `runAsNonRoot`) or with `--read-only`, and every call that compiles code fails with
`RuntimeError: cannot cache function ... no locator available` — even `list` and the tests — because the cache needs
a directory the process can write to. Give it one:

```
# non-root: any writable home
docker run --rm --user 1000:1000 -e HOME=/tmp pyvar-local:<full-sha> list

# read-only filesystem (root or not): a tmpfs for the cache
docker run --rm --read-only --tmpfs /tmp -e NUMBA_CACHE_DIR=/tmp/numba pyvar-local:<full-sha> list
docker run --rm --read-only --user 1000:1000 --tmpfs /tmp -e NUMBA_CACHE_DIR=/tmp/numba pyvar-local:<full-sha> list
```

The results are identical to the root run (the seeded Monte Carlo call gives the same numbers), but the baked cache is
not used, so the first call in each container compiles. Found and checked by `scripts/validate_pyvar_local_release.sh`
(workflow "pyvar Local release validate"), which tries all of these on the published release. Making the image work
as a non-root user by default is a change to `pyvar-local/Dockerfile` and a rebuild: not done yet.

The image is `linux/amd64` only. On an ARM machine (Apple Silicon, Graviton) add `--platform linux/amd64` to every
`docker run`; it then runs under emulation, which has not been tested.

## Checking a published release

`bash scripts/validate_pyvar_local_release.sh [pyvar-local-v0-<sha>]` downloads the release asset, checks its size and
sha256 against GitHub's own digest, loads it, and runs the default command, the engine tests, a seeded VaR call twice
(the output must be byte-identical) and the runs above. Needs Docker, curl and python3. The same script runs in GitHub
Actions as "pyvar Local release validate" (Run workflow; leave the tag empty for the newest release). Run it after
every rebuild.

## What's deliberately NOT in this image (yet)

This image is scoped to the engine and a CLI — not a full local
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
