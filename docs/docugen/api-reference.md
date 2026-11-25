# pyvar API reference

This reference is derived from the route modules under `api/routes/`, the Pydantic models under `schemas/` and the middleware under `api/middleware/`. Every route is mounted under `/api/v1` unless noted (`config.py:29`, `main.py:196-251`). The running application also serves an interactive reference at `/docs`, `/redoc` and `/openapi.json` (`main.py:152-153`). Routes marked `include_in_schema=False` in the source are absent from that generated document and are described only here.

The per-function endpoint names for the eight compute domains are listed in [api-domain-endpoints.md](api-domain-endpoints.md).

## 1. Conventions

### Base URL

The hosted API is at `https://www.pyvar.com` (`README.md:27`). A local `uvicorn main:app --port 8000` serves the same routes on `http://localhost:8000` (`README.md:142-146`).

### Authentication

Send `Authorization: Bearer <credential>`. Two credentials are accepted on ordinary routes (`api/middleware/auth.py:13-18`):

| Credential | Looks like | Lifetime | Tier comes from |
|---|---|---|---|
| Session token (JWT) | returned by `GET /auth/verify`, `POST /auth/google`, `GET /billing/checkout/complete` | 60 minutes | its claims |
| API key | `pyvar_` followed by random characters | one year by default (`README.md:29-30`) | the database, cached briefly |

Narrower tokens exist for single purposes and are refused everywhere else because they carry an `aud` claim: the stream token (`pyvar-stream`), the admin token (`pyvar-admin`) and the trial ticket (`pyvar-trial`) (`api/middleware/auth.py:45-48`). Key-management routes accept only a session token, so a leaked key cannot mint more keys (`api/routes/auth.py:333-336`, `CLAUDE.md:229-231`).

### Optional client label

Send `X-Pyvar-Client: <name>/<version>` to label a call. The server matches the name against an allowlist, records `other` for unknown names and never ties it to a user (`api/middleware/usage.py:22-24`, `pyvar-client/README.md:39-42`).

### Status codes seen across the API

| Code | Meaning | Source |
|---|---|---|
| 200, 202 | success; 202 for an accepted VaR job | `api/routes/var.py:179-183` |
| 204 | key revoked | `api/routes/auth.py:389` |
| 400 | bad Stripe signature or an unpaid checkout session | `api/routes/billing.py:366-367`, `:408-410` |
| 401 | missing, invalid, revoked or expired credential | `pyvar-client/README.md:75` |
| 403 | simulation count above the tier cap; non-internal caller on an internal route | `api/routes/var.py:216-224`, `api/routes/internal.py:89-90` |
| 404, 409 | missing user or key; conflicting state such as a duplicate Pro checkout | `api/routes/billing.py:277-288`, `api/routes/auth.py:346-353` |
| 422 | request validation error; the body stays renderable for NaN and Infinity | `main.py:161-162` |
| 429 | rate limit or monthly cap; the text names the cap and carries `Retry-After` | `api/middleware/rate_limit.py:74-80`, `pyvar-client/README.md:77` |
| 503 | audit write failed, queue dispatch failed, billing not configured, feature switched off | `api/routes/var.py:283-286`, `:317-320`, `api/routes/billing.py:65-67`, `api/assistant/routes.py:7-9` |

### Quotas

Limits per tier come from one table (`api/tiers.py:75-142`):

| Tier | Max `n_simulations` per request | Daily compute requests |
|---|---|---|
| free | 10,000 | 20 by default (`config.py:180`) |
| pro | 100,000 | 500 by default (`config.py:181`), plus monthly request and simulation caps |
| enterprise | 500,000 | exempt |
| internal | 500,000 | exempt |
| education | 100,000 | from settings, plus a per-minute burst cap and monthly caps |
| trial | 10,000 | 5 |

The compute quota is one account-wide bucket shared by every compute endpoint, not one per endpoint (`api/middleware/rate_limit.py:24-30`). Rate limiting fails open if Redis is unavailable (`api/middleware/rate_limit.py:48-52`).

## 2. VaR jobs (`/api/v1/var`)

Router: `api/routes/var.py:109`.

