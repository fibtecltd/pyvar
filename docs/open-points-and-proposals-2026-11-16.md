# Open points and proposals, 2026-11-16

For each open point: what it is, the options (with pros and cons where there is more than one) and a
recommendation. Nothing here has been decided; the decisions are the owner's. Facts about the code were
checked against master at `7e35bbc` unless marked as inference. Companion documents:
`docs/internal-tokens-and-signing-secrets.md`, `docs/plan-academic-access.md`,
`docs/plan-anonymous-plugin-keys.md`, `docs/p9-aws-evidence-2026-11-13.md` (section 7).

## Decisions of 2026-11-16 (the owner)

| Point | Decision | State |
| --- | --- | --- |
| A1 shared tier policy | Option 1 (recommendation) | Next to build; not started |
| A2 education access | Option 2, lean first version, after A1 | Queued behind A1 |
| A3 plugin keys | Anonymous keys rejected: "nothing represents a win here"; look for other options | Options in `docs/plan-plugin-keyless-access-options.md`; owner to choose |
| A4 cancelling internal tokens | Recommendation: short expiry, database-backed keys for longer use | Scripts done (`0b40cdc`); nothing more to build |
| A5 start-up secret guard | Option 1 | Built on `fix/lost-worker-retry-and-secret-guard`, no PR yet |
| B1 lost workers | Option 1 "with only one retry" | Built on the same branch (`task_reject_on_worker_lost`, receive limit 2), no PR yet |
| B2 group id | Recommendation (confirm first, then a group per message); prompt requested | Confirmed on dev (evidence section 9); per-message group built and tested on the A5/B1 branch, no PR yet |
| G1, G2 dependency drift, workers clone master | New, found while confirming B2 | Options below; owner to choose |
| B3 public Spot wording | Leave it | Closed |
| B4 second W4/W5 pass | Recommendation: after B1 and B2, as their acceptance test | Waiting for B1 and B2 |
| C1 dev check of the fix | Prompt requested | Done: five fallback rows seen in `var_jobs`, no failure line since 2026-11-14; closed apart from the Sentry issue (owner) |
| C2 prod "Succeeded" | The owner approved it ("it has always been me") | Closed |
| C3 AWS access for agents | Keep on hold | On hold |
| C4 Dependabot | Prompt requested | PR #432 open (black 26.10.1, two manifests); CI green except one job still running at the last look; not merged |
| D2 idle Aurora readers | If both are proved idle this is the highest priority (second round) | Both IDLE (evidence section 10); dev-only CDK flag built and synthesised, not pushed; waiting for the go-ahead and the prod decision |
| A6 free-tier limits | Review them and consider about twice as much (second round) | Limits listed and options below; owner to choose |
| D1 cost tags | Tags activated; inventory run | Outcome in `docs/p9-aws-evidence-2026-11-13.md` section 8; new points D2 to D4 below; README wording after a month of tagged data |
| E1 Medium article | Close the point; the owner will write another article | Closed |
| E2 typed assistant | Recommendation: keep off; one legal-text pass with A2 | Kept off |
| E3 "JIT-accelerated" | Leave it | Closed |
| E4 pilot sign-off, ES source | Not discussed | On hold |
| C5 `var_jobs` rows stuck pending | New (from the C1 result) | Seven rows from 2026-11-14; not yet looked at |
| F1, F2 housekeeping | Not discussed | Open; F1: nine commits, only `docs/`, `scripts/`, `tests/`, ready to open |

## Decisions, second round (later on 2026-11-16, the owner)

