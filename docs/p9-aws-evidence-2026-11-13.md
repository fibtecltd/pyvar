# AWS evidence for the SWOT integration claim: cost per job and latency (W2, W3), 2026-11-13

**Status: W2 done, W3 done in part; W4 and W5 were not run on 2026-11-13 and were run once, in dev, on 2026-11-14 (section 7).** Source: a delegated agent in Filippo's environment, working from the prompt in `docs/plan-swot-engineering-integration.md` (section 5, W2 to W5). Its report is the source of every AWS figure below; where this document adds something, it says so. Where a figure was not re-checked against AWS by the author, it is the agent's.

**Nothing was changed in prod or dev.** The agent's AWS calls were read-only (Cost Explorer, CloudWatch metrics, CloudWatch Logs Insights, Auto Scaling activity history, SQS metrics). It sent no messages, terminated no instance, made no API call to either environment, and did not touch the dev Auto Scaling group (recorded as min 0, max 5, desired 0). Cost Explorer API calls are billed at about $0.01 each; the agent estimates about $0.08 in total (not checked on the bill).

## 1. Things to know before reading the numbers

1. **Account-wide, not prod, and probably not only pyvar.** Dev and prod share one AWS account, and so (per Filippo, 2026-11-13, and a sibling product's own CDK notes on a shared account) do other Fibtec products. The resources are already tagged in code (`pyvar-cdk/app.py` adds `Project=pyvar` and `Environment=<env>` to everything; the sibling product's app adds its own `Project`), but the tags are **not activated as cost-allocation tags** in the Billing console and resource-level cost data is not enabled, so Cost Explorer cannot split by them. Every cost figure below covers dev, prod and whatever else runs in the account. Only the `CostComponent` tag has data, and only for `spot-worker-compute`. The job counts are pyvar's own (the `JobCount` and `job-submitted-*` metrics), so the per-job divisions mix a pyvar-only denominator with an all-products numerator. The largest fixed items (Aurora, ElastiCache, VPC endpoints, NAT, Fargate, ALB) are the kind pyvar runs; the sibling product's CDK app, the only other one the author could read, is serverless and has none of them, so the pyvar share is probably the larger one. That is an inference, not a measurement: the README's "real prod invoice" for $900 to $1,000 a month is the account's bill and cannot be called pyvar's until the tags are activated.
2. **The credential.** The agent worked as the CDK deployer IAM user of that account, the only credential it had. That user has far more access than a measurement needs, and nothing but naming and the agent's rules separates dev from prod. Recommendation (open, section 6): a dedicated read-only role for this work.
3. **Most production jobs are probably synthetic (inferred, not verified).** Prod shows 19 to 20 jobs a day, steadily. The repository explains it: `pyvar-cdk/lambda/public_data_publisher/handler.py` submits the same fixed `POST /var/compute` payload every 15 minutes to refresh `demo-result.json`; a one-hour Redis result cache (`celery_result_ttl`) answers most of those calls without a job, so a real job runs every 60 to 75 minutes (19 to 24 a day, against the 19.4 launches a day measured). The agent could not check who submitted the jobs. If this is right, the per-job figures and the cold-start rate describe the demo refresh, not the experience of a customer's job, and "99% of jobs start cold" is a property of that traffic: the jobs arrive further apart than the worker lives.
4. **No distribution by domain.** Percentiles per function domain need `api_usage.duration_ms`, which lives in the database (section 5).

## What W2 to W5 are

The labels come from `docs/plan-swot-engineering-integration.md`, section 5, and are about evidence for the architecture claim, not only cost. **W2** is cost per job from the bill (done here). **W3** is latency percentiles (done in part). **W4** is a **Spot interruption drill**: AWS can reclaim a Spot worker at short notice, and the design says no job is lost (FIFO queue, late acknowledgement); W4 reclaims a dev worker mid-job and checks that the job completes exactly once. **W5** is a **throughput test**: jobs per minute with 1, 2, 4 workers and so on in dev, to show that capacity scales with workers. Neither W4 nor W5 measures cost.

## 2. W2: cost per job, from the bill (Cost Explorer, 2026-08-01 to 2026-11-01)

Gross usage, account-wide; tax comes on top ($177.35, $202.87, $210.40) and there were no credits.

| Item | Aug | Sep | Oct |
| --- | --- | --- | --- |
| Gross usage | $886.79 | $1,014.33 | $1,051.98 |
| Variable (Spot, S3, transfer, SQS; SQS rounds to $0.00) | $22.94 | $29.20 | $32.76 |
| Variable as a share of the total | 2.6% | 2.9% | 3.1% |
| Fixed or other | $863.85 | $985.13 | $1,019.22 |
| Jobs, dev and prod together (`JobCount`, no environment dimension) | 1,209 | 1,157 | 1,241 |
| Jobs, prod (`job-submitted-prod`) | 274 (partial) | 579 | 600 |
| Jobs, dev (`job-submitted-dev`) | 312 | 578 | 641 |
| Spot instance-hours billed | 262 | 317 | 351 |
| Total cost per combined job | $0.73 | $0.88 | $0.85 |
| Variable cost per combined job | $0.019 | $0.025 | $0.026 |

October, the largest fixed items: Aurora ACU hours $314.37, ElastiCache $208.32, VPC endpoint hours $163.68, NAT hours $107.14, Fargate $55.16, ALB $37.50, WAF $36.18, CloudWatch $28.62, public IPv4 $26.06. The per-environment job metrics start about mid-August, and for September and October `JobCount` equals prod plus dev exactly.

Checks made by the author: the three variable shares and the three per-job figures reproduce from the table. A prod-only cost per job cannot be computed; attributing the whole bill to prod's own jobs gives an upper bound of $1.75 in both September and October, a bound and not a measurement.

