# P10 — Claude Code Skills & pyvar MCP Plugin
## Exposing pyvar.com's domain expertise and API as installable Claude Code assets

**Version:** 1.2
**Date:** August 2026
**Status:** Part A (skills plugins) implemented; Part B (MCP plugin) still planning
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
repository: 13 skills under `.claude/skills/*` (8 domain skills — alm, credit-risk,
derivatives, liquidity-risk, market-risk, operational-risk, portfolio-analytics,
regulatory — plus 5 architecture skills), and the pyvar REST API itself (385
functions across 8 domains). Neither is currently reachable by someone who isn't
working inside this repo's own Claude Code session.

This phase makes both installable directly into *any* user's own Claude Code setup:

1. **Skills plugins** — turns out this was already half-planned: `.claude-plugin/
   marketplace.json` was already committed at repo root, declaring 13 individual
   single-skill plugins (one per `.claude/skills/*` entry) at `plugins/<path>/` --
   the actual plugin directories just didn't exist yet. This phase builds them
   (§A), verified against Claude Code's real, documented plugin format rather than
   guessed.
2. **pyvar MCP plugin** — a new Claude Code plugin bundling an MCP server that wraps
   the live pyvar.com API, giving any Claude Code session direct tool access to all
   385 functions. Referenced from each domain page's existing API-reference section.