| Method and path | Auth | Source |
|---|---|---|
| `POST /var/compute` | session or key, compute quota | `api/routes/var.py:179-331` |
| `GET /var/result/{task_id}` | session or key | `api/routes/var.py:430-452` |
| `POST /var/stream-token/{task_id}` | session or key | `api/routes/var.py:713-748` |
| `WS /var/stream/{task_id}?token=` | stream token for this task, or a session JWT | `api/routes/var.py:751-` |

### POST /var/compute

Submits a Monte Carlo VaR job. Returns 202 with a `task_id`, or 200 with a cached result for an identical request (`api/routes/var.py:184-188`).

Request body, `VaRRequest` (`schemas/var.py:38-87`):

| Field | Type | Constraint | Default |
|---|---|---|---|
| `portfolio_value` | float | greater than 0 | required |
| `returns` | list of float | 30 to 10,000 items, all finite | required |
| `confidence_level` | float | between 0.90 and 0.9999 | 0.99 |
| `horizon_days` | int | 1 to 250 | 1 |
| `n_simulations` | int | 1,000 to `max_n_simulations` | `default_n_simulations` |
| `seed` | int or null | | 42 |

`max_n_simulations` is 500,000 and `default_n_simulations` is 10,000 (`config.py:145-148`). The `confidence_level` validator rejects values outside 0.90 to 0.9999 (`schemas/var.py:68-77`). A series containing NaN or infinity is rejected (`schemas/var.py:79-87`).

Response, `JobResponse` (`schemas/var.py:129-134`): `task_id`, `status` (default `pending`) and `message`.

Behaviour: the tier cap on `n_simulations` returns 403 (`api/routes/var.py:213-224`); Pro and education accounts also draw on a monthly simulation quota that returns 429 (`api/routes/var.py:233-256`); an education account draws from a shared monthly pool and falls back to free limits once it is spent (`api/routes/var.py:202-213`).

### GET /var/result/{task_id}

Returns `JobResultResponse` (`schemas/var.py:137-143`): `task_id`, `status`, `result` and `error`. `status` is one of `pending`, `started`, `success`, `failure` (`schemas/var.py:28-32`). Celery `RETRY` is reported as `pending` (`api/routes/var.py:394-401`).

When `status` is `success`, `result` is a `VaRResult` (`schemas/var.py:93-126`): `var_pct`, `var_abs`, `cvar_pct`, `cvar_abs`, `loss_dist`, `mu`, `sigma`, `n_simulations`, `confidence_level`, `horizon_days`, `s3_key`, `presigned_url` and `duration_ms`. Above `s3_result_offload_threshold` simulations, `loss_dist` is an empty list and `presigned_url` is set (`schemas/var.py:93-100`, `tasks/var_task.py:420-423`).

Caching headers: a successful result is sent with `Cache-Control: public, max-age=3600`, every other state with `no-store` (`api/routes/var.py:443-451`).

Any authenticated caller who knows a `task_id` can read its result. There is no per-user ownership check, by design (`api/routes/var.py:738-741`, `api/routes/var.py:767-773`).

### POST /var/stream-token/{task_id}

Exchanges the caller's key or session for a token that opens the result stream of this one task. `task_id` must match `^[A-Za-z0-9_-]+$` and be 1 to 64 characters (`api/routes/var.py:726`). The response is `StreamTokenResponse` (`schemas/var.py:146-151`): `task_id`, `token` and `expires_in`. The token lasts `var_stream_token_ttl_seconds`, 60 seconds (`api/routes/var.py:718-722`). The response carries `Cache-Control: no-store` (`api/routes/var.py:743`).

### WS /var/stream/{task_id}

Open with `?token=<stream token>`. The server accepts, then validates the token. Close codes in the source:

| Close code | Reason | Source |
|---|---|---|
| 1008 | `Missing token`, or `Invalid or expired token` | `api/routes/var.py:798-808` |
| 1013 | open-stream cap reached for the server or for the account | `api/routes/var.py:817-824` |

If the job is already finished the server sends the `JobResultResponse` as JSON text and closes (`api/routes/var.py:810-815`). Otherwise it waits, bounded by `var_stream_max_wait_seconds` (`api/routes/var.py:837`).

## 3. Compute domains

Eight routers share one pattern: one POST endpoint per engine function, protected by `enforce_compute_rate_limit` as a router-level dependency (`main.py:217-234`).

