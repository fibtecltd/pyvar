# Plan: presenting the engineering integration in the funding-fit SWOT

**Status: draft, 2026-11-13; W1, W2 and part of W3 done the same day.** Request from Filippo (2026-11-13): present as a real innovation the integration and orchestration of NumPy and Numba (a JIT Monte Carlo engine, `@njit` parallel), Polars and PyArrow (lazy-scan ingestion), FastAPI and orjson (async REST), Celery and SQS FIFO (the job queue), and ECS Fargate and EC2 Spot (compute, in eu-west-1 and us-east-1), to achieve what pyvar delivers today in cost, speed and efficiency. This plan says how to do that so that an assessor cannot dismiss it. The SWOT itself is not changed here.

## 1. The claim, stated so that it can be defended

Every component is mainstream and widely used. A reviewer will not accept any of them as novel, and the SWOT should not suggest otherwise. What can be argued is the **integration**: one architecture that runs regulatory-grade risk computation with the marginal cost of a job close to zero, warm compute in milliseconds, workers that scale to zero on Spot capacity, and a data contract that says for each of time, cost and accuracy whether a number is real, estimated or static. Draft wording, to be used only with the evidence levels attached:

> pyvar is an engineering integration of established components. A warm Monte Carlo VaR at 100,000 simulations took 7 ms in the original benchmark (measured, and not a JIT advantage: see the first update below). Workers scale to zero between jobs: on a fresh worker a job takes a median 171 s from submission to result (288 jobs, last 15 days, production), and 99% of production jobs started on a fresh worker. The variable cost of a job is about $0.02 to $0.03, almost all of it a Spot instance that lives about 18 minutes for a job of about 6 seconds (account-wide bill, August to October 2026), while the account's monthly bill of $887 to $1,052 (dev, prod and other products together; not yet split by tag) is 97% fixed infrastructure. No comparison with other architectures has been made yet.

The production figures are probably dominated by a scheduled demo refresh (`docs/p9-aws-evidence-2026-11-13.md`, section 1), not by customer jobs; say so wherever they are used.

**Update 2026-11-13 (W1: `docs/p7-numba-vs-numpy-results.md`).** A comparator now exists for the compute kernels, and it takes *speed over vectorised
NumPy* out of the claim. The compiled kernels are 2 to 14 times faster than NumPy where per-path computation dominates, but **end to end, Numba is faster
than a plain-NumPy version of the same function in one of five measured cases, at parity in one and slower in three** (Monte Carlo VaR, where a Numba sort
costs 11.5 times a NumPy sort, and rough Bergomi, whose kernel recomputes path-independent weights). Two engine fixes made in the same pull request (the VaR sort, the rough Bergomi weights) moved that to **faster in 3 of 5, parity in 2, slower in none**
(Asian 1.55x, rough Bergomi 1.69x, 10-day VaR 1.24x). So the draft wording above must still not be read as a JIT speed advantage: the margins are small, the
random draws dominate several functions, and one machine and one size were measured. What remains defensible is the architecture around the kernels (scale-to-zero on Spot, marginal cost flat in volume, the data contract),
and for those there is still no comparator (W2 to W5, W6). With no comparator, the numbers show what pyvar does, not that it does it better or at lower cost
than the alternatives; that is why this is not yet "a real innovation" in an assessor's terms.

**Update 2026-11-13 (W2 and W3: `docs/p9-aws-evidence-2026-11-13.md`).** Cost and latency now come from the bill and from production metrics, and they correct three
of the draft's own statements. (1) *The marginal cost of a job is not a fraction of a cent*: it is about $0.02 to $0.03 (variable $22.94, $29.20 and $32.76 over
1,209, 1,157 and 1,241 jobs in August to October, account-wide), because every job gets its own Spot instance that lives about 18 minutes. (2) *Cost is
mostly fixed*: $864 to $1,019 a month of $887 to $1,052, which is 2.0 to 2.9 times the bottom-up audit's range, and flat in volume only because it is fixed. (3) *Warm is
not the normal case*: 576 of 580 production jobs ran on a freshly started worker, with a median of 171 s from submission to result, not the single 145 s. What the
measurement cannot say: the figures are account-wide (dev included) for cost, mostly scheduled demo jobs for latency, and per-domain percentiles are not
measured. W4 (interruption) and W5 (throughput) were run once in dev on 2026-11-14 as a first pass: graceful termination of a worker kept all 5 jobs, an abrupt kill lost all 5, and queue-mode throughput did not rise with the number of workers (small samples, causes not proven; `docs/p9-aws-evidence-2026-11-13.md`, section 7).

