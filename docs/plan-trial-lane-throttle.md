# A3: keyless first use with a throttle (proposal, 2026-11-17)

Decision of 2026-11-17 (A3): the owner takes the risk of giving a first result with no registration and asks for a
throttle that bounds the abuse. A Fable research subagent designed it (read-only, 28 tool calls); I re-read the claims
marked **checked** against the repository and AWS's pages; the rest is the subagent's reading. Nothing is built; the owner's decisions are in the next section.

## Decisions of 2026-11-17 (the owner)

The owner accepted the recommendations in this document, so the trial-ticket lane is the chosen design (the anonymous
per-install keys of `docs/plan-anonymous-plugin-keys.md` stay rejected) and PR 0 below is opened. Four points the
acceptance did not name are recorded here as the working defaults, each easy to change before PR 1 is written:

| Point | Working default | Why |
| --- | --- | --- |
| First-use friction alone justifies the build | Yes, accepted; the nine held plugins' directory flag is **not** expected to clear (reasons in "What I add") | The owner's rule was to rediscuss if the status of the nine did not improve; the proposal states plainly that it will not, and the owner went ahead |
| Sizing | 260 tickets and 2,500 units a day, as written | The compute bound is the same for any size; the numbers only set how much real use fits |
| L6 per-IP counters | Built, behind `trial_ip_counter_enabled`, **off until a short privacy note is written** | An IP prefix is personal data under UK GDPR even as a keyed hash; the note belongs with the A2 and A3 legal-text pass (register, section E2) |
| `CLAUDE.md` 3.5 paragraph | Go given by the owner later on 2026-11-17; **applied in PR 1** (not edited before) | `CLAUDE.md` is the owner's file and 3.5 is a security rule; it is a root-level file, so editing it starts a pipeline run, which PR 1 starts anyway |

PRs 1 to 3 wait for the whitelist benchmark (`docs/trial-lane-whitelist-benchmark-2026-11-17.md`) and the owner's review of the candidate list. Nothing in this plan's PR 0 changes the A3 lane's code, settings or infrastructure; PR #435 also carries the separate dev cache-engine change (`docs/plan-dev-idle-savings.md`).

**Second batch, later on 2026-11-17 (the owner):**

- **Meter actual time** instead of a weight table (section "The p95 run and what it changes"): yes.
- **`CLAUDE.md` 3.5 text:** go given. It is applied in PR 1 and not before: `CLAUDE.md` is a root-level file, so editing it starts a
  CodePipeline run, and PR 1 starts one anyway; a separate text-only edit would cost a run for no change.
- **"Contact Anthropic" is closed:** four e-mails to the directory team, no reply. No further effort goes into the nine held plugins'
  directory status; distribution through our own marketplace is explored instead (`docs/plan-plugin-marketplace-status-and-submission.md`,
  note at the top).
