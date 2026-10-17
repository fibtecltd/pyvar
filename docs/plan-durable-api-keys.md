# API keys, sign-in and the plugin launch path

Status: in place. This describes how authentication works today. The choices below are
between named alternatives, recorded so they are not re-litigated by accident.

## Decisions

| Question | Chosen | Rejected |
|---|---|---|
| Key model | Durable, revocable, hashed API keys | Just lengthen the session token (cannot be revoked, tier goes stale); short session token plus refresh tokens (most moving parts, awkward for paste-once users) |
| Returning users on a non-Google email | Email sign-in link through the register form, plus Google | Google only; passwords (contradicts the privacy policy's "no password") |
| Default key lifetime | 1 year, then rotate | Never expires; 90 days |
| `pyvar-mcp` delivery | PyPI via trusted publishing, plugin launches `uvx pyvar-mcp` | Git-based `uvx`; both |

## Design

- **Key**: `pyvar_` + `secrets.token_urlsafe(32)` (256 bits). Shown once, at creation.
  Stored: SHA-256 hex (`api_keys.key_hash`, unique), a 14-character display prefix, a
  name, and `created_at / expires_at / last_used_at / revoked_at`. SHA-256 rather than a
  password hash because the secret is random and high-entropy (nothing to brute-force)
  and the lookup must be one indexed equality on every request. Rows are never deleted
  (CLAUDE.md §3.3); revoking sets `revoked_at`.
- **Authentication**: `get_current_user` accepts either a session JWT or a `pyvar_` key and
  returns the same `TokenPayload`, so rate limiting (one per-user bucket), billing and the
  VaR audit see one account either way. A JWT's tier is a claim inside it; a key's tier is
  **read from the database**, so an upgrade or an automatic downgrade applies to keys
  within the cache TTL.
- **Cost of the lookup**: a resolved key is cached in Redis for
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
  address emails a single-use sign-in link (valid `signin_link_expiry_minutes` = 30,
  at most one per `signin_link_min_interval_seconds` = 300 per address, on top of the
  per-IP limit). Every outcome returns the identical 202, so the form cannot be used to
  probe which addresses have accounts. `verified_at` is not overwritten by a sign-in (the
  daily "new verified accounts" count reads it).
- **Dashboard** (`portal/dashboard.html`): the first sign-in creates a first key
  automatically (only if the account has *never* had one); afterwards it lists, creates
  and revokes keys. The session JWT stays in `localStorage` under `pyvar_jwt` for the
  "Try it" panels. All API text is inserted with `textContent`.
- **Sign-in button**: the Google button on the home page is pinned to English with the
  `locale: 'en'` option of `renderButton`. The `hl` parameter on the library URL does not
  reach the button iframe. `tests/test_portal_google_signin.py` fails on any button
  without the option.
- **Clients**: `pyvar_client.Client()` reads `PYVAR_API_KEY`. `pyvar-client`, `pyvar-mcp`,
  `pyvar-jupyter` and the `pyvar` command each send `X-Pyvar-Client: <name>/<version>`. The
  command passes `client_name="pyvar-cli"` to `Client`; `pyvar-jupyter` wraps `pyvar-client`
  and rewrites the header in an httpx request hook (a custom transport would make httpx
  ignore `HTTP(S)_PROXY`). The API records an allowlisted name in `api_usage.client`
  (`pyvar-client`, `pyvar-mcp`, `pyvar-jupyter`, `pyvar-cli`, otherwise `other`, or NULL if
  absent).
  **No user identifier is stored in `api_usage`**; adoption by surface is visible,
  per-user retention is not. `api_keys.last_used_at` gives "keys used in the last 7/30
  days" without logging per-request identity.
- **Plugins**: the 8 domain skills tell Claude to send people to the dashboard for a key;
  `plugins/mcp` launches `uvx pyvar-mcp`. Each package publishes to PyPI from its own
  tag (`pyvar-client-v*`, `pyvar-mcp-v*`, `pyvar-jupyter-v*`) through trusted publishing
  (OIDC, GitHub environment `pypi`, no token stored).

## Settings

All in `config.py`; each is an environment variable of the same name in upper case.

| Setting | Default | Meaning |
|---|---|---|
| `jwt_expiry_minutes` | 60 | Session token lifetime |
| `api_key_default_expiry_days` | 365 | Key lifetime |
| `api_key_max_active_per_user` | 5 | Active keys per account |
| `api_key_max_total_per_user` | 50 | Keys per account including revoked and expired |
| `api_key_cache_ttl_seconds` | 60 | Redis cache for a resolved key (and the longest a tier change waits) |
| `api_key_failed_attempts_per_minute` | 30 | Unknown-key attempts per client address before 429 |
| `signin_link_expiry_minutes` | 30 | Sign-in link lifetime |
| `signin_link_min_interval_seconds` | 300 | Minimum gap between sign-in links to one address |

The 30-second negative cache for unknown keys is the module constant `_NEGATIVE_TTL_SECONDS`
in `api/middleware/api_keys.py`.

## Where the code is

- `api/middleware/api_keys.py`: key generation, hashing, the cache, the failure counter.
- `api/middleware/auth.py`: `get_current_user` (key or session), `require_session`.
- `api/routes/auth.py`, `schemas/auth.py`: register and sign-in, verify, Google, key routes.
- `storage/models.py` (`ApiKey`, `ApiUsage.client`), `migrations/versions/0009_api_keys.py`.
- `portal/dashboard.html`, `portal/pyvar.js`: the dashboard and the sign-in button.

## Security notes

- Keys never reach logs, Sentry or the database in clear: creation logs only the prefix.
- `portal/privacy.html` and `portal/terms.html` say what is stored (a hash, a name, a
  prefix and timestamps) and that a lost key cannot be recovered.
- WebSocket streaming (`/var/stream/{task_id}`) accepts a session JWT only: a key in a query
  string would end up in access logs. Revisit before offering keys there.

## Not covered (decide separately)

- Per-user retention analytics (needs a user dimension in usage records: a privacy-policy
  decision).
- Key use over WebSocket, scoped keys (read-only / per-domain), and a per-key rate bucket.
