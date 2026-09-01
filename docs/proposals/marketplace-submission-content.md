# Claude Code plugin marketplace — submission content

**Correction (2026-08-31):** this document's original premise was wrong and
is corrected here rather than silently rewritten, since the wrong premise
was already acted on once (P11 item 7 called it a submission to "the
official marketplace"). Verified directly against
https://code.claude.com/docs/en/plugins ("Submit your plugin to the
community marketplace" section):

- **`claude-plugins-official`** (the one this doc originally targeted) has
  **no submission process at all**. It's curated entirely at Anthropic's own
  discretion — quoting the docs verbatim: *"There is no application process,
  and the submission form does not add plugins to the official
  marketplace."* The `clau.de/plugin-directory-submission` URL this doc
  previously cited does not resolve to a form; it redirects to the docs page
  above.
- **`claude-plugins-community`** is the real, submittable public
  marketplace — third-party submissions land there after review. This is
  what the content below now targets.
- Distinct from both: the self-hosted marketplace pyvar already ships
  (`.claude-plugin/marketplace.json`), installable today via
  `/plugin marketplace add fibtecltd/pyvar` — unaffected by any of this.

**Correction (2026-09-01):** this document's Licence field said MIT
throughout — wrong, and already acted on: the real submission (P11 item 7,
received by the review team) carried "License MIT" too. pyvar's actual
license, root `LICENSE` file, is Apache-2.0 — every occurrence of MIT below
is fixed in this pass, alongside the same mistake in `scripts/
generate_plugins.py` (fed into all 14 generated `plugin.json` files),
`plugins/mcp/pyproject.toml`, and the portal's own footer text. The already-
submitted form itself is not something this repo can retroactively fix —
flagged for a human decision on whether the review team needs a correction.

**Real submission mechanism, two authenticated in-app forms (pick one):**
- **claude.ai**: https://claude.ai/admin-settings/directory/submissions/plugins/new
  — requires a Team/Enterprise organization and directory management access
  (org Owners have this by default).
- **Console**: https://platform.claude.com/plugins/submit — for individual
  authors not part of a Team/Enterprise org.

Both are authenticated web forms tied to the submitter's own claude.ai/Console
identity — **not something a Claude Code session can complete on the user's
behalf**, and not something to request credentials for. What this session
*can* and did do: run the same local check the review pipeline runs before
accepting a submission —

```
claude plugin validate ./plugins/<name>
```

against all 13 real plugin directories (`plugins/arch/` itself is a grouping
folder, not a plugin — its 5 subdirectories are the real ones). **All 13
pass cleanly** (`✔ Validation passed`, `mcp` included) — confirmed
2026-08-31. The content below is prepared for whoever completes the actual
form (the user, or their separately-delegated agent with access to the
user's claude.ai/Console identity).

---

## Marketplace identity

- **Name:** pyvar-marketplace
- **Owner:** Fibtec Limited (https://fibtec.co.uk)
- **Repository:** https://github.com/fibtecltd/pyvar
- **Homepage:** https://pyvar.com
- **Licence:** Apache-2.0

## One-line pitch

385 regulatory-grade financial risk functions (VaR, credit risk, derivatives
pricing, liquidity, operational risk, portfolio analytics, ALM, regulatory
capital) as Claude Code skills and an MCP server, backed by a free, open,
auditable API.

## Description (longer form)

pyvar.com is an open-source (Apache-2.0-licensed) financial and risk computation
platform. This marketplace ships two kinds of Claude Code plugin:

- **13 skills** — 8 domain skills (one per risk domain: market risk, credit
  risk, liquidity risk, operational risk, portfolio analytics, regulatory,
  derivatives, ALM) and 5 architecture skills covering pyvar's own technical
  stack (API gateway, data ingestion, compute, storage, observability). Each
  skill is pure instructional content — no code execution, no network
  access of its own.
- **pyvar-mcp** — an MCP server exposing all 385 functions as Claude Code
  tools, plus two generic tools (`list_pyvar_functions`,
  `call_pyvar_function`) meant as the first choice over guessing among 385
  individually named ones. It is a thin wrapper over the live pyvar REST API
  — every tool call is a real HTTPS request to pyvar.com, not a bundled copy
  of the compute engine. Requires a free pyvar API key (prompted for at
  install time via the plugin's `userConfig`).

All 14 plugins are **generated directly from this repository's own source of
truth** (the skills under `.claude/skills/*`, the function catalogue in
`portal/functions.json`) by committed generator scripts
(`scripts/generate_plugins.py`, `scripts/generate_mcp_tools.py`), with CI
(`​.github/workflows/plugins-ci.yml`) failing the build if the committed
output ever drifts from what regenerating produces. Nothing here is
hand-maintained separately from the code it describes.

## Category / tags

`finance`, `risk-management`, `regulatory-compliance`, `api`, `mcp-server`,
`quantitative-finance`

## Security / trust disclosure

- **pyvar-mcp's only external dependency is the pyvar REST API itself**
  (`https://www.pyvar.com`, or a self-hosted instance) — no third-party
  services, no telemetry, no analytics.
- **Data sent:** whatever parameters the user explicitly provides to a
  function call (e.g. a returns series, portfolio value) — sent over HTTPS
  with the user's own API key, exactly as if they had called the REST API
  directly. No portfolio or position data is retained beyond pyvar's own
  documented job-result TTL (VaR jobs only; all other 384 functions are
  synchronous with no persistence).
- **Auth:** a free-tier pyvar API key, provided by the user during plugin
  install via the documented `userConfig` mechanism (`sensitive: true`,
  never committed to source control).
- **One documented manual step:** `pyvar-mcp`'s Python dependencies (`mcp`,
  `anyio`) are not yet auto-installed by the plugin install flow — a
  one-time `pip install -e plugins/mcp` is required and documented in
  `plugins/mcp/README.md`. Flagged here for transparency, not glossed over.
- **Open source, Apache-2.0-licensed, publicly auditable** — every tool's
  behaviour is generated from and traceable to the actual REST API route it
  calls; nothing is closed-source or obfuscated.

## Links to include

- Marketplace source: https://github.com/fibtecltd/pyvar/blob/master/.claude-plugin/marketplace.json
- Plugins directory: https://github.com/fibtecltd/pyvar/tree/master/plugins
- Portal page listing all 14 plugins: https://pyvar.com/plugins.html
- MCP server source + README: https://github.com/fibtecltd/pyvar/tree/master/plugins/mcp
