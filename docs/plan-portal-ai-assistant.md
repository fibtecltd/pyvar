# Plan: an AI chat assistant in the pyvar portal (Claude Haiku 5.5)

**Status 2026-11-07: exploration. No assistant code exists.** Two things that do not ship the assistant are built: the Phase 0
eval harness (`scripts/assistant_eval/`, dev tooling) and a description for every API parameter (section 1a), both in the PR
that carries this document. Filippo's decisions are in section 9; the menu-only update is section 1a. Written from a read of this repository
(portal, API, CDK stacks, privacy policy) and Anthropic's Claude API reference (model table cached
2026-10-06). Anything marked "not verified" was not seen or run.

## 1. Recommendation

Build it, small, and gate it on an offline quality check before any user sees it.

- **Where it runs:** a new same-origin route in the existing FastAPI app (`POST /api/v1/assistant/chat`,
  server-sent events). The portal is already served by that app, so the widget needs no CORS, no new
  service and no key in the browser.
- **Model:** `claude-haiku-5-5`, effort `low`, streaming. Estimated **about $0.001 per visitor turn**,
  roughly $10 per 10,000 turns (section 5).
- **Grounding:** a compact, cached index of the 385 functions (about 10K tokens) plus two lookup tools
  over `portal/functions.json`. Never the whole catalogue (about 208K tokens, and prompts over 100K
  tokens move to the dearer rate card).
- **Stateless:** no chat is stored server-side; the browser keeps the conversation and resends it.
  No database table, no Alembic migration in v1.
- **The one real blocker is not technical.** `portal/privacy.html` section 5 promises that pyvar's
  backend "never sends your portfolio data, return series, or computed results to Anthropic or any
  other AI provider". The assistant must be designed so that stays true for computation data, and the
  policy must add Anthropic as a sub-processor for chat messages **before launch** (section 4.6).

## 1a. Update 2026-11-07: menus only, no typing

Filippo's answer to question 3: the visitor types nothing; every action is chosen from a contextual
drop-down. The assistant becomes a **guided help panel**, not a chat.

What that removes:
- Visitor text never reaches a model, so there is no prompt injection from visitors, no need for the secrets
  scrub or the input limits (4.4), and the panel cannot be used as a free model endpoint. Anonymous access
  (decision 1) becomes much safer to allow.
- The privacy exposure shrinks to almost nothing: a model call carries pyvar's own function record and the
  menu choice, with no visitor-written text and no computation data. The call is made from pyvar's server, so
  Anthropic does not see the visitor's address. Decision 3 is closed by design. I would still add one line
  to the policy's sub-processor table saying exactly that, because the table presents itself as the full
  list. That is cheap and not legal advice.

What it does not remove:
- **Accuracy.** A generated explanation or a set of example values can still be wrong, on a risk product. The
  disclaimers, the graders and the judge stay, and Phase 0 measures how often it happens. That the code is
  open source does not change the cost of a wrong answer to the person who relied on it.
- **The documentation ceiling, partly lifted.** Measured 2026-11-07, before the change below: of 1,577
  parameters, none had a description or a bound, in the catalogue or in the OpenAPI schema, and 255 of 385
  functions have an `object` or `array` parameter whose inner shape the catalogue leaves unspecified. A guide
  could say what a function does and what it takes, but what an input *means* came only from its name and the
  formula's symbol map. The same PR as this document now gives every parameter the `Args:` text of its engine
  docstring, so it appears in the OpenAPI schema, the catalogue and the Try-it panel (1,577 of 1,577; the
  engine stays the single source). It is deliberately not in the skills' parameter tables, the plugins or
  the MCP tool schemas yet, so that `plugins/` does not change while they wait for the directory's review
  (`param_docs.PLUGIN_PARAM_DESCRIPTIONS`); the assistant reads the catalogue, so it is unaffected. Those
  descriptions are unreviewed beyond spot checks, and Phase 0 now shows them to the model, so it measures
  the catalogue as it is. Still open: numeric bounds, the inner shape of the 255 `object` or `array` parameters, and
  `liquidity_gap_analysis`, whose `opening_balance` argument the engine takes and the API model does not.

