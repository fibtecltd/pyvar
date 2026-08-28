# P10 — Claude Code Skills & pyvar MCP Plugin
## Exposing pyvar.com's domain expertise and API as installable Claude Code assets

**Version:** 1.0
**Date:** August 2026
**Status:** Planning — not yet implemented
**Prepared by:** Fibtec Limited (drafted with Claude Code)

---

## Executive Summary

pyvar.com already ships two Claude Code-native assets that live only inside this
repository: 12 domain skills under `.claude/skills/*` (alm, credit-risk, derivatives,
liquidity-risk, market-risk, operational-risk, portfolio-analytics, regulatory, plus
4 architecture skills), and the pyvar REST API itself (385 functions across 8 domains).
Neither is currently reachable by someone who isn't working inside this repo's own
Claude Code session.

This phase makes both installable directly into *any* user's own Claude Code setup,
downloadable from the portal:

1. **Skills package** — the 12 domain skills, packaged as a proper Claude Code plugin
   (not a bare zip) and available from a new portal page.
2. **pyvar MCP plugin** — a new Claude Code plugin bundling an MCP server that wraps
   the live pyvar.com API, giving any Claude Code session direct tool access to all
   385 functions. Distributed the same way, and referenced from each domain page's
   existing API-reference section.

Both are built fresh from the actual repository content at deploy time — the same
"never let a published fact drift from reality" principle that motivated the recent
homepage fixes (stale region/model strings, a demo runtime figure that hid a real bug,
a version badge that had drifted from the actual PyPI release).

---

## Part A — Skills package

### A.1 What ships

All 12 directories under `.claude/skills/*`, as they exist in the repo at build time —
no hand-curation, no separate copy to keep in sync. This mirrors this project's own
"drift is a bug" lesson: a maintained *copy* of the skills, refreshed by hand, is
exactly the failure mode that produced the stale version badge and the 4x-stale demo
runtime figure fixed in the last two PRs.

### A.2 Packaging — proper Claude Code plugin, not a bare zip

Structured as an installable Claude Code plugin:

```
pyvar-skills-plugin/
├── .claude-plugin/
│   └── plugin.json          # name, version, description
├── skills/
│   ├── alm/
│   ├── arch-api-gateway/
│   ├── arch-compute/
│   ├── arch-data-ingestion/
│   ├── arch-observability/
│   ├── arch-storage/
│   ├── credit-risk/
│   ├── derivatives/
│   ├── liquidity-risk/
│   ├── market-risk/
│   ├── operational-risk/
│   ├── portfolio-analytics/
│   └── regulatory/
└── README.md
```

`plugin.json`'s `version` field is set at build time from the same git short-SHA
convention the pipeline already uses for image tags (`pipeline_stack.py`'s
`SHORT_SHA`), so a downloaded package is traceable to the exact commit it came from.

A marketplace-style `marketplace.json` (or equivalent) is added alongside it so the
package installs via Claude Code's own `/plugin` flow, not a manual unzip into
`.claude/skills/`.

### A.3 Build & publish — fresh at deploy time

New step in the existing CDK Synth ShellStep (`pyvar-cdk/stacks/pipeline_stack.py`),
gated by the same portal-relevance path check already used for the image-build and
migration-skip gates (`_PORTAL_RELEVANT_PATHS`-style hashing), but keyed specifically
on `.claude/skills/**`:

1. Hash `.claude/skills/**`. If unchanged since the last recorded build, skip (same
   no-op-on-irrelevant-push philosophy as the existing gates).
2. If changed: zip `.claude/skills/*` into the plugin structure above, upload to the
   public S3 bucket (`pyvar-cdk/stacks/public_data_stack.py`'s existing bucket — same
   one `status.json`/`demo-result.json` already live in) at a fixed key, e.g.
   `public/pyvar-skills-plugin.zip`.
3. Record the new hash in SSM (same pattern as `/pyvar/pipeline/last-image-relevant-hash`).

No new Lambda needed — this is a deploy-time artifact, not a periodically-refreshed
one (skills change on commit, not on a clock), so it belongs in the pipeline's own
Synth step, not `public_data_publisher`.

### A.4 Portal placement

New page, `portal/skills.html`, following the exact same shared-header/footer/palette
pattern as the other 9 portal pages (`buildNav`/`buildFooter`, `pyvar.css` variables).
Lists all 12 skills with their one-line descriptions (pulled from each skill's own
frontmatter at build time, not hand-copied), and a single "Download skills plugin"
button pointing at the S3 key above.

---

## Part B — pyvar MCP plugin

### B.1 Architecture — thin API wrapper

The MCP server does **not** vendor `engine/` locally. Each tool call is a real HTTPS
round-trip to `https://www.pyvar.com/api/v1/{domain}/compute` using the same async
job pattern (`POST` → `task_id` → poll `GET .../result/{task_id}`) every other pyvar
client already uses — the MCP server is functionally a third implementation of the
same client pattern `pyvar-client` (the PyPI package) already implements in Python.

Rejected: vendoring the engine directly into the plugin. It would need `numpy`/`numba`
as plugin dependencies (heavy install, `numba`'s first-call JIT compilation cost paid
*inside a Claude Code session* rather than on a warm ECS worker), and — more
importantly — its compute logic would silently drift from what's actually deployed at
pyvar.com the moment either one changes without the other, the exact class of bug this
whole phase is trying to move away from, not toward.

### B.2 Tool coverage — all 385 functions, individually

