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
| B2 group id | Recommendation (confirm first, then a group per message); prompt requested | Prompt delivered in chat; the fix follows its result |
| B3 public Spot wording | Leave it | Closed |
| B4 second W4/W5 pass | Recommendation: after B1 and B2, as their acceptance test | Waiting for B1 and B2 |
| C1 dev check of the fix | Prompt requested | Prompt delivered in chat |
| C2 prod "Succeeded" | The owner approved it ("it has always been me") | Closed |
| C3 AWS access for agents | Keep on hold | On hold |
| C4 Dependabot | Prompt requested | Prompt delivered in chat |
| D1 cost tags | Tags activated; inventory run | Outcome in `docs/p9-aws-evidence-2026-11-13.md` section 8; new points D2 to D4 below; README wording after a month of tagged data |
| E1 Medium article | Close the point; the owner will write another article | Closed |
| E2 typed assistant | Recommendation: keep off; one legal-text pass with A2 | Kept off |
| E3 "JIT-accelerated" | Leave it | Closed |
| E4 pilot sign-off, ES source | Not discussed | On hold |
| F1, F2 housekeeping | Not discussed | Open |

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
**Recap.** 352, 364 and 251 jobs a minute at 1, 2 and 4 workers, no two jobs overlapping. Likely cause:
every message in one FIFO group (kombu sends group `default` when none is set; nothing in the repo sets
one). A hypothesis, not proven. First step in any case: confirm the deployed kombu version and read one dev
message's group id.

| Option | Pros | Cons |
|---|---|---|
| 1. A group id per message | Workers run in parallel; ordering is not needed | Needs the mechanism confirmed in dev; FIFO ordering lost (unused) |
| 2. A group per user | A heavy user cannot occupy every worker | One user's jobs run one at a time; more design |
| 3. A standard (non-FIFO) queue | Simplest scaling | A new queue and CDK change; CLAUDE.md 3.2 rewritten; duplicates and no ordering |
| 4. Leave it | No work; about 1,200 jobs a month today | The scaling claim stays unproven; autoscaling adds idle workers |

**Recommendation: confirm first, then 1.**

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

### C1. Check the fallback-insert fix on dev
**Recap.** Merged as PR #429. The agent saw no failure lines in 5 queue-dispatched jobs, against 251 before.
Database rows and Sentry were not seen. One more scale-up in dev (task `ad8148f5`) is probably the hourly demo
publisher (inference).

| Option | Pros | Cons |
|---|---|---|
| 1. You run the SQL and look at Sentry | Authoritative, a few minutes | Needs your database path |
| 2. A read-only database role for the agent | Repeatable; also serves B4 | A new credential and IAM work |

**Recommendation: 1 now** (the query is in the earlier report; add `ad8148f5%` to it), then resolve the Sentry issue.

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

### C4. Two high-severity Dependabot alerts
**Recap.** GitHub reported them in a push; not yet looked at.

| Option | Pros | Cons |
|---|---|---|
| 1. You send the two package names; one separate PR bumps them | Targeted | A pipeline run if requirements change |
| 2. Turn on automatic security-update PRs | Ongoing | More PRs and CI runs |

**Recommendation: 1 now, then consider 2.**

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


### D2. Two idle Aurora readers (about $157 a month)
**Recap.** From the inventory (`docs/p9-aws-evidence-2026-11-13.md` section 8): both clusters have a reader
with 0 connections on every day of October, billing the minimum capacity: about $105 for prod and $52 for dev,
roughly half the Aurora line. They look like deliberate failover targets (promotion tier 1); intent cannot be
read from AWS.

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Remove both readers | Saves about $157 a month | No warm failover target: after a writer failure a new instance has to be created, which typically takes minutes (not verified for these clusters) |
| 2. Remove the dev reader only | Saves about $52; dev needs no failover | Prod keeps paying for its target |
| 3. Keep both | Failover readiness | About $157 a month for an unused instance |

**Recommendation: 2**, and decide prod once you have said what outage the service should tolerate.

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

### D4. No lifecycle policy on the prod API image repository
**Recap.** 157 images, ECR billed $17.46 in October (not one of the nine lines).

| Option | Pros | Cons |
| --- | --- | --- |
| 1. Keep the newest 30 images, expire the rest | Small, safe saving; tidy | Rollback beyond 30 builds needs a rebuild; a CDK change, so a pipeline run |
| 2. Leave it | No work | The count grows with every deploy |

**Recommendation: 1.**

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

## F. Housekeeping

- **F1. Unmerged branch.** `claude/fibtec-redesign-continue-3i4abm` holds the token scripts, their tests, the
  two proposals and the open-points register. Everything is under `scripts/`, `tests/` and `docs/`, so a PR is
  pipeline-safe. **Recommendation:** open one PR now.
- **F2. Local scratch.** Old worktrees and scratch files from earlier work are still on disk here. Harmless;
  I can clear them when you say.