What it changes in the design:
- The input is a **closed set**: 1,924 selections for the whole catalogue (385 explain, 385 when to use, 770
  example values, 384 comparisons with a sibling).
- That opens a fork. **A, runtime generation:** a key in production, a model call on each uncached selection,
  answers cached by function record, action and scenario. **B, build-time generation:** Haiku writes the 1,924
  answers once, a person reads them, they are committed as JSON and served statically, and a drift test
  regenerates an entry when its function record changes. B needs no key in production, no runtime call and no
  runtime failure mode, answers instantly, and lets every answer be read before a visitor sees it. One-off
  cost is about $1 at Haiku rates (estimate; Phase 0 measures it). **I recommend B if Phase 0 passes**: the
  menu-only design removes the reasons to call a model at request time. Haiku still writes the content.
  Sections 4.1 to 4.5 then apply to option A only.
- Suggested parameters (decision 4) stay as two presets, "typical" and "stress". Their values are validated
  against the real request schema before they are stored or shown. Arrays are limited to 10 items in the
  Phase 0 prompts, so functions that need a long series (37 take `returns`) would use the Try-it panel's
  synthetic-series placeholder instead of literal values; not checked yet.

## 2. What it is for, and not for

For: "which function answers my question", what a parameter means, how to read a result, getting an API
key, tier limits, installing the client, plugins and MCP server, finding the right page or Try-it
panel, and suggesting example values for a function's Try-it form (the visitor applies them; nothing
is submitted for them). It is a guide to the portal, not a second product.

Not for, in v1:
- computing or estimating any risk number (pyvar computes; the model does not);
- stating regulatory thresholds from memory (they live in code and tests, CLAUDE.md section 4);
- investment, legal or regulatory advice;
- calling the API for the visitor, spending their quota, or handling their API key;
- seeing Try-it inputs, results or portfolios (unless the visitor pastes them, section 4.4).

## 3. What in the repository shapes the design (verified)