- **The benchmark script is a new pull request** (the earlier one, #435, merged before it was written).

## What the proposal is, and how it differs from the rejected design

It does **not** hand out API keys. It adds a **trial lane**: three routes and a signed, stateless **ticket**
(`aud="pyvar-trial"`, random `jti`, 72 hours, no tier). `decode_token_payload` refuses any token that has an `aud`
without a check of its own (checked, `api/middleware/auth.py`; it is how the stream token already works), so every
existing route rejects a ticket and `CLAUDE.md` 3.5 holds unchanged. The lane runs only a **whitelist of cheap inline
functions**; `/var/compute`, the queue and the other 386-route surface are unreachable from it. No `users` or
`api_keys` row, no migration. Second best is the earlier design (anonymous per-install `pyvar_` keys on every route).

## The finding that reframes the risk: dollars are the small part

With the lane limited to inline functions, a botnet of any size causes under $1 a day of lane compute. The real
exposures are capacity (the domain routes are `async def` and call the engine synchronously, **checked**: one heavy
call blocks a 0.5 vCPU event loop; the queue runs about 6 jobs a second for everyone), denial of the trial itself, and
edge request fees, which exist today on every public path. Today's WAF allows 100 requests per 5 minutes per IP and
6,000 per 5 minutes in total, so a botnet can already trip the aggregate rule and block everyone.

| Abuser, no throttle | Per day | Cost per day | Other damage |
| --- | --- | --- | --- |
| One script, one IP | 28,800 requests | one worker all day about $2.09 | 1,440 times the free tier |
| Botnet, thousands of IPs | 1,728,000 (WAF aggregate); the queue drains 524,160 | about $103 to $153 (Spot, Fargate scale-out, Aurora at 16 ACU) | queue saturated; the aggregate rule blocks everyone |
| Install wiper | tens of calls | under $0.01 | free-tier bypass |
| CI behind one NAT | about 1,000 | $0 to $2.09 | looks like one abusive IP |
| Scraper reselling compute, 10 IPs | 288,000 | up to about $52 | serial queue starves real jobs |

## The throttle: nine layers

| # | Layer and parameters | Stops | Does not stop | Failure mode |
| --- | --- | --- | --- | --- |
| L1 | Whitelist of inline functions (p95 of 1 s or less, no uncompiled Numba kernel); charge = ceil(measured ms / 50) per call, hard 1 s deadline (metered, no weight table); run in a threadpool behind a per-task semaphore of 1; 429 when busy | queue starvation, Spot cost, event-loop stalls | many cheap calls | closed |
| L2 | Per-ticket quota: 5 calls a day, 72 hours, so at most 15 per ticket (counter by `jti`) | value per ticket, replay of a leaked ticket | many tickets | closed |
| L3 | Global compute budget: token bucket, capacity 100 units, 100 an hour, at most 2,500 a day; cache hits cost 0 | all compute cost, whatever the botnet size | denial of the trial to real users | closed (precedent: the assistant spend cap) |
| L4 | Global issuance budget: capacity 20, 10 an hour, at most 260 tickets a day | ticket farming | fast draining of each refill | closed |
| L5 | Per-network share: no ASN takes more than 25% of an hour's issuance or compute (`CloudFront-Viewer-ASN`, needs an origin request policy) | a botnet in a few cloud networks | residential botnets across hundreds of networks | a missing header falls into one shared bucket |
| L6 | Per-IP issuance: 2 tickets a day per IPv4 or IPv6 /64, 4 per /48; key = HMAC(daily rotating secret, prefix), 26-hour TTL, Redis only; switch `trial_ip_counter_enabled` | one IP farming, install wiping, a CI NAT | IP rotation | closed |
| L7 | Proof of work at issuance: SHA-256, 20 leading zero bits (24 in attack mode), HMAC-signed single-use challenge, 2 minutes | casual scripts | a native or GPU solver | closed |
| L8 | WAF rules scoped to `/api/v1/trial/`: 30 per 600 s per IP; 600 per 600 s per ASN; 300 per 300 s count-all; before the aggregate rule | floods before Fargate, trial traffic eating the 6,000 aggregate | low-and-slow traffic | effectively open |
| L9 | Auto breaker: if L3 or L4 is empty at 3 consecutive hourly checks, attack mode (PoW 24 bits, ASN share 10%); at 6, pause issuance | sustained drain without a human | the first hours | Redis flags |

WAF facts (checked): rate rules can aggregate by source IP, **ASN**, JA3, JA4 or count-all (scope-down required); the
lowest limit is 10; windows are 60, 120, 300 or 600 seconds; WAF is $0.60 per million requests, $1 per rule a month,
$5 per web ACL. Because the lowest limit is 10 per 10 minutes, WAF alone cannot enforce "2 tickets a day": that is why
L6 lives in the API. **Rejected:** WAF CAPTCHA and Challenge (they would block a non-browser plugin), Bot Control (the
plugin is itself a bot), `AnonymousIpList` (it would refuse cloud dev sessions; run in Count mode for labels later),
and a tarpit (holding connections costs a 0.5 vCPU task more than the attacker).

## Worked cost bound (50 ms of one API task per unit; the proof of work is solved for free)

| Attacker | Tickets a day | Units a day | Lane compute a day | Edge fees if every IP stays just under L8(a) |
| --- | --- | --- | --- | --- |
| 1,000 IPs | 260 | 2,500 | $0.0009 | $2.59 |
| 10,000 IPs | 260 | 2,500 | $0.0009 | $25.92 |
| 100,000 IPs | 260 | 2,500 | $0.0009 | $259.20 |

Compute stops at the 101st unit of any burst, then 100 an hour; issuance stops at the 21st ticket, then 10 an hour.
Neither depends on the botnet's size. If the 50 ms assumption is 100 times too low, lane compute is $0.09 a day. What
the throttle cannot bound is the edge fee, which grows with attacker traffic and is the same on every public path today.

**What a first-time user sees when the budget is spent:** HTTP 429 with `Retry-After` and
`{"code": "trial_exhausted", "detail": "The no-sign-up trial is busy. A free key gives 20 calls a day: register at ...
and set it in the plugin settings. The trial refills within the hour."}`. Every refusal (L2 to L9, the kill switch,
Redis down) returns this shape, so the worst case is today's flow, never a dead end.

## What a stdio client can and cannot do

No browser, so CAPTCHA and Challenge do not apply and the client is open source, so nothing it does is secret.
Client measures only reduce accidental abuse: the ticket stored at mode 0600 in `${CLAUDE_PLUGIN_DATA}/install.json`
and fetched lazily on the first tool call; honouring `Retry-After` with one retry; refusing to bootstrap when `CI` is
set; an `X-Pyvar-Client` header. Proof of work is bypassed by a native solver for cents. Only the server layers bound anything.

## Operations

Switches without a deploy: Redis keys `pyvar:trial:on` (absent or unreadable means off, so this is also how the lane is
enabled), `pyvar:trial:attack`, `pyvar:trial:budget`, set with a new `scripts/trial_ctl.py` (status, on, off, attack);
an edge kill rule scoped to the trial path. Alarms: compute bucket empty at two consecutive hourly checks; issuance
refusals above 50 an hour; any ASN hitting its share cap; proof-of-work failure ratio above 20%; WAF trial-rule blocks
above 1,000 in 5 minutes; any breaker state change. Refusals are counted in Redis and Prometheus, not Postgres
(at most 86,400 `api_usage` rows a day reach the app).

## Plan (three pull requests after a docs-only one)

| PR | Change | Pipeline run |
| --- | --- | --- |
| 0 | This design and the decisions above; `docs/prompts/agent-a3-p95-measure.txt`, a read-only prompt that measures per-function p95 on dev's `api_usage` for the weights (one Fargate one-off of the migrate task, as the C1 check did; its SQL was run against a throwaway local Postgres, including a write that the read-only transaction refused) | no (docs only) |
| 1 `feat(api)` **(built 2026-11-18; as-built notes below)** | `"trial"` row in `api/tiers.py` (`max_simulations` 10,000, `daily_requests` 5, `assistant_daily` 0) and `KNOWN_TIERS`; settings; `api/middleware/trial.py`; `api/routes/trial.py`; weight table; `scripts/trial_ctl.py`; a `CLAUDE.md` 3.5 paragraph (**go given 2026-11-17**, text below); metering by measured time with the 1 s deadline, a body-size cap and an array-length cap; the whitelist from the benchmark; the trial decoder must **require** `aud` to be present and equal to `pyvar-trial` (tested below); off until the Redis key is set | yes |
| 2 `feat(mcp)` 0.3.0 **(built 2026-11-18; as-built notes below)** | lazy bootstrap, `install.json`, proof-of-work solver, `CI` refusal, key wins if set, one retry, README "what this stores and sends" | yes |
| 3 `infra(cdk)` **(built 2026-11-19; as-built notes below)** | three scoped WAF rules, a kill rule in Count, `CloudFront-Viewer-ASN` in the origin request policy, alarms | yes |

Enabling in dev and then prod is `trial_ctl.py on`, with no run. PR 3 can ship before or after enabling: without it L5
uses the shared "unknown" bucket and the application layers still bound cost.

## Proposed `CLAUDE.md` 3.5 text (go given 2026-11-17; applied in PR 1, not before)

Checked on 2026-11-17 against `api/middleware/auth.py` with python-jose, the library in use. A ticket with `aud`
"pyvar-trial" is refused by a decoder that names no audience (every HTTP route through `decode_token_payload`) and by the
stream decoder (`audience="pyvar-stream"`), both with `JWTClaimsError`. **The converse needs an explicit check:** a decoder that
names an audience still accepts a token with **no** `aud` (a session JWT), and refuses a stream token. The trial decoder
must therefore require the claim to be present and equal, and the paragraph below says so; PR 1 carries a test for
each of the four tokens (ticket, session JWT, API key, stream token) against the trial routes, and for the ticket
against a normal route and the stream route.

Insert after the stream-token bullet and before "Design, settings and failure modes", inside the same code block (the new
bullets use the file's wording and 100-column wrapping; route names are fixed in PR 1):

```
- The no-sign-up trial lane (the routes under /api/v1/trial/) accepts only a trial ticket: a signed
  token with `aud` "pyvar-trial", a random `jti`, a 72 h life and no tier, issued with no users or
  api_keys row. Every other route must keep refusing it (decode_token_payload does, by that claim),
  and the trial routes must REQUIRE `aud` to be present and equal to "pyvar-trial" (python-jose lets
  a token with no `aud` through a decoder that names one, so a session JWT would pass), which also
  refuses an API key and a stream token. Do not drop the `aud`, do not accept a ticket in
  get_current_user, and never give a ticket a tier claim or any way to raise one.
- The trial lane runs only functions on its whitelist, inline, and never enqueues a job. Its global
  compute and issuance budgets FAIL CLOSED, the opposite of the key cache above: if Redis cannot be
  read, or the `pyvar:trial:on` key is absent, the lane is OFF and answers 429 `trial_exhausted`,
  never a pass.
- The per-IP counter holds only an HMAC of the IP prefix under a daily-rotating secret, in Redis with
  a 26 h TTL. Never log it, never write it to Postgres, and leave it off unless
  `trial_ip_counter_enabled` is set (after the privacy note exists).
- Design, budgets and failure modes: docs/plan-trial-lane-throttle.md.
```

The same PR adds `api/middleware/trial.py` and `api/routes/trial.py` to the section 2 layout, as section 10 requires for any
new module.

## The p95 run and what it changes (2026-11-17; decided by the owner the same day)

Result (evidence section 14): dev has no usable per-function timings, so the weight table of L1 cannot be sized from dev's
`api_usage`. Three consequences, the first two worth changing the design for:

1. **Meter the actual time instead of a table of weights. Decided: yes (owner, 2026-11-17).** The cost bound only needs the compute bucket (L3) to be in real
   time, so each lane call is charged `ceil(measured wall ms / 50)` units when it finishes (cache hits 0), the bucket is
   checked for at least 20 units (one second) before a call starts, and every call has a hard 1 s deadline. No table, no
   calibration, no stale weights when a function changes; the semaphore of one (L1) keeps one call in flight per task, so the
   overdraft is at most one call per task. The earlier weights `ceil(p95 ms / 50)` become a documentation figure only.
2. **The whitelist must exclude, or pre-warm, any function that runs an uncompiled Numba kernel.** The image pre-bakes the cache
   of one kernel and the lifespan warms the same one, so a whitelisted function that calls any other `@njit` kernel would compile
   it on its first call in each new API task, seconds on a worker thread and a charge of many units for that one caller. Either
   leave such functions out, or add their kernels to the Dockerfile warm-up and the lifespan (PR 1).
3. **The whitelist still needs a measurement, once, in this repository and not from traffic. Built in the benchmark PR; results in `docs/trial-lane-whitelist-benchmark-2026-11-17.md`:** a script `scripts/trial_weight_bench.py`
   (`scripts/` is a pipeline-excluded directory; it ships in the image because the Dockerfile copies everything) that posts a
   synthetic payload to each candidate route in process, as `scripts/generate_plugin_examples.py` does, and prints the first call
   and the p50, p95 and max of the next 30. Run locally for relative cost and broken payloads; run once on dev through the same
   one-off pattern for absolute time (the migrate task is 0.25 vCPU, half the API task's 0.5, so its times are conservative) after
   a build that contains the script has been deployed. Payloads come from the catalogue's limits and defaults, from named fixtures for array parameters and from the domain API tests; all 385 functions
   are covered (`docs/trial-lane-whitelist-benchmark-2026-11-17.md`).
4. **Prod's `api_usage` would answer a different question:** which functions real users actually call, which is the right input for
   choosing the whitelist. It needs its own authorisation and is probably thin (the prod ALB saw 16,444 requests in 14 days, section 12).

## PR 1 as built (2026-11-18) and where it differs from this plan

The lane is built behind the Redis key `pyvar:trial:on`; nothing changes for anyone until `scripts/trial_ctl.py on` is run.
The module docstrings (`api/middleware/trial.py`, `api/routes/trial.py`, `api/trial_whitelist.py`) carry the reasoning; this is the
summary, with every difference from the plan above.

**What exists.** Three routes under `/api/v1/trial/` (not in the public OpenAPI document): `POST /challenge`, `POST /ticket`, and
`POST /run/{function}` (the body is that function's own request). L1 to L7 and L9, the per-network share (L5) and the per-IP
counter (L6, off) are in the API; L8 (the WAF rules) and the `CloudFront-Viewer-ASN` header are PR 3. The tier row `"trial"` is in
`api/tiers.py` (10,000 simulations, 5 calls a day, no assistant questions); `scripts/trial_ctl.py` is the operator's tool
(`status`, `on`, `off`, `attack on|off`, `pause on|off`, `budget`).

**The whitelist is 30 functions, not the 315 that qualify.** The qualifying rule is the benchmark's: answered 200, p95 far under the
deadline, no uncompiled kernel on a first call in a freshly warmed process. Of the 315 that pass, the lane takes three or four of each
domain (list below), chosen as the functions a first-time user asks for, and **leaves out every function with a simulation, path,
scenario or step count** (a test pins that). Reason: a call cannot be cancelled once it runs and the lane has one slot per API task, so
the cost of a function must not grow with a number the caller picks. The 70 functions that compile on first call, among them the
historical VaR and expected-shortfall, GARCH, Sharpe and drawdown functions, stay out until their kernels are baked into the image
(a separate decision; `tests/test_trial_whitelist.py` fails if a listed function starts compiling). Widening the list is one line in
`api/trial_examples.json` plus the tests that apply these rules. **For the owner's review:**

| Domain | Functions |
| --- | --- |
| market-risk (7) | `parametric_delta_normal_var`, `cornish_fisher_var`, `component_var`, `kupiec_pof_test`, `traffic_light_backtesting`, `frtb_ima_expected_shortfall`, `reverse_stress_testing` |
| derivatives (5) | `black_scholes_european_option`, `black_scholes_greeks`, `bond_pricer_fixed_coupon`, `yield_to_maturity`, `interest_rate_swap_irs_pricer` |
| credit-risk (4) | `credit_var_analytical_vasicek`, `altman_z_score_credit_scoring`, `cds_spread_to_pd_conversion`, `ifrs_9_12_month_ecl_stage_1` |
| liquidity (3) | `survival_horizon_calculator`, `wholesale_funding_concentration`, `liquidity_buffer_sizing` |
| operational (3) | `basel_standardised_measurement_sma`, `kri_threshold_breach_detection`, `rcsa_inherent_risk_scoring` |
| portfolio (3) | `mean_variance_optimisation`, `tracking_error`, `calmar_ratio` |
| regulatory (3) | `basel_iii_cet1_ratio`, `basel_iii_leverage_ratio`, `basel_iv_output_floor` |
| alm (2) | `duration_gap_analysis`, `irrbb_six_standard_rate_shocks` |

**Differences from the plan**

| Plan | As built | Why |
| --- | --- | --- |
| A token bucket kept in Redis (method unspecified) | A GCRA bucket in ONE key, changed with WATCH/MULTI and no Lua; a hard daily counter beside it | Every command is single-key, so a cluster-mode cache accepts it, and the tests can run the same commands on an in-process double (CLAUDE.md section 5 forbids a real server in tests). The key holds the time the bucket is next empty, so an idle bucket stores no credit |
| (not stated) | A conflicting write waits a random, doubling moment and retries up to 8 times | **Measured on a real `redis-server` 7.0.15** (the one place the double could be wrong): with 5 immediate retries, 30 simultaneous takers got 9 tickets and 21 gave up, and 24 of 30 simultaneous charges were lost; with the backoff, 30 takers get exactly 20 tickets and 10 refusals, 60 get 20 and 40, none give up, and 30 of 30 charges land. Never more than the capacity in any run. Valkey 7.2 and ElastiCache Serverless are untested |
| L9: "hourly checks" | The first request of each UTC hour (by whichever task is first; Redis decides) runs the check; the flags carry their own life (attack 24 h, pause 12 h) | The API has no scheduler. A forgotten flag cannot lock the lane for good. `trial_ctl.py attack off` / `pause off` also clear the strike count |
| L5 for a request with no `CloudFront-Viewer-ASN` | Not capped by the share (still bound by the global budgets) | The header does not exist until PR 3; capping the shared "unknown" bucket at 25% would have limited the whole lane to 2 tickets an hour |
| "Cache hits cost 0" | No result cache in the lane | The lane runs the engine every time; nothing to hit |
| Refusal body for L2 to L9 | One 429 `trial_exhausted` body for all of them, including a bad or replayed proof of work | As planned. A bad ticket (401 `trial_ticket_invalid`), a function not on the list (404), an over-size body (413) and a body that does not validate (422) keep their own status |
| 1 s deadline | On a timeout the caller gets 504 `trial_timeout` and is charged the deadline; **the worker thread keeps running to its end and keeps the lane's one slot until then**, so the next call on that task is refused as busy | A thread cannot be cancelled. The overdraft is bounded by that single slot. A function that can run long on bad input is exactly what the list excludes |
| Per-ticket quota | 5 a day (read from the tier row) and 15 in all; a call that never reaches the engine (422, busy) gives its use back | A typo should not burn one of five |
| Usage rows | An allowed call writes an `api_usage` row with tier `trial`; **no refusal does** (`api/middleware/usage.py`: only 2xx under `/trial/`) | The plan's "refusals are counted in Redis and Prometheus, not Postgres" |
| Red-team changes (lottery, a 30% reserve for new networks, jittered refill) | **Not built.** The rolling bucket refills continuously, not on the hour; the semaphore of one is built | The plan listed them as proposals for the owner; they add state and are best decided after the lane has run |
| Warm-up | `main.py` runs each whitelisted function once at start-up in hosted environments (`trial_warm_on_start`) | Measured 0.02 s for all 30 on a 4 vCPU machine once the app is imported, so it is insurance, not a known fix; the 0.5 vCPU figure is not measured |

**Metrics** (Prometheus, bounded labels): `pyvar_trial_events{event}` (`issued`, `ran`, `timeout`, `input_error`, `ticket_invalid`,
`function_unavailable`, `too_large`, `refused_<reason>`), `pyvar_trial_units`, `pyvar_trial_unrecorded` (a charge or refund that
could not be written: a budget undercounts until it is read). The alarms of "Operations" are PR 3.

**Not verified:** the Valkey 7.2 and ElastiCache Serverless behaviour of WATCH/MULTI and of pipelined single-key commands through its proxy; that CloudFront overwrites a viewer-supplied `CloudFront-Viewer-ASN` (if it does not, a caller could claim any network and escape its share; the global budgets still bound the cost); per-call time on a 0.5 vCPU Fargate task (the
benchmark ran on 4 vCPUs, so every figure is the best case); the proof of work's real cost (20 bits is extrapolated); whether a
client in the wild survives the 429 shape (PR 2); and demand.

## PR 2 as built (2026-11-18): `pyvar-mcp` 0.3.0

The plugin side of the lane, in `plugins/mcp`. **Not released:** merging does not publish; the tag `pyvar-mcp-v0.3.0` does (see "Release"
below), and that needs the owner's go.

| Piece | What it does |
| --- | --- |
| `pyvar_mcp/client.py` | `from_env` no longer fails without a key (the server used to stop at start-up); an empty key or an unsubstituted `${user_config...}` counts as no key. With a key, the path is unchanged and **the key always wins**. Without one, a call goes to `trial.py` |
| `pyvar_mcp/trial.py` | Lazy bootstrap at the first call that needs a ticket (never at start-up or when listing tools): `POST /trial/challenge`, solve the SHA-256 puzzle, `POST /trial/ticket`, then `POST /trial/run/{function}`. `install.json` in `${CLAUDE_PLUGIN_DATA}`, mode 0600, written to a temporary file and `os.replace`d, with `install.lock` (`O_EXCL`, stale after 60 s) so two processes ask once. The ticket is ignored if the file is damaged, from another API address, or within 5 minutes of its end. Redirects are not followed, so a ticket goes to pyvar.com only. **One retry**: a 401 `trial_ticket_invalid` deletes the ticket and asks once more; a 429 whose `Retry-After` is 10 s or less is waited out once; anything else returns the server's own words (they name the free key), with "may work again in about N" when the wait is long |
| Never in CI, never outside Claude Code | `CI` set (not empty, `0`, `false`, `no`), or no `CLAUDE_PLUGIN_DATA`: no trial, the old instruction to set `PYVAR_API_KEY`, as a tool error and not a crash |
| `pyvar_mcp/trial_functions.py` | The 30 trial function names, a copy. A function off the list is refused **without a request** and with a message naming the free key. `list_pyvar_functions` marks each entry `available_without_key` when no key is set (and is unchanged when one is) |
| `pyvar_mcp/main.py` | A tool call now runs in a worker thread (`anyio.to_thread`), so a sign-up puzzle or a wait never blocks the MCP loop; `PyvarSetupError` becomes an error result |
| `.claude-plugin/plugin.json`, `pyproject.toml` | 0.2.2 to 0.3.0, the launcher pin `uvx pyvar-mcp==0.3.0`, and `pyvar_api_key` is `required: false` (still `sensitive`) |
| `README.md` | "What this plugin stores and sends", in the wording of `docs/plan-anonymous-plugin-keys.md` section 2 (an "anonymous installation ticket issued by pyvar.com", "the plugin's own data directory") |

**Proof-of-work cost** (this machine, pure Python): 20 bits, median 0.44 s (0.05 to 1.3 s over six runs); 24 bits (attack mode), 6 to 10 s. The
client refuses a puzzle above 24 bits and gives up after 120 s.

**Decisions of 2026-11-18 recorded here:** the 30-function list is confirmed (owner); `Retry-After` stays one value per refusal reason.

**Left alone on purpose:** `plugins/mcp/smithery.yaml` and its `Dockerfile` (a container has no `CLAUDE_PLUGIN_DATA`, so it keeps requiring a key);
the nine held skill plugins (byte-identical); `pyvar-client`; the key path's own `urllib` call (it still follows redirects; changing it is a separate decision).

**Tests.** In `plugins/mcp/tests` (111 in all): the ticket file (mode 0600 under a permissive umask, atomic replace, damaged, oversized, other address,
near expiry), the lock (mutual exclusion, stale takeover, released on error), the solver, lazy bootstrap (no file and no request until a call needs
one), reuse across processes, two processes asking once, the single retry on 401 and on a short 429, a long wait reported not slept, the server never
being asked after an unsolvable puzzle, the ticket never appearing in an error message, redirects refused, the key winning, CI and non-Claude-Code
refusals, the listing marks, and the event loop staying free during a slow call. In the main repository, `tests/test_mcp_trial_contract.py` (45) runs
the client's real code against the server's real routes in process: the function list equals the whitelist, the solver satisfies the server's
check, bootstrap, reuse, the quota, a busy task, a replaced ticket, a switched-off lane, paused issuance and attack mode, and every one of the 30
functions answering as it does through the authenticated route.

**Release (the owner's go needed; PyPI never accepts a version twice).** Merge, then tag the merge commit `pyvar-mcp-v0.3.0` immediately: until the
workflow has published, the launcher pin names a version PyPI does not have, so a fresh install from `master` fails (README, "Install"). Both
marketplaces list the plugin from its default branch, so that window is real, and short. The lane is separate: until `trial_ctl.py on` is run, a
0.3.0 plugin with no key gets the lane's 429 and the free-key message.

**Not verified:** how the plugin directory's scanner treats `CLAUDE_PLUGIN_DATA` and a file-to-bearer-to-network path (the plan rated a resubmission's
risk medium; the listing is frozen and nothing is resubmitted); what an unset optional sensitive option actually substitutes (an empty string and a
literal placeholder are both handled); behaviour on Windows (the file mode is not enforced there; the tests that check it are skipped); the proof of
work's time on a slow laptop.

## PR 3 as built (2026-11-19): the edge and the alarms

Everything here is in `pyvar-cdk` (`edge_stack.py`, `api_stack.py`, `alerts_stack.py`), `scripts/toggle_kill_switch.sh`, and the lane's own
log lines. **Nothing is enabled by it**: the lane stays off until `scripts/trial_ctl.py on`, and the new kill rule ships in Count.

**At the edge (us-east-1, `EdgeStack`).** All scoped to a starts-with match on `/api/v1/trial/` **after URL decoding and path normalisation**
(the API decodes `%74rial` and collapses `//` before routing, so a raw-path match could be walked around).

| Priority | Rule | Action | What it does |
| --- | --- | --- | --- |
| 0 | `EmergencyKillSwitch` (unchanged) | Count | Block everything, flipped by the script |
| **5** | **`TrialKillSwitch`** | **Count** | Block the trial path only; independent of the rule above |
| 10, 20 | the two managed rule groups (unchanged) | | |
| **21** | **`TrialRateLimitPerIp`** | Block | 30 per 600 s per source address |
| **22** | **`TrialRateLimitPerAsn`** | Block | 600 per 600 s per network (WAF's own ASN key, so it does not depend on the header below) |
| **23** | **`TrialRateLimitAll`** | Block | 300 per 300 s for the whole path (CONSTANT, so the scope-down is mandatory, as the file's docstring records) |
| 25 | `AggregateRateLimit` (unchanged) | Block | 6,000 per 300 s for everyone |
| 30 | `RateLimitPerIp` (unchanged) | Block | 100 per 300 s per address |

The three trial rate rules sit before the aggregate rule, so a flood on the trial path is refused there and does not use up the 6,000 every other
caller shares. A trial request the rules let through is still counted by `RateLimitPerIp` and `AggregateRateLimit`. A new cache behaviour
`/api/v1/trial/*` (same cache policy as the default behaviour, so `Authorization` is in the key and POSTs are not cached) uses a **new origin
request policy** that forwards three headers: `User-Agent`, `X-Pyvar-Client` and **`CloudFront-Viewer-ASN`**, no cookies and no query string. It is
an allow-list rather than "all viewer headers" because the lane reads nothing else. Like the default behaviour's policy it does not forward the
`Host` header. **`scripts/toggle_kill_switch.sh status|enable|disable [env] [rule]`** takes
`EmergencyKillSwitch` (the default, so nothing that uses it changes) or `TrialKillSwitch`, and refuses any other name before it calls AWS.

**Alarms (all page an SNS topic that has no subscribers until someone adds one, as the existing alerts topic).**

| Alarm | Where | Condition |
| --- | --- | --- |
| `pyvar-<env>-trial-waf-blocks` | us-east-1, own topic `pyvar-<env>-edge-alerts` (a CloudFront ACL's metrics are in us-east-1 and an alarm must publish to a topic of its own region) | WAF blocks of the three trial rate rules above 1,000 in 5 minutes |
| `pyvar-<env>-trial-budget-empty` | API region, alerts topic | a breaker strike (the hourly check found the compute or issuance budget empty) in each of two consecutive hours: the word before the breaker trips at three |
| `pyvar-<env>-trial-issuance-refusals` | same | more than 50 ticket refusals for the issuance budget in an hour |
| `pyvar-<env>-trial-asn-cap` | same | any request refused because its network reached its share (5 minute window) |
| `pyvar-<env>-trial-pow-failures` | same | proof-of-work failures above 20% of ticket attempts in an hour, counted only from 20 attempts |
| `pyvar-<env>-trial-breaker-state` | same | the breaker set attack mode or paused issuance (5 minute window) |

**Why the alarms count log lines.** Nothing in AWS scrapes the API's Prometheus counters. The lane now writes **one INFO line per issued ticket and per
refusal** (`trial_issued`, `trial_refused_<reason>`) and **one WARNING line per breaker change** (`trial_breaker_strike`, `_attack`, `_pause`), and a
CloudWatch metric filter on the API container's log group counts each by the JSON key `event`. This app's structlog set-up renders a stdlib record's
message as `event` and does **not** render `extra=`, so the name carries the fact; the number of strikes, for example, is not in the line. Calls
that ran, failed on input or timed out write nothing (an allowed call already has an `api_usage` row). The metric names carry the environment
(`trial-<kind>-<env>` in namespace `pyvar`, like the worker-error metric) because dev and prod share one account. `ApiStack` now exposes its
container's log group (`api_log_group`); its logical ID and name are unchanged. The synth of that stack differs only by one new export.
`tests/test_trial_events.py` pins the lane's side with the real JSON logging set-up; `tests/test_cdk_trial_lane.py` pins the CDK side and that the
two agree.

**Synth diff against the master before this change** (dev and prod alike): `pyvar-<env>-alerts` +12 resources (7 metric filters, 5 alarms);
`pyvar-<env>-api` no resource change (one new export); `pyvar-<env>-edge` +3 (an origin request policy, an SNS topic, an alarm) and two changed in
place (the web ACL: five new rules; the distribution: one new cache behaviour). Nothing is replaced.

**What a reader should know before enabling it.**
- `TrialRateLimitAll` is a shared bucket: 300 per 5 minutes for **every** trial caller together. Someone who fills it blocks every other trial
  caller at the edge until the window passes (the lane's own budgets are far below it: 20 tickets an hour). That is the plan's design, not a bug.
- A request whose path is not exactly `/api/v1/trial/...` after decoding is not subject to these rules and does not get the ASN header; the API then
  treats it as "no network known" (not capped by the per-network share, still bound by every global budget).
- The ALB-fronting WAF (`alb_waf_stack.py`) is left as it was; it never had the kill switch or the aggregate rule.

**Not verified (a first deploy to dev is the check):** that `CloudFront-Viewer-ASN` is accepted in an origin request policy's header allow-list by
CloudFormation (AWS's documentation lists it; nothing here can call the API); the web ACL's capacity after five more rules (the limit is 5,000
units; the two managed groups use about 900 and the new ones a few each); that a CloudFront web ACL's metrics have exactly the dimensions the alarm
uses (`WebACL` and `Rule`, no `Region`, per AWS's metric reference, not seen on a live ACL); whether CloudFront overwrites a viewer-supplied
`CloudFront-Viewer-ASN` (carried over from PR 1; if it does not, a caller can claim another network and escape its share, and the global budgets
still bound the cost); whether WAF bills the requests it blocks (the plan's open question since PR 0).
As the file's own docstring records, a WAF shape can pass `cdk synth` and be refused at deploy; the pipeline deploys dev first, so a refusal stops
there and prod is not reached.

**Enabling, after the dev deploy:** add a subscriber to the new `pyvar-dev-edge-alerts` topic (the alerts topic has its own); then run
`docs/prompts/agent-trial-enable-dev.txt` (it switches the lane on in dev and makes one real call through CloudFront, which is also the check that
`Authorization`, the body and the ASN header arrive). Prod follows the same two steps when the owner says so.

## Red team (one afternoon)

About 150 residential proxy addresses over 8 or more networks and a native solver, polling the ticket route every few
seconds: each refill of 10 tickets goes to the attacker within seconds, the ASN cap does not bind, real users almost
never get a ticket, and after 6 hours the breaker pauses issuance, which finishes the job. The compute burned costs under
a cent; **the product goal fails**. Changes proposed: refill continuously with jitter, never on the hour; admit issuance
by lottery among requests in a short window; keep 30% of issuance for networks that took no ticket in the last 24 hours;
make L1's semaphore a hard requirement of PR 1. Denial of the trial cannot be fixed without identity: the durable
answer stays remote MCP with sign-in (the keyless options document's option 2), with this lane as the on-ramp.

## What I add

- **The nine held plugins' status is not expected to change, and the reason is not the ticket file.** (An earlier
  version of this bullet said the ticket in `install.json` would still read as "a credential from the user's machine"
  to the directory scan; that tied a different risk to the nine and is withdrawn.) What the repository's own records
  say (`docs/plan-plugin-marketplace-status-and-submission.md` sections 5 and 6):
  - The nine (the eight domain skills and `pyvar-arch-observability`) were held on 2026-10-31 under the rule "Update adds
    credential forward", for their **own text**: the setup sections told Claude to look for `PYVAR_API_KEY` in the
    environment, and the architecture skill showed a Secrets Manager call. They contain no code.
  - The hold is **at plugin level, not by version**: it stayed after 1.2.0 removed the wording, "Publish update" returns
    "Needs the directory team", and `liquidity-risk` gives the same result for the same bytes with nothing left to
    reword. Only the directory team can lift it; the one route the records named, "Contact Anthropic" in the portal and
    e-mail, was tried (four e-mails, no reply: owner, 2026-11-17) and is closed.
  - The lane changes the API and `pyvar-mcp` only. The nine stay byte-identical (the standing rule is not to change
    `plugins/` for them, because each changed version adds a review row), so nothing the hold depends on moves.
  - Separately, `pyvar-mcp` is a `uvx` launcher, which the directory holds for review whatever it stores.
  - **The file does matter for a different listing:** if `pyvar-mcp` 0.3.0 is ever resubmitted, a file-to-bearer-to-network
    path may draw a new finding (rated medium, unverified: `docs/plan-anonymous-plugin-keys.md` section 2). The plan
    there is not to resubmit until the nine holds clear; users reach 0.3.0 through `pyvar-marketplace` meanwhile.
  So the lane improves first use for everyone who installs through the marketplace, and does nothing for the flag.
- **Edge fees are the one uncapped line** and the lane adds a target, not a new exposure.
- The existing aggregate WAF rule lets any botnet block everyone today; this PR plan does not change that.

## Not verified

Whether WAF bills blocked requests and whether CloudFront bills WAF-blocked ones; how WAF aggregates IPv6 in IP-keyed
rate rules; the WCU of the new rules; whether the managed origin request policy can carry `CloudFront-Viewer-ASN` (a
custom one may be needed) and that CloudFront overwrites a viewer-supplied `CloudFront-*` header; inline function
durations on 0.5 vCPU (so the weights and the 50 ms unit); proof-of-work timing (20 bits at about 1 s is extrapolated);
the Aurora and Spot prices (repository figures); Redis Lua atomicity (from memory); legitimate demand for the lane.
Checked by me: the `aud` refusal, the WAF aggregation keys, limit and windows, the WAF prices, the synchronous engine calls.
The subagent reported its own wrong turns: an initial per-call price from the queued-job figure (orders of magnitude
too high for inline calls), per-IP limits first sized from WAF alone, and an unverified claim about tracked-IP limits it then dropped.
