# P7 — Cost & Performance Optimisation
# Used by: scripts/claude/run.sh p7 --mode seq
# Machine: M4, sequential mode (tasks are dependent — profiling informs
# caching decisions, caching informs cost, etc.)
# Prerequisite: P6 complete, master clean

Do not ask for confirmation. Do not present options. The answers to any questions
you might have are already provided below. Proceed immediately after reading.

---

## Environment facts

- AWS account: 347228921290, primary region: eu-west-1, edge: us-east-1
- All 9 stacks UPDATE_COMPLETE/CREATE_COMPLETE per P6 close
- AMI: ami-053d838c9735b7a03 (Hypothesis C, avg cold-start 3s per last measurement)
- CloudWatch dashboard: pyvar-dev-overview
- SNS alerts topic: arn:aws:sns:eu-west-1:347228921290:pyvar-dev-alerts
- AWS Budget already live: pyvar-dev-monthly = USD 250 (80% ACTUAL / 100% FORECASTED)
  — note: release plan target is £150/month; budget is in USD (GBP unsupported on
  this billing account, confirmed in P6). Keep cost comparisons in USD or convert
  consistently — do not silently mix currencies in any report.
- pyvar/JobCount and pyvar/JobErrors custom metrics live (interim CloudWatch
  measure per P6 Task 4b — dimensioned by TaskName only, not Domain/Tier)
- Known tracked gaps (do not attempt to fix in P7 — out of scope):
  #118 var_jobs audit log never written (compliance)
  #119 no CI/CD deploy pipeline (infrastructure)
- gh CLI and SSM Session Manager plugin both available in claude-docker

---

## P7 scope — work through in this order, stop after each task and await
## confirmation before proceeding to the next.

Cost targets from the release plan (in £, convert to USD for actual Budget
comparison — check current GBP/USD rate or note the target as approximate):

| Service | Target | Lever |
|---|---|---|
| EC2 Spot workers | ~£12/month | Scale-to-zero, Spot vs On-Demand |
| ECS Fargate (API) | ~£18/month | FARGATE_SPOT + on-demand base |
| Aurora SV2 | ~£45/month | 0.5 ACU minimum |
| ElastiCache | ~£10/month | Serverless, pay per ECU |
| **Total** | **< £150/month** | At 500 jobs/day |

---

### Task 1 — Performance profiling (Numba kernel efficiency)

Read CLAUDE.md section 3.1 (Numba rules) in full before touching any engine code.

Use pytest-benchmark to run the 10 most compute-intensive functions across the
8 domains (check pyvar_functions.csv for candidates — prioritise Market Risk
Monte Carlo, Portfolio Optimisation, and any Derivatives pricing functions
likely to be hot paths) at n_simulations=100_000.

For any function taking > 5 seconds:
1. Profile with cProfile to identify the bottleneck
2. Check whether prange is used correctly (parallel, not sequential)
3. Check whether random numbers are pre-drawn before the JIT region (Rule 3)
4. Check whether all array dtypes are explicitly float64 (Rule 2)
5. Propose a specific code change with expected speedup

Show before/after benchmark for any change made. Do NOT change function
signatures or return types — internal implementation only.

Branch: perf/p7-numba-profiling
Commit: "perf(engine): optimise hot-path Numba kernels — before/after benchmarks"

Exit criterion for this task: no profiled function exceeds 10s at 100k paths,
OR a documented reason why a specific function cannot be reasonably optimised
further (report rather than force a bad change).

---

### Task 2 — ElastiCache result caching

Implement a result cache in api/routes/ as a cache_check decorator:
1. Before dispatching to Celery: check ElastiCache for cached result using
   SHA-256 of canonical JSON request params as cache key
2. On cache hit: return 200 with the cached result immediately (not 202)
3. On cache miss: dispatch to Celery as normal; on completion write result
   to cache with TTL=3600
4. Cache key format: "pyvar:{domain}:{sha256_of_params}"
5. Log cache hits vs misses as a CloudWatch custom metric — reuse the
   pyvar/JobCount pattern from P6 Task 4b (same _emit_job_metric-style
   helper, same best-effort try/except isolation, same worker_role/
   api task role IAM scope check — confirm the API task role also has
   cloudwatch:PutMetricData scoped to pyvar namespace; if not, this is a
   new IAM grant needed in api_stack.py)

Test with the same request params submitted twice — second call must return
instantly (< 200ms) from cache, first call goes through the normal Celery path.

Branch: feat/p7-elasticache-caching
Commit: "feat(api): ElastiCache result caching — cache_check decorator"

