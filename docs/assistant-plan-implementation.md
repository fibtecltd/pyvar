# Plan 2: implementing the settled design (answer bank + live agent + watchdog)

Status: draft by the planning fork, 2026-11-10. Read-only on the repo. Every repo fact below cites `path:line`; items marked **(unverified)** were not read.
"Free tier diagram" is the shared skeleton: the bank for menus, the gateway and a live agent for typed questions. Tiers differ only in the live agent model, quota and gate.

## Decisions taken (2026-11-11)
Filippo accepted the review's recommendations "for now". They replace the "decisions needed" list in the summary below where they overlap.

- **Release 1 is menus only**: the bank is built by an agent run (option A, as in Phase 0) and committed to git; the typed box stays off.
- **Release 2: refresh the bank by GitHub Actions with an AWS OIDC role (option B)**, if the OIDC role is accepted when it is proposed; otherwise option C.
- **Bank writer: Sonnet**, by rule M1 of the measurement plan (run A, results 9.17), to be confirmed by run B's Haiku grader control. A full build costs about $13.6 before regenerations (Sonnet $6.0 plus 1,154 Opus verdicts $7.6) against about $8 with Haiku. With the v4 prompt about a quarter of first drafts fail the `no_source_claims` wording check; regeneration with feedback is not yet tested.
- **Pins use CUSUM** (section 8), **confirmed by Filippo on 2026-11-11**. Revisit with real traffic.
- **JSON reply, no token streaming** (section 4).
- **A person still reads a random sample of at least 40 bank answers per release**, outside the request path. The recall-check rule that makes Opus usable as the gate assumed it, and nothing automatic replaces it (the watchdog sees live typed answers only). Section 12 is written to match.
- **Open:** the key for the bank build; the pro tier's pricing (not defined yet, 2026-11-11); Fable's id and prices; the privacy wording and Anthropic's API retention terms; the egress check.

## Summary (10 lines)

1. Decisions needed from Filippo: (a) bank storage: repo-committed (recommended for the first release) or S3-served (needed for full no-human refresh); (b) accept CUSUM instead of "3 of 20" for pins (section 8); (c) typed questions reopen the privacy decision (plan 9, decision 3): privacy.html:86-87 and terms.html:94 say the opposite today; (d) the key for the bank build (dev key was only approved for evals); (e) token streaming or not (section 4).
2. Total effort: about 31 to 39 working days across 8 PRs; the first user-visible release (bank only, PRs 1 and 2) is about 10 to 12 days. Run cost: bank build about $9 for a full run, a few cents per changed function.
3. Pipeline: PR 1, 2, 3, 4, 5, 6, 7 each **start a CodePipeline run** (new top-level dir, `portal/`, `api/`, `pyvar-cdk/`, root files). Only PR 8 (docs/tests/scripts only) is pipeline-safe. Per-PR statement in section 10.
4. **The budget idea is workable only as a tripwire for gross failure**, not as a guarantee of the 4% tolerance (section 8). "3 of 20 in a sliding window" falsely pins busy healthy functions: at 7 audited answers a day, 0.59 false pins per function-month and 14% of days pinned; CUSUM: 0.04 and 0.9%.
5. Long-tail functions (385 active, about 0.7 audited answers a day each) take 27 days to fill one window of 20. Coverage there is thin by arithmetic.
6. Design inconsistency: guardrails after generation defeat token streaming. Plan: JSON reply (or one SSE message), not streamed tokens.
7. Design inconsistency: `scripts/` is pipeline-excluded, so prompts or graders imported from `scripts/assistant_eval` could change in git without changing production. Move the shared kernel into a top-level `assistant/` package.
8. No DB migration is needed (Redis counters, Prometheus, S3 or git). One would be needed only for per-user usage history (section 9).
9. Existing CI has no AWS access and no secrets (no `secrets.` in `.github/workflows`, no AWS credentials or role in `pyvar-cdk`; the only OIDC in the repo is GitHub-to-PyPI trusted publishing): the no-human bank release is net-new infrastructure either way.
10. Biggest risks: typed accuracy is unmeasured (Plan 1); audit coverage; the privacy copy; the Anthropic SDK entering the production image.

## 1. Settled design, restated and checked

- Menus (explain, when, compare): 1,154 static answers (385 + 385 + 384, `cases.py --all`), written by Haiku 5.5 with the v4 prompt, checked by graders then Opus, up to 2 regenerations, else static text from the record. Same for every tier. No model call at request time.
- Typed questions: `POST` to a gateway (auth to tier, per-tier quota, scrub, pin check), live agent by tier (free Haiku; pro Sonnet or Opus; enterprise Opus or Fable, pending Plan 1), read-only tools, guardrails, one retry, static fallback.
- Watchdog: fixed daily audit budget, pin flag in Redis, global alert.