**Not claimed:** novelty of any component; Dask or Ray (installed, not wired into the compute path); compute in two regions (section 2).

## 2. The components as built

| Layer | What is built | Notes |
| --- | --- | --- |
| Compute core | NumPy and Numba; 58 `@njit` kernels in `engine/`, 14 with `parallel=True` (static count, commit `dfbf0cc`) | Kernels are stateless; random numbers are drawn in Python before the JIT region (`CLAUDE.md` 3.1) |
| Ingestion and storage | Polars lazy Parquet scan into NumPy (`ingestion/loader.py`); PyArrow and boto3 Parquet writer to S3 (`storage/s3.py`) | No measurement of the ingestion path is recorded |
| API | FastAPI with Pydantic v2; orjson responses (`api/responses.py`); async | |
| Queue | Celery on SQS FIFO; `task_acks_late`, `worker_prefetch_multiplier=1`, `max_tasks_per_child=100`; visibility timeout above the longest simulation | Local development uses Redis |
| Compute fleet | ECS Fargate (Fargate Spot plus an on-demand base for high availability); EC2 Spot workers (`PRICE_CAPACITY_OPTIMIZED`) from a pre-baked image (EC2 Image Builder) | |
| Regions | **All compute, data and queues are in eu-west-1.** us-east-1 holds only the edge stack (CloudFront, its WAF and certificate), which AWS requires there (`CLAUDE.md` 3.4) | "Compute in eu-west-1 and us-east-1" would be inaccurate |

The orchestration decisions that carry the claim, each with its evidence level:

1. **Spot-safe queueing.** FIFO plus late acknowledgement, intended so that a reclaimed Spot instance does not lose a job. Designed; **one drill in dev (2026-11-14, n = 5 per arm): graceful termination kept every job, an abrupt kill lost every job** (late acknowledgement alone does not redeliver a job whose worker process is lost); a real 2-minute Spot notice was not tested.
2. **Scale from zero on a custom metric.** SQS stops publishing its CloudWatch metrics after more than six idle hours, which delayed the first job after idle to 401.5 s; publishing a `pyvar/job-submitted-{env}` metric at enqueue time brought it to 145 s (instance in service at 63 s). Measured once on each side (`docs/p9-day-minus-3-smoketest-status.md`), and since over 288 production jobs: median 171 s from submission to result on a fresh worker (`docs/p9-aws-evidence-2026-11-13.md`).
3. **Pre-baked worker image** with the compiled Numba cache, so a fresh worker avoids the first-call compile (2.47 s over ten kernels, `docs/p7-numba-profiling-results.md`). Designed; the image's own effect is not measured.
4. **The Iron Triangle data contract** (`docs/p8-iron-triangle-data.md`): time is real per job (`api_usage.duration_ms`), and the document labels each axis real, aggregate estimate or static score so an estimate is never shown as a live metric.

## 3. Evidence ledger

