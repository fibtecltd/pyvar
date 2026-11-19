# pyvar-mcp

MCP server exposing all 385 [pyvar.com](https://www.pyvar.com) risk
functions — VaR, credit risk, derivatives, liquidity, operational risk,
portfolio analytics, ALM, regulatory capital — as Claude Code tools.

It's a thin wrapper over the live pyvar API (each tool call is a real HTTPS
request), not a bundled copy of the compute engine — results always match
what's actually deployed at pyvar.com.

## Install

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-mcp@pyvar-marketplace
```

You'll be asked for a pyvar API key during install, and you can leave it empty:
without one, 30 of the functions work with no sign-up, a few calls a day
(`list_pyvar_functions` marks them `available_without_key`). For every function
and higher limits, sign in at <https://www.pyvar.com#get-api-key> (emailed link
or Google; no password, no credit card), create a key on the dashboard and set it
in the plugin's settings. It starts with `pyvar_`, lasts a year, and you can
revoke it there at any time. A key you set is always the one used.

The plugin starts the server with `uvx pyvar-mcp`, which downloads it from PyPI
on first use, so it needs [uv](https://docs.astral.sh/uv/) on your PATH. If the
tool calls fail with a "command not found" style error, a missing uv is almost
certainly why. No uv? Run `pip install pyvar-mcp` and change the plugin's
`mcpServers` command to `pyvar-mcp` (with no `args`). Working from a checkout of
this repo instead: `pip install -e plugins/mcp`.

`pyvar-mcp` is published to PyPI by `.github/workflows/pyvar-mcp-publish.yml`
when a `pyvar-mcp-v*` tag is pushed (trusted publishing). The plugin starts the
server with an exact pin, `uvx pyvar-mcp==X.Y.Z` (the plugin directory refuses an
unpinned launcher), so a release changes three things together: `version` in
`pyproject.toml`, `version` in `.claude-plugin/plugin.json`, and the pin in its
`mcpServers.pyvar.args`. The workflow fails before building if the tag, those two
versions and the pin disagree. Tag the merge commit as soon as it lands: until the
tag's workflow has run, the pin names a version PyPI does not have yet.

## What this plugin stores and sends

**With an API key** the plugin sends it to pyvar.com as a bearer token with every
call, together with the function's parameters and the label `X-Pyvar-Client:
pyvar-mcp/<version>`. It stores nothing.

**With no key** (inside Claude Code only, and never when `CI` is set; set
`PYVAR_API_KEY` there) the first tool call that needs one asks pyvar.com for an
anonymous installation ticket:

- It sends a solved puzzle (a small proof of work, about a second of CPU) and
  nothing else: no account, name, e-mail or machine details.
- It keeps the ticket in `install.json` in **the plugin's own data directory**
  (`${CLAUDE_PLUGIN_DATA}`), readable by you only (mode 0600), together with its
  expiry, the time it was issued and the API address it came from. While it asks, a
  lock file `install.lock` sits beside it. The plugin opens no file outside that
  directory.
- Later calls send the ticket to pyvar.com (and nowhere else: redirects are not
  followed), plus the function's parameters and the label above.
- A ticket lasts 72 hours and allows 5 calls a day, 15 in all, on the 30 functions
  of the trial. When it expires or is refused it is replaced once, automatically.
  When the trial is busy or spent, the answer says so and points to a free key.
- Nothing is requested when the server starts or when tools are listed, only at the
  first call that needs a ticket.
- To stop it: set a key (it wins), or delete `install.json`. Removing the plugin
  removes its data directory.

pyvar.com counts calls by function, tier (`trial`), duration and status, with no
user identifier; see <https://www.pyvar.com/privacy.html>.

## Tools

Two generic tools, meant as your first choice:

- **`list_pyvar_functions(domain?)`** — browse available functions, optionally
  filtered to one domain (`alm`, `credit-risk`, `derivatives`, `liquidity`,
  `market-risk`, `operational`, `portfolio`, `regulatory`). With no API key set,
  each entry also says whether it is `available_without_key`.
- **`call_pyvar_function(domain, function_name, params)`** — call any
  function by name. Validates `params` against the function's own schema
  before calling the API.

Plus all 385 functions as individually named tools (`alm_stress_test`,
`historical_simulation_var`, etc.) with precise per-parameter schemas, for
when you already know exactly which one you want.

## Local development

```
cd plugins/mcp
pip install -e ".[dev]"
pytest
```

Regenerating the tool catalogue after `portal/functions.json` changes:

```
python3 scripts/generate_mcp_tools.py   # from the repo root
```

`.github/workflows/plugins-ci.yml` fails CI if the committed `pyvar_mcp/_generated/`
doesn't match what regenerating produces — same drift-check pattern the skills plugins
and `pyvar-client` use. The catalogue is one module per domain, not one file: the plugin
directory's safety scan reads a file in full only up to 256 KiB, and the generator refuses to
write a file over 200,000 bytes (the largest today is about 78,000).
