# Plan: one-off `pyvar Local` package generation and sharing

**Item 2 of 6** in `docs/roadmap-six-open-initiatives.md`. Ranked low
complexity: the package and its publish pipeline already exist; this is
about running what's built, not building something new — with one scoping
call up front (below) that changes how much "new" is actually in play.

## 1. Scoping: what "one-off generation and sharing" actually means here

`docs/proposals/pyvar-local-package-proposal.docx` describes a full
**commercial product** — signed JWT-style license files, a regulatory
documentation bundle, an update/security-patch SLA, per-node/per-year
billing. Filippo's phrasing ("**one-off** pyvar local package generation
and sharing") reads as something narrower: build the artifact once, share
it with whoever needs it now — not stand up the full licensing/subscription
mechanism, which naturally belongs with item 5 (monetization
implementation) if/when there's an actual paying customer to gate it for.

**This plan treats it as the narrow scope** (build once, share once) and
flags the full commercial mechanism as a separate, later decision — say so
if that's wrong and the full product build is actually wanted now.

## 2. What's already built and verified against the repo

- **`pyvar-local/`** — a working package: `Dockerfile`, a minimal CLI
  (`pyvar_local/cli.py`) that reflects over the real `engine/` modules at
  runtime (can't drift out of sync with what `engine/` actually contains),
  and a README explaining scope, licensing note (correctly says
  Apache-2.0, already fixed), and build/publish instructions.
- **Deliberately out of scope for this first release** (per the package's
  own README, a real prior decision, not a gap to close now): a full local
  FastAPI server matching the hosted API's route surface. Only the engine +
  CLI ship. This is fine to leave as-is for a one-off share.
- **`pyvar-cdk/stacks/local_package_stack.py`** — a manually-triggered
  (`trigger_on_push=False`, no webhook/schedule) two-stage CodePipeline:
  Build+Test (docker build, pre-warm the Numba JIT cache, run
  `tests/test_engine.py` inside the built image as a release gate) then
  Publish. Wired into `pyvar-cdk/app.py` as a standalone stack
  (`pyvar-{env}-local-package`) — correctly *not* part of
  `PyvarDeployStage`'s auto-deploy graph, since it's meant to run on
  demand, not on every push (unlike the `TokenReportStack` bug fixed in
  `v0.2.0`, this one's absence from the pipeline's deploy stage is by
  design, confirmed by its own module docstring).
- **`scripts/publish_local_package_release.sh`** — publishes the built
  image tarball as a **GitHub Release asset**, not new AWS storage (a
  deliberate choice: avoids the us-east-1/eu-west-1 data-residency
  constraint `public_data_stack.py` already hit once). Uses its own tag
  namespace (`pyvar-local-v<version>-<short-sha>`, created as a
  prerelease), separate from the app version tags (`v0.1.0`, `v0.2.0`) —
  confirmed no collision: `v0.2.0`'s release currently has zero assets,
  which is expected and correct, not evidence of a problem.
- **The GitHub token this needs already exists** — `pyvar/github-token` in
  Secrets Manager, the same one `pipeline_stack.py`'s main pipeline uses.
  No new secret to provision.

## 3. What's not yet confirmed — needs Filippo or AWS access this session doesn't have

1. **Has `pyvar-{env}-local-package` ever actually been deployed** (a
   `cdk deploy` of this standalone stack)? Can't check from git — no AWS
   credentials in this session. If not deployed, that's step 1 below.
2. **Has the pipeline ever been triggered**, even once? The zero-assets
   finding above is consistent with "never triggered" but isn't proof by
   itself (a prerelease could have been deleted). Worth a direct look at
   the CodePipeline console, or I can re-check GitHub for any
   `pyvar-local-v*` tag once you've looked.
3. **Which environment** — `dev` or `prod`? The stack is parameterized by
   `cfg.env_name` like everything else; a one-off share probably wants the
   `prod`-configured build (real `requirements-heavy.txt`, not a dev
   shortcut), but confirm.
4. **Who is "sharing" for** — since the repo (and therefore the eventual
   GitHub Release) is already public, anyone can already find this once
   published. If this is for a specific prospect who hit the data-residency
   objection on the hosted tier (the proposal's own described early-customer
   path), a direct link works today once published; if you want it *not*
   publicly discoverable yet, that needs a different distribution
   mechanism than what's built (a public GitHub Release is, by definition,
   public).

## 4. Concrete next actions

**For Filippo / a delegated agent with real AWS credentials (not this
session):**
1. Confirm/deploy the stack: `cdk deploy pyvar-prod-local-package` (or
   `dev`, per the decision above) from `pyvar-cdk/`.
2. Trigger the pipeline once: AWS Console → CodePipeline →
   `pyvar-{env}-local-package` → "Release change", or
   `aws codepipeline start-pipeline-execution --name pyvar-{env}-local-package`.
3. Watch the Build+Test stage — it fails closed if `tests/test_engine.py`
   fails inside the built image, so a red pipeline here means a real
   problem worth looking at, not a flake to retry blindly.
4. Once green, the Publish stage's output is the `browser_download_url`
   logged by `publish_local_package_release.sh` — that's the artifact to
   share.

**For this session, once the above is confirmed working:**
- I can verify the resulting GitHub Release/asset exists and looks right
  (tag, asset name, size sanity-check) via the GitHub API, same as I did
  for the CHANGELOG/tag work earlier this session.
- If a written regulatory-documentation companion is wanted for whoever
  receives the share (not required for a bare "here's the Docker image"
  hand-off, but the proposal's own "what it sells" framing leans on it): a
  real head start already exists — `portal/functions.json` embeds a
  `[REGULATORY]` citation and a `caveat` field per function today (e.g.
  `alm_stress_test`'s description cites "BCBS d368" inline). Extracting and
  formatting that into a standalone bundle is a modest scripting task, not
  a research project from scratch — worth doing only if this one-off share
  actually needs it, not proactively.

## 5. Definition of done

- The build+publish pipeline has run at least once, successfully, with the
  test-suite gate passing inside the built image.
- A real download URL exists and has been verified (not just assumed from
  green CI).
- Whoever it's being shared with has actually received it, by whatever
  channel fits the "who" answered in §3.4.
- The full commercial licensing mechanism (signed license files, SLA,
  per-node billing) is explicitly deferred to item 5, not silently
  half-built here.
