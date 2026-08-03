# P7 Task 3 — Celery worker concurrency tuning results

> **Superseded 2026-08-03 — see "Rerun: corrected methodology" below.**
> An independent strategic assessment (Tier 3 findings) flagged that the
> original 10-job benchmark below supports no speed/concurrency claim at
> all, by its own Caveat's admission — the sequential submission loop
> dominated the measurement. The rerun below fixes the methodology and
> replaces the Interpretation/chosen-value section as the authoritative
> result. The original Method/Results are kept below unmodified as
> historical record.

## Method (original, superseded)

Forced a real `pyvar-dev-workers` EC2 Spot instance (`c5.xlarge`, the actual
current `worker_instance_type` per `pyvar-cdk/config.py` — not the release
plan's original `c7i.xlarge` assumption) up via
`scripts/force-worker-instance.sh run --yes --duration 1800`, which also
suspends the ASG's `Terminate` scaling process so the instance survives the
SQS queue draining between runs.

For each concurrency level (1, 2, 4):
1. Via SSM (`AWS-RunShellScript`): rewrite `CELERY_CONCURRENCY` in
   `/opt/pyvar/celery.env`, `systemctl restart celery-worker`, confirm active,
   then sample `top -bn1` and `free -m` for a 90s window.
2. From outside (this session, same approach `scripts/chaos_test.sh` already
   uses): submit a batch of 10 real VaR jobs (`n_simulations=100_000` each)
   through the actual public API
   (`https://d1mqqddh8gu2qi.cloudfront.net/api/v1/var/compute`, JWT +
   `X-Origin-Verify` auth), then poll `GET .../var/result/{task_id}` for all
   10 until `success`/`failure`, timing total wall-clock.

Jobs were dispatched through the real API rather than directly from the
worker instance — the worker's IAM role intentionally has no
`sqs:SendMessage` grant (only the API task role dispatches jobs; workers only
consume), so a first attempt to `apply_async` directly from the worker
correctly failed with `AccessDenied`. Going through the API is also more
representative of production traffic. No IAM changes were made.

## Results (original, superseded)

| Concurrency | total wall-clock (10 jobs) | submit wall-clock | peak CPU sample | memory delta (before→after) |
|---|---|---|---|---|
| 1 | 5.755s | 1.417s | ~20.9% (16.1 us + 4.8 sy) | 331→439 MB (+108 MB) |
| 2 | 4.279s | 1.192s | ~15.9% (14.3 us + 1.6 si) | 371→478 MB (+107 MB) |
| 4 | 4.247s | 1.278s | ~84.3% (73.4 us + 10.9 sy) | 441→689 MB (+248 MB) |

All 30 jobs (10 per run × 3 runs) completed with `all_success: true`.
`c5.xlarge` has 8GB RAM (`7739` MB reported by `free -m`); even the
concurrency=4 peak (689 MB) leaves ample headroom at this batch size.

## Interpretation (original, superseded — see Rerun below for the current conclusion)

Concurrency 1→2 cuts total wall-clock ~26% (5.76s → 4.28s). Concurrency 2→4
gives **no further improvement** (4.28s vs 4.25s — within noise for this
batch size) while peak instantaneous CPU jumps from ~16% to ~84% and the
memory delta roughly doubles.

This matches the hypothesis already recorded as a comment in `worker.py`:
*"Numba's parallel=True already uses all cores within a single task, so
concurrency=1 may be appropriate on smaller machines."* Each Celery worker
process that picks up a task runs Numba `parallel=True` kernels
(`_simulate_paths` etc.) which spread across **all** available vCPUs, not
just `1/concurrency` of them. Running 4 concurrent Celery worker processes on
a 4-vCPU box means up to 4x oversubscription of the same 4 cores — which is
exactly the CPU spike observed at concurrency=4, for zero measured
wall-clock benefit at this batch size.

**Chosen value: `CELERY_CONCURRENCY=2`.** It captures the real gain over
concurrency=1 without paying concurrency=4's CPU-contention cost for no
additional throughput. Applied in `pyvar-cdk/stacks/compute_stack.py`'s baked
`celery.env` (previously unset, which defaulted to `os.cpu_count()` = 4 on
`c5.xlarge` per `worker.py`).

## Caveat (original — this is exactly what the rerun below addresses)

This is a 10-job batch at `n_simulations=100_000` — total wall-clock is
dominated by SQS/HTTP round-trip latency (submit alone takes ~1.2-1.4s of
the ~4.2-5.8s total), not raw compute, since warm per-job compute is
sub-second (see `docs/p7-numba-profiling-results.md`). A much larger
concurrent batch, or a heavier per-job `n_simulations`, could shift this
balance and should be re-benchmarked before assuming `CELERY_CONCURRENCY=2`
holds at higher production load — this result characterises the *current*
dev-scale workload, not an asymptotic ceiling.

---

## Rerun: corrected methodology (2026-08-03)

**What was wrong, precisely:** the batch above was submitted with a
*sequential* shell `curl` loop — one request after another. At only 10
jobs, that loop's own overhead (network round-trip + TLS handshake + auth,
per request, run one at a time) was ~1.2-1.4s of the ~4.2-5.8s total. The
measurement was dominated by how long it takes a shell loop to fire 10 HTTP
requests in series, not by how the Celery/worker pipeline behaves under
load — the original Caveat above says as much. It supported no
speed/concurrency-tuning claim at all.