Both follow the same "never let a published fact drift from reality" principle that
motivated the recent homepage fixes (stale region/model strings, a demo runtime
figure that hid a real bug, a version badge that had drifted from the actual PyPI
release) -- concretely, via the same generate-and-CI-diff pattern this repo already
uses for `pyvar-client` (`pyvar-client/codegen/generate.py` +
`.github/workflows/pyvar-client-ci.yml`'s "Codegen drift check" job), not a new
deploy-time build mechanism invented for this phase specifically.

---

## Part A — Skills plugins  (IMPLEMENTED as of this revision)

### A.1 Format, verified not guessed

Before writing any files, the real Claude Code plugin/marketplace format was
confirmed against actual documentation (not invented): `.claude-plugin/plugin.json`
(only `name` is required; `version`, `description`, `author`, `mcpServers`,
`skills`, `userConfig` etc. are all real optional fields), a repo-root
`.claude-plugin/marketplace.json` (required `name`/`owner`/`plugins[]`, each entry a
`name` + a `source` -- a relative path for a same-repo plugin, or a full git
reference for an external one), and the *single-skill shorthand*: a plugin wrapping
exactly one skill can put `SKILL.md` straight at the plugin root instead of nesting
it under `skills/<name>/`.

### A.2 What already existed vs. what this phase built

`.claude-plugin/marketplace.json` was already committed at repo root (predates this
phase), declaring exactly 13 plugins -- one per `.claude/skills/*` skill -- each
with a `name` (matching that skill's own frontmatter `name`, e.g. `pyvar-market-risk`)
and a GitHub `source` pointing at `plugins/<path>` (e.g. `plugins/market-risk`,
`plugins/arch/api-gateway` for the 5 architecture skills, nested under `plugins/arch/`).
The `plugins/` directories themselves didn't exist yet -- this phase builds them,
matching the already-declared marketplace exactly rather than inventing a different
(single combined bundle) structure, which was this doc's own original, incorrect
first draft.

### A.3 Generator, not a deploy-time build step

`scripts/generate_plugins.py`: reads each `.claude/skills/*/SKILL.md` (source of
truth, unchanged), copies it to the matching `plugins/<path>/SKILL.md` (single-skill
shorthand -- no nested `skills/` dir), and writes `plugins/<path>/.claude-plugin/
plugin.json` (`name`+`version` from the skill's own frontmatter, `description` from
the already-committed `marketplace.json` entry, `author`/`homepage`/`repository`/
`license` fixed).

This is a **generate-and-commit** step, not a deploy-time artifact: a git-based
Claude Code plugin install (`/plugin marketplace add fibtecltd/pyvar`, then
`/plugin install pyvar-market-risk@pyvar-marketplace`, etc.) reads directly from
whatever's committed in the repo tree -- there is no server-side build/zip/S3 step
in that flow at all, unlike the portal's own `status.json`/`demo-result.json`
pattern. `.github/workflows/plugins-ci.yml` is the drift check: re-run the
generator, diff against what's committed, fail with the exact fix command if stale
-- the same shape as `pyvar-client-ci.yml`'s existing "Codegen drift check" job, and
(like that job) informational rather than one of the branch ruleset's required
status checks.

### A.4 Portal & distribution

No zip download after all -- `/plugin marketplace add fibtecltd/pyvar` (once the
repo goes public) is the real, standard, already-working install path once
`plugins/` exists, and a portal page's job is simply to *tell* a visitor that
command plus which of the 13 plugin names to install, not to serve a file. A new
`portal/skills.html`, matching the shared-header/footer/palette pattern of the other
9 pages, lists the 13 plugins with their descriptions (already written, in
`marketplace.json`) and the exact install commands -- still open per §B.6 below
whether this is its own page or folded together with the MCP plugin's page.

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

### B.4 Authentication — plugin.json's real `userConfig` mechanism

Verified, not guessed (§A.1): `plugin.json` supports a `userConfig` block that
Claude Code itself prompts the user for at install time (typed fields --
`string`/`number`/`boolean`/`file`/`directory`, a `sensitive: true` flag that masks
password-style input, `required: true`). This plugin declares one:

```json
"userConfig": {
  "pyvar_api_key": {
    "type": "string",
    "title": "pyvar API key",
    "description": "Free-tier key from https://www.pyvar.com#get-api-key",
    "sensitive": true,
    "required": true
  }
}
```

and the bundled MCP server's own config references it directly:
`"env": {"PYVAR_API_KEY": "${user_config.pyvar_api_key}"}`. The user obtains the
key through the portal's existing "Get API key" flow (`portal/index.html`'s
`#get-api-key` section, `api/routes/auth.py`) — no new auth mechanism on the API
side, no bundled/shared key, and no manual "go edit a config file" step on the
plugin side either, since `userConfig` is a real interactive install-time prompt.
A 403 (tier cap exceeded) from the API surfaces back through the tool call as a
plain error a model can read and relay, not a silent failure.

### B.5 Packaging & build

Same real plugin structure as the skills plugins (§A.1), added as a 14th entry in
the already-existing `.claude-plugin/marketplace.json` (`source: "./plugins/mcp"`
or similar). Its `mcpServers` block (either inline in `plugin.json` or a sibling
`.mcp.json`) points at the bundled server's entry point via `${CLAUDE_PLUGIN_ROOT}`.
Tool definitions generated from `portal/functions.json` follow the exact same
generate-and-commit-and-CI-diff pattern as §A.3 (extending `scripts/
generate_plugins.py` or a sibling script, and `.github/workflows/plugins-ci.yml`'s
drift check) — not a deploy-time S3 artifact, for the same reason: a git-based
plugin install reads the committed tree directly.

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

- ~~`pyvar-cdk/stacks/pipeline_stack.py`: two new hash-gated build steps in the
  shared Synth ShellStep (skills zip, MCP plugin zip), each keyed on its own
  relevant-path set, each a no-op when nothing relevant changed — same shape as
  the existing image-build and migration-skip gates.~~ Not needed, see §A.3/§B.5:
  no CDK/pipeline changes at all turned out to be required for either plugin (a
  git-based plugin install reads the committed tree directly -- there's no
  deploy-time build step in that flow to hook into). Struck through rather than
  deleted so a future reader can see the design actually changed, not just
  vanished.
- ~~`pyvar-cdk/stacks/public_data_stack.py`: no changes expected — reuses the
  existing public S3 bucket, just two new fixed keys.~~ Not needed -- no S3
  artifact, see §A.3/§B.5.
- New MCP server source: **resolved** (was open question #1) — `plugins/mcp/`
  in `fibtecltd/pyvar` itself, matching how the skills plugins turned out to
  already be scaffolded in this same repo (`.claude-plugin/marketplace.json`,
  predating this phase) rather than a separate one.
- Actual new infra: `.github/workflows/plugins-ci.yml` (drift-check CI job,
  implemented in §A.3) and `scripts/generate_plugins.py` (the generator).

---

## Testing plan

- Skills plugins: `.github/workflows/plugins-ci.yml`'s drift-check job IS the test
  (regenerate, diff against committed, fail with the fix command if stale) --
  implemented, not just planned. Still open: an actual smoke-install into a scratch
  Claude Code config to confirm `/plugin marketplace add` + `/plugin install`
  genuinely works end-to-end, which needs a real Claude Code session outside this
  sandbox to verify.
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

1. ~~**MCP server source location.**~~ **Resolved**: `plugins/mcp/` in
   `fibtecltd/pyvar` itself — the skills plugins turned out to already be scaffolded
   in this same repo (a pre-existing `.claude-plugin/marketplace.json`), so the MCP
   plugin follows the same convention rather than a separate repository.
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

## Revision history note — this one is NOT a docs-only change, and surfaces a gap

The first two versions of this plan (#288, #289) were pure `docs/` changes,
confirming the CodePipeline Git push-filter trigger (#282–#285) correctly starts
**zero** `pyvar-dev-pipeline` executions for a docs-only push. This revision (v1.2)
ships alongside the actual Part A implementation (`scripts/generate_plugins.py`,
`.github/workflows/plugins-ci.yml`, and the 13 `plugins/*` directories) in the same
commit, since the doc text and the code it describes need to land together to stay
accurate.

Worth flagging rather than quietly working around: `scripts/` and `.github/` are
both already in the trigger's 8-entry exclude list, but the new top-level `plugins/`
directory is in neither that exclude list nor `_PORTAL_RELEVANT_PATHS` (the
in-execution skip gates' allowlist) -- exactly the "a 9th non-portal top-level
directory shows up" scenario `pipeline_stack.py`'s own comments warned about when
the exclude list was built (PR #284), and the exclude list is already at its
AWS-imposed 8-entry cap, so adding `plugins` there means deliberately dropping one
of the current 8. Net effect on this specific push: the trigger starts a real
execution (falls back to the safe direction -- an unrecognized path is treated as
relevant, not silently skipped), and then the in-execution image-build gate
correctly no-ops the rebuild anyway since `plugins/` isn't portal-relevant either --
so nothing wrong happens, just one wasted-but-harmless execution, the same shape of
waste the whole trigger effort was meant to eliminate. Not fixed in this PR
(changing the trigger's exclude list is its own decision, not bundled into a
feature PR) -- flagged here for a deliberate follow-up call instead.