| Prefix | Router | Endpoints | Examples |
|---|---|---|---|
| `/api/v1/market-risk` | `api/routes/market_risk.py:252` | 71 | `historical_simulation_var`, `frtb_ima_expected_shortfall`, `kupiec_pof_test` |
| `/api/v1/credit-risk` | `api/routes/credit_risk.py:216` | 55 | `credit_var_monte_carlo`, `cds_pricing_isda_standard`, `ifrs_9_lifetime_ecl_stage_2_3` |
| `/api/v1/derivatives` | `api/routes/derivatives.py:223` | 62 | `black_scholes_european_option`, `heston_stochastic_volatility_model` |
| `/api/v1/liquidity` | `api/routes/liquidity.py:185` | 40 | `liquidity_coverage_ratio_lcr`, `net_stable_funding_ratio_nsfr` |
| `/api/v1/operational` | `api/routes/operational.py:169` | 44 | `loss_distribution_approach_lda`, `kri_trend_analysis` |
| `/api/v1/portfolio` | `api/routes/portfolio.py:193` | 50 | `mean_variance_optimisation`, `sharpe_ratio`, `maximum_drawdown` |
| `/api/v1/regulatory` | `api/routes/regulatory.py:131` | 30 | `basel_iii_cet1_ratio`, `emir_margin_requirement` |
| `/api/v1/alm` | `api/routes/alm.py:128` | 33 | `economic_value_of_equity_eve`, `irrbb_standardised_framework` |

The endpoint counts are the number of path declarations that matched a `docugen-src grep` over each module; together they come to 385, which equals the README's function count (`README.md:12`).

A call is `POST /api/v1/<domain>/<function_name>` with a JSON body. Per-function request and response models live in the per-domain modules of `schemas/` (for example `schemas/market_risk.py`, `schemas/derivatives.py`, `schemas/alm.py`). Not determined from the source: the field list of each function. The canonical catalogue, with parameters, summaries and a `caveat` field, is `portal/functions.json` (`README.md:17-19`, `README.md:259-262`).

Engine input errors map to HTTP 422 through an explicit exception tuple in each router (comment at `api/routes/alm.py:130`, same pattern in the other seven modules).

The trial lane reaches the same endpoint coroutines, so a whitelisted function behaves the same through `/trial/run/{function}` (`api/routes/trial.py:15-17`).

## 4. Authentication and keys (`/api/v1/auth`)

Router: `api/routes/auth.py:73`. Request and response models are in `schemas/auth.py`.

| Method and path | Auth | Body | Response | Source |
|---|---|---|---|---|
| `POST /auth/register` | none; per-IP limit | `{"email": ...}` | 202 `RegisterResponse` | `api/routes/auth.py:175-181` |
| `GET /auth/verify?token=` | single-use token from the e-mailed link | none | `VerifyResponse` | `api/routes/auth.py:253` |
| `POST /auth/google` | none; per-IP limit | `{"id_token": ...}` | `VerifyResponse` | `api/routes/auth.py:436-441` |
| `POST /auth/api-keys` | session token | `{"name": ...}` | 201 `ApiKeyCreated` | `api/routes/auth.py:333-367` |
| `GET /auth/api-keys` | session token | none | `ApiKeyList`, up to 50 keys, newest first | `api/routes/auth.py:370-386` |
| `DELETE /auth/api-keys/{key_id}` | session token | none | 204 | `api/routes/auth.py:389-409` |

Details:

- **Register** doubles as sign-in. It returns the same 202 and the same message for every outcome, so it cannot reveal which addresses have accounts (`schemas/auth.py:35-38`, `api/routes/auth.py:23-28`). The address is trimmed and lower-cased (`schemas/auth.py:29-32`). Known disposable domains are skipped without a database write or an e-mail (`api/routes/auth.py:183-191`).
- **Verify and Google** return `VerifyResponse` (`access_token`, `token_type` `bearer`, `tier`): a 60-minute session token, not the credential to paste into a plugin (`schemas/auth.py:41-49`). A Google sign-in links to an existing account by e-mail and never sends a verification link (`api/routes/auth.py:441-456`).
- **Create key** takes `name` of 1 to 64 characters, default `default` (`schemas/auth.py:60-69`). It returns the secret once in `key`. It answers 409 when the account has reached the active-key cap or the total-key cap (`api/routes/auth.py:346-353`). The key expires after `api_key_default_expiry_days` (`api/routes/auth.py:361`). Only the key's SHA-256 is stored (`storage/models.py:164-174`).
- **List keys** returns `ApiKeyInfo`: `id`, `name`, `prefix`, `created_at`, `expires_at`, `last_used_at`, `revoked_at`, never the secret (`schemas/auth.py:72-81`).
- **Revoke** is idempotent, keeps the row, and answers 404 for a key that is not the caller's (`api/routes/auth.py:393-409`).