| Claim | Evidence | Level | Gap |
| --- | --- | --- | --- |
| Warm Monte Carlo VaR (100,000 simulations) in 7 ms | `p7-numba-profiling-results.md` (`run_monte_carlo_var`: 0.007 s warm, 1.083 s first call) | Measured, one machine, fixed seed | W1 baseline: a plain-NumPy version of the same function is as fast or faster end to end, so the 7 ms is not a JIT result |
| First-call JIT cost | Same: 2.47 s for ten kernels (0.46 s warm) | Measured | |
| First job after idle (scale from zero) | 401.5 s before the fix, 145 s after (once each); then **submit to result on a fresh worker: p50 171 s, p95 204 s, p99 218 s (n = 288, last 15 days, production, accurate to about 30 s)**; launch to worker ready p50 79 s (n = 581) | Measured (W3) | Mostly scheduled demo jobs, so not a customer's experience; warm cell has n = 3 and is not reported |
| Marginal compute cost per job | Cost Explorer, Aug to Oct 2026: variable $22.94 / $29.20 / $32.76 over 1,209 / 1,157 / 1,241 jobs = **$0.019 / $0.025 / $0.026 a job**; Spot about $0.023 an activation (0.266 instance-hours at about $0.087) | Measured (W2), **account-wide: dev, prod and other products on the same account** | The bottom-up audit ($0.006 to $0.012 an activation, 10 activations a month) was too low by activation count (about 580 in prod) and by instance lifetime; no prod-only figure is computable |
| Monthly cost | Cost Explorer: gross $886.79 / $1,014.33 / $1,051.98 (Aug / Sep / Oct), tax on top; fixed or other $864 / $985 / $1,019 (97% of the total); the audit's prod estimate of $349 to $430 was 2.0 to 2.9 times too low | Measured (W2) | Account-wide including dev and other Fibtec products (not split until the `Project` and `Environment` tags are activated for billing); $0.73 to $0.88 total per combined job at about 1,200 jobs a month; cost is flat in volume, not low |
| API reliability and latency | `p9-soak-test-status.md`: 579 canary invocations, 0 errors, ALB p95 3.9 to 6.2 ms; W3: ALB, all endpoints, about 33,300 requests in 30 days: p50 5 ms, p95 60 ms, p99 258 ms; worker `compute_var` runtime p50 5.85 s, p95 20.46 s, p99 29.32 s (n = 580), 0 errors in 17,592 log lines | Measured | The ALB figures are a light API, not compute; per-domain percentiles are not measured (no database read access) |
| Spot interruption safety | W4 (dev, 2026-11-14): graceful termination (Auto Scaling terminate plus drain hook) 5 of 5 jobs finished once; abrupt kill (`ec2 terminate-instances`) 5 of 5 jobs lost, reported failed, not redelivered. Design (`CLAUDE.md` 3.2) says a reclaimed instance does not lose a job | Measured once, n = 5 per arm, one kill timing (about 1.3 s into a 3.3 s job) | No real 2-minute Spot notice (no FIS template); duplicates on the killed worker not visible (its logs are lost); cause is the missing `task_reject_on_worker_lost` (checked in code, not by test); decision open (section 7) |
| Throughput scaling | W5 (dev, queue mode, 2026-11-14): 352, 364 and 251 jobs a minute at 1, 2 and 4 workers; no two jobs ever overlapped | Measured once per N, 60 to 120 jobs of about 0.15 s each | Measures the queue path, not CPU scaling; the likely cause (all messages in one FIFO group) is not verified; API and WAF not measured in queue mode; `locustfile.py` untried |
| Faster than plain NumPy | `p7-numba-vs-numpy-results.md` (W1): four functions against equivalent vectorised baselines, one 4-core machine, 21 repeats | Measured: kernels 2 to 20 times faster where per-path work dominates; end to end, first run **faster in 1 of 5, parity in 1, slower in 3**; after two engine fixes (same PR) **faster in 3, parity in 2, slower in none** | One machine and one size; not production hardware |
| Better than alternatives on cost or efficiency | None | Not measured | No on-demand, Lambda or other comparison anywhere in the repository |

## 4. Where it goes in the SWOT, and what it changes