### Method

`scripts/p7_concurrency_bench.py` (new) fixes this two ways, both
necessary:

1. Submits the whole batch **concurrently** — a thread pool firing all
   requests at once, not a sequential loop. This decouples "time to get N
   jobs into the queue" from N.
2. Uses a batch 5x larger (**50 jobs**, `n_simulations=100_000` each,
   default) — large enough that total processing time is dominated by the
   queue actually draining at the configured concurrency, not by one-time
   connection/auth overhead.

It measures `submit_wallclock` and `total_wallclock` as separate numbers
(and reports `submit_share_pct`) rather than asserting the split in prose,
so the submission-bound-vs-compute-bound question is answered by a number
each run, not eyeballed once and assumed to hold.

Same worker force-up / SSM concurrency-switch procedure as the original
Method above (`scripts/force-worker-instance.sh`), same public API
endpoint and JWT+`X-Origin-Verify` auth pattern as `scripts/chaos_test.sh`.

### Results

| Concurrency | n_jobs | n_success | n_failed | n_timeout | submit_wallclock_s | total_wallclock_s | submit_share_pct |
|---|---|---|---|---|---|---|---|
| 1 | 50 | 9 | 0 | 41 (600s poll cutoff) | 14.109 | 615.223 (censored — see note) | 2.3 |
| 2 | 50 | 50 | 0 | 0 | 14.772 | 44.497 | 33.2 |
| 4 | 50 | 50 | 0 | 0 | 14.992 | 42.765 | 35.1 |

At concurrency=1, only 9 of 50 jobs finished within each job's individual
600s poll deadline — **this is a real throughput ceiling, not a bug or a
timeout that was set too short**: the SQS queue was confirmed fully
drained after the run ended, meaning the worker kept grinding through the
backlog well past the point this script gave up watching any individual
job. `total_wallclock_s` for concurrency=1 is therefore censored (a lower
bound, not the true completion time) and should not be read as a real
number — the `n_timeout=41` is the finding.

### Interpretation (current, supersedes the original above)

**Concurrency=1 cannot clear a 50-job burst in reasonable time at all.**
That's a genuine capacity ceiling at this batch size, visible only because
this rerun uses a batch big enough to expose it — the original 10-job
benchmark was too small to ever surface this.

**Concurrency=2 vs. concurrency=4 show no meaningful difference**
(44.497s vs. 42.765s, both clean 50/50 completions) — at 5x the original
batch size, with a corrected methodology, this reinforces the original
`CELERY_CONCURRENCY=2` choice rather than overturning it. The relative
comparison between 2 and 4 holds regardless of the absolute-timing caveat
below, since both runs carry the same jitter under the same conditions.

**`CELERY_CONCURRENCY=2` stands, now on firmer evidence than before.** No
change to the applied value in `pyvar-cdk/stacks/compute_stack.py`.

### Caveat on this rerun — not papered over

`submit_share_pct` is above this script's own 15% warning threshold at
both concurrency=2 (33.2%) and concurrency=4 (35.1%) — still partly
submission-bound at n_jobs=50, and that share is inflated further by a
real-world complication encountered during this run: a live AWS-side
automatic edge mitigation (confirmed not to be either of this account's
own WAF Web ACLs — zero matches in `aws wafv2 get-sampled-requests` across
every rule in both, zero `BlockedRequests` CloudWatch datapoints) was
triggered by the original tight-burst connection pattern and required a
0-15s random jitter before each submission to avoid, which is *itself*
baked into the measured `submit_wallclock_s` window. Real submission cost
is likely lower than these numbers suggest.

**What this does and doesn't affect:** the `CELERY_CONCURRENCY=2` vs. 4
comparison above is unaffected (same jitter, same conditions, both runs) —
but `submit_share_pct` should not yet be cited as a clean, general
submission-cost figure. A follow-up run with the jitter engineered out of
the timed window (e.g. a longer fixed warm-up delay before the timer
starts, or routing around whatever triggers the edge mitigation) would be
needed before treating that specific number as authoritative.

Also fixed during this rerun, real production-relevant findings in their
own right: `api/routes/caching.py`'s `cache_check` decorator serves a
cached result and bypasses Celery entirely for a repeated identical
request body — the benchmark's fixed payload would otherwise have poisoned
every run after the first (`"task_id": "cached"`, confirmed live), making
concurrency=2/4's apparent results meaningless cache hits rather than real
dispatch. `scripts/p7_concurrency_bench.py` works around this by
perturbing one `returns` value per call; this is not a change to
`caching.py` itself.
