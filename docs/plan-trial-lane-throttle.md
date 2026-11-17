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
| 1 `feat(api)` | `"trial"` row in `api/tiers.py` (`max_simulations` 10,000, `daily_requests` 5, `assistant_daily` 0) and `KNOWN_TIERS`; settings; `api/middleware/trial.py`; `api/routes/trial.py`; weight table; `scripts/trial_ctl.py`; a `CLAUDE.md` 3.5 paragraph (**go given 2026-11-17**, text below); metering by measured time with the 1 s deadline, a body-size cap and an array-length cap; the whitelist from the benchmark; the trial decoder must **require** `aud` to be present and equal to `pyvar-trial` (tested below); off until the Redis key is set | yes |
| 2 `feat(mcp)` 0.3.0 | lazy bootstrap, `install.json`, proof-of-work solver, `CI` refusal, key wins if set, one retry, README "what this stores and sends" | yes |
| 3 `infra(cdk)` | three scoped WAF rules, a kill rule in Count, `CloudFront-Viewer-ASN` in the origin request policy, alarms | yes |

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
   a build that contains the script has been deployed. Payloads come from the catalogue's limits and defaults, from named fixtures for array parameters and from the domain API tests; 260 of the 385 functions
   are covered so far (the results document says which are not).
4. **Prod's `api_usage` would answer a different question:** which functions real users actually call, which is the right input for
   choosing the whitelist. It needs its own authorisation and is probably thin (the prod ALB saw 16,444 requests in 14 days, section 12).

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