Note: ElastiCache connection uses rediss:// with ssl_cert_reqs=CERT_NONE,
same pattern as CELERY_RESULT_BACKEND (see compute_stack.py / api_stack.py
for the existing connection string construction — reuse, don't duplicate).

---

### Task 3 — Celery worker concurrency tuning

Benchmark Celery worker concurrency at 1, 2, and 4 on c5.xlarge (current
worker_instance_type per config.py — note: release plan mentions c7i.xlarge,
but P4/P6 work switched to c5.xlarge for Spot availability; use the actual
current instance type, not the plan's original assumption).

For each concurrency level, run a representative batch of jobs (e.g. 10
VaR computations at n_simulations=100_000) and measure:
- Total wall-clock time for the batch
- CPU utilisation during the batch (via CloudWatch EC2 metrics)
- Memory headroom (c5.xlarge has 8GB — Numba parallel kernels are memory-hungry)

Report the concurrency sweet spot with data, then update the systemd unit's
worker.py --concurrency flag (or CELERY_WORKER_CONCURRENCY env var if that's
cleaner) to the chosen value.

Branch: perf/p7-celery-concurrency
Commit: "perf(worker): tune Celery concurrency to N based on c5.xlarge benchmark"

This requires forcing a worker instance (same suspend-Terminate pattern used
throughout P6) — remember to resume Terminate and confirm the ASG returns to
desired=0 / 0 instances / 0 suspended processes afterward. Do not leave a
pinned instance running.

---

### Task 4 — SQS visibility timeout review

Review the current queue_visibility_timeout_seconds (config.py) against the
actual p99 simulation time measured in Task 1/3. Per CLAUDE.md and the
original P4 design, visibility timeout must exceed max simulation runtime
to avoid duplicate delivery during long-running jobs.

If the current timeout is insufficient given measured p99 times, propose
the new value and update config.py.

Branch: fix/p7-sqs-visibility-timeout (only if a change is needed — if the
current value is already correct, report this and skip the branch)

---

### Task 5 — S3 Intelligent-Tiering verification

Verify S3 Intelligent-Tiering is correctly configured on the result bucket
(check data_stack.py — this may already be implemented per earlier stack
work). Confirm:
1. Intelligent-Tiering is enabled on pyvar-dev-results-{account}
2. Objects transition to IA after 30 days (check the actual tiering
   configuration, not just that the feature is toggled on)
3. No objects are currently old enough to have transitioned yet (dev
   bucket is likely too new) — if so, report this as "cannot verify
   transition behaviour yet, configuration confirmed correct" rather
   than fabricating a transition that hasn't happened

No code change expected unless a misconfiguration is found.

---

### Task 6 — CloudFront cache hit rate review

Review the existing CloudFront cache policy (edge_stack.py) for
GET /api/v1/var/result/{task_id}. Per the release plan, target is > 60%
cache hit rate for SUCCESS responses.

Check:
1. Is Cache-Control: public, max-age=3600 actually being set by the API
   for SUCCESS responses (per the original edge_stack.py design docstring)?
2. Is Cache-Control: no-store correctly set for PENDING responses?
3. Query CloudFront metrics (if any traffic exists) for actual cache hit
   rate — if no meaningful traffic exists yet in dev, report this as
   "cannot measure yet, configuration reviewed and correct" rather than
   fabricating a hit-rate percentage.

No code change expected unless a misconfiguration is found.

---

### Task 7 — AWS Cost Explorer review

Query Cost Explorer for the current month's spend breakdown by service.
Identify the top 3 cost drivers. For each, document:
1. What is driving the cost (idle resources, over-provisioning, data
   transfer, etc.)
2. Whether it's expected given dev-environment usage patterns or a genuine
   inefficiency
3. A specific mitigation if one exists, or confirmation that current cost
   is already near-optimal for the given usage level

Write findings to docs/p7-cost-review.md (new file).

---

## P7 exit gate

Per the release plan:
- [ ] p99 latency < 10s at 100k paths for all profiled domains
- [ ] Cache hit rate > 30% (ElastiCache result cache, Task 2)
- [ ] Monthly AWS cost forecast < £150 (or USD equivalent) at 500 jobs/day
      — note: dev environment won't hit 500 jobs/day; extrapolate from
      current usage rather than requiring live measurement at that volume
- [ ] No Spot interruptions causing job loss — this requires either a
      soak test (see below) or documentation that task_acks_late=True +
      the chaos_test.sh script (P5b) already demonstrated recovery from
      Spot interruption without job loss, satisfying this criterion
      without re-running a full 72h soak in dev

## Soak test — flag, do not run automatically

The release plan calls for a 72h soak test with no Spot-interruption job
loss. This is expensive and slow for a dev environment. Report this as a
recommended pre-P9 activity rather than attempting it within this P7
session — a 72h unattended test needs its own planning (monitoring,
alerting on failure, cost of sustained worker activity) separate from the
other P7 tasks.

## Post-task validator

After all P7 tasks complete and any changes are deployed:
1. Run scripts/adversarial/p4_post_deploy_validator.md
2. Append to P4_ADVERSARIAL_POST_DEPLOY.md:
   "## P7 Cost & Performance Optimisation — full stack pass"
   covering: benchmark results (before/after), cache hit rate measured
   (or noted as unmeasurable in dev), concurrency tuning result, cost
   review summary, validator results.
   Do NOT modify any existing sections.
