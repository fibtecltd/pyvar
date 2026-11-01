# pyvar-mcp new-portal submission — Step 1 validation holds, triaged

Recorded against the Source-step validation run on `master @ 51c04ad`
(`plugins/mcp` as the plugin path): **3 warnings, 6 policy holds**. None of
these blocked Step 1 from passing — the submission proceeded to Step 2 —
but a human reviewer will see all 6 holds, so this doc triages each one:
what it means, whether it's a real gap, and what (if anything) to do about
it before or during review.

## Safe to leave as-is — no code change, reviewer confirms

### 1. `UNREAD_ASSET_REFERENCED` — `icon.png`

`plugin.json`'s `icon` field names `./icon.png`, a plain 180×180 PNG (copied
from `portal/apple-touch-icon.png`). The scanner can't prove from raw bytes
alone that an image file won't be executed by something, so it holds any
asset reference for manual confirmation. Nothing in the plugin runs
`icon.png` as code. No action needed.

### 2. `MCP_FORWARDS_CREDENTIAL_ENV` — `pyvar_mcp/client.py` → `www.pyvar.com`

`client.py` reads `PYVAR_API_KEY` from its process environment and sends it
as a Bearer token to `https://www.pyvar.com`. This is exactly the
documented pass-through exception: *"If the credential is for that host's
own vendor, you can leave it as it is and a reviewer confirms that."*
`PYVAR_API_KEY` is a pyvar API key, sent only to pyvar's own API — same
vendor, by construction.

It's also already sourced the *recommended* way, not read raw off the
user's machine: `plugin.json`'s `mcpServers.pyvar.env` is
`"PYVAR_API_KEY": "${user_config.pyvar_api_key}"` — a `user_config` option
(`sensitive: true`, `required: true`), substituted by Claude Code itself
before the process launches. `client.py` reading `os.environ` is just how
any subprocess receives that already-consented value — not an independent
credential read.

### 3. `NAME_CONFUSABLE` — collides with `fibtecltd/pyvar/plugins-mcp`

**Not a code fix.** The collision target (`fibtecltd/pyvar/plugins-mcp`)
looks like a stale listing of this exact plugin from a prior submission —
plausibly the old Claude Console entry marked "Published" (24/09/2026) or
residue from the withdrawn new-portal submission (01/09/2026). This is a
portal-side identity conflict, the same category as the orphan `pyvar-mcp`
submission already tracked via an open Anthropic support ticket — worth
raising in that same thread rather than anything fixable in this repo.

## Real fixes — one root cause, two symptoms

### 4 & 5. `BINARIES_NOT_INSPECTED` + the second `MCP_FORWARDS_CREDENTIAL_ENV` ("across its surfaces")

