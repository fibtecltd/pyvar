# P7 Task 3 — Celery worker concurrency tuning results

## Method

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

## Results

| Concurrency | total wall-clock (10 jobs) | submit wall-clock | peak CPU sample | memory delta (before→after) |
|---|---|---|---|---|
| 1 | 5.755s | 1.417s | ~20.9% (16.1 us + 4.8 sy) | 331→439 MB (+108 MB) |
| 2 | 4.279s | 1.192s | ~15.9% (14.3 us + 1.6 si) | 371→478 MB (+107 MB) |
| 4 | 4.247s | 1.278s | ~84.3% (73.4 us + 10.9 sy) | 441→689 MB (+248 MB) |

All 30 jobs (10 per run × 3 runs) completed with `all_success: true`.
`c5.xlarge` has 8GB RAM (`7739` MB reported by `free -m`); even the
concurrency=4 peak (689 MB) leaves ample headroom at this batch size.

## Interpretation

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

## Caveat

This is a 10-job batch at `n_simulations=100_000` — total wall-clock is
dominated by SQS/HTTP round-trip latency (submit alone takes ~1.2-1.4s of
the ~4.2-5.8s total), not raw compute, since warm per-job compute is
sub-second (see `docs/p7-numba-profiling-results.md`). A much larger
concurrent batch, or a heavier per-job `n_simulations`, could shift this
balance and should be re-benchmarked before assuming `CELERY_CONCURRENCY=2`
holds at higher production load — this result characterises the *current*
dev-scale workload, not an asymptotic ceiling.
