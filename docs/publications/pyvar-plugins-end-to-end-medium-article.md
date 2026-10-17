# From /plugin install to a Computed Number: How pyvar's Claude Code Plugins Work

*Skills generated from the function catalogue and run against the live API, API keys that last a year, and the check every call goes through.*

![Four tiles: 385 functions in 8 domains; 16 worked examples in the skills, with 28 requests run against the real application on every test run; an API key lifetime of 365 days with up to 5 active keys per account; and a longest wait for a tier change of 60 seconds.](./assets/plugins-end-to-end/plugins-end-to-end-header.png)

*What the plugins rest on, read from the code.*

---

pyvar.com is an open-source (Apache-2.0) risk platform: 385 functions across eight domains — market risk, credit risk, liquidity, operational risk, portfolio analytics, regulatory capital, derivatives and ALM — behind one REST API. It reaches Claude users through fourteen plugins: eight domain skills, five architecture skills for contributors, and the `pyvar-mcp` server.

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-market-risk@pyvar-marketplace
```

This article follows one question from the install to a computed number: what the skill tells Claude, where the key comes from, and what happens to that key on every call.

## The skills are generated

A skill is a markdown file that Claude reads when your question matches its description. pyvar's eight domain skills are not written by hand. `scripts/sync_skills.py` renders each one from the function catalogue (`portal/functions.json`) and the live OpenAPI schema, so every function carries its real route, parameters, types and defaults:

```
### historical_simulation_var

POST /api/v1/market-risk/historical_simulation_var

| Parameter        | Type                   | Default  |
|------------------|------------------------|----------|
| returns*         | number[] or number[][] | required |
| portfolio_value* | number                 | required |
| confidence_level | number                 | 0.99     |
```

Each skill opens with the setup Claude follows. Look for `PYVAR_API_KEY`; if it is missing, walk the user through getting one. Then call the function in whichever way is available: the Python client (`Client(...).market_risk.<function>(**body)`), REST (`POST /api/v1/market-risk/<function>` with `Authorization: Bearer $PYVAR_API_KEY`), or MCP (`call_pyvar_function`). Each error has one meaning: `401` is a bad, revoked or expired key, `422` names the wrong parameter, `429` is the daily quota. If Claude cannot run code or reach the network, it hands the user the exact `curl` or Python to run instead of guessing a result.

Two tests keep the skills true. `tests/test_skills_sync.py` fails if a skill drifts from the catalogue: a function added, renamed or re-parameterised. `tests/test_skill_examples.py` takes the 16 worked examples in the skills and POSTs all 28 of their requests to the real application on every run, checking that each returns every response key the skill documents.

## Getting a key

![Flow chart in six steps: install the plugin; ask a risk question and the skill tells Claude to look for PYVAR_API_KEY; with no key, go to pyvar.com and sign in with Google or an emailed link; create a key on the dashboard, shown once and valid 365 days; set PYVAR_API_KEY or paste it when the MCP plugin asks; Claude makes the call. A revoked or expired key returns 401 and sends you back to the sign-in step.](./assets/plugins-end-to-end/plugins-end-to-end-setup-flow.png)

*Figure 1. The path a new user takes. The skill tells Claude each step.*

**Signing in.** There is no password and no credit card. The home page offers "Sign in with Google", or an email address. The same form registers a new address and signs a returning one in, by emailing a single-use link that is valid for 30 minutes, at most one per five minutes per address. Every outcome returns the identical `202` response, so the form cannot be used to find out which addresses have accounts. The sign-in button is pinned to English with its `locale` option, and a test fails on any button without it.

**The key.** On first sign-in the dashboard creates a first key. A key is `pyvar_` plus 32 random bytes, shown once. Only its SHA-256 is stored, with a short display prefix, a name and timestamps. A hash rather than a password hash, because the secret is 256 bits of randomness (there is nothing to brute-force) and the lookup has to be one indexed equality on every request; a password hash would add roughly 100 ms to every call for no security gain. A key lasts 365 days. An account can hold 5 active keys and 50 in total. Revoking sets a timestamp; rows are never deleted. A lost key cannot be recovered, only replaced.

**Keys cannot manage keys.** Creating and revoking keys needs a signed-in session. The dashboard holds a 60-minute session token for that, and a leaked key cannot create its own replacement.

**The tier follows the account.** A key's tier is read from the database, so an upgrade or an automatic downgrade applies to existing keys within a minute.

**Where the key goes.** `PYVAR_API_KEY` in the environment. The Python client reads it when you call `Client()` with no arguments. The `pyvar-mcp` plugin asks for it once at install and starts the server with `uvx pyvar-mcp`, which is published on PyPI through trusted publishing (OIDC, no token stored anywhere). In a notebook, `%pyvar_key pyvar_...` or the same environment variable.

## What a key costs on every call

A session token is just decoded. A key needs the account's tier, so there is a lookup per call, and that is worth designing rather than hoping about.

![Flow chart: a Bearer pyvar_ key is hashed with SHA-256 and looked up in Redis. A hit returns the account and tier. A miss goes to the database by hash; found is cached for 60 seconds and returned; not found returns 401, cached for 30 seconds, and past 30 bad keys a minute from one address returns 429; a database error returns 503.](./assets/plugins-end-to-end/plugins-end-to-end-key-check.png)

*Figure 2. A cache hit costs one Redis read and no database connection. Only misses reach the database.*

That matters because the async database pool is deliberately small (5 plus 5 connections). The failure modes are asymmetric on purpose:

- **Redis is only a cache.** If it errors, the lookup falls through to the database. A Redis outage makes calls slower, not wrong.
- **A database error is a 503**, never a 401 and never a pass. A user with a good key must not be told it is bad.
- **Unknown keys are cheap to refuse.** They are cached as invalid for 30 seconds, and failures are counted per client address. Past 30 a minute the answer is `429`, so spraying random keys cannot turn into unbounded database load.
- **Revoking is immediate.** It deletes the cache entry, so a revoked key stops working on the next call.
- **Using a key does not write per request.** `last_used_at` is refreshed at most hourly, on the cache-miss path.

One limit: the streaming endpoint for Monte Carlo VaR (`WS /api/v1/var/stream/{task_id}`) accepts a session token only, because a key in a query string would end up in access logs.

## One label per surface

The API counts calls by client surface, using an allowlisted `X-Pyvar-Client` header. `pyvar-client`, `pyvar-mcp`, `pyvar-jupyter` and the `pyvar` command (as `pyvar-cli`) each send their own name; anything else is recorded as `other`, and a call with no header as nothing at all. The allowlist bounds how many distinct values can ever be stored. `pyvar-jupyter` wraps `pyvar-client`, which stamps its own name on every request, so the notebook magics relabel their requests in an httpx request hook. (A custom transport would also work, but it makes httpx ignore `HTTP(S)_PROXY`, which breaks notebooks behind a corporate proxy.)

## What is measured, and what is not

Two signals are available on the server side: calls by client surface (`api_usage.client`), and keys used in the last 7 and 30 days (`api_keys.last_used_at`).

Per-user retention is not measured. `api_usage` stores no user identifier, and that is deliberate: it would need a user dimension in the usage records, which is a privacy-policy decision rather than an engineering one. The design chooses to see adoption by surface and not to know which person did what.

## Try it

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-market-risk@pyvar-marketplace
```