| Fact | Consequence |
|---|---|
| `main.py` mounts `portal/` at `/` in the same app that serves `/api/v1/*`; CloudFront has one origin; `API_BASE = ''` in `pyvar.js` | The assistant is one more router. Same origin, no CORS, nothing per environment. |
| API tasks run in private subnets with egress (`PRIVATE_WITH_EGRESS`, 1 NAT gateway by default, 2 in prod) and already reach Stripe and SES | `api.anthropic.com` is reachable with no network change. CLAUDE.md's "no direct internet routes" rule covers SQS/ECR/S3/Secrets Manager, not this. |
| `config.py` treats integrations as optional (`stripe_secret_key`, `sentry_dsn`); secrets come from Secrets Manager, gated on `ecs_container_metadata_uri_v4` | Add `anthropic_api_key` the same way: absent means the feature is off. The tests must pin that gate (what failed the dev pipeline in #412). |
| `api/middleware/rate_limit.py`: Redis-backed limiter, fixed-scope buckets, IP-keyed `enforce_public_rate_limit` with a trusted two-hop client-IP rule; **fails open** on a Redis error | Reuse the IP logic and the Redis store, but **fail closed** for the assistant: failing open there means unbounded spend. |
| Tiers today: free 10 and pro 500 compute calls per day, enterprise exempt (`config.py`) | The assistant gets its own, separate buckets. Chat must not eat a user's compute quota. |
| WAF: `RateLimitPerIp` blocks at 100 requests per 5 minutes per IP; `AggregateRateLimit` blocks at 6,000 per 5 minutes across all clients (`edge_stack.py`) | Assistant traffic counts toward both. A flood of chat requests could trip the aggregate rule and block real API users. It needs its own path-scoped rules (4.8). |
| CloudFront default behaviour has `compress=True` and one cache policy | Streaming needs a dedicated behaviour with caching and compression off. Not verified that events arrive incrementally; test in dev. |
| `portal/functions.json`: 385 functions with `summary`, `description`, `params`, `formula`; a compact index of `domain/name: summary` is 36 KB, about 10.4K tokens | The index fits in a cached system prompt. Counts use a 3.5 chars-per-token heuristic, not `count_tokens`; Haiku 5.5's tokenizer counts about 30% more than Haiku 4.5's. Re-measure in Phase 0. |
| No `Content-Security-Policy` anywhere (portal HTML or CDK) | No CSP conflict. Model output must still be escaped, never injected as raw HTML. |
| `privacy.html`: no cookies, no analytics; sub-processors are AWS, Stripe, Sentry, Google (sign-in only) | Chat history stays in the browser. Anthropic joins the table. No tracking in the widget. |
| No `anthropic` package in the requirements; the repo never calls an LLM | New pinned dependency; bandit and CI run on it. |
| 1,577 parameters in `functions.json` and the OpenAPI schemas: none had a description (measured 2026-11-07; added from the engine docstrings in this PR) and none has a numeric bound; 255 of 385 functions have an `object` or `array` parameter the catalogue leaves unspecified | The assistant can now say what an input means from its description, which is only as good as the docstring behind it. It still cannot state a valid range or the inner shape of an `object` or `array` (section 1a). |
| The whole catalogue is 1,924 distinct menu selections | Small enough to generate once and review (section 1a, option B). |

## 4. Design

> Sections 4.1 to 4.9 were written for free-text chat. Read them with section 1a: where it removes a rule, that rule is not needed, and the whole of 4.1 to 4.5 applies to option A (runtime generation) only.

### 4.1 Flow

Browser widget (`pyvar.js`) sends `{messages, page_context}` to `POST /api/v1/assistant/chat`. The route
checks the feature flag, budget and rate limits, scrubs the input, then calls `AsyncAnthropic` with a
streaming request and relays text deltas as SSE. When the model asks for a tool, the route runs it
locally (a dictionary lookup, no network) and continues the loop (at most 3 rounds).

### 4.2 Model settings (Claude Haiku 5.5 rules, from the API reference)

- `model="claude-haiku-5-5"`; omit `temperature`, `top_p`, `top_k` (any non-default value is a 400).
- Adaptive thinking is **on by default** and effort defaults to `medium`. Set
  `output_config={"effort": "low"}`; thinking counts toward `max_tokens`, so use about 1,500.
- Read response content blocks **by type**, never `content[0]`. No assistant prefill (400).
- `tool_choice: auto`. A forced tool call skips thinking and is not wanted here.
- Safety classifiers can decline a request (`stop_reason == "refusal"`) and Haiku 5.5 has no server-side
  fallback, so the route must show a plain "I can't help with that" message.
- Cache: one breakpoint at the end of the static prefix (system prompt, index, tool definitions); keep the
  tool list ordered and identical so the prefix never changes. The API reference gives 512 tokens as the
  minimum cacheable prefix for this model and says to confirm it in the caching docs; Phase 0 checks it by
  watching `cache_creation_input_tokens` and `cache_read_input_tokens`.

### 4.3 Grounding and tools

- **Knowledge file:** generated, not hand-written, by a script in the style of `scripts/sync_skills.py`
  (so a drift test fails when it is stale): the function index from `functions.json`, the tier limits from
  `config.py`, and a short FAQ (sign-up, plugins, pyvar Local, MCP). Single source of truth, no numbers typed
  twice.
- **Tools, no network:** `search_functions(query)` (keyword scoring over names, summaries and
  domains; 385 entries need no embeddings), `get_function(name)` (parameters, formula, caveat, domain
  page and anchor) and `propose_parameters(function, values)`.
- **Suggested parameters (decision 4):** `propose_parameters` does not run anything. The server checks the
  values against the function's `params` in `functions.json` (names, types, required fields, bounds) and
  returns errors for the model to correct, up to two retries. Only a valid set reaches the browser, as a
  `suggestion` event that fills the Try-it form after the visitor clicks **Apply**. The values are
  synthetic examples, labelled as such, and the form is never submitted for the visitor.
- **Answers cite function cards** by link (`domain-*.html#...`), so a visitor can always check the source.

### 4.4 Guardrails

- **Computation data stays out.** The widget sends the question, the visible page and, on a Try-it panel,
  the function name. It never sends parameter values or results. If a visitor pastes data, the UI warns
  first; the server does not log it.
- **No page scraping, and none on `dashboard.html`.** The widget reads no page content. On every page
  (decision 6) it sends only the page name; on `dashboard.html`, where a new API key is shown once, it sends
  no page context at all, and the key scrub below still applies to anything typed.
- **Secrets scrub:** before the model call, replace anything shaped like a pyvar key (`pyvar_` plus a
  token), a JWT or an AWS key with `[removed]`, and tell the visitor. Logs hold lengths and hashes, never
  message text.
- **Injection:** the visitor's text and every tool result are data, stated in the system prompt. The tools
  can read and nothing else, so an injected instruction has nothing to act with.
- **No numbers, no thresholds from memory:** thresholds and formulas come from `get_function` or the
  assistant says it does not know and links the page.
- **Output limits:** max input 2,000 characters, max 10 turns, max 1,500 output tokens.
- **Disclosure:** the widget says it is an AI, can be wrong, and is not financial or regulatory advice.

### 4.5 Limits and cost control

Placeholders, to be set from real traffic like the existing rate limits (the repo says the same of its own):

- anonymous visitors are allowed (decision 1): 10 messages per hour per IP; signed-in free: 40 per day;
  pro: 200 per day; enterprise: 500 per day;
- **no monthly budget ceiling** (decision 2), but I recommend a **global daily token cap** held in Redis as a
  circuit breaker, not a budget: anonymous access with no cap at all leaves cost open to a scripted flood
  that gets past the per-IP limits. Set it generously from Phase 1 traffic (a config value, no code change);
  at 80% the widget shows a notice, at 100% the route returns "unavailable today" and nothing is sent to
  Anthropic;
- a **feature flag** (`assistant_enabled`, default false) that is also a kill switch, read from `/public/config`
  so the widget hides itself;
- a CloudWatch alarm on daily tokens and on `refusal` and 5xx rates.

### 4.6 Privacy and terms (must ship with the feature)

- `privacy.html`: add Anthropic to the sub-processor table (what it sees: the chat messages the visitor types,
  and the page or function name; nothing from computations) and reword section 5 so it stays true: computation
  data is still never sent. State the retention that applies at Anthropic. **Not verified:** Anthropic's current
  API data-retention terms for this model; read them before the wording is final.
- `terms.html`: a short "AI assistant" clause (informational, may be wrong, no advice).
- The widget stores the conversation in `sessionStorage` only, and says so.
- **Decision 3 is open** (section 9). My recommendation is to add the sub-processor row.

### 4.7 UI

A launcher on every page through `pyvar.js` (decision 6), and an "Ask about this function" entry in the Try-it
panel (`openTryItPanel` already has the function object). Streaming text, three suggested questions per page,
copyable answers, an **Apply to Try it** button on a suggested parameter set, a thumbs up and down that
increments a server-side counter (no user id). Escape all model text; allow
only links to pyvar.com pages.

### 4.8 Infrastructure (an `infra/` branch, with `cdk diff` in the PR, per CLAUDE.md section 8)

- Secret `pyvar/{env}/anthropic-api-key`: the repo's convention is `pyvar/{env}/<name>` (for example
  `pyvar/dev/sentry-dsn`), a plain string, **one key per environment**. It is imported with
  `from_secret_name_v2` and `grant_read(task_role)` in `api_stack.py`, as the Stripe secrets are, and
  resolved at startup the way `_resolve_stripe_secrets` does it. A single shared `pyvar/anthropic-api-key`
  would let a dev test spend prod's key and force a prod rotation for a dev leak.