**Against the earlier bottom-up audit** (`docs/p9-scenario-volume-cost-audit.md`):

- *Fixed cost.* The audit put prod at $349 to $430 a month; the account-wide measured figure is $864 to $1,019 (2.0 to 2.9 times), which includes dev. This is in line with the 2.2 times "too low" already noted.
- *Variable cost.* The audit's Spot activation cost was $0.006 to $0.012 and it assumed 10 activations a month. Measured: about 580 prod activations a month, and about $0.023 each (0.266 instance-hours at about $0.087 an hour). The sources of the gap are the activation count (about 58 times) and the instance's lifetime (section 3), not the compute seconds.
- *What it means for the claim.* "The marginal compute cost of a job is a small fraction of a cent" is not supported. Measured: about $0.02 to $0.03 a job, nearly all of it a Spot instance kept alive about 18 minutes for a job of about 6 seconds. What the bill does support is that cost is mostly **fixed** (97% of it), so it is flat in volume at these volumes; it is not low.

## 3. W3: latency, prod, read-only

| Measure | Value | n | Window |
| --- | --- | --- | --- |
| ALB target response time, all endpoints | p50 5 ms, p95 60 ms, p99 258 ms | about 33,300 | 14 Oct to 13 Nov |
| Worker runtime of `compute_var` | p50 5.85 s, p95 20.46 s, p99 29.32 s, max 32.62 s | 580 | 14 Oct to 13 Nov |
| Launch to worker ready | p50 79 s, p95 104 s, p99 121 s, max 138 s | 581 | 14 Oct to 13 Nov |
| Instance lifetime | p50 1,098 s, p95 1,156 s | 581 | 14 Oct to 13 Nov |
| Jobs that were the first on a fresh worker | 99% (576 of 580) | 580 | 14 Oct to 13 Nov |
| Submit to result, cold (fresh worker) | p50 171 s, p95 204 s, p99 218 s, max 255 s (accurate to about 30 s) | 288 | last 15 days |
| Queue wait, submit to received | p50 164 s, p95 188 s, p99 201 s | 291 | last 15 days |
| Submit to result, warm | not reported (n = 3, below the cut of 30) | 3 | last 15 days |
| Per-domain percentiles | not measured | | |

Also: 582 worker launches in 30 days (19.4 a day), 154.6 prod instance-hours, and 0 tracebacks or error lines in 17,592 worker log lines. The submit time comes from the per-minute SQS send metric, hence the 30-second accuracy and the 15-day window.

**Notes.**

- The ALB figures describe a light API, not compute: a p95 of 60 ms is far below any Monte Carlo job, as the soak test's 3.9 to 6.2 ms (canary invocations) already showed. All endpoints are mixed.
- The earlier single measurement of 145 s for the first job after idle (`docs/p9-day-minus-3-smoketest-status.md`) is below the measured median of 171 s and was one sample. The measured distribution replaces it.
- The instance lifetime of about 18 minutes for a 6-second job is consistent with the scale-in rule in `pyvar-cdk/stacks/compute_stack.py`: capacity follows target tracking on queue depth, and AWS's target tracking waits for a long run of consecutive low readings before it scales in. The agent did not trace this and the author did not test it; it is the first thing to look at if cost per job matters. The agent also saw a constant 304 s launch-activity duration in the Auto Scaling history and did not investigate what sets it.
- 79 s to a ready worker is in line with the "about 90 s" in the design comment.

## 4. W4 and W5: not run (as of 2026-11-13; both run on 2026-11-14, see section 7)

**W4, Spot interruption drill (dev).** Not run, deliberately. Dev is the Auto Scaling group `pyvar-dev-workers` (min 0, max 5, desired 0) and the queue `pyvar-dev-var-jobs.fifo` (visibility timeout 60 s, three receives before the dead-letter queue; the agent's reading of the live queues). Reasons:

- No Fault Injection Service role or template exists, and creating one needs an IAM role.
- The only dev credential the agent had is the free-tier test token: 10 jobs a day, 10,000 simulations at most, while the repository's chaos test uses 500,000.
- Terminating the instance triggers the graceful-shutdown hook, and a short job can finish before the instance dies, so a weak version would not test message loss and would mislead. The agent chose not to run one.
- `scripts/chaos_test.sh` reads the dev JWT secret from Secrets Manager and forges a pro-tier token. The agent judged that to be widening its own access and did not run it.
- The audit-row check could not be made without database read access. What the code shows (author, `tasks/var_task.py`): the API inserts the job row on submit, the worker updates it by task id, and if it finds none it inserts a row with `user_id="unknown"`. That fallback is the only duplicate-row path and is the thing a drill would need to look for.

**W5, throughput against workers (dev).** Not run. The free tier's 10 jobs a day cannot supply the hundreds one step needs. `locustfile.py` sends the origin-verify header, which the agent would strip, so traffic would go through CloudFront and its WAF, which (per the agent's notes) allows 100 requests per 300 seconds per IP: a step would measure the WAF limit, not the workers.

## 5. What the evidence changes in the SWOT plan

Applied to `docs/plan-swot-engineering-integration.md` in the same pull request: the draft wording, the evidence ledger (cost per job, monthly cost, first job after idle, API latency, Spot safety, throughput), the weaknesses, W2 to W5 status and the decisions table. In short: cost is mostly fixed and the variable part is about $0.02 to $0.03 a job, not a fraction of a cent; the first job after idle takes about three minutes at the median and nearly every job is first; the interruption and throughput claims remained unmeasured (both were measured on 2026-11-14: section 7).

## 6. What W4, W5 and per-domain percentiles need (Filippo's decisions)

*Update 2026-11-14: W4 and W5 were run without the pro-tier credential, the database role, the FIS template or an allow-listed load source (section 7 says what that cost the evidence). The agent minted its own 24-hour token with the owner's explicit authorisation. Per-domain percentiles, the dedicated read-only AWS role, the cost-allocation tags and the optional steps are still open.*