Inconsistencies found against the repo (plain):

1. **Streaming vs guardrails.** The gateway cannot stream model tokens if graders (and for enterprise a gate model) must pass the whole answer first. Showing tokens and retracting a wrong claim is worse than waiting. Recommendation: a JSON reply, with an optional SSE of status events ("looking up `lcr`") then one `answer` event. This also removes plan 10's unverified "SSE through CloudFront and ALB unbuffered" (`docs/plan-portal-ai-assistant.md` section 10).
2. **Quotas differ from the existing compute limits.** `config.py:161-164`: unauth 60 an hour, free 10 a day, pro 500 a day; `rate_limit.py:106` exempts enterprise and internal entirely. The assistant quotas (plan 4.5: anonymous 10 an hour per IP, free 40, pro 200, enterprise 500 a day) need their **own scope** that does not exempt enterprise.
3. **Auth cannot serve anonymous visitors as written.** `auth.py:40` is `HTTPBearer()` with `auto_error` defaulting to true, so a missing header is rejected before any limit runs. An optional-user dependency is needed (new code beside `get_current_user`, `auth.py:144`).
4. **`scripts/` is pipeline-excluded** (`pipeline_stack.py:1053`). A merge that changes only `scripts/assistant_eval/prompts.py` would not deploy, so git and production would disagree until some unrelated deploy. Section 3 fixes it.
5. **The Phase 0 text says visitors type nothing** (plan section 1a, decision 3 closed "by design"). Typed questions reverse that. `portal/privacy.html:86-87` says "our own backend never sends your portfolio data ... to Anthropic" and `terms.html:94` says results are not AI. Both need new wording **before** the flag goes on.
6. Plan section 7 says phases 1 to 3 "were written for a runtime chat route (option A)" and are "to be rewritten". This plan is that rewrite.
7. The bank key and the eval key: only the DEV key was approved, for evals. A production bank build needs an explicit decision (open question d).
8. Model id: the design says "Fable 5.1"; the current model list has `claude-fable-5-2`. And Fable has no price in `cost.py`.

## 2. Component to repo-path map (verified)

| Component | Where it lives today | Change |
|---|---|---|
| App factory, routers, static mount | `main.py:94-217`; portal served by `_PortalStaticMount("/", StaticFiles(directory=PORTAL_DIR, html=True))` | add `assistant_router`; add `/api/v1/assistant` (already under `cfg.api_v1_prefix`, a reserved prefix, `main.py:58-66`) |
| Reserved path prefixes | `main.py:58-66` | no change (assistant route is under `/api/v1`); the bank under `/assistant/bank/` is a static path and must **not** be reserved |
| Settings | `config.py` (single source; no assistant keys today, grep empty) | add `assistant_*` keys (section 9) |
| Tier and token | `api/middleware/auth.py:46-70` (`TokenPayload`, tiers free, pro, enterprise, internal); `create_access_token` `:213` | optional-user dependency; tier read from DB for keys is already handled (`api_keys.py`) |
| Rate limit | `api/middleware/rate_limit.py:106-241` (slowapi `Limiter` over Redis, plain FastAPI dependencies, `enforce_compute_rate_limit :160`, `enforce_public_rate_limit :226`, `get_trusted_client_ip :129` index -2 for CloudFront + ALB) | new `enforce_assistant_rate_limit`, same pattern, own prefix, no tier exemption |
| Redis | `storage/redis_client.py:redis_url()`; async client built lazily in `api/routes/caching.py:69-80` | a small async helper in `assistant/store.py` using the same URL helper |
| Secrets | `api_stack.py:248-287` import by name, `grant_read(task_role)`; app resolves at startup (`billing._resolve_stripe_secrets :165`, `observability/setup.py:74-103`); deliberately **not** ECS `secrets={}` | add `pyvar/{env}/anthropic-api-key` the same way (plan 4.8) |
| Public flags | `api/routes/public_data.py` `/public/config` returns `google_sign_in_enabled`, `google_client_id` | add `assistant_enabled`, `assistant_bank_version` (widget hides itself when false) |
| Widget | `portal/pyvar.js` (41,604 bytes): `API_BASE` `:15`, search panel with lazy `functions.json` fetch `:500-560`, Try-it `:899`, `DOMContentLoaded` init `:928` | `portal/assistant.js` (new, lazy-loaded), launcher injected from `initSearch`-style init; keep `pyvar.js` change small |
| Catalogue | `portal/functions.json` 990,448 bytes, 385 entries (keys description, display_name, domain, formula, name, params, path, summary...) | source of truth for records, tools and drift hash |
| Eval harness | `scripts/assistant_eval/{prompts,graders,cases,cost,judge,run_eval,body_schema,...}.py` | kernel moves to `assistant/` (section 3) |
| Drift-test pattern | `tests/test_skills_sync.py` (re-runs `scripts/sync_skills.py`, fails until regenerated); `scripts/sync_portal_seo.py`, `tests/test_portal_links.py` | `tests/test_assistant_bank.py` (section 5) |
| Egress guard | `tests/test_data_residency.py::test_check7` scans `engine api tasks` for HTTP client imports (`:298-343`); `anthropic` is not in its regex | keep gateway in `api/assistant/`; add an explicit test that only `assistant/client.py` imports `anthropic` |
| Metrics | `observability/setup.py:26-48` (two `Histogram`s, structlog `:183`, Sentry `:109`), `/metrics` reserved | add counters and histograms there |
| Image | `Dockerfile:139` `COPY . .` (portal and scripts are in the image); `requirements.txt` has no `anthropic` | `anthropic==2.6.0` pin (as in `scripts/assistant_eval/requirements.txt`) into root `requirements.txt` |
| Pipeline trigger | `pipeline_stack.py:1053-1084` excludes 8 dirs from the push filter | see section 11 |
| Edge | `edge_stack.py:409-435`: default behaviour ALLOW_ALL, `compress=True`, `api_cache_policy` (default TTL 0, max 1 h, keyed on Authorization and Cache-Control, `:308-324`); extra behaviours only `/health`, `/docs`. WAF in `alb_waf_stack.py` (rules at priorities 10, 20, 30 `RateLimitPerIp`) | see section 9 |
| Static files cache headers | no `Cache-Control` set in `main.py` or `api/middleware/*` (grep empty) | the bank needs one (section 5) |
Not read **(unverified)**: `observability/setup.py` instrumentator wiring; `api/middleware/usage.py` columns; `alerts_stack.py` alarm patterns beyond the four `Alarm(` calls.

