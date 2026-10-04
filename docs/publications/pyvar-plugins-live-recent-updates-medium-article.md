# pyvar Today: 13 Live Plugins, Real-Time Results, and a One-Command Deployment

*A follow-up to "14 Plugins, One API" — where the platform stands right now.*

> **Draft status:** not yet published. Every fact below is checked against
> this repository at drafting time (`.claude-plugin/marketplace.json`,
> `config.py`, `docker-compose.yml`, `api/routes/auth.py`, `api/routes/var.py`) —
> see **Sources** at the end. Needs review before it goes anywhere.

---

pyvar.com is an open-source (Apache-2.0), Numba-accelerated risk computation platform covering VaR, credit risk, derivatives, liquidity, operational risk, portfolio analytics, ALM, and regulatory capital — 385 functions behind a single REST API. Here's what's available today.

## 14 plugins, 13 live

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-market-risk@pyvar-marketplace
```

8 domain skills (market risk, credit risk, liquidity risk, operational risk, portfolio analytics, regulatory, derivatives, ALM) and 5 architecture skills are `Published` on Anthropic's developer portal. `pyvar-mcp` — the MCP server that turns all 385 functions into Claude Code tools, generic (`list_pyvar_functions`, `call_pyvar_function`) and individually typed alike — is `In review`.

The install command above doesn't care either way: it's a direct GitHub-source marketplace add, live against this repository right now, independent of portal review status.

## Two ways to get a result

`POST /var/compute` submits a job the same way it always has. From there, you choose:

| | Poll | Stream |
|---|---|---|
| Endpoint | `GET /var/result/{task_id}` | `WS /api/v1/var/stream/{task_id}` |
| How you get the result | Ask until the status flips to `SUCCESS` | Held open, pushed the instant the job completes |
| What it costs | One request per check | One connection, no polling loop |

Both read from the same authoritative job state, so the stream endpoint never has to be trusted blindly: every wake-up — pushed or timed out — re-reads that state directly, bounded by `var_stream_max_wait_seconds` (900s). A result is never more than one poll interval (2s) stale on either path.

## One command, the full stack

`pyvar-full/` is a self-contained Docker distribution of the entire application — API, worker, Redis, Postgres — not just the compute engine:

```bash
cd pyvar-full/
docker compose up
```

That's the whole setup. No bind mounts, no external Docker network to create first, no separate migration step to remember — a one-shot `migrate` service runs automatically before the API comes up. `pyvar-local/` remains the narrower, engine-only package for people who just want the compute core.

## Two ways into an account

| | Email | Google |
|---|---|---|
| Steps | Register → check inbox → click the verification link | Click the sign-in button |
| Result | A JWT, after the link is clicked | A JWT, immediately |
| Verification | Confirmed by the link click | Confirmed by Google's own `email_verified` claim |

`POST /auth/google` verifies the ID token Google Identity Services hands the frontend — signature, issuer, audience, expiry — and either creates a new verified account or signs into an existing one matched by email. Both paths issue the same kind of JWT, usable identically across every API call afterward.

## Try it

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-market-risk@pyvar-marketplace   # any of the 13 published skills
/plugin install pyvar-mcp@pyvar-marketplace            # pending review, installs today regardless
```

`pyvar-full/` is a `docker compose up` away from a complete local instance, Google sign-in included once a Client ID is configured.

---

## Sources

- [`.claude-plugin/marketplace.json`](https://github.com/fibtecltd/pyvar/blob/master/.claude-plugin/marketplace.json) — 14-plugin manifest.
- [`api/routes/var.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/var.py), [`tasks/var_task.py`](https://github.com/fibtecltd/pyvar/blob/master/tasks/var_task.py) — `WS /api/v1/var/stream/{task_id}`.
- [`config.py`](https://github.com/fibtecltd/pyvar/blob/master/config.py) — `var_stream_poll_interval_seconds`, `var_stream_max_wait_seconds`, `google_oauth_client_id`.
- [`pyvar-full/docker-compose.yml`](https://github.com/fibtecltd/pyvar/blob/master/pyvar-full/docker-compose.yml) — the one-command stack.
- [`api/routes/auth.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/auth.py), [`api/routes/public_data.py`](https://github.com/fibtecltd/pyvar/blob/master/api/routes/public_data.py) — `POST /auth/google`, `GET /public/config`.
- [`docs/publications/pyvar-plugins-medium-article.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-plugins-medium-article.md) — the original 14-plugin piece this one follows up on.