## 5. Billing (`/api/v1/billing`)

Router: `api/routes/billing.py:98`. Response models are in `schemas/billing.py`.

| Method and path | Auth | Response | Source |
|---|---|---|---|
| `POST /billing/checkout` | session or key | `CheckoutResponse` with `checkout_url` | `api/routes/billing.py:243-316` |
| `POST /billing/portal` | session or key | `PortalResponse` with `portal_url` | `api/routes/billing.py:319-348` |
| `GET /billing/checkout/complete?session_id=` | none; the Stripe session is verified server to server | `CheckoutCompleteResponse` | `api/routes/billing.py:351-383` |
| `POST /billing/webhook` | Stripe signature, no bearer token | `{"received": true}` | `api/routes/billing.py:386-415` |

- **Checkout** answers 409 for an account already on Pro and for enterprise or internal accounts, and 503 "not configured" where billing is unavailable or checkout is restricted to allowed accounts (`api/routes/billing.py:247-263`, `:279-288`). It is monthly-only, with one Stripe price id (`api/routes/billing.py:11-14`).
- **Portal** answers 409 when the account has no Stripe customer yet (`api/routes/billing.py:338-342`).
- **Checkout complete** answers 400 unless the Stripe session is paid, and returns a fresh session token carrying the tier read from the database. The webhook may land a moment later, so a client that still sees `free` should ask again (`api/routes/billing.py:357-383`).
- **Webhook** verifies the signature against `stripe_webhook_secret` and answers 400 on a bad one; an event type it does not handle is acknowledged with `{"received": true}` (`api/routes/billing.py:403-414`). Handling is idempotent on the Stripe event id (`api/routes/billing.py:68-71`). Two events change a tier (`api/routes/billing.py:51-57`).

## 6. Trial lane (`/api/v1/trial`)

Router: `api/routes/trial.py:79`, `include_in_schema=False`. No account is needed.

| Method and path | Purpose | Source |
|---|---|---|
| `POST /trial/challenge` | hands out a signed proof-of-work challenge | `api/routes/trial.py:272` |
| `POST /trial/ticket` | exchanges a solved challenge for a 72-hour ticket | `api/routes/trial.py:305` |
| `POST /trial/run/{function}` | runs one whitelisted function inline for a ticket holder | `api/routes/trial.py:378` |

Limits: 5 calls a day per ticket (`api/tiers.py:133-141`); one call at a time per API task with a hard deadline, answered 504 when exceeded (`api/routes/trial.py:17-25`). Refusals for a switched-off lane, a spent budget, a used-up ticket, a busy task or a bad proof of work share one 429 `trial_exhausted` body, with `Retry-After` varying by reason (`api/routes/trial.py:9-14`). The lane is off until the Redis key `pyvar:trial:on` is set (`main.py:236-239`). The whitelist has 30 functions (`CLAUDE.md:90`). The request and response bodies of the three routes were not read in detail: not determined from the source here.

## 7. Portal assistant (`/api/v1/assistant`)

Router: `api/assistant/routes.py:69`.

`POST /assistant/ask` (`api/assistant/routes.py:72-93`). Open to anonymous callers; a bearer credential, if sent, is validated and picks the tier (`api/assistant/routes.py:10-13`, `main.py:242-245`).

Request, `AskRequest` (`schemas/assistant.py:36-43`), unknown fields rejected:

| Field | Type | Constraint |
|---|---|---|
| `question` | string | 1 to 500 characters after trimming |
| `function` | string or null | up to 100 characters; ignored unless it is a catalogue name |
| `history` | list of `{q, a}` | at most 3 turns; `q` up to 500, `a` up to 1,500 characters |

Response, `AskResponse` (`schemas/assistant.py:46-56`): `answer`, `source` (`live` or `static`), `model_tier` (a family label, never a model id), `functions`, `suggested_parameters` and `request_id`.