`pyvar_mcp/_generated/functions.py` is **408,795 bytes (~399 KiB)** — over
the scanner's 256 KiB full-read threshold, hence `BINARIES_NOT_INSPECTED`.
Because it's only partially read, the scanner's fallback heuristic scan
over the *unread* tail appears to have misread Sphinx/RST docstring
cross-references — e.g. `:func:`~engine.alm_nii_eve.eve_sensitivity_analysis``,
plain documentation markup, not executable code — as "a command assembled
at run time." That's the second, combined `MCP_FORWARDS_CREDENTIAL_ENV`
hold ("Read together that is a credential leaving the machine in two
steps").

**Fix**: split `functions.py` by domain (8 files, mirroring how every
other part of pyvar — `plugins/market-risk`, `plugins/credit-risk`, etc. —
is already organized), regenerated via `scripts/generate_mcp_tools.py`.
Each resulting file lands well under 256 KiB, the scanner reads all of it,
and the docstring false-positive should disappear as a direct consequence
of the file being fully readable instead of heuristically scanned.

### 6. `MCP_SCRIPT_NOT_READ` — `mcpServers.pyvar.command` is `"pyvar-mcp"`

The scanner wants either a known interpreter prefix (`docker`, `node`,
`python`, `java`) or a script path under `${CLAUDE_PLUGIN_ROOT}/...` it can
read directly. `"pyvar-mcp"` is a bare console-script name, resolved at
runtime via the `pyvar-mcp = "pyvar_mcp.main:main"` entry point in
`pyproject.toml` (installed by the manual `pip install -e plugins/mcp`
step `README.md` already flags as "not yet automated") — the scanner has
no way to trace a bare command name to a file.

**Fix**: point `command`/`args` at the bundled entry file directly —
`python3 ${CLAUDE_PLUGIN_ROOT}/pyvar_mcp/main.py` (or equivalent) instead
of the bare `pyvar-mcp` string. The scanner's own guidance names exactly
this pattern as acceptable.

## Informational only (no hold, no action)

- `UNKNOWN_KEY_CROSS_TOOL` / `UNKNOWN_KEY` on `icon`, `privacyPolicyUrl`,
  `termsOfServiceUrl` — the plugin manifest reference itself documents
  these as directory-listing-only fields Claude Code ignores at load time.
  Expected, not a gap.
- `STDIO_WEB_UNSUPPORTED` — `pyvar-mcp` is a local stdio MCP server (runs
  in Claude Code / Cowork, not on claude.ai) — a statement of fact, not an
  issue.
- `ASSETS_PASSED_UNREAD` — confirms `icon.png` was screened as a
  well-formed image. Matches item 1 above.

## Status

**Update, 2026-11-01:** items 4 and 5 are done in `pyvar-mcp` 0.2.2 (the catalogue is split by
domain; the largest file is 78 KB, and the generator refuses any file over 200,000 bytes). Item 6
is deliberately not changed: `mcpServers.pyvar.command` is now `uvx pyvar-mcp`, not the bare
console script of the original draft, and a `python3 ${CLAUDE_PLUGIN_ROOT}/...` command would drop
the automatic dependency install that `uvx` provides. Items 1 to 3 need no repo change. What the
directory reports for 0.2.2 decides whether item 6 is worth that cost.

Original status, 2026-09:
Documented only, per explicit instruction — **no code changes made yet**.
Revisit items 4-6 (the `functions.py` split and the `command` path fix) if
the submission doesn't clear review as currently drafted; items 1-3 need
no repo change regardless of outcome.

## 2026-11-01: the new portal's draft submission (Source step, `master @ b867c7d`)

1 blocking, 5 warnings, 4 policy holds. Triage:

| Finding | What it is | Action |
|---|---|---|
| **Unpinned uvx launcher** (blocking, `mcpServers.pyvar`) | `uvx pyvar-mcp` fetches whatever is newest | **Fixed**: `uvx pyvar-mcp==0.2.2`. Checked against PyPI: the server starts and lists 387 tools. Once the pin can be checked the package is held for review instead of blocked. |
| Image or font file that the plugin's code could run (hold) | `icon.png` | Nothing runs it; leave it (item 1 above). |
| Uses a credential from the user's machine (hold, 2 findings) | `client.py` reads `PYVAR_API_KEY` from its environment and sends it as a Bearer token. The key reaches that environment from the sensitive `userConfig` option through `mcpServers.pyvar.env`. | Not cleared by code: the documented same-vendor pass-through (item 2 above). The two findings' text is collapsed in the screenshot; if one is `PYVAR_API_BASE_URL` (the base URL is also read from the environment and not validated), restricting it to https pyvar hosts and loopback is the code change to make. |
| Name may be confused with an existing listing (hold) | `pyvar-mcp` matches `fibtecltd/pyvar/plugins-mcp`, the old platform's published listing of this same plugin ("not yours") | Not a code fix (item 3 above). Renaming the plugin is possible but touches every skill that tells users to install `pyvar-mcp`. |
| Unrecognized field in plugin.json (4), Field from another tool's manifest (`icon`) | the directory's own listing fields | "No action needed" per the portal. |
| Local MCP server: not on claude.ai; Images and fonts passed without a code check | facts / info | None. |