Get a free key at https://www.pyvar.com#get-api-key (Google, or an emailed link), create it on the dashboard, and set `PYVAR_API_KEY`. The free tier is 10 calls a day.

```
pip install pyvar-client       # Python client; reads PYVAR_API_KEY
pip install pyvar-jupyter      # %pyvar and %%pyvar magics
uvx pyvar-mcp                  # the MCP server the plugin launches
```

---

## Sources

- [`scripts/sync_skills.py`](https://github.com/fibtecltd/pyvar/blob/master/scripts/sync_skills.py), [`scripts/skill_specs/`](https://github.com/fibtecltd/pyvar/tree/master/scripts/skill_specs) and [`.claude/skills/`](https://github.com/fibtecltd/pyvar/tree/master/.claude/skills) — the generator, its specs and the eight rendered domain skills.
- [`tests/test_skills_sync.py`](https://github.com/fibtecltd/pyvar/blob/master/tests/test_skills_sync.py) and [`tests/test_skill_examples.py`](https://github.com/fibtecltd/pyvar/blob/master/tests/test_skill_examples.py) — the drift test and the executed worked examples.
- [`docs/plan-durable-api-keys.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/plan-durable-api-keys.md) — the API key design and the alternatives considered.
- [`api/middleware/api_keys.py`](https://github.com/fibtecltd/pyvar/blob/master/api/middleware/api_keys.py) and [`api/middleware/auth.py`](https://github.com/fibtecltd/pyvar/blob/master/api/middleware/auth.py) — key generation, hashing, the cache and the failure modes.
- [`config.py`](https://github.com/fibtecltd/pyvar/blob/master/config.py) — the lifetimes, limits and TTLs quoted above.
- [`portal/pyvar.js`](https://github.com/fibtecltd/pyvar/blob/master/portal/pyvar.js) and [`tests/test_portal_google_signin.py`](https://github.com/fibtecltd/pyvar/blob/master/tests/test_portal_google_signin.py) — the sign-in button and its test.
- [`pyvar-jupyter/pyvar_jupyter/_magics.py`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-jupyter/pyvar_jupyter/_magics.py) and [`api/middleware/usage.py`](https://github.com/fibtecltd/pyvar/blob/master/api/middleware/usage.py) — the client label and the allowlist.
- [`scripts/generate_plugin_flow_figures.py`](https://github.com/fibtecltd/pyvar/blob/master/scripts/generate_plugin_flow_figures.py) — draws the figures; every number in them is read from the code.
