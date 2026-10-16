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

You'll be prompted for a pyvar API key during install. Sign in at
<https://www.pyvar.com#get-api-key> (emailed link or Google; no password, no
credit card) and create one on the dashboard. It starts with `pyvar_`, lasts a
year, and you can revoke it there at any time.

The plugin starts the server with `uvx pyvar-mcp`, which downloads it from PyPI
on first use, so it needs [uv](https://docs.astral.sh/uv/) on your PATH. No uv?
Run `pip install pyvar-mcp` and change the plugin's `mcpServers` command to
`pyvar-mcp` (with no `args`). Working from a checkout of this repo instead:
`pip install -e plugins/mcp`.

`pyvar-mcp` is published to PyPI by `.github/workflows/pyvar-mcp-publish.yml`
when a `pyvar-mcp-v*` tag is pushed; until the first release exists, use the
checkout install above.

This installs the `pyvar-mcp` console command the plugin's `mcpServers`
config invokes. If the tool calls fail with a "command not found" style
error, this step is almost certainly why. A future revision may publish
`pyvar-mcp` to PyPI (mirroring `pyvar-client`'s own release workflow) and
switch the plugin to `uvx pyvar-mcp`, removing this step entirely — tracked
as an open question in `docs/p10-skills-and-plugin-plan.md`.

## Tools

Two generic tools, meant as your first choice:

- **`list_pyvar_functions(domain?)`** — browse available functions, optionally
  filtered to one domain (`alm`, `credit-risk`, `derivatives`, `liquidity`,
  `market-risk`, `operational`, `portfolio`, `regulatory`).
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

`.github/workflows/plugins-ci.yml` fails CI if the committed
`pyvar_mcp/_generated/functions.py` doesn't match what regenerating produces
— same drift-check pattern the skills plugins and `pyvar-client` use.