- CloudFront behaviour for `/api/v1/assistant/*`: caching disabled, `compress=False`, POST allowed.
- WAF: a stricter per-IP rate rule scoped to that path, and take the path out of the aggregate rule's count so
  assistant abuse cannot block compute users.
- Prefer a **dedicated Anthropic Console workspace and key** for the portal. The API reference lists spend limits
  only as an early-access preview for Console organizations, so do not plan on a provider-side cap; the Redis
  budget is the control.

### 4.9 Observability and tests

- Prometheus: input, output and cache-read tokens, latency to first token, tool calls, refusals, rate-limit hits,
  daily budget used. Sentry for exceptions, with no message content. A `cache_read_input_tokens` of zero across
  repeated requests means something is breaking the prefix.
- Tests use a fake Anthropic client (CLAUDE.md: no real external services in tests), covering budget, scrub,
  streaming, refusal, tool loop and the ECS gate. Coverage stays above 80%.

## 5. Cost (estimate)

Haiku 5.5 on the Claude API, prompts of 100K tokens or fewer: $0.10 input and $0.50 output per million tokens;
cache reads 0.1x and 5-minute writes 1.25x input. Prefix of 12K tokens (system prompt, index, tools).

| Turn | Cost |
|---|---|
| Answer from the index, cache hit | $0.0005 |
| One `get_function` lookup, cache hit | $0.0013 |
| First turn after idle, cache miss | $0.0027 |
| **Blended (55 / 35 / 10)** | **$0.0010** |

