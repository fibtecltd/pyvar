# P10 — Claude Code Skills & pyvar MCP Plugin
## Exposing pyvar.com's domain expertise and API as installable Claude Code assets

**Version:** 1.4
**Date:** August 2026
**Status:** Part A (skills plugins) and Part B (MCP server + tools, incl. §B.6
portal placement) implemented. P10 is complete.
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
command plus which of the 14 plugin names to install, not to serve a file.
**Implemented as `portal/plugins.html`** (see §B.6) rather than a separate
`skills.html`: one combined page, matching the shared-header/footer/palette
pattern of the other 9 pages, listing all 13 skills plus the MCP server with
their descriptions (copied verbatim from `marketplace.json`) and the exact
install commands.

---

## Part B — pyvar MCP plugin  (IMPLEMENTED as of this revision, incl. §B.6)

### B.1 Architecture — thin API wrapper

The MCP server does **not** vendor `engine/` locally. Each tool call is a real HTTPS
`POST {path}` to the API, where `path` is the function's own catalogued endpoint
(e.g. `/api/v1/alm/alm_stress_test`) — see §B.3 below for why this is a plain
request/response, not the submit/poll shape originally assumed here.

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

### B.3 Async handling — turned out to be unnecessary; a real homepage bug found along the way

This section originally assumed the API's async submit/poll shape (`task_id` +
polling) applied to all 385 functions, matching what `portal/index.html`'s own API
section claims: *"All 385 functions use the same async job pattern: POST to submit,
GET to poll."* That claim is **false**, confirmed by reading the actual route code,
not assumed from the homepage's own text (the same "verify, don't trust a published
claim" discipline behind the recent version-badge and demo-runtime fixes):
`grep`-ing every file under `api/routes/*.py` for the async job markers
(`apply_async`, `task_id`) turns up exactly one hit — `api/routes/var.py`
(`POST /api/v1/var/compute` → `task_id` → poll `GET /api/v1/var/result/{task_id}`,
Celery-backed, reserved for the one heavy Monte Carlo path per `scripts/gen_p3.py`'s
own design docstring). Every other route (`api/routes/alm.py` and the other 6
domain route files) is a plain synchronous `POST` returning a JSON dict directly —
confirmed by reading the generated route bodies themselves, not inferred. `var.py`'s
async endpoint isn't even one of the 385 catalogued `functions.json` entries (its
domain there is `market-risk`, and none of that domain's 68 catalogued functions are
`/api/v1/var/compute` — they're all separate, already-synchronous VaR-adjacent
functions like `historical_simulation_var`).

Net effect: **no polling logic exists in the MCP server at all** — every one of the
385 generated tools, plus `call_pyvar_function`, is a single synchronous
POST-and-return. Simpler and more correct than the original plan, and a real,
separate finding worth fixing on the homepage itself (not done as part of this
plugin work — flagged, not silently patched, same as this whole project's other
mid-task discoveries).

**Also worth recording:** initial research into the Python `mcp` SDK's API for a
large, programmatically-generated tool set (asked of a research agent, not written
from memory) came back claiming the SDK's low-level `Server` class -- exactly the
API a ~385-tool dynamic catalogue needs -- had been "removed" in the current major
version. That claim didn't match this project's own prior confidence about MCP's
SDK design, so it was checked directly against the actually-installed `mcp` package
(`pip install mcp`, then introspecting `mcp.server.lowlevel.Server`'s real
constructor and `mcp.types.Tool`/`CallToolResult`/etc. field names) rather than
trusted or dismissed on priors alone -- the claim was wrong: `Server(name,
on_list_tools=..., on_call_tool=...)` is real, current, and exactly the shape used
in `plugins/mcp/pyvar_mcp/main.py`. Recorded here because a second source turning
out to be confidently wrong on something this foundational is worth knowing, not
because the mistake mattered once caught.

### B.3a Implementation

`plugins/mcp/` is a real installable Python package (`pyvar_mcp`), structured
exactly like `pyvar-client/` (its own `pyproject.toml`, `[project.scripts] pyvar-mcp
= "pyvar_mcp.main:main"`, `tests/`, `.gitignore`) rather than a bare script:

- `pyvar_mcp/client.py` — the thin HTTP client (stdlib `urllib`, matching
  `pyvar-cdk/lambda/*/handler.py`'s own no-extra-HTTP-stack convention).
- `pyvar_mcp/catalogue.py` — lookup helpers (`by_tool_name`, `by_domain_and_function`,
  `in_domain`) over the generated function list.
- `pyvar_mcp/_generated/functions.py` — generated by `scripts/generate_mcp_tools.py`
  from `portal/functions.json`, same generate-and-commit-and-CI-diff pattern as the
  skills plugins (§A.3) and `pyvar-client`'s own codegen.
- `pyvar_mcp/main.py` — `mcp.server.lowlevel.Server` wiring: one `on_list_tools`
  handler building all 387 `Tool` objects (385 named + the 2 generic), one
  `on_call_tool` handler dispatching all three call shapes (a named tool,
  `call_pyvar_function`'s explicit domain+function_name, `list_pyvar_functions`) to
  the same underlying `_invoke()`. Errors (unknown tool, missing required param, a
  4xx/5xx from the API) come back as `CallToolResult(is_error=True, ...)` -- a
  normal tool result the model can read, never a raised exception.

22 tests (`plugins/mcp/tests/`), 96% coverage on `pyvar_mcp` (the uncovered lines are
the stdio entry point itself, `main()`/`_amain()`, which needs a real subprocess to
exercise meaningfully) -- no live network calls, `urllib.request.urlopen` mocked
throughout.

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

Added as the 14th entry in the already-existing `.claude-plugin/marketplace.json`
(`source: "./plugins/mcp"`). `plugin.json`'s `mcpServers` block runs the installed
console script directly (`"command": "pyvar-mcp"`) rather than pointing at a
`${CLAUDE_PLUGIN_ROOT}`-relative script path -- simpler once the package is
actually installed, at the cost of one real, currently-manual step (below).
`pyvar_mcp/_generated/functions.py` follows the exact same generate-and-commit-
and-CI-diff pattern as §A.3, via a second job (`.github/workflows/plugins-ci.yml`'s
`plugins-drift-check`, extended, plus a new `pyvar-mcp-tests` job running this
package's own lint+test suite) -- not a deploy-time S3 artifact, for the same
reason as the skills plugins: a git-based plugin install reads the committed tree
directly.

**One real, currently-manual step, documented rather than glossed over**
(`plugins/mcp/README.md`): `/plugin install` doesn't itself run `pip install` for a
bundled Python package's dependencies (`mcp`, `anyio`) -- there's no verified
"auto-install my requirements" plugin mechanism to build against, so rather than
invent one, the honest state is documented: run `pip install -e plugins/mcp` once,
which puts the `pyvar-mcp` console command `mcpServers` invokes onto `PATH`. Same
category as this project's other flagged one-time manual steps (the AMI Image
Builder bootstrap, the PyPI Trusted Publisher bootstrap for `pyvar-client`) --
tracked as open question #4 below (publish to PyPI, switch to `uvx pyvar-mcp`,
remove the step entirely) rather than solved with an unverified guess now.

### B.6 Portal & docs placement  (IMPLEMENTED as of this revision)

- **One combined page**, `portal/plugins.html` — resolves open question #2 in
  favour of a single page over a `skills.html` + `plugin.html` split: quickstart
  (`/plugin marketplace add fibtecltd/pyvar`, then `/plugin install
  <name>@pyvar-marketplace`), the 8 domain skills and 5 architecture skills as
  cards (descriptions copied verbatim from `.claude-plugin/marketplace.json`,
  the same source `scripts/generate_plugins.py` reads — hardcoded HTML rather
  than a client-side fetch, matching how `index.html`'s own domain-grid is
  already static rather than JSON-fetched; only the granular 385-function list
  uses the fetch-`functions.json` pattern), and a dedicated MCP server section
  covering the `list_pyvar_functions`/`call_pyvar_function` fallback pair, the
  per-function tools, and the one manual `pip install -e plugins/mcp` step
  (content mirrors `plugins/mcp/README.md` verbatim, not reworded from memory).
  Linked from the shared nav (`pyvar.js`'s `buildNav`) and footer.
- A small, mechanical callout box added to each of the 8 `domain-*.html`
  pages' API-reference section, immediately above the existing "← All
  domains / API access →" button row: names that domain's specific skill
  plugin (e.g. `pyvar-market-risk`) and links to `plugins.html`. Same
  structure on all 8 pages, only the plugin name changes.
- **Found and fixed while touching this section**: all 8 domain pages' two
  CTA buttons per page used `class="btn-outline"` / `class="btn-gold"`, but
  `pyvar.css` only ever defined `.btn-ghost` / `.btn-green` (the names
  `index.html` itself uses) — a naming drift that left every domain page's
  most prominent CTAs rendering as bare unstyled links, no border/background/
  padding, on every one of the 8 pages, since whenever those buttons were
  first added. Same bug class as the version-badge/demo-runtime/homepage-
  async-claim fixes already in this plan doc: a real, live inaccuracy/defect
  discovered incidentally, not searched for. Fixed by renaming the classes to
  the ones `pyvar.css` actually defines (16 occurrences across 8 files) rather
  than adding duplicate CSS for a second pair of names.

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
- Actual new infra: `.github/workflows/plugins-ci.yml` (drift-check CI job for
  both generators, plus a `pyvar-mcp-tests` lint+test job), `scripts/
  generate_plugins.py` and `scripts/generate_mcp_tools.py` (the two generators),
  `plugins/mcp/` itself (a real installable package, `pyproject.toml` +
  `[project.scripts]`, mirroring `pyvar-client/`'s own structure exactly).

---

## Testing plan

- Skills plugins: `.github/workflows/plugins-ci.yml`'s drift-check job IS the test
  (regenerate, diff against committed, fail with the fix command if stale) --
  implemented, not just planned.
- MCP plugin: **implemented**, 22 tests in `plugins/mcp/tests/`, 96% coverage on
  `pyvar_mcp` (`pytest --cov=pyvar_mcp --cov-fail-under=90`, enforced in CI's
  `pyvar-mcp-tests` job) -- `test_client.py` (the HTTP layer, `urlopen` mocked
  throughout, both success and error paths incl. network failures), `test_catalogue.py`
  (lookup helpers against the real generated 385-entry list), `test_main.py`
  (the actual `on_list_tools`/`on_call_tool` handlers registered on a real
  `mcp.server.lowlevel.Server` instance -- confirms all 387 tools list correctly,
  the generic pair validates params and dispatches to the right endpoint without
  ever calling a nonexistent one, a named tool call reaches the identical endpoint
  `call_pyvar_function` would, and every error path (unknown tool, unknown function,
  missing required param, a 403 from the API) returns `CallToolResult(is_error=True)`
  rather than raising).
- Still open, not verifiable from this sandbox: an actual smoke-install into a real
  Claude Code session (`/plugin marketplace add fibtecltd/pyvar` then `/plugin
  install pyvar-mcp@pyvar-marketplace`) to confirm the full install -> `userConfig`
  prompt -> `pip install -e plugins/mcp` manual step -> working tool calls chain
  genuinely works end-to-end, not just each piece in isolation.

---

## Open questions — before implementation starts

1. ~~**MCP server source location.**~~ **Resolved**: `plugins/mcp/` in
   `fibtecltd/pyvar` itself — the skills plugins turned out to already be scaffolded
   in this same repo (a pre-existing `.claude-plugin/marketplace.json`), so the MCP
   plugin follows the same convention rather than a separate repository.
2. ~~**One combined "Claude Code" portal page vs. two separate pages.**~~
   **Resolved**: one combined page, `portal/plugins.html` — see §B.6.
3. ~~**MCP server implementation language/framework.**~~ **Resolved**: Python,
   implemented (`plugins/mcp/pyvar_mcp/`) -- reuses this codebase's own stdlib-HTTP
   convention (`pyvar-cdk/lambda/*/handler.py`'s pattern) and mirrors `pyvar-client/`'s
   package structure exactly.
4. **PyPI publish + `uvx pyvar-mcp`** (was "Marketplace listing") -- currently a
   `pip install -e plugins/mcp` manual step is required after `/plugin install`
   (§B.5). Publishing `pyvar-mcp` to PyPI (mirroring `pyvar-client`'s own
   `pyvar-client-publish.yml` release workflow, including its same one-time PyPI
   Trusted Publisher bootstrap) and switching `plugin.json`'s `mcpServers.command`
   to `uvx pyvar-mcp` would remove that manual step entirely. Not done in this
   pass -- worth a deliberate follow-up, not a blocker for the plugin working today.
5. **Rate limits at scale** — if the MCP plugin sees real adoption, free-tier API key
   usage from many simultaneous Claude Code sessions is a new usage pattern the
   existing tier system (`api/middleware/rate_limit.py`) wasn't originally sized
   around. Not a blocker for a first version, but worth a deliberate look before any
   broad promotion of the plugin.
6. ~~**The homepage's async-job-pattern claim**~~ (found while building §B.3).
   **Resolved**: `portal/index.html`'s API section rewritten to state the real
   architecture — 384 of 385 functions are synchronous (`POST` params, get the
   JSON result straight back); the one exception is large-scale Monte Carlo VaR
   (`POST /api/v1/var/compute` + `GET /api/v1/var/result/{task_id}`). Same class
   of fix as the stale version badge and misleading demo runtime already
   corrected earlier in this project.

---

## Revision history note — none of the code-shipping revisions are docs-only

The first two versions of this plan (#288, #289) were pure `docs/` changes,
confirming the CodePipeline Git push-filter trigger (#282–#285) correctly starts
**zero** `pyvar-dev-pipeline` executions for a docs-only push. v1.2 shipped
alongside the Part A implementation; this revision (v1.3) ships alongside Part B
(`plugins/mcp/`, `scripts/generate_mcp_tools.py`, the extended
`.github/workflows/plugins-ci.yml`) in the same commit, for the same reason: the
doc text and the code it describes need to land together to stay accurate.

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

v1.4 closes out §B.6, the one item left open after v1.3: `portal/plugins.html`
(one combined page, resolving open question #2), the 8 domain-page callouts, the
`buildNav`/`buildFooter` links, the homepage async-claim rewrite (open question
#6), and the incidentally-discovered `btn-outline`/`btn-gold` CTA styling bug on
all 8 domain pages. `portal/` changes are outside the trigger's 8-entry exclude
list by design (portal changes should deploy), so this push starts a normal
pipeline execution, not a docs-only-skip one. With this revision P10 is complete:
both plugins are installable, both linked from the portal, ahead of the P9
visibility flip as planned in the Sequencing section above.