- **Strengths:** a new row, "Engineering integration (cost, speed, efficiency)", with the draft wording above and the level of each figure.
- **Weaknesses:** the $887 to $1,052 monthly cost is 97% fixed infrastructure and about $0.85 per job at current volume; the variable cost of about $0.02 to $0.03 a job is almost all a Spot instance kept alive about 18 minutes for a 6-second job (a design lever, untested); a fresh worker is the normal case (99% of production jobs, median 171 s from submission to result); the production figures are mostly scheduled demo jobs; and Numba is not an end-to-end speed advantage over vectorised NumPy for the functions measured (W1).
- **BridgeAI:** relevant as deployment efficiency (a deployer's cost does not grow with volume). No rating changes.
- **Eurostars:** supports an "innovative" criterion only if framed with a measured comparison; it is not the R&D question.
- **EIC:** the "Breakthrough shown" row stays a **Gap**. An integration of established components with no IP position does not meet that bar, and re-rating it without a baseline and an IP view would not survive an assessor. The readiness percentages change only if a row's rating changes.

## 5. Work that makes the claim defensible

| # | Work | Needs | Pipeline |
| --- | --- | --- | --- |
| W1 | **Done 2026-11-13** (`docs/p7-numba-vs-numpy-results.md`, `scripts/p7_vs_numpy.py`). **Fair NumPy baselines** for the hottest kernels in the p7 benchmark (`run_monte_carlo_var`, `american_option_lsm`, `rough_volatility_rbergomi_model`, `asian_option_pricer`). Rules: same algorithm and the same random draws; vectorised NumPy and SciPy; float64; same sample size; median of k runs after warm-up; hardware stated; warm and cold both reported. A pure-Python-loop baseline (`NUMBA_DISABLE_JIT=1`) may be shown only if labelled "not a fair comparator". | Nothing external; offline and free | `scripts/` and `docs/`: none |
| W2 | **Done 2026-11-13** (`docs/p9-aws-evidence-2026-11-13.md`). Cost per job from billing, against the bottom-up estimate. Account-wide only: the `Environment` tag is not activated, so prod cannot be split from dev | Delegated agent, read-only | none |
| W3 | **Partly done 2026-11-13** (same document). Cold-start, queue, worker and end-to-end percentiles from CloudWatch and logs; the warm cell has n = 3. **Not done:** per-domain percentiles from `api_usage.duration_ms` | A read-only database role (open) | none |
| W4 | A Spot interruption drill: reclaim a worker mid-job; success is the job completing exactly once (dev only). **Done 2026-11-14, first pass** (`docs/p9-aws-evidence-2026-11-13.md`, section 7): 5 trials per arm; graceful 5 of 5 completed, abrupt kill 5 of 5 lost. No FIS arm, no database counts | A second pass needs a FIS template, a read-only database role, several kill timings and a larger n | none |
| W5 | Throughput against the number of workers (a script) (dev only). **Done 2026-11-14, first pass** (same document, section 7): queue-mode load through the repository's own Celery code, 60 to 120 jobs per step; throughput did not rise with workers. API and WAF not measured | A second pass needs an allow-listed source for API-mode load, and the message-group question settled first | none |
| W6 | Optional: a paper comparison with an on-demand-only or Lambda-based design | Nothing external | none |

Baselines are against NumPy only. No vendor is named in this public repository (the same rule as for deployers).

## 6. Order

W1 first (free, offline, and the missing comparator), then W2 and W3 (both pulled on 2026-11-13). W4 and W5 ran on 2026-11-14 as a first pass, without the inputs in section 7 (queue-mode load, no database counts, no FIS arm). The SWOT wording above predates their results and has not been revised for them; `docs/pyvar-funding-fit-swot.md` mentions neither interruption nor throughput, so its PDF is unchanged. Each step is docs-only or `scripts/`-only.

## 7. Decisions for Filippo

| Decision | Status |
| --- | --- |
| Accept "an evidenced integration of established components" rather than "a real innovation" until a comparator exists | **Open**; W1 makes it stronger: speed over NumPy cannot be the innovation |
| Who pulls W2 to W5 from AWS | **Decided** (2026-11-13): a delegated agent with an assigned prompt (read-only on prod; the drill and the load test only in dev). **W2 and part of W3 done the same day**, with the CDK deployer's credentials (broader than needed) |
| Run W1 now | **Done** (2026-11-13): `docs/p7-numba-vs-numpy-results.md` |
| Baselines against NumPy only, no vendor names | **Applied** in W1 |
| Review the "JIT-accelerated" wording in the GitHub description and the README | **Deferred** (Filippo, 2026-11-13): leave it unchanged for now |
| Make the two engine changes W1 exposes (`np.sort` in the VaR function; lag weights computed once in rough Bergomi) | **Decided and made** (Filippo, 2026-11-13), in PR #428; they change `engine/`, so merging that PR starts a CodePipeline run |
| Inputs for W4, W5 and per-domain percentiles | **Partly overtaken** (2026-11-14): W4 and W5 ran without them, as a first pass; the owner authorised the agent to mint its own 24-hour dev token. **Still open:** a read-only database role (per-domain percentiles, the duplicate-row check), FIS versus terminate-instance for the real notice, a load source that is not WAF-throttled, a dedicated read-only AWS role instead of the deployer user (details: `docs/p9-aws-evidence-2026-11-13.md`, sections 6 and 7) |
| Activate the `Project` and `Environment` cost-allocation tags | **Open**: the resources already carry `Project` and `Environment` in code; activating them for billing splits pyvar from the other products on the account and prod from dev |
| Set `task_reject_on_worker_lost` so a job whose worker is lost abruptly is redelivered, not failed | **Open** (found by W4, 2026-11-14): the trade is possible redelivery loops and double execution; it is a Celery setting in `tasks/var_task.py`, so a pipeline run. The public wording on late acknowledgement waits for this decision |
| Give each queue message its own group id so jobs can run in parallel | **Open** (found by W5): first confirm the deployed kombu version and read one dev message's group id. The comment in `pyvar-cdk/stacks/queue_stack.py` (Celery uses the task name as the group id) disagrees with the kombu source checked; the change would be in the dispatch code |
| Correct the four texts that say or imply a lost Spot instance's job is only delayed (`CLAUDE.md` 3.2, `portal/guide-technical-deepdive.html`, the technical deep-dive Medium article, the comment in `pyvar-cdk/stacks/compute_stack.py`) | **Open**, after the decision on `task_reject_on_worker_lost`; one of them is on the live portal |
