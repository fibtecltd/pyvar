# AWS evidence for the SWOT integration claim: cost per job and latency (W2, W3), 2026-11-13

**Status: W2 done, W3 done in part, W4 and W5 not run.** Source: a delegated agent in Filippo's environment, working from the prompt in `docs/plan-swot-engineering-integration.md` (section 5, W2 to W5). Its report is the source of every AWS figure below; where this document adds something, it says so. Where a figure was not re-checked against AWS by the author, it is the agent's.

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

## 4. W4 and W5: not run

**W4, Spot interruption drill (dev).** Not run, deliberately. Dev is the Auto Scaling group `pyvar-dev-workers` (min 0, max 5, desired 0) and the queue `pyvar-dev-var-jobs.fifo` (visibility timeout 60 s, three receives before the dead-letter queue; the agent's reading of the live queues). Reasons:

- No Fault Injection Service role or template exists, and creating one needs an IAM role.
- The only dev credential the agent had is the free-tier test token: 10 jobs a day, 10,000 simulations at most, while the repository's chaos test uses 500,000.
- Terminating the instance triggers the graceful-shutdown hook, and a short job can finish before the instance dies, so a weak version would not test message loss and would mislead. The agent chose not to run one.
- `scripts/chaos_test.sh` reads the dev JWT secret from Secrets Manager and forges a pro-tier token. The agent judged that to be widening its own access and did not run it.
- The audit-row check could not be made without database read access. What the code shows (author, `tasks/var_task.py`): the API inserts the job row on submit, the worker updates it by task id, and if it finds none it inserts a row with `user_id="unknown"`. That fallback is the only duplicate-row path and is the thing a drill would need to look for.

**W5, throughput against workers (dev).** Not run. The free tier's 10 jobs a day cannot supply the hundreds one step needs. `locustfile.py` sends the origin-verify header, which the agent would strip, so traffic would go through CloudFront and its WAF, which (per the agent's notes) allows 100 requests per 300 seconds per IP: a step would measure the WAF limit, not the workers.

## 5. What the evidence changes in the SWOT plan

Applied to `docs/plan-swot-engineering-integration.md` in the same pull request: the draft wording, the evidence ledger (cost per job, monthly cost, first job after idle, API latency, Spot safety, throughput), the weaknesses, W2 to W5 status and the decisions table. In short: cost is mostly fixed and the variable part is about $0.02 to $0.03 a job, not a fraction of a cent; the first job after idle takes about three minutes at the median and nearly every job is first; the interruption and throughput claims remain unmeasured.

## 6. What W4, W5 and per-domain percentiles need (Filippo's decisions)

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