| Point | Decision | State |
| --- | --- | --- |
| The four "ready" items (PR #432, A5 + B1 + B2, D2 dev flag, F1 docs and scripts) | Fold into ONE PR | **Merged 2026-11-16 as PR #433 (`864f58f`)**, CI green (15 checks); PR #432 closed as folded in. Pipeline run, dev deploy and prod approval follow; then B4 (W4 re-run) and the Aurora AFTER measurement |
| G2 workers clone master | Option 3: leave it; a merge to master is a worker release | Written into the PR description; no work |
| D2 idle readers | Option 3: remove the dev reader and lower prod's minimum capacity to 0.5 ACU, with measuring | In the combined PR: flag, 0.5 ACU, a prod writer CPU alarm, `docs/plan-aurora-floor-measurement.md` and a before/after prompt |
| G3 static uptime text | Recommendation: remove the item now | Queued for the second PR |
| G1 unpinned kombu | Recommendation: read the API's real versions, then pin | Prompt to write after the combined PR; pin in the second PR |
| A3 plugin keys | To be rediscussed if the better path does not improve the nine plugins' status; then option 1 (trial lane) with guardrails | On hold |
| A6 free-tier limits | Recommendation: 10 to 20 requests a day, as the first row of A1's table | Builds with A1 |
| C5 rows stuck pending | Option 3: a reconciler or a dead-letter handler | Design first, after the combined PR |
| D4 ECR lifecycle | Recommendation: keep the newest 30 images | Queued for the second PR |
| D3 dev's fixed footprint | Option 4: scale dev's stateful services down when idle | Research first (what can pause or scale to zero); no change yet |
| F2 local scratch | Clear it any time | Done conservatively (only what is merged, pushed or regenerable) |

## A. New high-priority work

### A1. A shared tier policy (prerequisite for A2 and A3)
**Recap.** Both new tiers (`academic`, `anon`) change the same code, and an unknown tier silently gets
free-tier limits today (`api/middleware/auth.py:66-71`, `rate_limit.py:184` and `:274`). Both plans also
name their migration `0010`.

| Option | Pros | Cons |
|---|---|---|
| 1. Put every tier's limits in one table that those places read, behaviour unchanged, then add tiers as rows | A new tier cannot fall through to free; one place to audit; both plans get simpler; tests can pin that existing tiers behave as before | Touches the authentication and rate-limit hot path; one pipeline run; one more PR before any feature |
| 2. Add each tier with its own branches, as the plans describe | No refactor; smaller first PR | The silent-fallthrough risk is created twice; the two features collide in the same files |

**Recommendation: 1.**

### A2. Education access requests
**Recap.** The ask was a portal section where education bodies request "internal unlimited" keys. The design
review recommends against `internal` (exempt from every limit, and the only credential the admin routes
check, so a holder could suppress any e-mail address) and proposes a finite `academic` tier with human
review (`docs/plan-academic-access.md`).

| Option | Pros | Cons |
|---|---|---|
| 1. The full plan: form, request queue, admin command line, expiry, usage alerts, three PRs | Complete lifecycle and audit | Largest; two pipeline runs; privacy and terms changes; the approval path assumes AWS SSO with MFA, which is not what the AWS work has used |
| 2. A lean first version: form, queue, admin command line, tier with expiry and the pool breaker; alerts and renewal banner later | Same safety on abuse and cost; smaller | Renewals and alerts are manual at first |
| 3. No portal: grant case by case through an admin command | No public attack surface; fastest for the first few institutions | Manual; needs the admin route anyway; no self-service |
| 4. A 100% Stripe coupon on Pro | Little code | Adds a sub-processor; the billing webhook then owns the tier (rejected by the review) |

**Recommendation: 2, after A1.** Decisions needed first: the limits (200 a day, 3,000 a month, 30 a minute),
the cohort cap (15), expiry (6 months), and how the approver signs in.

### A3. Plugins that get a free key without registering
**Recap.** The nine plugins the directory shows as held or flagged are skills with no code; the key lives in
`pyvar-mcp`, so only that package changes and the nine stay untouched. This improves their use but does not
clear the flag (`docs/plan-anonymous-plugin-keys.md`).

| Option | Pros | Cons |
|---|---|---|
| 1. Anonymous per-install keys (5 calls a day, 10 per IP, global fail-closed budget, claim step to raise quotas) | Zero-touch first result; bounded cost (about $15 a day worst case); degrades to today's flow | New tier and endpoint; at least three pipeline runs; IP counters need a privacy sign-off; a botnet can exhaust the anonymous pool daily; the directory scan may react if 0.3.0 is resubmitted |
| 2. Only a better message and README in `pyvar-mcp` | No server change; no privacy change; quick | Still needs registration, so the stated goal is not met |
| 3. Device-authorisation flow (click a link, nothing to paste) | Strong identity; simpler abuse model | Still an e-mail registration; more moving parts |
| 4. A shared public demo key | Trivial | One bucket anyone can drain; cannot revoke per abuser (rejected) |

**Recommendation: 2 now** (a small `pyvar-mcp` release), **1 later** after A1 and the privacy sign-off.

### A4. Cancelling an internal token before it expires
**Recap.** The API checks a JWT's signature and expiry and nothing else, so no command can switch one off.
The new scripts say so: `scripts/revoke_internal_token.py` lists what is outstanding, records a revocation
(exit code 4, "recorded, not enforced") and prints the emergency runbook. API keys are different: they are
revocable and `scripts/revoke_api_key.py` does it for real. Options for real per-token cancellation are in
`docs/internal-tokens-and-signing-secrets.md` section 5.

| Option | Pros | Cons |
|---|---|---|
| A. Short expiry; rotate the secret in an emergency (today) | Nothing to build | A leak is answered by signing everyone out |
| B. A revocation list in the API, by `jti` | Cancels one token; tokens already carry `jti` | A Redis read on every JWT request; a fail-open or closed choice; a pipeline run |
| C. Database-backed keys for anything long-lived | Revocable, listable, tied to an account | Needs the admin routes from A2 |

**Recommendation: A for tokens meant to last a day or less, C for longer ones; B only if still needed.**

### A5. A start-up guard against the default signing secret
**Recap.** `config.py:24` falls back to the public string `change-me-in-production`. AWS always injects the
real secret, so hosted environments are safe, but nothing refuses to start with the default or a short one.
Note `APP_ENV` is `dev` or `prod` in AWS, `development` locally and `test` in CI (`config.py:75-77`, `:352`).

| Option | Pros | Cons |
|---|---|---|
| 1. Refuse to start when `APP_ENV` is a hosted value and the secret is the default or under 32 characters | Closes a silent failure that would let anyone sign an `internal` token | Must not key on "not development" (it would break CI); a pipeline run |
| 2. A CDK or CI test only | No runtime change | Does not protect a live misconfiguration |
| 3. Nothing | No work | The gap stays |

**Recommendation: 1.**

### A6. Free-tier limits: review and a doubling
**Recap.** What a free account gets today (master `7e35bbc`):

| Limit | Value | Applies to | Where |
| --- | --- | --- | --- |
| Compute requests | 10 a day, one bucket for all 386 compute endpoints | per account (session or key) | `config.py` `rate_limit_free_daily`; `api/middleware/rate_limit.py` |
| Simulations per VaR request | 10,000 (the schema minimum is 1,000) | per request | `api/middleware/auth.py` `max_simulations` |
| Default when omitted | 10,000, which must never exceed the free cap | per request | `config.py` `default_n_simulations` |
| Result kept inline | up to 10,000 simulations; above that the result goes to S3 | per request | `config.py` `s3_result_offload_threshold`, set equal to the free cap on purpose |
| Return observations, horizon, confidence | 30 to 10,000; 1 to 250 days; 0.90 to 0.9999 | every tier | `schemas/var.py` |
| Monthly caps | none for free (Pro only: 5,000 requests, 2,000,000 simulations) | per account | `config.py` |
| API keys | 5 active, 50 in all | per account | `config.py` |
| Wrong-key attempts | 30 a minute | | `config.py` |
| Sign-in link | valid 30 minutes; one per 5 minutes | per address | `config.py` |
| Registration | 5 an hour | per IP | `rate_limit_register_per_hour` |
| Public status files, no account | 60 an hour | per IP | `rate_limit_unauth_per_hour` |
| Assistant questions | 10 an hour (no account, per IP); 40 a day (free account); a $5 a day budget across all tiers | | `config.py` |
| Edge, every caller | 100 requests per 5 minutes per IP; 6,000 per 5 minutes in total | | `pyvar-cdk/stacks/edge_stack.py` |

For comparison Pro has 500 requests a day and 100,000 simulations. The daily and simulation numbers are
repeated in about 20 places (README, the portal REST guide, the tier table SVGs, the Medium articles, the
plugin example generator and some architecture notes), so a change is mostly a text change.

**What is not known.** How many free accounts reach the cap. The config comment itself says no traffic data
exists, and `api_usage` deliberately keeps no user id. Rate-limited requests are recorded (status 429), so the
owner can read the pressure without a user id:

```sql
SELECT date_trunc('day', created_at) AS day,
       count(*) FILTER (WHERE status BETWEEN 200 AND 299) AS ok,
       count(*) FILTER (WHERE status = 429)               AS limited
FROM api_usage
WHERE tier = 'free' AND created_at >= now() - interval '30 days'
GROUP BY 1 ORDER BY 1;
```

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Daily requests only: 10 to 20 | One value; no coupling; Pro stays 25 times ahead | An account farmed for free requests yields twice as much; only the per-IP registration limit and the disposable-domain list stand against that |
| 2. Requests and simulations: 20 a day and 20,000 | Looks generous | Monte Carlo error falls with the square root of the simulations, so doubling them improves it by about 29%; the offload threshold must also move to 20,000 or every free result starts going to S3 with a different response shape; inline results get twice as large |
| 3. Double everything, assistant included | One rule | The assistant is limited by its $5 a day budget, so a bigger per-user quota only exhausts the budget sooner; the typed route is off |
| 4. Leave it and measure a month first | Decides with data | The cap is the first thing a new user meets, and the delay costs a month |

**Recommendation: 1**, as the first value in A1's tier-policy table, so the numbers and the texts come from one
place. Compute is not the cost driver (arithmetic: 1,000 accounts each using all 20 requests is about 14 a minute
over a day, against the 251 to 364 queued jobs a minute the W4/W5 runs completed); the fixed footprint is (D2, D3).
It is a code change under `config.py`, so a pipeline run. Do not touch the nine plugins that are held for review;
the generated texts are regenerated with `scripts/sync_skills.py` as `CLAUDE.md` section 10 says.

## B. Findings from the W4/W5 run

### B1. Jobs lost when a worker dies abruptly
**Recap.** Graceful termination kept 5 of 5 jobs; an abrupt kill lost 5 of 5 (reported failed, not
redelivered). Cause: `tasks/var_task.py` sets late acknowledgement but not `task_reject_on_worker_lost`, and
Celery 5.6.3 acknowledges a lost worker's task and fails it. A real Spot reclaim gives a 2-minute notice and
takes the graceful path, so the exposure is mainly crashes and no-notice failures.

| Option | Pros | Cons |
|---|---|---|
| 1. Set `task_reject_on_worker_lost=True` | Restores the documented design; results are deterministic, so a duplicate run is harmless to them; a message goes to the dead-letter queue after a set number of receives (3 on dev, per the agent's reading of the live queue) | A job that kills its worker is retried up to 3 times; duplicates count twice in usage; a pipeline run; needs the W4 re-run |
| 2. Leave it, document the behaviour | No change; clients get a fast failure | The Spot-safety claim stays incomplete; every client must retry |
| 3. Return a retriable "worker lost" error | Honest and automatable | Pushes retries to every client; more API surface |

**Recommendation: 1, accepted by a W4 re-run (n of at least 10, several kill timings).**

### B2. Throughput did not rise with workers
**Recap.** 352, 364 and 251 jobs a minute at 1, 2 and 4 workers, no two jobs overlapping. **Confirmed on dev
(`docs/p9-aws-evidence-2026-11-13.md` section 9):** a real message sent by this repository's dispatch carried
`MessageGroupId = default`. One FIFO group means one in-flight message, so jobs ran one at a time. Not observed:
the API's own sends (its kombu is probably 5.7.0, the workers' 5.6.2; both fall back to `default` by source reading).

**Built** on `fix/lost-worker-retry-and-secret-guard` as its own commit: a `before_task_publish` handler in
`tasks/var_task.py` sets `MessageGroupId` to the task id (SQS broker only; the API at submission, a worker on
retry). Tests follow Celery's real publish path into kombu's SQS `_put` on kombu 5.6.2 and 5.7.0, and fail if the
handler is disabled (`tests/test_sqs_message_group.py`). One message stuck in its visibility timeout no longer
holds the other jobs back. The throughput gain is **not yet measured**: that is B4.

| Option | Pros | Cons |
|---|---|---|
| 1. A group id per message (built) | Workers run in parallel; a stuck message blocks only itself; ordering was never used | FIFO ordering lost; a retry waits only for its own original message to be acknowledged |
| 2. A group per user | A heavy user cannot occupy every worker | One user's jobs run one at a time; more design |
| 3. A standard (non-FIFO) queue | Simplest scaling | A new queue and CDK change; `CLAUDE.md` 3.2 rewritten; duplicates and no ordering |
| 4. Leave it | No work; about 1,200 jobs a month today | Autoscaling adds workers that cannot run in parallel |

**Decision taken (2026-11-16): confirm first, then 1.** Confirmed; 1 is built and waits for the PR.

### B3. Public texts that imply a lost Spot job is only delayed
**Recap.** Four places: `CLAUDE.md` 3.2, the live `portal/guide-technical-deepdive.html` (line 92), the
deep-dive Medium article, and a comment in `pyvar-cdk/stacks/compute_stack.py`. W4 shows this is true for
graceful termination and not for an abrupt loss.

| Option | Pros | Cons |
|---|---|---|
| 1. Fix the live portal sentence and the draft now, from measured facts | No overclaim online | May be edited again if B1 is adopted; a portal change starts a pipeline run |
| 2. Wait for B1, edit all four once | One edit | The overclaim stays live meanwhile |
| 3. Edit all four now, including `CLAUDE.md` | Consistent at once | `CLAUDE.md` is the project's instruction file and needs your explicit go |

**Recommendation: 2 if B1 is decided within a week; otherwise 1.**

### B4. A second W4/W5 pass
**Recap.** The first pass had no database counts, no FIS arm, queue-mode load and one kill timing.

| Option | Pros | Cons |
|---|---|---|
| 1. After B1 and B2, as their acceptance test, with a read-only database role, a FIS template and an allow-listed source | Tests the fixes; fuller evidence | Needs those three inputs |
| 2. Now, to broaden the baseline | More evidence sooner | Repeated after the fixes |
| 3. Skip | No work | The fixes go unmeasured |

**Recommendation: 1.**

## C. Verification and governance

### C1. Check the fallback-insert fix on dev: done
**Result (2026-11-16, one run of the `pyvar-dev-migrate` task with a read-only script, about 29 s, exit 0).** The five
jobs sent straight to the queue on 2026-11-15 left five `var_jobs` rows with `user_id = unknown` and status
`success`, all in the 18:00 UTC hour. No failure rows of any kind in the last three days. The worker log shows 251
"audit write failed" lines, all in the 2026-11-14 18:00 hour, and none since; "cannot supply the request columns"
appears 0 times. The worker group did log activity in the 18:00 hour of 11-15 (51 events, 5 of them "VaR computation
complete"), so the silence is meaningful. The fix reached dev between 16:22Z (merge) and 16:47Z (API deployment);
whether the worker that ran the five jobs (launched 18:38:44Z) cloned the merge is inferred from its launch time,
not seen. The agent made no other change and recorded the run as a single authorisation, not a standing path to the
database. **Left for you:** look at the Sentry issue and resolve it. The mechanism stays available for G1.

### C2. Prod stage showed "Succeeded"
**Recap.** The pipeline has a manual approval step before prod and it is on in code
(`require_prod_approval = True`, no override). So a Succeeded Prod stage means someone approved it.
**Action:** open the pipeline's execution history and read who approved `ApproveProductionDeploy` and when. If it
was you, nothing to do; if not, treat it as an access question (C3).

### C3. What the agents run as
**Recap.** The AWS agents used the broad `pyvar-cdk-deployer` user in an account that also holds prod and other
products; only resource names kept them away from prod.

| Option | Pros | Cons |
|---|---|---|
| 1. A dedicated role per kind of task, limited by resource name or tag (dev only; read-only for evidence runs) | Removes the name-only guard; small | IAM work; must be kept in step with the stacks |
| 2. A permission boundary on the deployer user | Protects everything | May break CDK deploys |
| 3. Separate AWS accounts per environment and per product | Strongest isolation; also solves the cost split | A migration; duplicated fixed costs |

**Recommendation: 1 now; 3 as a planned project, decided with D1's results.**

### C4. Two high-severity Dependabot alerts: PR #432 is open
**Recap.** Both alerts are one advisory (GHSA-cg8m-r9f2-5wm2) on two manifests: `black` 26.5.1 in the dev extras of
`pyvar-client` and `pyvar-jupyter`, first patched 26.10.1. PR #432 changes those two lines and nothing else. The PR's
reachability reading: the flaw is in Black's GitHub Action (`use_pyproject`), the repository does not use that action,
and `black` is only run as a command-line formatter. Its before-and-after local runs are identical (root 2,882
passed, client 447, jupyter 33). At the last look every GitHub check had passed except one `Tests (Python 3.11)` job
still running; the merge state read "blocked" (a required check pending, or a review rule).

**Pipeline note (`CLAUDE.md` 8.1), stated before any merge:** `pyvar-client/` is one of the 8 excluded directories
but `pyvar-jupyter/` is not, so merging **will trigger a CodePipeline run** for a change to a development extra.

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Merge #432 alone, once the last check is green | Closes both alerts; smallest change | A pipeline run for two dev-extra lines |
| 2. Merge it right before the A5/B1/B2 PR so one pipeline run carries both | Possibly one run instead of two | Only if the pipeline supersedes a queued run, which I have not verified; couples two unrelated changes' timing |
| 3. Leave it open | No run | Two high alerts stay open (not reachable, so low urgency) |

**Recommendation: 1.** The alerts are not reachable; the cost is one pipeline run either way.

### C5. `var_jobs` rows left at "pending"
**Recap.** The C1 run showed 7 `var_jobs` rows created on 2026-11-14 by the API (not fallback rows) still `pending`
after more than an hour. The agent did not look into them. Likely cause (inference, not checked): jobs whose worker was
lost during the W4 drill, which never reached the terminal write. After B1 a job lost twice goes to the dead-letter
queue, which updates nothing, so the same state will recur for jobs that exhaust their one retry. `var_jobs` is an
audit log (`CLAUDE.md` 3.3: never delete rows).

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Look first: a read-only run listing the seven rows (ids, created, tier, size) | Facts before a change; same mechanism as C1, one new authorisation | Another agent run |
| 2. One reviewed UPDATE marking those seven as failed ("worker lost, W4 drill") | Clean audit trail | A write to an audit table, by hand; your call |
| 3. A reconciler that marks rows pending beyond a limit as failed, or a dead-letter handler | Fixes the recurring case | New code and design; sensible after B4 shows how often it happens |
| 4. Leave them | No work | Misleading rows; any count of pending jobs is wrong |

**Recommendation: 1 now; 2 if they are the drill's; 3 after B4.**

## D. Money and measurement

### D1. Cost tags, README wording and the inventory
**Recap.** Account-wide cost is about $887 to $1,052 a month, about 97% fixed; `Project` and `Environment`
are not activated as cost-allocation tags, so prod, dev and other products cannot be split. The README's "real
prod invoice" figure ($900 to $1,000) is account-wide.

| Option | Pros | Cons |
|---|---|---|
| 1. Activate the two tags in the Billing console | One setting; no code | Forward-looking (a backfill can be requested); untaggable spend stays unallocated |
| 2. Allocate by resource id from the cost-and-usage report | Works for past months | Heavy |
| 3. Run the read-only inventory prompt (already written) | Free; maps the nine fixed lines to products now | An estimate, not a bill |

**Recommendation: 1 and 3 now; change the README wording after one full month of tagged data.**


### D2. Two idle Aurora readers (about $157 a month): now the highest priority if proved idle
**Recap.** From the inventory (`docs/p9-aws-evidence-2026-11-13.md` section 8): both clusters have a reader
with 0 connections on every day of October, billing the cluster minimum: about $105 for prod and $52 for dev
(arithmetic: 1.0 and 0.5 ACU x 730 hours x $0.14). Code facts, checked on `7e35bbc`: the application connects only
to the host in the database secret (the cluster endpoint); no code uses a reader endpoint; each reader is one
`scale_with_writer` instance with promotion tier 1; its CloudFormation `DeletionPolicy` is `Delete` in both
environments, so removing it from CDK deletes it cleanly.

**Proof, run 2026-11-16: both readers are IDLE** (full table in `docs/p9-aws-evidence-2026-11-13.md` section 10).
Zero client connections in all 1,118 hours from 1 October, zero Performance Insights load in 10,020 of 10,020
one-minute points over the last 7 days, no result traffic, and no failover event in the 14 days RDS keeps. Cost,
at the average ACU: about $103.67 a month for the prod reader and $51.28 for the dev reader. Only the API and the
workers can reach a reader's port. Caveats: a connection shorter than the sampling interval cannot be excluded
(VPC flow logs were not read), and both readers show CPU and capacity bursts, in the maintenance window for prod,
that nothing explains. The metrics measure use, not failover readiness.

**Change, ready and not pushed.** Branch `infra/aurora-reader-flag` (`048526f`): `aurora_reader_enabled` in
`pyvar-cdk/config.py`, default true, false only in dev; `DataStack` builds its readers list from it; test
`tests/test_cdk_aurora_reader_flag.py`. `cdk synth` against master: the dev data stack loses `AuroraReader` and
nothing else; the prod data stack and every other stack are byte-identical. It is under `pyvar-cdk/`, so
merging it starts a pipeline run (`CLAUDE.md` section 8.1); `infra/*` needs the synth diff in the PR, which I have.

An idle reader is not an unneeded one: it is the failover target. The two readers are different decisions.

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Remove the dev reader only | Saves about $52; dev needs no failover; no prod change | Prod keeps its cost |
| 2. Remove both | Saves about $157 | Prod has no warm failover target: after a writer failure a new instance has to be created, which typically takes minutes (not verified for these clusters) |
| 3. Keep prod's reader and lower prod's minimum capacity from 1.0 to 0.5 ACU | Halves the reader's bill and the writer's floor (about $102 in all) | Not verified how prod behaves with the lower floor under bursts; a deliberate setting that has no stated reason |
| 4. Keep both | Failover readiness | About $157 a month for instances nothing queries |

**Recommendation: remove the dev reader now (option 1)**; the evidence is as solid as these metrics get and dev
needs no failover. **Decide prod together with G3**: the home page states "99.97% uptime", and a published uptime
figure leans on a warm failover target (the sentence has no source today either way, G3). Either keep the
reader and settle the sentence, or drop the reader and the sentence; the Terms already disclaim availability. If prod's reader goes, set `aurora_reader_enabled=False` for prod
in a second PR, which waits at the prod manual approval.

### D3. Dev's fixed footprint
**Recap.** Dev is an estimated $403 of the nine lines, about 72% of prod's $558, because it has its own VPC,
NAT, endpoints, cache, Aurora and ALB.

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Leave it | No work; dev mirrors prod | About $400 a month |
| 2. Turn off ECS Container Insights on dev | Removes part of the custom-metric charge (the CloudWatch line is $28.62, mostly Container Insights on the two clusters) | Less dev observability; the saving is small and the split is the weakest estimate |
| 3. Slim dev down: endpoints in one availability zone, review the NAT | Endpoints are $82 a month in dev; a single zone would roughly halve that | Dev no longer matches prod's network; needs a CDK change per environment |
| 4. Scale dev's stateful services down when idle | Largest possible saving | Not checked whether these services can pause, and cold starts on the next use |

**Recommendation: 1 for now; revisit with a month of tagged data (D1).**

### D4. No lifecycle policy on the API image repositories
**Recap.** The prod repository holds 157 images and ECR billed $17.46 in October. **Correction to the first plan:** the
repositories are not CDK resources. `api_stack.py` imports them by name ("lifecycle rules ... are managed on the repo
itself, not here") and the pipeline's Synth step creates `pyvar-prod-api` with `aws ecr describe-repositories ... ||
aws ecr create-repository`; `pyvar-dev-api` is also created outside the stack. The `api_stack.py` docstring says a
lifecycle policy deletes untagged images after 30 days; nothing in the repository sets one (searched `pyvar-cdk/`).
**Decision (owner): keep the newest 30 images** (the recommendation).

| Option | Pros | Cons |
| --- | --- | --- |
| 1. The pipeline sets the policy each run: `aws ecr put-lifecycle-policy` (keep the newest 30 images) for both repositories in the Synth step, with `ecr:PutLifecyclePolicy` added to the Synth role for both repositories | In code, idempotent, survives a recreated repository | A change to `pipeline_stack.py` (the pipeline updates itself), IAM, and a pipeline run; rollback past 30 builds needs a rebuild |
| 2. The owner applies the policy once with the CLI (an agent prompt) | No pipeline run; immediate | Not in code; a recreated repository loses it |
| 3. Leave it | No work | The count grows with every deploy |

**Recommendation: 1 in the second PR** (and fix the stale docstring). Option 2 meanwhile if you want the saving at once.

## E. Content and product

### E1. The assistant article for Medium
**Recap.** Written, the HTML built, the screens retaken after the portal fixes. It says the live site was
checked on 2026-11-14. **Recommendation:** publish when you choose, after re-running its two `curl` checks that
day and updating that date.

### E2. The typed assistant (switched off)
**Recap.** Gates before it can go on: privacy and terms wording naming the model provider, a guard for "Does X
support Y?" questions, and a second model sampling live answers.

| Option | Pros | Cons |
|---|---|---|
| 1. Keep it off; do the gates later | No risk | No typed answers |
| 2. A small beta after the gates | A feature | Cost, risk and work |
| 3. Remove the typed code | Less surface | Throws away built work |

**Recommendation: 1.** Do the privacy and terms wording in one pass with A2 and A3, which need it too.

### E3. "JIT-accelerated" in the GitHub description and README
**Recap.** Deferred by the owner on 2026-11-13. After the two engine fixes the NumPy comparison is faster in 3
cases, level in 2, slower in none, so speed over NumPy is not a JIT advantage in every case.

| Option | Pros | Cons |
|---|---|---|
| 1. Leave it | Your standing decision | The wording can be read as a claim the benchmark only partly supports |
| 2. "Accelerated with Numba where per-path work dominates" | Matches the measurements | Longer |
| 3. Drop the adjective | Safe | Loses a selling point |

**Recommendation: 2, whenever the README is next touched.**

### E4. Pilot sign-off and the ES source
**Recap.** On hold; this session holds no detail beyond that. **Recommendation:** leave it on hold; tell me what
it is waiting for and I will propose options.

## G. Found while confirming B2

### G1. Dependencies are not pinned, so the API and the workers run different kombu versions
**Fact (build logs, `docs/p9-aws-evidence-2026-11-13.md` section 11).** Dev and prod run the same API image
(identical digest, built 2026-11-15): kombu 5.7.0, celery 5.7.0, billiard 4.3.2, amqp 5.4.2, vine 5.1.0. The workers
run the AMIs of 2026-07-10 (dev) and 2026-08-08 (prod): kombu 5.6.2, celery 5.6.3, billiard 4.2.4, amqp 5.3.1, vine 5.1.0.
One minor version apart in both environments. `requirements.txt` pins `celery>=5.3.6` and nothing else on this path.
**Decision (owner): read the versions, then pin** (the recommendation).

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Pin the API to the workers' versions in `requirements.txt` (celery 5.6.3, kombu 5.6.2, billiard 4.2.4, amqp 5.3.1, vine 5.1.0) | One file; no AMI bake; restores the combination that ran until 2026-11-15; B2's handler is tested on both versions | The pins also have to go into `ami_stack.py`'s inline pip lines at the next bake, and changing that file starts a prod AMI bake (`CLAUDE.md` 11), so that part waits for an intended bake |
| 2. Move the workers to 5.7.0 instead (a rebake) | Newest versions everywhere | A bake in both environments; untested on workers |
| 3. A lock file read by the API image and the AMI recipe | Reproducible everywhere | Larger; the recipe installs from inline pip lines |

**Recommendation: 1 now (second PR); the matching `ami_stack.py` pins with the next intended bake.**

### G2. Workers run the code of the default branch at the moment they boot
**Recap (from `pyvar-cdk/stacks/compute_stack.py`, not observed live).** With the baked AMI the worker's user data
runs `git clone` of the repository's default branch into `/opt/pyvar` at every boot, with the packages already on
the image. So a worker that starts after a merge runs that merge, in prod too, whether or not the pipeline has
passed the prod manual approval for the same commit: the prod API and the prod workers can run different code for
a while. The stack's own comment marks the clone as a stop-gap ("TODO: remove when Hypothesis C replaces git
clone"). A change to `tasks/` therefore reaches new workers at once, while a change to the API waits for the
approval. It also means the A5/B1/B2 branch affects workers as soon as it is merged.

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Clone the commit the pipeline deployed (a tag or SHA passed to the launch template) | Workers and API stay in step; rollback is a tag | A CDK change, the commit must be known to the stack, a pipeline run |
| 2. Bake the code into the image or ship it in the container image | The deployed artefact is what runs | Larger change; a rebake per release |
| 3. Leave it, and treat a merge to master as a prod worker release | No work | Merge discipline carries a release risk, and the prod approval does not cover workers |

**Recommendation: 1.** Decide it before the A5/B1/B2 PR is merged, so that the merge is a conscious worker release.

### G3. "99.97% uptime" on the home page is static text
**Recap.** `portal/index.html` line 169 shows "99.97% uptime" in the status bar as fixed HTML. I found no source
for it in the repository (searched the portal and the docs; I did not look at any external monitor). The Terms
(`portal/terms.html`) say availability is not guaranteed, and "SLA guarantees" appear only for Enterprise via
fibtec.co.uk. It matters for D2: it is the one published availability claim.

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Replace it with a measured figure (from a monitor or the status data) | True and current | Needs a measurement source; none is known |
| 2. Remove the item | No unsupported claim | Less reassurance on the page |
| 3. Leave it | No work | A number with no source next to a service that has no failover guarantee |

**Recommendation: 2 now, 1 when a measurement exists.** A text change under `portal/` (outside the 8 excluded
directories, so a pipeline run).

## F. Housekeeping

- **F1. Unmerged branch.** `claude/fibtec-redesign-continue-3i4abm` holds the token scripts, their tests, the
  two proposals and the open-points register. Everything is under `scripts/`, `tests/` and `docs/`, so a PR is
  pipeline-safe. **Recommendation:** open one PR now.
- **F2. Local scratch.** Old worktrees and scratch files from earlier work are still on disk here. Harmless;
  I can clear them when you say.