About $10 for 10,000 turns a month, $50 for 50,000, $250 for 250,000. A pessimistic case (30% more input tokens,
double the output for thinking) is about $0.0016. The same workload on Sonnet 5.5 ($2 and $10) is about 20x dearer.
NAT data for text traffic is negligible.

## 6. Options considered

| Option | Verdict |
|---|---|
| Call Anthropic from the browser | No: the key would be public. |
| Third-party chat-widget service | Faster to start, but adds a sub-processor that sees visitor text and a recurring fee, and cuts against the privacy stance. |
| Search box only, no LLM | A good first step and the fallback: the same two tools behind a command palette. It can ship in Phase 0 while the quality check runs. |
| Claude Managed Agents | Overkill: no sandbox, no long-running work. |
| Sonnet 5.5 instead of Haiku | Only if the Phase 0 check shows Haiku misses; 20x the cost. Haiku stays the default. |
| A separate service for the assistant | Better isolation, more to run. Start inside the API behind a kill switch; split later if traffic justifies it. |

## 7. Phases (effort is my rough estimate)

**Phase 0: quality check, no product code (revised for menus).** `scripts/`, `tests/` and `docs/` only.
- **Built** (in the PR that carries this document): `scripts/assistant_eval/` builds the menu selections from
  `portal/functions.json`, the skill specs and the OpenAPI schemas; mechanical graders; a model judge; a
  runner with a spend cap, retries, a wall-clock ceiling and a served-model check; 41 tests with a fake client.
  Harness check, no API: the oracle (an answer built from the record) passes 1,924 of 1,924 selections, and
  the null (an empty answer) passes none.
- **Paid steps, after sign-off:** Haiku 5.5 on a 576-selection sample (134 functions: 15 per domain plus every
  function with a tested worked example); Sonnet 5.5 on the same sample for comparison; Opus 5.5 as judge on 12
  answers per action. Estimated $1 to $5 in total under a hard cap (estimates, not measured).
- **Gates:** explain, when and compare: at least 95% pass the mechanical checks and the judge calls at least
  90% faithful; example values: at least 95% fit the request schema within 3 tries and the judge calls at least
  80% plausible; refusals counted (none expected); p50 latency under 3 s per generation.
- **Also measured:** real token counts and cost per generation, projected to all 1,924 selections, to decide
  between options A and B.
- **Two paid runs, 2026-11-08, $2.74:** `docs/assistant-phase0-results.md`. **Conditional go: Haiku 5.5, option
  B.** Examples fit the schema 268 of 268, p50 1.6 s, about $0.0002 a case (about $0.43 for all 1,924). With the
  judge fixed (it had not been shown the sibling list), faithful is 100% for explain, 90% for when (n=40, interval
  77 to 96) and 95% for compare, and example values are 94% plausible. The 95% mechanical gate is missed for
  explain (88%) and by 0.2 points for when, mostly on a length limit the prompt never states; six answers quote a
  regulatory figure that is not in the record. About 3% of answers are unfaithful and 6% of example sets
  implausible, so a person reads what the judge flags before anything is published (option B).

