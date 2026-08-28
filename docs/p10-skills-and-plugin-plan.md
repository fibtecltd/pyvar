# P10 — Claude Code Skills & pyvar MCP Plugin
## Exposing pyvar.com's domain expertise and API as installable Claude Code assets

**Version:** 1.1
**Date:** August 2026
**Status:** Planning — not yet implemented
**Prepared by:** Fibtec Limited (drafted with Claude Code)

---

## Sequencing — ahead of the P9 public launch

P10 is scheduled to land **before** the repo visibility flip (`fibtecltd/pyvar`
private → public), the remaining gating step of P9's own Day-0 launch actions. In
practice this means: a Claude Code session pointed at this repo while it's still
private already has the domain skills and the pyvar API directly available, so
there's no functional urgency from *that* angle — the reason to sequence P10 first
is that going public is effectively pyvar's public debut, and both the skills
package and the MCP plugin are part of the story worth having ready at that moment
rather than as a follow-up announced later. Concretely: this plan should reach a
usable v1 (both plugins installable, both linked from the portal) before the
visibility flip is scheduled, not after.

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

### B.2 Tool coverage — all 385 functions, individually, plus a generic first choice

Every function across all 8 domains still gets its own named MCP tool (`compute_var`,
`compute_credit_pd`, `compute_lcr`, etc.), generated from `portal/functions.json`
(the same catalogue the portal's own search/domain pages already read from) at build
time — one tool definition per catalogue entry, so a new function added to any domain
automatically gets an MCP tool on the next deploy with no manual wiring.

**Revised per explicit direction — the tool-selection-quality risk below is now
mitigated, not just watched.** Two generic tools are added and positioned as the
model's *first* choice, ahead of hunting through 385 named tools:

- **`list_pyvar_functions(domain?: str)`** — returns names, one-line descriptions, and
  parameter summaries from `functions.json`, optionally filtered to one domain. The
  discovery step: a model that doesn't already know pyvar's exact function names
  starts here.
- **`call_pyvar_function(domain: str, function_name: str, params: object)`** — the
  actual dispatcher. Looks up `function_name` in the same `functions.json` catalogue
  used to generate the 385 named tools, validates `params` against that entry's own
  schema *server-side* before forwarding the call, and returns a clear
  "expected params: ..., got: ..." error on a mismatch rather than a raw API 422 —
  so the looser `params: object` typing (unavoidable for a single generic tool
  covering 385 different parameter shapes) doesn't trade away good error feedback.

Both tool descriptions explicitly steer a calling model toward this pair as the
default entry point ("use this first; reach for a specific named tool like
`compute_var` only when you already know its exact parameters and want its more
detailed per-parameter schema up front"). The 385 named tools remain fully present
and functional — for a model that already knows exactly which function it wants,
a direct named call with a precise per-function schema is still available and often
preferable. This is additive, not a reduction in coverage: the generic pair exists
specifically to give the model a low-cardinality default path, with the full
385-tool surface still there for direct, specific use.

**Residual risk, now smaller:** whether models in practice actually prefer the
generic pair over browsing the full 385-tool list depends on how the tool
descriptions read to each specific client/model — worth watching in real usage,
same as before, but no longer an unmitigated risk with zero corrective action.

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
- `call_pyvar_function`/`list_pyvar_functions` specifically: a valid
  `(domain, function_name, params)` call dispatches correctly; an unknown
  `function_name` and a `params` mismatch against the catalogue's own schema both
  return the clear, actionable error (not a raw API 422) *without* ever reaching the
  live API; `list_pyvar_functions` with and without a `domain` filter returns the
  expected catalogue subset.
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

## This document stays a docs-only change

The original version of this plan (#288) was the first real-world test of the
CodePipeline Git push-filter trigger added in #282–#285 — confirmed working:
that merge started **zero** `pyvar-dev-pipeline` executions, verified directly
against CodePipeline's own API. This revision (v1.1, adding the sequencing note and
the `call_pyvar_function`/`list_pyvar_functions` mitigation) keeps the same property
deliberately: still touches nothing outside `docs/`, so it should skip an execution
too, same as the first version did.