Every function across all 8 domains gets its own named MCP tool (`compute_var`,
`compute_credit_pd`, `compute_lcr`, etc.) rather than a curated subset behind a
generic dispatcher. Generated from `portal/functions.json` (the same catalogue the
portal's own search/domain pages already read from) at build time — one tool
definition per catalogue entry, so a new function added to any domain automatically
gets an MCP tool on the next deploy with no manual wiring.

**Known risk, accepted deliberately, worth monitoring in practice:** a 385-tool
surface is large enough that some MCP clients/models may show degraded tool-selection
quality compared to a curated subset. No corrective action is planned pre-emptively —
this is a "watch real usage, revisit if it's actually a problem" risk, not a blocker.

### B.3 Async handling

Given the API's own submit/poll shape, the MCP server itself owns the polling loop
(mirroring `lambda/public_data_publisher/handler.py`'s own poll pattern, and
`pyvar-client`'s Python SDK) — a tool call blocks until the job resolves (success,
failure, or a bounded timeout) rather than exposing raw `task_id`/poll semantics as
separate tools. A model calling `compute_var(...)` gets a result back directly,
without needing to understand pyvar's async job pattern itself.

### B.4 Authentication

`PYVAR_API_KEY` environment variable, set in the plugin's MCP server config at
install time. The user obtains a free-tier key through the portal's existing
"Get API key" flow (`portal/index.html`'s `#get-api-key` section, `api/routes/auth.py`)
— no new auth mechanism, no bundled/shared key. A 403 (tier cap exceeded) from the
API surfaces back through the tool call as a plain error a model can read and relay,
not a silent failure.

### B.5 Packaging & build

Same proper-plugin structure as the skills package (Part A.2), same
`.claude-plugin/plugin.json` + marketplace-manifest pattern, same "built fresh at
deploy time" rule — except this time gated on changes to `portal/functions.json`
(the tool-generation source) or the MCP server's own source, not `.claude/skills/**`.
Published to the same public bucket, e.g. `public/pyvar-mcp-plugin.zip`.

### B.6 Portal & docs placement

- New page, `portal/plugin.html` (or folded into `portal/skills.html` as a second
  section on one combined "Claude Code" page — open question, see below) — the
  primary download/install entry point, mirroring `skills.html`'s structure.
- A short "Use this domain via Claude Code" callout added to each of the 8
  `domain-*.html` pages' existing API-reference section (near the current
  POST/GET endpoint-example block), naming the specific MCP tools that domain
  exposes and linking to the plugin page. Touches all 8 domain pages — a small,
  mechanical addition per page, not a redesign.

---

## Build/pipeline changes summary

- `pyvar-cdk/stacks/pipeline_stack.py`: two new hash-gated build steps in the shared
  Synth ShellStep (skills zip, MCP plugin zip), each keyed on its own relevant-path
  set, each a no-op when nothing relevant changed — same shape as the existing
  image-build and migration-skip gates, not a new mechanism.
- `pyvar-cdk/stacks/public_data_stack.py`: no changes expected — reuses the existing
  public S3 bucket, just two new fixed keys.
- New MCP server source: location TBD (see open questions) — most likely a new
  top-level directory in this repo (e.g. `mcp-server/`), matching how `pyvar-client/`
  already lives alongside the main API rather than in a separate repo.

---

## Testing plan

- Skills plugin: verify the built zip's `plugin.json` version matches the deploying
  commit's short SHA; verify all 12 skill directories are present and non-empty;
  smoke-install into a scratch Claude Code config and confirm skills load.
- MCP plugin: unit tests generating tool definitions from a fixture
  `functions.json` (no live API calls, mirroring this repo's existing
  never-hit-a-real-backing-service test philosophy); a small number of
  integration-style tests against a mocked pyvar API confirming the submit→poll→
  result flow and 403/timeout error surfacing.
- Both: the existing `_PORTAL_RELEVANT_PATHS`-style hash gates get their own test
  coverage for the no-op-on-irrelevant-push path, matching how the image-build gate
  is already tested.

---

## Open questions — before implementation starts

1. **MCP server source location.** New top-level directory in `fibtecltd/pyvar`
   (matching `pyvar-client/`'s precedent), or a separate repository? This session's
   GitHub access is scoped to `fibtecltd/claude-docker`, `fibtecltd/pyvar`, and
   `fibtecltd/.github` — a new separate repo would need to be created and added to
   that scope first.
2. **One combined "Claude Code" portal page vs. two separate pages** (`skills.html` +
   `plugin.html`). Two pages match the existing one-topic-per-page portal convention;
   one page keeps everything Claude-Code-related in a single, more discoverable place.
3. **MCP server implementation language/framework** — Python (consistent with the
   rest of this codebase, could reuse `pyvar-client`'s own HTTP client code directly)
   vs. TypeScript (the more common ecosystem default for MCP servers). Reusing
   `pyvar-client` argues for Python; broader MCP tooling/ecosystem familiarity argues
   for TypeScript.
4. **Marketplace listing** — does `fibtecltd` want its own Claude Code plugin
   marketplace/registry entry for discoverability, or is direct
   git-repo/zip-based installation sufficient for a first version?
5. **Rate limits at scale** — if the MCP plugin sees real adoption, free-tier API key
   usage from many simultaneous Claude Code sessions is a new usage pattern the
   existing tier system (`api/middleware/rate_limit.py`) wasn't originally sized
   around. Not a blocker for a first version, but worth a deliberate look before any
   broad promotion of the plugin.

---

## Why this document exists as a docs-only change

This plan intentionally touches nothing outside `docs/` — no code, no portal files,
no CDK. That makes this commit the first real-world test of the CodePipeline Git
push-filter trigger added in #282–#285: `docs/` is one of the 8 paths explicitly
excluded from the trigger's file-path filter (`pyvar-cdk/stacks/pipeline_stack.py`),
so this push should start **no** pipeline execution at all, rather than the
"starts a full execution, then the in-execution gates skip the actual work" behavior
every push got before that feature existed.