**Phase 1: backend behind a flag (3 to 5 days).** Schemas, route, knowledge generator and drift test, tools,
budget and limits, scrub, config and secret, metrics, tests. Off by default. Merging starts a CodePipeline run.

**Phase 2: widget, suggested parameters, privacy, edge (5 to 8 days).** Launcher on every page and Try-it entry,
the `propose_parameters` tool with its server-side check and the **Apply to Try it** button, `privacy.html` and
`terms.html`, CloudFront and WAF (`infra/`), dev soak. Merging starts a CodePipeline run.

**Phase 3: tiers, feedback, tuning (ongoing).** Signed-in quotas, counters, a weekly look at declined and
low-rated questions.

## 8. Risks

| Risk | Handling |
|---|---|
| Wrong answer on a regulated topic | Thresholds only from `get_function`; visible disclaimer; eval set includes traps. |
| Cost abuse by anonymous traffic, with no budget ceiling (decisions 1 and 2) | Per-IP limits, fail closed, a WAF path rule, a technical daily token cap, a kill switch and a usage alarm. The cap is a safety valve and can be set high. |
| The privacy promise breaks | Computation data never sent; policy changed first; a test that the widget's request carries no Try-it values or results. |
| Suggested values mistaken for advice | Labelled "example values"; the server checks types and bounds; never submitted for the visitor. |
| The menu is too rigid for what visitors want | A guided panel answers four questions per function and links the rest. Watch which actions are used; free text can be added later behind the safeguards in 4.4. |
| Input meanings are thin or wrong | Every parameter now carries its engine docstring text, unreviewed beyond spot checks. A wrong description becomes a wrong answer that passes the graders and the judge, because both check an answer against the record and the description is in the record. So a person reads a sample of the descriptions before launch, and a correction is made once, in the engine docstring. |
| Chat load affects compute users | Own buckets, own WAF rule, kill switch; split into a service if needed. |
| Prompt injection | Tools that only look up or validate, nothing to act with, scrub, escape output. |
| Model or API behaviour changes | Pinned model id, eval re-run before any change, refusal handled. |

## 9. Decisions (2026-11-07, Filippo)

| # | Question | Answer | Effect on this plan |
|---|---|---|---|
| 1 | Anonymous access? | Yes | Small per-IP quota; higher limits when signed in (4.5). |
| 2 | Monthly budget ceiling and key | No ceiling. The key lives in AWS Secrets Manager; Filippo can create it now. Names confirmed: `pyvar/dev/anthropic-api-key` and `pyvar/prod/anthropic-api-key`. | No business budget, but keep a technical daily cap (4.5). One secret per environment, not a shared `pyvar/anthropic-api-key` (4.8). Filippo creates both; nothing reads them before Phase 1 (option A) or at all (option B, which needs no key in production). |
| 3 | Add Anthropic as a sub-processor, reword section 5? | Closed by design: the visitor types nothing (menus only, section 1a) | A model call carries only pyvar's own function record and the menu choice. I would still add one line to the sub-processor table saying so, because it presents itself as the full list. Not legal advice. |
| 4 | v1 scope | Questions, navigation and suggested parameters | `propose_parameters` and the Apply button move into Phase 2 (4.3, 4.7, 7). |
| 5 | Language | English only | |
| 6 | Placement | Every page | Includes `dashboard.html`, with no page context there (4.4). |

## 10. Not verified

- That SSE reaches the browser unbuffered through CloudFront and the ALB (ALB idle timeout is not set in
  `api_stack.py`, so the default applies).
- Real token counts (heuristic used) and real latency.
- Anthropic's data-retention terms and any provider-side spend limits for this account.
- That Haiku 5.5 meets the Phase 0 gate; that is what Phase 0 is for.