| Need | Why | Suggestion |
| --- | --- | --- |
| A dev credential with a pro-tier quota, issued by someone authorised | The free tier cannot supply a drill or a load step | Issue it from the dev environment's normal route; the agent should not mint it from the dev secret |
| A database read path to `api_usage` and the job table | Per-domain percentiles; the duplicate-row check after a drill | A read-only database role (or a Data API/reader route) for this work; not the database secret |
| FIS or terminate-instance for W4 | Terminating alone does not test message loss for a short job | FIS with an IAM role scoped to the dev group; or terminate mid-job on a deliberately long job (a large simulation count, which needs the pro quota) |
| A load source that is not WAF-throttled | W5 would otherwise measure the WAF | An allow-listed source, or a dev test route that bypasses the edge |
| A dedicated read-only role for AWS reads | The deployer user is much broader than W2 and W3 need | Create one; revoke it after the work |
| Activate `Project` and `Environment` as cost-allocation tags (Billing console, payer account) | Splits pyvar from the other products and prod from dev. The resources already carry both tags, so this is a console setting, not a deploy; it applies from activation, and AWS offers a backfill request for earlier months (not checked for this account) | One setting; no code change. Untaggable spend (data transfer, tax, support) stays unallocated |
| Optional first step, free and read-only: an inventory of the account's billable resources (Aurora clusters, ElastiCache, NAT gateways, VPC endpoints, load balancers) by name and tag | Maps the fixed items to products now, before the tags have data | A short prompt for the same delegated agent |
| Optional: enable ALB access logs in prod | Request-level latency without the database | An infrastructure change in `pyvar-cdk`, so a pipeline run |

## 7. What the agent got wrong along the way (as reported)

It first read the dead-letter queue's attributes for the prod queue and re-read both queues by exact name; a first SQS reconstruction counted zero-minute datapoints as sends and was discarded; its log-query guard let two raw Celery lines through (a boot line with an internal hostname and a task-received line with a task id, neither a secret nor personal data) and was fixed. Its intermediate files are in `/tmp/w3` and `/tmp/ce_*.json` in its own environment, with timestamps and instance ids and no secrets, and are not in this repository.

## 7. W4 and W5, run on 2026-11-14

**Status: both run once, in dev only, as a first pass.** Source: a second delegated agent, working from `docs/spot-drill-throughput-delegated-agent-prompt.md` (same pull request). Its report is the source of every figure in this section. Its raw output is on its own machine (`/tmp/w4w5`) and is not in the repository, and the author has not re-checked any figure against AWS. Where this section adds something, it says so (the sub-section "Checked against the code").

