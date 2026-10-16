# Plan: durable API keys, sign-in for returning users, and a plugin that can start

Status: implemented in PR #388 (branch `claude/fibtec-redesign-continue-3i4abm`).
Decisions below were taken by the project owner on 2026-10-16; each one is a choice
between named alternatives, recorded so it is not re-litigated by accident.

## Why

Directory usage for `pyvar-portfolio-analytics` (456 installs, 366 installer accounts,
86 accounts ever active, 103 skill uses, 2 of 83 new accounts back the next day, 0 errors
in 27,003 loads) said people install the plugins and then cannot get anything done.
Two layers of cause:

1. **The skills gave Claude nothing to run** (no key, URL, parameters or namespace that
   exists; 26 of market-risk's 68 names were not real endpoints). Fixed by
   `scripts/sync_skills.py` (Part 1 of the PR).
2. **The credential was unusable for a plugin.** The "API key" was the session JWT:
   - valid 60 minutes (`jwt_expiry_minutes`), shown once on the dashboard;
   - the tier is a claim inside it, so a Stripe upgrade changed nothing until a new JWT
     was fetched (and `docs`/the REST guide said no other refresh existed);
   - the emailed verification link is single use, and `POST /auth/register` for an
     already-verified address sent nothing, so only "Sign in with Google" could issue a
     second token. A user who verified a non-Google address could never get another;
   - `pyvar-mcp` asks for this key once at install, so it stopped working an hour later;
   - `pyvar-mcp` was not on PyPI (`pypi.org/pypi/pyvar-mcp/json` was a 404), and a plugin
     install never installs the `pyvar-mcp` command it launches.

## Decisions

| Question | Chosen | Rejected |
|---|---|---|
| Key model | Durable, revocable, hashed API keys | Just lengthen the JWT (cannot be revoked, tier stays stale); short JWT + refresh tokens (most moving parts, awkward for paste-once users) |
| Returning users on non-Google email | Email sign-in link through the existing register form, plus Google | Google only; passwords (contradicts the privacy policy's "no password") |
| Default key lifetime | 1 year, then rotate | Never expires; 90 days |
| `pyvar-mcp` delivery | PyPI via trusted publishing, plugin launches `uvx pyvar-mcp` | Git-based `uvx` stopgap; both |

## Design

- **Key**: `pyvar_` + `secrets.token_urlsafe(32)` (256 bits). Shown once, at creation.
  Stored: SHA-256 hex (`api_keys.key_hash`, unique), a 14-character display prefix, a
  name, and `created_at / expires_at / last_used_at / revoked_at`. SHA-256 rather than a
  password hash because the secret is random and high-entropy (nothing to brute-force)
  and the lookup must be one indexed equality on every request. Rows are never deleted
  (CLAUDE.md §3.3); revoking sets `revoked_at`.
- **Authentication**: `get_current_user` accepts either a session JWT or a `pyvar_` key and
  returns the same `TokenPayload`, so rate limiting (one per-user bucket), billing and the
  VaR audit see one account either way. A key's **tier is read from the database**, not
  from a claim, so an upgrade or an automatic downgrade applies to keys within the cache
  TTL.
- **Cost of the extra lookup**: a resolved key is cached in Redis for
  `api_key_cache_ttl_seconds` (60 s). A hit costs one Redis GET and no database
  connection (the async pool is 5 + 5). Revoking deletes the cache entry, so revocation is
  immediate on the same Redis. Unknown keys are negatively cached for 30 s.
  `last_used_at` is refreshed at most hourly, on the cache-miss path.
- **Failure modes**: Redis errors fail open to the database (it is only a cache). A
  database error is a **503**, never a 401 and never a pass. Unknown-key attempts are
  counted per trusted client IP and answered 429 past
  `api_key_failed_attempts_per_minute`, so random-key spraying cannot become unbounded
  database load.
- **Key management** (`/auth/api-keys`: `POST` create, `GET` list, `DELETE /{id}` revoke)
  requires a signed-in **session** (JWT). An API key cannot create or revoke keys, so a
  leaked key cannot mint replacements. Max 5 active keys and 50 in total per account.
- **Returning users**: `POST /auth/register` for an already-verified, non-suppressed
  address now emails a single-use sign-in link (valid `signin_link_expiry_minutes` = 30,
  at most one per `signin_link_min_interval_seconds` = 300 per address, on top of the
  existing per-IP limit). Every outcome returns the identical 202, so the form still
  cannot be used to probe which addresses have accounts. `verified_at` is not overwritten
  by a sign-in (the daily "new verified accounts" count reads it).
- **Dashboard** (`portal/dashboard.html`): first sign-in creates a first key
  automatically (only if the account has *never* had one); afterwards it lists, creates
  and revokes keys. The session JWT stays in `localStorage` under `pyvar_jwt`, as before,
  for the "Try it" panels. All API text is inserted with `textContent`.
- **Clients**: `pyvar_client.Client()` reads `PYVAR_API_KEY`; the client and `pyvar-mcp`
  send `X-Pyvar-Client: <name>/<version>`. The API records an allowlisted name in
  `api_usage.client` (otherwise `other`, or NULL if absent). **No user identifier is
  stored in `api_usage`**; adoption by surface is visible, per-user retention is not.
  `api_keys.last_used_at` gives "keys used in the last 7/30 days" without logging
  per-request identity.
- **Plugins**: the 8 domain skills tell Claude to send people to the dashboard for a key;
  `plugins/mcp` launches `uvx pyvar-mcp`; `.github/workflows/pyvar-mcp-publish.yml`
  publishes on a `pyvar-mcp-v*` tag.

## Security notes

- Keys never reach logs, Sentry or the database in clear: creation logs only the prefix.
- `portal/privacy.html` and `portal/terms.html` now say we store a hash, a name, a prefix and
  timestamps, and that a lost key cannot be recovered. **Needs the owner's read.**
- WebSocket streaming (`/var/stream/{task_id}`) still accepts a session JWT only: a key in a query
  string would end up in access logs. Revisit before offering keys there.
- Existing JWTs keep working everywhere; nothing is migrated.

## Rollout (order matters)

1. Merge. The pipeline runs the Alembic step (`0009_api_keys`: new table and
   `api_usage.client`, purely additive) before the new API tasks start.
2. Approve **Prod promptly** after Dev is green. The plugin directory scans `master` about
   every 6 hours and auto-publishes the 12 plugins that are not reviewer-gated, and their
   skills now describe a dashboard that creates keys. Merging and then waiting days to
   promote leaves a window where the skills describe something production does not do yet.
3. Do the PyPI bootstrap for `pyvar-mcp` (create the project / pending publisher with
   trusted publishing for `fibtecltd/pyvar`, `pyvar-mcp-publish.yml`, environment `pypi`),
   then push the tag `pyvar-mcp-v0.2.0`. `pyvar-jupyter-publish.yml` has the same
   one-time bootstrap and `pyvar-jupyter` was also absent from PyPI when checked.
4. Push `pyvar-client-v0.2.0` to publish the client that reads `PYVAR_API_KEY`.
5. Confirm the production value of `JWT_EXPIRY_MINUTES` (the repo default is 60).

## Not done here (decide separately)

- Per-user retention analytics (needs a user dimension in usage records: a privacy-policy
  decision).
- Key use over WebSocket, scoped keys (read-only / per-domain), and a per-key rate bucket.
- Rewriting `docs/publications/*` articles that describe the old JWT flow; they record what
  was true when published.