## 3. New modules and responsibilities
Top-level **`assistant/`** (pure functions, no FastAPI, no network except `client.py`) so eval and production share one kernel:

- `assistant/prompts.py`, `graders.py`, `cost.py`, `records.py` (`trim_record`), `body_schema.py`: moved from `scripts/assistant_eval/` with `git mv`; `scripts/assistant_eval/` keeps thin re-export shims so Phase 0 tests and the harness still import. This is PR 1 and changes no behaviour.
- `assistant/client.py`: the **only** module importing `anthropic`; retries, served-model check (as `run_eval.call_model`, `run_eval.py:86-123`), usage and cost, a hard per-call timeout; takes only scrubbed strings.
- `assistant/scrub.py`: removes `pyvar_` keys (`"pyvar_" + token_urlsafe(32)`, 43 chars of `[A-Za-z0-9_-]`, verified `api_keys.py:45,75`), JWT shapes (`eyJ...` three dot-separated segments; HS-algorithm tokens, `auth.py:88,117`), long hex and base64 runs, and email addresses; replaces with a marker. Applied to the question before any model call and to the answer before it is returned.
- `assistant/bank.py`: bank build (writer, graders, Opus verdict, regeneration ladder, static fallback), manifest, hashes. Used by a CLI `python -m assistant.bank`.
- `assistant/agent.py`: the live loop: system prompt, tools, at most 4 tool turns, token cap.
- `assistant/tools.py`: `search_functions` (Fuse-like server-side scoring over `functions.json`), `get_function` (returns `trim_record`), `propose_parameters` (validated against the catalogue's parameter types and bounds via `body_schema`).
- `assistant/guardrails.py`: `grade_typed` (union of tool records, question numbers whitelisted, typed length bound), gate interface (enterprise: a different model), one retry, static fallback builder.
- `assistant/watchdog.py`: allocator, audit scheduling, verdict recording, CUSUM, pin flag, alerts.
- `assistant/store.py`: Redis access (async) for quotas' companion keys, pins, counters.
`api/assistant/`: `routes.py` (`POST /api/v1/assistant/ask`), `deps.py` (optional-user, `enforce_assistant_rate_limit`), `schemas` in `schemas/assistant.py` (repo convention: `schemas/var.py`, `schemas/derivatives.py`).
`portal/assistant.js` and `portal/assistant.css` (or a section of `pyvar.css`): launcher, menus, typed box, escaping; reads the bank, calls the gateway.
`tests/test_assistant_*.py`.
Why a top-level package: one source for eval and production; a new dir triggers the pipeline, which is **correct**, since it changes production. `test_check7` roots (`engine api tasks`) should gain `assistant` (widening a guard, not relaxing it).

## 4. Gateway API contract
`POST /api/v1/assistant/ask` (JSON; optional `Authorization: Bearer <session JWT | pyvar_ key>`; anonymous allowed)
Request:
```
{ "question": str (1..500 chars, trimmed),
  "function": str | null   (page context: a catalogue name),
  "history": [ {"q": str, "a": str} ] (max 3 turns, kept in the browser, scrubbed again server-side) }
```
Response 200: `{"answer": str, "source": "live"|"static", "model_tier": "haiku"|"sonnet"|"opus"|"fable",
"functions": [names], "suggested_parameters": {...}|null, "request_id": str}`. `source:"static"` means a pin, a guardrail failure or a budget stop produced the answer from catalogue text. The model id is not exposed for free users beyond `model_tier`.
`suggested_parameters`: only when `propose_parameters` validated; the widget shows "Apply to Try it" and never submits.
Errors: 400 empty or over-length; 401 bad token (an **API key is accepted** here: this route is not key management, `require_session` is not used; stream-token `aud` tokens stay refused, `auth.py:99-141`); 429 with `Retry-After` and which quota; 503 `assistant_disabled` or daily cap or provider outage, always with a static-answer hint, never a stack trace. Anthropic 5xx or refusal: one retry, then `source:"static"`.
Limits (placeholders from plan 4.5, a new scope): anonymous 10 an hour per IP (`get_trusted_client_ip`, `rate_limit.py:129`); free 40 a day; pro 200; enterprise 500; counters in Redis under `pyvar-ratelimit:assistant:*`. Global daily token cap as a circuit breaker (plan 4.5). Kill switch: `assistant_enabled` in `/public/config`; when false the route returns 503 and the widget shows the bank only.
Streaming: not for tokens. Option: `Accept: text/event-stream` returns `status` events and one final `answer` event. Recommendation: ship JSON first; SSE is a later, optional polish.
Order of work in the handler: auth and quota, scrub, pin check on `function`, agent loop, pin check on cited functions (replace by static if any pinned), guardrails (and enterprise gate), response, then (after the response) the audit decision. Logs carry request id, tier, function names, model tier, latency, token counts and outcome; **never the question or answer text**.

## 5. Bank layout, widget and drift
Layout (first release, committed to git): `portal/assistant/bank/<bank_version>/<function>.json` plus `manifest.json`.

- `<function>.json`: `{"explain": {...}, "when": {...}, "compare": {...}}`, each `{"text", "source": "model"|"static", "record_sha256", "verdict"}`; about 3 answers of up to 1,200 characters, so about 3 KB per function, **about 1.1 MB for 385 files** (an estimate from the character budgets, `prompts.py` `CHAR_BUDGET`). `compare` lists every sibling pair, so one file may hold several `compare` entries (384 total).
- `manifest.json`: `bank_version`, `prompt_version`, `grader_sha256`, `catalogue_sha256`, writer and judge ids, build date, counts (model, static, regenerated).
- `bank_version` = `<prompt_version>-<first 8 of catalogue_sha256>`; the directory name is the version so old bank files can sit beside new ones for rollback.
Widget reading: `GET /assistant/bank/<bank_version>/<function>.json` on first menu open (lazy, like `functions.json` at `pyvar.js:520`). It never loads all 385. `bank_version` comes from `/public/config`.
Caching: the static mount sets no Cache-Control (grep empty), CloudFront's policy has default TTL 0 and max 1 h (`edge_stack.py:308-324`). Without a header every bank read reaches Fargate. Fix: a small `StaticFiles` subclass for `/assistant/bank/` adding `Cache-Control: public, max-age=3600`; the version in the path makes files immutable, so a long `max-age` is safe. (Edge max is 1 h.)
Drift (`tests/test_assistant_bank.py`): (1) recompute `catalogue_sha256` from `portal/functions.json` and require it equals the manifest's, with the failure message "run `python -m assistant.bank --incremental`"; (2) for every function, `record_sha256` of its record equals the one stored in each answer (so a single edited function fails by name); (3) every served answer re-passes `graders.grade_prose` (a model-free re-check); (4) file sizes under a bound; (5) `static` count under 3% of answers (acceptance, section 12). Model for the pattern: `tests/test_skills_sync.py`.
Runtime safety: in release 1 the bank and the catalogue deploy in one image and the CI drift test guarantees they match. If the bank is later served from S3 (options C and D), the widget must show a bank answer only when the manifest's `catalogue_sha256` equals the deployed catalogue's (exposed as a 64-character value in `/public/config`); otherwise it shows catalogue text, so drift cannot reach a visitor.
Static text when the model cannot be trusted: built from the record (`graders.oracle_text`, verified in Phase 0 to pass 1,924 of 1,924).

## 6. Release pipeline (no human): options and recommendation
Inputs that force a rebuild: `portal/functions.json`, `assistant/prompts.py`, `assistant/graders.py`. A catalogue edit needs only the changed functions (record hash differs): 3 answers x (writer + verdict) about $0.02 per function, pennies. A prompt or grader change needs a full build, about $9 (Haiku $0.32 + 1,154 verdicts $8.19 + about 40 regenerations).
Why not CodeBuild per push: the push filter excludes 8 directories only; any other push would rebuild or re-check. Hash-gate it.

| Option | Key lives | Human | Pipeline cost | Rollback | Verdict |
|---|---|---|---|---|---|
| A. Agent run by Filippo (as Phase 0) | agent's Secrets Manager read | **yes** | none | git revert | fine for release 1, not "no human" |
| B. GitHub Actions on PRs touching the inputs, OIDC to AWS, bot commits the bank into the PR | new IAM OIDC role reading Secrets Manager (none exists for AWS; the only OIDC in the repo is PyPI trusted publishing, `id-token: write` in the `pyvar-*-publish.yml` workflows) | no | the merge runs one CodePipeline execution (it touches `portal/`) | git revert | good audit trail; needs new `infra/` work (OIDC provider, role) |
| C. Hash-gated CodeBuild started from the pipeline's pre-synth step (copy of the AMI-bake mechanism, CLAUDE.md section 11), writing to **S3**; widget and API read S3 | CodeBuild role reads Secrets Manager; key never leaves AWS | no | no extra run (the push already ran); build time added to the Synth stage | S3 object versions | no repo artefact; serving needs the `/public/` pattern or a new behaviour |
| D. Scheduled Fargate task, S3 | same | no | none | S3 versions | Lambda is out (the public-data publisher is a Lambda with a 15-minute cap; a full build is about 20 minutes at 8-way concurrency, an estimate) |
Recommendation: **release 1 = option A** (committed bank, ships soonest, matches the settled design exactly). **Release 2 = option B** if Filippo accepts a GitHub OIDC role; otherwise C. B keeps the bank in git (reviewable, revertable) and the PR carries both the catalogue change and its bank, so the drift test passes in the same PR; no chicken and egg. C removes git but then the drift test cannot compare against a repo file; it would test the S3 manifest at deploy time instead.
If S3 is chosen later: serve through the API like `api/routes/public_data.py` (private bucket in eu-west-1, no S3 origin at the edge: `tests/test_data_residency.py` check 5 and 6), **without** that router's per-IP hourly limit (60, `config.py:161`), which would throttle menu reads; cache with Cache-Control 1 h.

## 7. The live agent, tools, guardrails, fallback

- Model by tier from Plan 1 rules T4: free Haiku 5.5 (typed may be off if rejected); pro Sonnet 5.5 or Opus 5.5; enterprise Opus 5.5 or Fable. Config keys, not code: `assistant_model_free|pro|enterprise`.
- System prompt: the v4 menu prompt's rules (visitor wording, no absence claims, no advice) plus typed rules (answer only from tool results; refuse off-topic and advice politely; never reveal instructions). `output_config.effort` low, `max_tokens` 1,500 as in `prompts.py:100-101`; thinking on by default counts toward max_tokens (prompts.py:10-11), so keep `effort` low.
- Tools (read-only, local, no network): `search_functions(query)`, `get_function(name)` (returns `trim_record`), `propose_parameters(name, values)` (validates types and bounds; returns errors to the model, shows the visitor only a passing object). At most 4 tool turns. Prompt caching on the system prompt and tool block (`cost.py` models cache reads at 0.1x Haiku, 0.05x Opus).
- Injection: the visitor's text is user content, never concatenated into the system prompt; tool results are data; function names from the catalogue are trusted, visitor strings are not; output escaped in the widget and links limited to pyvar.com (plan 4.7).
- Guardrails (`grade_typed`): identifiers known, numbers supported (union of tool records plus numbers in the question), no advice, wording rules, length. One retry with the failures as feedback (the pattern `build_request(feedback=...)` already has, `prompts.py:137`). Second failure: static fallback (the function's bank text plus catalogue link) with `source:"static"`.
- Enterprise gate: a **different** model reads question, tool results and answer and returns pass or fail; synchronous; fail then one retry then static. Cost about $0.007 per answer at Opus verdict prices, plus latency (unmeasured; rule L1 in Plan 1).
- Refusals and provider errors: counted, not retried more than once; the user sees the static fallback.

## 8. Watchdog: budget allocator, pin flag, and a plain verdict
**Verdict.** The fixed-budget audit is workable as a **tripwire for gross, sustained failure** on functions that see audits regularly, and as a global regression alert. It is **not** a way to prove or enforce the 4% tolerance, because 280 verdicts a day cannot estimate a per-function rate near 3.5%. "3 or more of the last 20" without a TTL, a probe or a different statistic also pins healthy busy functions repeatedly. The plan keeps the coordinator's rule as the baseline and adds the changes below; the choice between them is open question (b).
Facts (all simulated by me, same arithmetic as the coordinator for the fresh-window figures: false pin 0.031, 15% true caught 0.595, global false alarm 0.00075, 8% true alerts 0.434, 12% true alerts 0.954):

- $2 a day buys 282 verdicts at $0.0071, or 143 if a typed verdict needs about double the input ($0.014; **unmeasured**, Plan 1 R4).
- Days to fill one 20-answer window at 280 audits a day: 385 active functions 27.5; 150 functions 10.7; 60 functions 4.3; 20 functions 1.4.
- **Multiple looks.** A sliding 3-of-20 rule on a healthy function (true 3.5%), pinned 7 days then probed with 20 audited answers, per function:

| Audited answers a day | 3-of-20: false pins a month | days pinned | CUSUM (k .10, h 2.5): false pins a month | days pinned |
|---|---|---|---|---|
| 0.7 | 0.06 | 1.5% | 0.00 | 0.1% |
| 2.8 | 0.25 | 5.9% | 0.01 | 0.3% |
| 7 | 0.59 | 13.8% | 0.04 | 0.9% |
| 20 | 1.29 | 30.4% | 0.10 | 2.4% |
- **Time to the first pin** (median days, true failing function): at 0.7 audits a day, true 15%: 26 (3-of-20) or 66 (CUSUM); true 30%: 12 or 17. At 2.8 a day: 15%: 7 or 14; 30%: 3 or 4. At 7 a day: 15%: 2 or 5; 30%: 1 or 2.
- Audited answers needed to pin (median): 3-of-20 18, 9, 5 at true 15%, 30%, 50%; CUSUM 31, 12, 6.
Recommendation: **CUSUM** (reference 3.5%, allowance 0.10, threshold 2.5) as the pin rule, with 3-of-20 kept as a fast trigger only for catastrophic runs, written as "4 flags in the last 8 audited". If the coordinator prefers plain 3-of-20, accept that busy functions spend about 6% to 30% of days pinned for nothing; a false pin degrades UX (static text), not safety.
**Allocator** (each UTC day; eligible = free and pro live answers; every number is a config key):

- Budget `assistant_audit_budget_usd_day` = 2.00, tracked in Redis as spent micro-dollars (`INCRBY` reserve at decision, correct after the verdict from real `usage` and `cost.py`). Stop when spent.
- Two pools. **Coverage pool 60%**: water-filling. Keep per-function audited counts for the day; audit an answer iff the function's count is below the level `tau`; recompute `tau` hourly as the largest k with sum over functions of min(k, expected answers per day) times verdict cost within the pool, using each function's trailing 7-day answer count. Selection depends on counts, not on outcomes, so audited samples are unbiased for each function. **Exposure pool 40%**: uniform random sampling at probability pool budget / (verdict cost x trailing 7-day eligible answers); gives an unbiased, traffic-weighted global rate without weights.
- **Strata by writer.** One global window of the last 200 exposure audits **per writer model**; a blended rate would hide a regression in the small tier. Alert when a writer's window flag rate exceeds 8% (false alarm 0.07% at 3.5%). Floor of 25% of the exposure pool per writer that has any traffic, so a small tier's window fills (about 2 to 5 days at the 110 exposure verdicts a day).
- **Multi-function answers** (typed answers cite several functions through tool calls): the audit counts for every function the agent fetched with `get_function`.
- **Enterprise**: answers are gated synchronously; audit 1% (config) of published enterprise answers; its "flag rate" is gate misses, and its alert is the gate's rejection rate above a config value.
- **Pin flag** (Redis `asst:pin:<function>`, value written by the watchdog, read by the gateway in microseconds, **TTL 7 days**, doubling to 28 on a repeat): pinned functions serve static answers and receive no new audits, so a **probe** follows expiry: the next 20 audited answers of that function are taken at 100% from the coverage pool; fewer than 3 flags unpin for good, otherwise re-pin with a doubled TTL. Seed pre-pins from the bank build's twice-failed list.
- **Global alert** (writer window above 8%): sets `asst:degrade:<writer>`; typed answers of that writer's tiers become static plus search results until the next 200 exposure audits (taken at 10% live probe traffic) fall to 5% or less. No human step.
- **No text retention.** The decision to audit is taken when the answer is produced, and the audit runs immediately after the response in the same process (a bounded `asyncio` task), holding question and answer only in memory. Redis keeps counts, function names, writer, tier, hour and a boolean; **no question, answer or verdict text** and no log lines with message text. If the container dies mid-audit, that audit is lost (acceptable). This avoids the 24-hour text store I had considered; if Filippo wants verdict text for debugging, that is a privacy change (open question).
- Verdict calls count the same way as writer calls in the daily token cap.
Cost: $2 a day is about $60 a month, plus enterprise sync gates (about $0.007 per enterprise answer).

## 9. Config and CDK
`config.py` additions (pydantic-settings; no `os.environ` elsewhere, CLAUDE.md section 7): `assistant_enabled=False`, `assistant_model_free|pro|enterprise`, `assistant_gate_model`, `assistant_quota_anon_per_hour`, `..._free_daily`, `..._pro_daily`, `..._enterprise_daily`, `assistant_daily_token_cap`, `assistant_audit_budget_usd_day`, `assistant_audit_enterprise_rate`, `assistant_pin_ttl_days`, `anthropic_api_key` (resolved at startup, never from env in prod).
Secret: `pyvar/{env}/anthropic-api-key`, imported with `Secret.from_secret_name_v2`, `grant_read(task_role)` in `api_stack.py` next to Sentry and Stripe (`api_stack.py:248-287`), fetched by the app lazily so that a missing secret never blocks task launch (the reason given in that file's comment, `:233-244`). One key per env (plan 4.8).
`infra/assistant-edge` PR (needs `cdk diff` in the description, CLAUDE.md section 8):

- CloudFront: the default behaviour already allows POST (`ALLOW_ALL`, `edge_stack.py:413`) and its cache policy does not cache POST, so `/api/v1/assistant/*` works. If SSE is ever added, add a behaviour for the path with `compress=False` (the default has `compress=True`, `:416`).
- WAF: a stricter per-IP rate rule scoped to the path, and exclude the path from the aggregate rule so assistant abuse cannot block compute users (`alb_waf_stack.py` rules at priorities 10, 20, 30; `edge_stack.py` has its own set). Edge stack is us-east-1 on purpose: do not move it.
- Alarms (`alerts_stack.py` has four `Alarm(` calls): daily tokens, 5xx, refusal rate, audit spend near the budget.
- No Redis change. Outbound to `api.anthropic.com` needs internet egress: the VPC has NAT gateways and `PRIVATE_WITH_EGRESS` subnets (`network_stack.py:48,57`), and the API already calls Stripe and Sentry, so egress very likely exists **(unverified: that the API task runs in those subnets)**. CLAUDE.md section 3.4 only forbids direct internet routes for SQS, ECR, S3 and Secrets Manager; keep those on their endpoints. NAT data cost for a few KB per call is negligible.
Observability: Prometheus counters and histograms beside `observability/setup.py:35-48`: tokens in, out, cache read, by model and action; latency per source; tool calls; refusals; rate-limit hits; pins set and cleared; audit spend; guardrail failures by check; static fallback share. Alert if `cache_read_input_tokens` is zero across repeated requests. structlog events with `extra={}`; Sentry with no message content (the sub-processor row already says "configured not to include request content by default", `privacy.html:106`).
Privacy and terms (must merge before the flag goes on; plan 4.6): `privacy.html` section 5 and the sub-processor table get an Anthropic row (sees: the visitor's typed question after scrubbing, function names, answers the model wrote; nothing from computations; no key or token); state retention **(unverified: read Anthropic's current API retention terms first)**; `terms.html` an AI-assistant clause. The scrub is a privacy control, so its tests are acceptance tests.
DB: **no Alembic migration** for any of the above. A migration is needed only if per-user usage history is wanted: `api/middleware/usage.py` writes `api_usage` rows **(unverified columns)**; adding `route` or `kind` would need one (CLAUDE.md section 3.3). Not recommended for v1; Redis counters and Prometheus suffice.

## 10. Phases (separate PRs; one branch per PR from latest `origin/master`)

| # | Branch | Content | Effort | CodePipeline run |
|---|---|---|---|---|
| 1 | `feat/assistant-core` | move kernel to `assistant/`, shims, tests, widen `test_check7` roots | 1.5 days | **yes** (new top-level dir) |
| 2 | `feat/assistant-bank` | bank builder, committed bank (agent run, about $9), `portal/assistant.js` menus, `/public/config` flag, drift test, cache header | 8 to 10 days | **yes** (`portal/`, `api/`) |
| 3 | `feat/assistant-gateway` | route, optional auth, quota scope, scrub, client, agent, tools, guardrails, config, metrics, tests; flag off | 7 to 9 days | **yes** (`api/`, `config.py`, root `requirements.txt`) |
| 4 | `infra/assistant-edge-secret` | secret import and grant, WAF path rule, alarms, egress check, `cdk diff` | 3 to 4 days | **yes** (`pyvar-cdk/`) |
| 5 | `feat/assistant-privacy-terms` | privacy.html, terms.html wording, typed box on | 1 day plus review | **yes** (`portal/`) |
| 6 | `feat/assistant-watchdog` | allocator, audits, CUSUM, pins, degrade flag, tests with seeded simulation | 5 to 7 days | **yes** (`assistant/`, `api/`) |
| 7 | `infra/assistant-bank-release` | option B or C | 5 to 6 days | **yes** (`.github` is excluded but OIDC needs `pyvar-cdk/`) |
| 8 | `docs/assistant-design-tiers` | plans, results, runbooks only | 0.5 day | **no** (`docs/` and `tests/` only are in the excluded list) |
Order: 1, 2 (release 1: menus for everyone, no typed box), then 4 and 3 in parallel, 5, 6, then 7. The flag stays off in prod until 3, 4, 5 and 6 are in and Plan 1 has set the tier ladder.
Every PR: `plugins/`, `.claude/`, `.claude-plugin/`, `scripts/skill_specs/` byte-identical to master (verify with `git diff --stat origin/master -- <paths>`); lint pins black 26.5.1, isort 8.0.1, ruff 0.15.22; mypy rules of CLAUDE.md section 5a; type hints, structlog, 100 columns; no `os.environ` outside `config.py`. Each PR states its CodePipeline consequence before merge (CLAUDE.md section 8.1).

## 11. Tests (80% gate: `.github/workflows/ci.yml:135-139` `--cov-fail-under=80`)
Fake Anthropic client only (no real AWS or API in tests, CLAUDE.md section 5). Covered: scrub (every key and JWT shape, a model that echoes a key is scrubbed on the way out); quota per tier and anonymous; optional auth; pin read; tool loop and the 4-turn cap; `propose_parameters` validation; guardrail retry then static; enterprise gate; budget stop; refusal; provider outage; disabled flag; no message text in any log line (capture structlog); the egress test (only `assistant/client.py` imports `anthropic`); bank drift tests; allocator and CUSUM with a **seeded simulation** asserting the numbers in section 8 (false-pin rate under 0.05 a month at 7 audits a day; first pin within 5 days at a true 15% and 7 a day); the widget's escaping (jsdom-free string tests on the renderer, or a Playwright smoke using the pre-installed Chromium).

## 12. Acceptance criteria (tied to measured numbers)
Bank (release 1): 1,154 of 1,154 answers present; every served answer passes all graders on re-check; at most 3% are `static` (35); **a person reads a random sample of at least 40 served answers** (the rule of recall check 9.16: 0 errors in 40 keeps Opus as the gate, any error reopens the question). A second Opus pass over the served set is reported as a noise check only, not as acceptance: it is the same judge that already passed these answers, and one verdict in 120 changed on a repeat. The recall check showed 0 of 40 clean wrong (upper bound 8.8%), so state in the release note that 4% is **not proven**, only not contradicted. Bank read p95 under 300 ms from cache (target, unmeasured).
Typed (before the flag is on): Plan 1 rules T1 to T5 satisfied for the tier's writer; scrub tests 100%; typed p95 under 12 s (rule L1).
Watchdog: simulation tests pass; after release, the audited flag rate by writer reported daily; global alert and a deliberately injected failure (a dev-only switch that corrupts one function's answers) pinned within 5 days at 7 audits a day, 14 days at 2.8.
Cost: worst user-day per tier below the pro price per day (Plan 1 T5); $2 a day audit budget never exceeded (alarm at 90%).

## 13. Risks

- Audit coverage is thin in the long tail; a bad function with under 1 audited answer a day can run for weeks. Mitigation: the coverage pool, pre-pins from the build, and the **menu bank needing no pins** (it is checked offline).
- Unmeasured: typed accuracy and latency, verdict cost on typed, sync-gate latency, streaming, real traffic volume.
- Anthropic SDK in the production image (root `requirements.txt` change; `scripts/assistant_eval/requirements.txt` kept it out deliberately for this reason).
- Privacy copy reversal; Anthropic retention terms unread.
- Bank staleness if the pipeline is not automated (release 1).
- Prompt injection through the visitor's text into the audit judge (the judge sees question and answer): mitigated by the judge's system prompt treating them as data and by only recording a boolean.
- A false pin storm in the long tail after a catalogue release (every function's record hash changes at once): hash-gate pins by `bank_version`, so a new version resets windows.

## 14. What to decide first (in this order)

1. Fable id and price; prompt version v4 or v5 (Plan 1 blockers). 2. Bank storage and release option (section 6). 3. Pin statistic: CUSUM or 3-of-20 (section 8). 4. JSON reply or SSE (section 4). 5. Whether the bank key may be the dev key or needs its own. 6. Confirm the API task has egress (section 9). 7. Privacy wording and Anthropic retention terms.

## 15. Open questions
a. Is the design meant to give free users typed questions at all, if Plan 1 rejects Haiku for typed? b. CUSUM or the coordinator's rule. c. Debug text retention (default none). d. Key for the bank build. e. Does the enterprise sync gate apply to the first token latency target (no streaming)? f. Should per-user assistant usage be recorded for billing (migration)? g. Who owns the alarm responses with no human in the loop: the degrade flag handles the answer path; page-out of the alarm is still a human step.