**Scope.** Dev only; nothing in prod; no change to IAM, security groups, WAF, queues or CDK. The Auto Scaling group `pyvar-dev-workers` was pinned (min = max = desired = N, never above 5) during W5 and ended at its recorded values, min 0, max 5, desired 0, with no instances and an empty queue and dead-letter queue; the scaling policy raised desired back to 1 on its own after several restores (alarm lag) and it returned to 0 each time. Estimated spend: 21 Spot instances, 1.42 instance-hours, about $0.12, plus under $0.05 for everything else (the agent's estimate; not checked on the bill).

**Settings of this pass:** no database access, no FIS template, load through the queue and not the API. So there are no `var_jobs` row counts, no arm with a real 2-minute Spot notice, and W5 measures neither the API nor the WAF.

**The token.** With the owner's explicit authorisation the agent read the dev JWT signing secret once and signed one token: `sub` `internal-w4w5-agent`, tier `internal`, issued 2026-11-14 17:50:14 UTC, expiring 2026-11-15 17:50:14 UTC. It cannot be revoked before then (rotating the dev secret is the only way). Per the agent it was held in memory in one local process, forwarded only to the dev API, and never printed or stored; a scan found it in no file.

### Calibration

A 20 to 30 s job was not reachable with the parameters the API accepts.

| Settings | Warm runtime |
| --- | --- |
| n = 100,000, 1 day | 0.16 to 0.27 s |
| n = 500,000, 1 day | 0.29 s |
| n = 500,000, 50 days | 0.86 s |
| n = 500,000, 125 days | 1.78 s |
| n = 500,000, 250 days | 3.27, 3.28, 3.30 s |

The agent used n = 500,000 and `horizon_days` = 250 (about 3.28 s warm), the longest job the API accepts. The first job on a fresh worker takes 4.6 to 4.8 s because of JIT compilation. Each W4 job had a unique portfolio value with the same seed, because the API's result cache answers identical requests without running anything; the expected result was computed once, and the percentages, mu, sigma and n match exactly across jobs.

### W4: is a job lost or duplicated when the worker dies mid-job?

| Arm | n (valid) | Lost | Duplicated executions | Seconds to result |
| --- | --- | --- | --- | --- |
| A: hard kill (`ec2 terminate-instances`) | 5 | 5 | 0 seen | no result: the API reports failure at 10.3 to 10.4 s |
| B: graceful (Auto Scaling terminate, drain hook) | 5 | 0 | 0 (received once, succeeded once, each) | 10.3 to 10.5 s |

- **Arm A:** every job was reported as failed, with "Worker exited prematurely: signal 15 (SIGTERM)". None was redelivered, and the queue and the dead-letter queue were empty afterwards. A client polling sees a quick failure, not a hang. The dying instance shipped no log lines, so "0 duplicated" means none visible. A replacement worker was ready 60 to 194 s after the kill.
- **Arm B:** all 5 jobs finished once on the original worker, about 1.9 s after the terminate call, and all 5 results equal the expected one. The replacement was ready 86 to 111 s after the call.
- **Timing:** every kill landed 1.31 to 1.32 s after the queue showed the job in flight, which is 40% of 3.28 s, measured from the queue and not from the log line (the log lags by several seconds, longer than the whole job). "Seconds to result" is limited by the agent's polling (about 6 s).
- **Small and narrow:** n = 5 per arm, one kill timing. A discarded first run had a second hard kill at 1.71 s after in-flight; that job was redelivered and succeeded and is not counted. So "5 of 5 lost" applies to kills at about 1.3 s, and the data cannot say how often a hard kill loses a job in general.
- **Not tested:** the real 2-minute Spot notice (arm C needs a FIS template; none was supplied).

### W5: throughput against the number of workers (queue mode)

| N | Jobs completed | First enqueue to last completion | Throughput, middle 60% | Worker runtime p50 / p95 | Instance-hours | Efficiency |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 60/60 | 10.2 s | 352 jobs/min | 0.154 / 0.186 s | 0.019 | 1.00 |
| 2 | 60/60 | 11.0 s | 364 jobs/min | 0.152 / 0.190 s | 0.054 | 0.52 |
| 4 | 120/120 | 27.0 s | 251 jobs/min | 0.152 / 0.195 s | 0.151 | 0.18 |

- Workers were ready after 42, 76 and 81 s for N = 1, 2 and 4. The group was pinned at N each step, because otherwise the queue-depth scaling policy would have added workers.
- **Serial execution:** measured from true execution intervals, no two jobs overlapped at any step. The gap between consecutive jobs was about 11 to 12 ms, and jobs were spread about evenly across workers but never ran at the same moment. Throughput is therefore about 1 / (0.152 + 0.011 s), roughly 6 jobs per second, whatever N is, and N = 4 is lower.
- **Job size:** the jobs take about 0.15 s, so this measures the queue path, not CPU scaling.
- **Small:** one run per N, each over a window of 10 to 27 s. The agent dispatched with kombu 5.7.0; the API's own kombu version may differ.
- The agent's report says queue mode "added about 251 `var_jobs` rows with user_id 'unknown'" and that jobs above 10,000 simulations wrote an estimated 300 or so result objects to the dev S3 bucket. The first statement is probably wrong (see below); the second was not verified.

### Checked against the code (author; not part of the agent's report)

All at release `c52e056`, the code running in dev.

- **Why arm A lost its jobs.** `tasks/var_task.py` sets `task_acks_late=True` and nothing sets `task_reject_on_worker_lost`. In Celery 5.6.3's `Request.on_failure` (read in the installed source, not run), a task whose worker process is lost is acknowledged and marked failed unless `reject_on_worker_lost` is set, even with late acknowledgement. That fits "signal 15, failed, not redelivered". The deployed Celery version was not checked (`requirements.txt` has `celery>=5.3.6`).
- **Why throughput did not rise.** kombu's SQS transport (5.6.2 here) sends `MessageGroupId` "default" when a message carries none (`kombu/transport/SQS.py`), and no `MessageGroupId` is set anywhere in the repository. A FIFO queue releases one in-flight message per group, so every job would run one at a time whatever the worker count, which matches the serial execution. `pyvar-cdk/stacks/queue_stack.py` says Celery uses the task name as the group; kombu's code says otherwise. This is a hypothesis: the agent did not read queue messages (receiving them changes their receive counts), and the deployed image's kombu version was not checked. If it holds, API-submitted jobs are serialised too.
- **Sentry errors during W5.** Two events (dev, 2026-11-14 18:41:10 and 18:41:22 UTC, release `c52e056`): `IntegrityError ... null value in column "portfolio_value" of relation "var_jobs"`. Queue-mode jobs have no submission row, so the worker's fallback INSERT ran, and it left out four NOT NULL columns, so the database refused it. The jobs themselves succeeded. This is fixed in this pull request (`tasks/var_task.py`, `tests/test_var_task.py`). Consequence: queue-mode jobs most likely wrote no `var_jobs` rows at all (inferred from the code and the events; the row count was not checked, since there was no database access). The failed write ran inside each job after the timed engine call, so it may account for part of the 11 to 12 ms gap; it cannot explain jobs never overlapping.

### What the agent reported getting wrong

- A first POST with a 12.5 KB body was blocked by the managed 8 KB body-size WAF rule. The agent confirmed that from read-only WAF samples, shrank the body to about 3 KB and continued, without touching the origin secret or the WAF. This was a judgement call against the prompt's rule to stop on a denied call.
- A second identical request was answered from the API cache; each request was then made unique.
- The first W4 driver classified trials from the victim's logs (lost after a fast kill) and would have picked arm A forever; it was stopped and its two trials discarded into a separate file. An interrupt was sent to three processes, one of them the agent's own tool call; no harm followed.
- An equality tolerance of 1e-9 was too tight for cent-rounded amounts and was changed to 1e-6.
- Trial 8 started on an instance that had just been killed (the group still listed it as in service); its job ran normally on the replacement, and an EC2 running check was added.
- The first W5 driver counted two jobs "executing at once" at N = 2 and N = 4 from the "received" log line; from execution intervals the figure is 1.

### What this changes, and what is open

- **Spot safety:** graceful termination held (5 of 5); an abrupt loss of the worker lost the job and reported it failed (5 of 5, one timing); a real Spot notice was not tested. These statements say or imply that late acknowledgement makes an interrupted Spot instance's job only delayed: `CLAUDE.md` 3.2, `portal/guide-technical-deepdive.html` (line 92), `docs/publications/pyvar-technical-deepdive-medium-article.md` (line 79) and the comment at `pyvar-cdk/stacks/compute_stack.py` line 429. They are **not changed** in this pull request: the right wording depends on the decision below.
- **Decisions for the owner, open:** (1) set `task_reject_on_worker_lost` so an abruptly lost job is redelivered (the trade is possible redelivery loops and double execution, which the visibility timeout and the job's determinism limit); (2) give each message its own group id so jobs can run in parallel, after confirming the deployed kombu version and the cause; (3) then correct the four texts above and re-run W4 and W5.
- **A second pass would add:** a read-only role on `var_jobs`/`api_usage` (row counts, duplicate check), a FIS template (the real 2-minute notice), an allow-listed source (API-mode load, which also measures the WAF), several kill timings and a larger n.

## 8. Fixed-cost inventory, run on 2026-11-16

**Status: done, read-only.** Source: a third delegated agent working from `docs/aws-inventory-delegated-agent-prompt.md`. Its report is the source of every figure here; the full report (`/tmp/inv/REPORT.md`) is on its own machine and not in the repository, and the author has not re-checked any figure against AWS. The agent changed nothing, made 106 logged read-only calls (plus about 270 unlogged ones, below) and 4 of its 30 Cost Explorer calls; one call was denied (resource-level Cost Explorer data is an opt-in on the payer account) and it did not work around it. It ran as an IAM user named for the CDK deployer, which probably has write rights.

**Tags.** `Project` and `Environment` were activated for billing on 2026-11-16 (about 11:50 UTC) and activation is not retroactive: a group-by-tag call for October puts all $1,262.38 under a blank `Project`. Spend from 2026-11-16 onward can be split by tag; October cannot. `CostComponent` has been active since 2026-08-04; `Owner` and `ManagedBy` are inactive.

**The nine lines.** They come to $977.03, 77.4% of October's $1,262.38; every billed figure matched Cost Explorer. The product columns are the agent's estimates: each billed line allocated by a counted or measured quantity (published unit prices times billed quantities reproduce the lines), not billed per resource.

| Line | October $ | pyvar prod | pyvar dev | other | unknown | Error of the derived quantity |
| --- | --- | --- | --- | --- | --- | --- |
| Aurora ACU hours | 314.37 | 209.95 | 104.42 | 0 | 0 | -0.02% |
| ElastiCache | 208.32 | 104.16 | 104.16 | 0 | 0 | 0% |
| VPC endpoint hours | 163.68 | 81.84 | 81.84 | 0 | 0 | 0%; the split assumes symmetry |
| NAT hours | 107.14 | 71.43 | 35.71 | 0 | 0 | 0% |
| Fargate | 55.16 | 36.76 | 18.40 | 0 | 0 | +0.12% |
| ALB | 37.50 | 18.75 | 18.75 | 0 | 0 | 0% |
| WAF | 36.18 | 10.00 | 18.13 | 8.00 (tengrade) | 0.05 | 0% |
| CloudWatch | 28.62 | 9.95 | 9.95 | 2.70 | 6.01 | not bounded |
| Public IPv4 | 26.06 | 14.89 | 11.17 | 0 | 0 | -0.07% |
| **Total** | **977.03** | **557.73** (57.1%) | **402.53** (41.2%) | **10.70** (1.1%) | **6.06** (0.6%) | |

- **Almost nothing is shared.** Prod and dev each have their own VPC, NAT, cache, Aurora cluster and ALB; the other products own none of these except one WAF ACL (tengrade) and some CloudWatch metrics and alarms. What cannot be split is part of CloudWatch, one RDS OS-metrics log group used by both clusters, and about $0.12 of residuals.
- **CloudWatch is the weakest estimate.** The $28.62 is custom-metric billing ($25.93, mostly ECS Container Insights, enabled on the two pyvar clusters only) plus alarms ($2.70). The agent split the eu-west-1 metrics by today's metric counts (116 non-AWS metrics, 96 of them Container Insights) and could not reconcile that to the 80.4 billed metric-months. The "unknown" $6.01 is us-east-1's $4.34, where no custom metric exists today, plus $1.67 of pyvar metrics with no environment dimension.
- **Idle-looking.** Both Aurora readers (prod and dev) had 0 connections every day of October but bill the minimum capacity: about $105 for prod and $52 for dev, roughly half the Aurora line. They are promotion-tier-1 instances, so probably a deliberate failover target; intent cannot be read from AWS. The prod API ECR repository has no lifecycle policy and holds 157 images (ECR billed $17.46, not one of the nine lines). The agent found no unassociated Elastic IPs, running EC2 instances or EBS volumes, and nothing in the other 15 regions.
- **Outside the nine lines, not split:** tax $210.40, EC2 Spot $30.46, ECR $17.46, Secrets Manager $11.77, CodePipeline $3.58, CodeBuild $2.65.
- **Untagged:** 4 Elastic IPs (all on ALB interfaces, 2 prod and 2 dev, product inferred), 99 of 143 log groups in eu-west-1 and all 8 in us-east-1, 23 of 39 secrets, and the default VPC (which holds nothing that costs money).
- **What the agent reported getting wrong:** a truncated tag sweep (fixed; final count 1,070 rows); ECS settings printed as absent before it asked for them; the Tagging API missed 4 CloudFront distributions that do carry `Project` and listed 3 EBS volumes that do not exist (every "untagged" claim was re-checked directly); throttled log-group lookups briefly printed "4 of 99 tagged" (after a sequential retry, 0 of 99); about 270 read-only calls ran outside its logging wrapper; and the premise given to it (tags inactive) was out of date.

**What this changes.** The README's "real prod invoice" of $900 to $1,000 is the whole account (prod, dev and other products). For the nine fixed lines pyvar prod is an estimated $558 and dev an estimated $403, so dev's fixed footprint is about 72% of prod's. Do not restate a prod cost from this: wait for a month of tagged spend. New cost questions are in `docs/open-points-and-proposals-2026-11-16.md`, D2 to D4.


## 9. The message group of a real dev message, checked on 2026-11-16

An agent put ONE job on the dev queue with the repository's own dispatch (`compute_var_task.apply_async`, from an export of `7e35bbc`), read it back and deleted it before any worker ran it.

| Item | Observed |
| --- | --- |
| MessageGroupId | `default` |
| MessageDeduplicationId | a random UUID, not the task id |
| ApproximateReceiveCount | 1 on the first receive, 2 on the second |
| Queue | FIFO, `FifoThroughputLimit` perQueue, visibility timeout 60 s, `maxReceiveCount` 3 (this branch's change makes it 2) |
| kombu / celery of the dispatch | 5.6.2 / 5.6.3 |
| kombu / celery on the dev workers | 5.6.2 / 5.6.3, read from the pip summary of the latest dev Image Builder build (1.0.251, 2026-07-10); not confirmed that a running worker uses that image |
| kombu / celery in the dev API container | not determinable (no Docker on the agent's host, ECS Exec off) |

- **What it settles.** A message sent by this code under kombu 5.6.2 goes to the single group `default`; with SQS FIFO that allows one in-flight message at a time, which matches 352, 364 and 251 jobs a minute at 1, 2 and 4 workers. The throughput claim itself was not re-measured.
- **What it does not settle.** The API's own sends were not observed. The API image tagged `7e35bbc` was built on 2026-11-15 from unpinned requirements (`celery>=5.3.6`, no kombu pin, no lock file); kombu 5.7.0 was released on 2026-11-03, so the API very likely runs 5.7.0 while the workers run 5.6.2 (inference). The agent read kombu 5.7.0's SQS transport and found the same `default` fallback; the local test on this branch reproduces both versions.
- **A flaw in the prompt, mine.** `--visibility-timeout 0` returns a receipt handle that is already expired, so the delete failed. The agent received once more with 30 s and deleted it (receive count 2 of 3, no dead-letter message). The queue and the dead-letter queue ended at 0.
- **What the agent reported getting wrong:** the second receive above; a dev worker launched at 13:51Z by the scale-from-zero alarm, so it waited read-only until the group reached 0 at 14:09Z before sending (the message sat about 35 s); extras beyond the prompt (a 5 s short poll, a scrubbed environment with the result backend disabled, the 5.7.0 wheels read as text, ECR metadata and the Image Builder log); minor slips (an `-I` import, a recorder that blocked SQS calls twice, an account id printed in working output, not in the report).

## 10. Are the two Aurora readers idle? Checked on 2026-11-16

Read-only agent run (CloudWatch hourly from 2026-10-01 00:00Z to 2026-11-16 14:00Z, Performance Insights, RDS events, security group). No call was denied. Both clusters are Aurora PostgreSQL 16.13, serverless v2, one writer (tier 0) and one reader (tier 1) each, all available; prod 1 to 16 ACU, dev 0.5 to 2 ACU.

| | Prod reader | Dev reader |
| --- | --- | --- |
| Hours with client connections | 0 of 1,118 | 0 of 1,118 |
| Performance Insights active-session load, last 167 hours | 0 in 10,020 of 10,020 one-minute points | same |
| Receive / transmit peak | 0.8 to 0.9 KB/s | 0.8 to 0.9 KB/s |
| Average ACU, share of hours at the minimum | 1.0144, 99.3% | 0.5017, 99.2% |
| Replica lag (average, peak) | about 16 ms, 11.4 s | about 16 ms, 21.0 s |
| ACU-hours over the window, cost at $0.14 | 1,134.1 (floor 1,118.0), $158.77 | 560.9 (floor 559.0), $78.53 |
| Monthly (average ACU x 730 h x $0.14) | about $103.67 | about $51.28 |

- **Verdict: both IDLE** by the prompt's definition. Their writers had connections in every one of the 1,118 hours (maximum 9 in prod, 10 in dev) and were the only instances with write IOPS, so the current writers were the writers throughout; no failover or promotion event in the 14 days RDS keeps (2026-11-02 onward; the same query returned 56 routine snapshot events, so the empty result is real).
- **Who could reach a reader:** one security group per cluster, one ingress rule (TCP 5432) whose only sources are the API tasks' and the Celery workers' security groups. No CIDR sources.
- **Unexplained, with no connection or load behind them:** dev reader CPU above 50% in 117 hours (43 of them at 22:00 UTC on weekdays); prod reader scaled to 16 ACU at about 02:00 UTC on 10-10, 10-24 and 11-07 (14 days apart, inside its Saturday maintenance window 02:36 to 03:06 UTC; no RDS event was recorded for 11-07); the dev reader reads about 15 rows/s against 2.3 on prod's. Cause unproven.
- **Cannot be excluded:** a connection shorter than the sampling interval (CloudWatch about one minute; Performance Insights about one second, from the agent's memory, not confirmed); VPC flow logs were not read; Performance Insights keeps 7 days, so before 2026-11-09 only CloudWatch applies. The metrics measure use, not failover readiness.
- **What the agent reported getting wrong:** a first Performance Insights window of 5 days instead of 7 (date arithmetic), and a first pull that silently kept only the last 350 points of each call, so its first "0 load" covered about 24% of minutes (redone in 340-minute chunks, not reported); a noisy 122-row printout; a failed jq attempt it did not use; extra read-only metrics beyond the prompt (WriteIOPS, DBLoad, NetworkTransmit, Performance Insights counters); the partial current hour dropped.

## 11. kombu and celery in the API images and the worker AMIs, from build logs (2026-11-16)

Read-only agent run. Every version comes from build-log text (CodeBuild for the API, Image Builder for the workers); nothing was inspected inside an image or an AMI.

| Env | Component | Image or AMI | kombu | celery | billiard | amqp | vine | redis | boto3 | pycurl | urllib3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev | API | tag `7e35bbc`, built 2026-11-15 | 5.7.0 | 5.7.0 | 4.3.2 | 5.4.2 | 5.1.0 | 8.1.0 | 1.44.3 | 7.49.0 | 2.8.0 |
| prod | API | the same image (identical digest in both repositories) | 5.7.0 | 5.7.0 | 4.3.2 | 5.4.2 | 5.1.0 | 8.1.0 | 1.44.3 | 7.49.0 | 2.8.0 |
| dev | workers | `pyvar-dev-worker-2026-07-10T03-14-10.669Z` (the only AVAILABLE dev build; four earlier ones failed) | 5.6.2 | 5.6.3 | 4.2.4 | 5.3.1 | 5.1.0 | 8.0.1 | 1.43.45 | 7.47.0 | 2.7.0 |
| prod | workers | the two AVAILABLE builds of 2026-08-08 (identical to each other) | 5.6.2 | 5.6.3 | 4.2.4 | 5.3.1 | 5.1.0 | 8.1.0 | 1.43.67 | 7.47.0 | 2.7.0 |

- **Different in both environments, by one minor version** on kombu and celery: the API is on 5.7.0, the workers on 5.6.x. It is the first API build to be on 5.7.0 (built 2026-11-15; the release was 2026-11-03), so the API ran 5.6.x until then (inference from the release dates; not read from older builds).
- **One image serves both environments:** the pipeline built it once and pushed it to the dev repository (16:37Z) and the prod repository (16:39Z); deployed to dev at 16:47Z and prod at 17:17Z on 2026-11-15.
- **The worker boot script** only does `git clone` and runs no pip (read from the repo, not from a live launch template).
- **Not determinable:** which AMI each launch template uses now (an earlier session's note says dev the 2026-07-10 AMI and prod the 2026-08-08 AMI); PyPI patch releases between these versions; the release dates.
- **What the agent reported getting wrong:** one unlisted read-only call (`ecs list-clusters`); a withdrawn inference from the gitignored `cdk.context.json`; the CodeBuild project name taken from an August handoff document and confirmed with `list-builds-for-project`; one harmless parse crash.

## 12. Prod Aurora baseline at the 1.0 ACU floor, last 14 full days (2026-11-02 to 2026-11-16, 336 hourly buckets)

Read-only agent run of `docs/prompts/agent-d2-floor-measure.txt` in BASELINE mode (the cluster still reads MinCapacity 1.0; the last data-stack update, 2026-11-13, touched only CDKMetadata).

| Measure | Writer | Reader |
| --- | --- | --- |
| CPU: mean of hourly averages; highest hourly maximum | 2.77%; 80.0% | 2.36%; 97.6% |
| CPU: p99 of the hourly maxima | 19.1% to 19.7% | 25.0% to 27.3% |
| FreeableMemory: lowest hourly minimum; mean | 5.99 GiB; 29.1 GiB | 6.07 GiB; 29.1 GiB |
| ACU: mean of hourly averages; highest hourly maximum | 1.011; 16 | 1.024; 16 |
| Hours with any datapoint above the 1.0 minimum | 77 of 336 (22.9%) | 63 of 336 (18.8%) |
| DatabaseConnections: highest hourly maximum | 6 | 0 in all 336 hours |
| CommitLatency: highest hourly maximum (milliseconds) | 5.06 ms, otherwise about 1 ms or less | 0.85 ms |
| Read and write latency: highest hourly maximum | 0 and 0.45 ms | 0 and 0 |
| Saturday maintenance-window hours (two Saturdays) | 05:30 to 06:00 UTC: CPU up to 59.5%, ACU up to 16 | 02:36 to 03:06 UTC: CPU up to 45.3%, ACU up to 16 |

- **Client side (the prod ALB):** hourly p95 response time peaked at 1.38 s (2026-11-13, 72 requests that hour); over the whole window p95 was 0.057 s and p99 0.256 s. One 5xx in 16,444 requests (2026-11-14 03Z). Zero ALARM transitions in 30 days for `pyvar-prod-api-latency-p95`, `pyvar-prod-api-5xx` and `pyvar-prod-aurora-writer-cpu` (the last did not exist yet).
- **RDS events (14 days):** none for the cluster or either instance.
- **Cost (hourly average ACU x $0.14, compute only):** writer 339.6 ACU-hours, $47.55; reader 344.0, $48.16; both $95.70 in the window. Average capacity across both is 2.0345 ACU, about $207.93 a month; both pinned at 1.0 would be $204.40.
- **The earlier "99.3% to 99.5% of hours at the minimum" (section 10, 1,118 hours) and today's "77 of 336 hours above it" count differently** (today counts any hour with a datapoint above 1.0). The averages agree (1.01 ACU), and billing follows the average, so the cost basis stands; the share of time at the floor cannot be resolved from hourly data.
- **Outliers, no cause attributed:** both instances reached 16 ACU in the same hour on 2026-11-03 10Z (writer CPU 80%, free memory down to 5.99 GiB, reader CPU 97.6% with no connections, no RDS event, ALB p95 0.039 s that hour). Hours above the minimum cluster at fixed UTC hours: the writer's at 00, 06, 13 and 20Z daily (plus 05Z on 11 days), the reader's at 11Z daily (plus 22Z and 02Z). On 11-14 neither instance went above 2 ACU.
- **Not visible:** `FreeableMemory` reads about 29 GiB at a 1 ACU floor, so it is not bounded by the current capacity's memory (the agent reads it as relative to the 16 ACU maximum; not checked against documentation). Memory pressure at 0.5 ACU therefore will not show in that metric. Hourly resolution cannot place a spike inside its hour. The events query has no known-positive control. Alarm history cannot be listed with the allowed calls.
- **What the agent reported getting wrong:** a first analysis multiplied CommitLatency by 1000 (it is published in milliseconds; read and write latency in seconds), corrected; reads beyond the three named alarms and across several prod stacks; dev metadata visible in the listings but only prod queried; two notes written to its own memory folder.

## 13. ElastiCache Serverless data size, last 14 full days (2026-11-03 to 2026-11-17, 336 hourly buckets)

Read-only agent run of the prompt written on 2026-11-17 (describe-serverless-caches, list-metrics and get-metric-data only; no call was denied; no hours were missing in any series). Both caches are Redis 7.1 serverless caches (dev created 2026-06-22, prod 2026-08-08), maximum 10 GB and 5,000 ECPU a second, snapshot retention 0; they are the only serverless caches in the account. `BytesUsedForCache` is published in Bytes (unit checked).

| Measure | pyvar-dev | pyvar-prod |
| --- | --- | --- |
| Highest hourly maximum | 1,390,143 B (1.33 MB), 2026-11-14 18Z | 79,864 B (0.076 MB), 2026-11-11 10Z |
| Mean of hourly averages | 46,987 B | 42,828 B |
| p99 of hourly maxima | 86,411 B (nearest rank 89,594 B) | 58,102 B |
| Hours above 80 MB / 100 MB | 0 / 0 | 0 / 0 |
| Lowest hourly maximum | 52,637 B | 52,639 B |
| `CurrItems`, highest hourly maximum | 335 | 10 |
| Evictions | 0 in every hour | 0 in every hour |
| Share of the 10 GB maximum at the peak | 0.0129% | 0.0007% |
| Trend in the 14 daily highs (slope, 95% interval) | +27,368 B/day (-23,331 to +78,067): none | +61 B/day (-994 to +1,116): none |
| Cost per month at 730 h: Redis 1 GB minimum / Valkey 0.1 GB minimum | $102.20 / $6.86 | $102.20 / $6.86 |

- **Shape.** Both caches sit at a floor of about 52 KB with 2 items. Dev went from 2 items to 335 at about 18:46Z on 2026-11-14, held about 1.39 MB and was back at 2 items by 20:00Z; prod's peak is a 4-to-10-item bump on 2026-11-11 10Z to 11Z. Both peaks were read at one-minute resolution and equal the hourly maximum. (Inference, not checked: dev's burst falls on the day of the W4 and W5 runs, section 7.)
- **Cost.** Storage is billed at the minimum, not at the observed average (0.00004 GB), so the whole difference is $95.34 a month for each cache; ECPU cost is a fraction of a cent on either engine. October's $104.16 per cache used 744 hours; the 730-hour figure above is $102.20.
- **The agent's two judgement calls.** Valkey's minimum was stated as 100 MB but its own formula gave 0.1 GB (102.4 MB), which it followed (reading it as 100 MB gives $6.70 a cache); hours per month were 730 as specified.
- **Verdicts as defined in the prompt:** pyvar-dev FITS; pyvar-prod FITS.
- **Not visible:** AWS's metered data stored against `BytesUsedForCache`, and whether Valkey counts the same bytes; October's billed amount (no billing call was allowed); key types and contents (the dev burst fits keys with a one-hour expiry, which is a guess); size within an hour except the two peak hours; some one-minute readings far below the usual floor (127 B in prod's peak hour, 4,972 B in dev's), unexplained and without effect on the maximums; future load.
- **What the agent reported getting wrong:** nothing that changed a figure. Scripts and data were left outside the repository and a short memory note was saved.

## 14. Per-function request timings on dev, for the A3 trial lane (2026-11-17)

Read-only agent run of `docs/prompts/agent-a3-p95-measure.txt`: one Fargate one-off of `pyvar-dev-migrate` (the agent pinned revision 204, the one "latest ACTIVE" resolved to), command overridden to the script, exit code 0, the migration did not run. `api_usage` on dev holds 190,603 rows from 2026-07-16 to 2026-11-17.

| Group (status 200, last 30 days, at least 5 rows) | Rows | p50 / p95 / max (ms) |
| --- | --- | --- |
| `internal` / `token-report` (a database read, not a lane function) | 30 | 135 / 168 / 220 |
| `var` / `compute` (queue dispatch time only) | 2,302 | 41 / 61 / 653 |
| `var` / `result/<task id>` (582 groups, one polling route per job) | 5 to 43 each | p50 2 to 6; p95 3 to 81; highest max 716 |
| Groups with fewer than 5 successful rows (not split by domain) | 60 | not reported |

- **Reading:** dev has no usable timings for any domain function. Outside the `var` domain, one group reached 5 rows and one reached 20; the 60 groups below 5 rows cannot be split by domain, so how many are domain functions is not known. Nothing was extrapolated. Prod's `api_usage` was not read (it needs its own authorisation).
- **Facts about the mechanism that the run and a follow-up read of the repository showed** (not the agent's report): the migrate task is 0.25 vCPU and 512 MB (`pyvar-cdk/stacks/api_stack.py`), a quarter of what a timing on the API's 0.5 vCPU would need to be compared with; the image is `COPY . .` with no `.dockerignore`, so anything under `scripts/` ships in the image of the build that deployed it; the Dockerfile pre-bakes the Numba cache for **one** kernel (`run_monte_carlo_var`) and the lifespan warm-up runs only that one, so any other `@njit(cache=True)` kernel compiles or loads on its first call in each new API task.
- **Safety checks the agent reported:** names scanned for "prod" (none); `DB_*` secrets read by name only; the default command is the migration and the image has no ENTRYPOINT, so the override replaced it; all three required assertions passed, plus two extras (no write keywords, exactly three SELECTs); one `run-task` call; failures empty.
- **Spend:** about $0.0003 (72 s at 0.25 vCPU and 0.5 GB, Fargate list prices assumed, not read from a bill).
- **What the agent reported getting wrong:** nothing that changed a figure. Disclosed: it pinned the revision instead of the bare family name; the "verbatim" output in its report was abridged to keep job ids out of the body (the full file stayed on its machine); it added two safety assertions.