Dependency order, fixed: availability (switches, kill switch, spend cap), model client, concurrency slot, per-caller quota (`api/assistant/routes.py:11-13`, `:76-83`). The route answers 503 `assistant_disabled` while `assistant_typed_enabled` is off (default off, `config.py:267`), and 503 `assistant_unavailable` on an unexpected error (`api/assistant/routes.py:7-9`, `:22-24`). A question is never logged or stored (`api/assistant/routes.py:16-19`).

## 8. Public data and system routes

| Method and path | Notes | Source |
|---|---|---|
| `GET /public/status.json` | unauthenticated, per-IP limit, S3-backed | `api/routes/public_data.py:72` |
| `GET /public/demo-result.json` | unauthenticated, per-IP limit, S3-backed | `api/routes/public_data.py:77` |
| `GET /public/config` | unauthenticated, reports assistant availability and bank version | `api/routes/public_data.py:82`, `assistant/README.md:63-64` |
| `GET /health` | unauthenticated; returns `status`, `app`, `env` | `main.py:254-256` |
| `GET /docs`, `/redoc`, `/openapi.json` | generated documentation | `main.py:152-153` |
| `GET /metrics` | registered by the Prometheus instrumentator | `main.py:62-74` |
| `GET /assistant/bank/...` | static answer-bank files with `Cache-Control: public, max-age=3600` | `main.py:263-267`, `assistant/README.md:64-65` |

The `/public/*` routes have no `/api/v1` prefix (`main.py:248-251`).

## 9. Service and admin routes (`/api/v1/internal`)

Router: `api/routes/internal.py:73`.

| Method and path | Auth | Purpose | Source |
|---|---|---|---|
| `POST /internal/suppress-email` | session JWT with tier `internal`; 403 otherwise | flag a user's address as bounced or complained, called by the SES suppression Lambda | `api/routes/internal.py:78-119` |
| `GET /internal/token-report` | `get_current_user` | issued-today and cumulative verified-account counts for the daily report | `api/routes/internal.py:122-162` |
| `POST /internal/admin/education/grant` | admin token | give a verified free account education access | `api/routes/internal.py:176-195` |
| `POST /internal/admin/education/extend` | admin token | move an education end date out, at most 12 months from today | `api/routes/internal.py:198-204` |
| `POST /internal/admin/education/revoke` | admin token | end education access | `api/routes/internal.py:220` |
| `GET /internal/admin/education/list` | admin token | list education accounts | `api/routes/internal.py:236` |
| `POST /internal/admin/education/suspend-all` | admin token | suspend all education accounts | `api/routes/internal.py:257` |
| `POST /internal/admin/education/tidy` | admin token | housekeeping; dry run unless the body says `apply` | `api/routes/internal.py:270` |
| `POST /internal/admin/accounts/erase` | admin token | erase an account at its holder's request; dry run unless `apply` | `api/routes/internal.py:286` |
| `POST /internal/admin/accounts/export` | admin token | read-only copy of one account's data | `api/routes/internal.py:317` |
| `POST /internal/admin/audit/cleanup` | admin token | six-year clean-up of `var_jobs` and `billing_events`; dry run unless `apply` | `api/routes/internal.py:357` |
| `POST /internal/admin/billing/checkout-allow` | admin token | allow an account to reach Stripe checkout where it is restricted | `api/routes/internal.py:378`, `api/routes/billing.py:250-253` |

The admin token has audience `pyvar-admin`, lasts 10 minutes and is signed by operator scripts. A session JWT, an internal JWT, an API key and a stream token are all refused. All `/admin/*` routes are kept out of the public OpenAPI document. `grant` and `extend` answer 503 while `education_tier_enabled` is off, and the other admin routes always work (`api/routes/internal.py:21-32`).

## Sources

main.py
config.py
README.md
CLAUDE.md
api/routes/var.py
api/routes/auth.py
api/routes/billing.py
api/routes/trial.py
api/routes/internal.py
api/routes/public_data.py
api/routes/market_risk.py
api/routes/credit_risk.py
api/routes/derivatives.py
api/routes/liquidity.py
api/routes/operational.py
api/routes/portfolio.py
api/routes/regulatory.py
api/routes/alm.py
api/assistant/routes.py
api/middleware/auth.py
api/middleware/rate_limit.py
api/middleware/usage.py
api/tiers.py
schemas/var.py
schemas/auth.py
schemas/billing.py
schemas/assistant.py
storage/models.py
tasks/var_task.py
assistant/README.md
pyvar-client/README.md
