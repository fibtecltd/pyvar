# Day -3 prod smoke test — all 8 domains + async VaR, real end-to-end

Run 2026-08-14. Real authenticated compute requests against prod, not just
`202`/`401` checks — first genuine compute traffic prod has ever processed
(the 48h soak test, `docs/p9-soak-test-status.md`, only ever hit `/health`
and an unauthenticated 401 check).

**Update 2026-08-15**: the cold-start finding below is now resolved — see
"Resolution" at the bottom for the root-cause fix (PR #232), its live
verification against prod, and the interim mitigation's revert (PR #233).

## Setup

- **Credentials**: confirmed real, account `347228921290`, role
  `pyvar-cdk-deployer`.
- **Reused, not reinvented**: `pyvar-cdk/stacks/pipeline_stack.py`'s
  `_smoke_test_step`/`ProdSmokeTest` was read in full first. Finding worth
  recording: **prod's actual `ProdSmokeTest` only ever checks `GET /health`**
  — it has never made an authenticated request, never touched a domain
  endpoint, never exercised `/var/compute`. Dev's `SmokeTest` goes one step
  further (also checks `POST /var/compute` with no auth expects `401`) but
  still never authenticates. Confirmed via reading `pipeline_stack.py:447-515`
  (dev) and `:791-800` (prod) directly — this doc's checks go meaningfully
  beyond both.
- **Auth**: registration (`/auth/register` + email verification) isn't
  viable for an automated check against a freshly-migrated, empty `users`
  table. Reused the existing, already-established pattern from
  `scripts/chaos_test.sh` / `scripts/p7_concurrency_bench.py`: pull
  `pyvar/prod/jwt-secret` from Secrets Manager, hand-sign an HS256 JWT
  (`sub=day-minus-3-smoketest`, `tier=internal` — exempt from the
  free/pro daily rate caps per `api/middleware/rate_limit.py`). Verified
  the minted token actually works before running anything else.

## Architecture correction worth flagging

The task description assumed all 8 domains follow the async
`202` + poll pattern. **They don't.** Confirmed by reading `main.py` and
each `api/routes/*.py`: the 8 domain routers (386 endpoints total) are
**synchronous** — each call runs inline in the FastAPI process and returns
`200` immediately with the result. The `202`/`task_id`/poll/Celery/Spot-worker
pattern exists **only** for the separate `/api/v1/var/compute` endpoint.
So: the 8 domains below were checked as direct synchronous calls (confirm
`200` + sane result), and `/var/compute` was run separately, end-to-end,
specifically because it's the only endpoint that actually touches the
worker fleet and its cold start.

## 8 domains — all PASS (200, real compute, numerically sane)

| Domain | Endpoint | Result | Sanity check |
|---|---|---|---|
| market-risk | `POST /market-risk/historical_simulation_var` | `var_pct=0.0203, cvar_pct=0.0203` | VaR>0 ✓. CVaR==VaR (not >) — expected artifact of n=60 historical obs at 99% CI (tail average collapses to the single worst point), not a bug. |
| credit-risk | `POST /credit-risk/probability_of_default_pd_estimation` | `pd_pooled=0.02581` | =8/310 pooled defaults/obligors, exact match; per-cohort PDs (0.02, 0.04167, 0.01111) each verified = defaults/obligors. |
| derivatives | `POST /derivatives/black_scholes_european_option` | `price=9.4134` | ATM call, spot=strike=100, r=3%, σ=20%, τ=1y — matches textbook Black-Scholes value; d1=0.25/d2=0.05 correct. |
| liquidity-risk | `POST /liquidity/liquidity_coverage_ratio_lcr` | `lcr=1.6667, compliant=true` | 1,000,000 HQLA / 600,000 net outflows (800k-200k, inflow cap not binding) = 1.667, correctly >1.0 minimum. |
| operational-risk | `POST /operational/frequency_distribution_fitting` | `lambda=10.8` | Poisson MLE = sample mean of [10,12,8,15,9] = 10.8, exact. |
| alm | `POST /alm/macaulay_duration_balance_sheet` | `duration=2.861, pv=1025.46` | 3-period bond-like cashflow, discount<coupon → priced above par (1025), duration <3y (front-loaded coupons) — correct direction and magnitude. |
| portfolio-analytics | `POST /portfolio/mean_variance_optimisation` | `weights sum≈1, sharpe=9.40` | Internally consistent (`return/volatility` = 28.55/3.04 = 9.398 ≈ reported sharpe). **Caveat**: my test `mean_returns` (0.08-0.12) read as annual figures, but the engine annualizes via `periods_per_year=252` multiplicatively, producing an inflated `return=28.55` (2855%) — a units-choice artifact of my test input, not an engine defect. Future smoke tests should pass per-period (daily) mean returns if `periods_per_year=252` is used. |
| regulatory | `POST /regulatory/basel_iii_cet1_ratio` | `cet1_ratio=0.08, compliant=true` | 80/1000 = 8%, correctly above the 4.5% Basel III minimum, surplus=3.5% exact. |

All 8: HTTP 200, well-formed JSON, response times 68-540ms (no worker
involvement, pure FastAPI/Numba inline compute).

## Async `/var/compute` — the real cold-start test

**Job 1 (99% VaR, n_simulations=10,000, cold — first-ever real compute job
in prod):**
- `POST /var/compute` → `202`, `task_id=2fb411b1-...`.
- Polled `GET /var/result/{task_id}` — stayed `pending` far longer than
  expected. Investigated directly rather than just waiting blindly:
  - `pyvar-prod-workers` ASG: `DesiredCapacity=0`, 0 instances, for the
    first ~80s of polling.
  - The scale-from-zero CloudWatch alarms
    (`WorkerAsgScaleFromZero{Upper,Lower}Alarm`) were in **`INSUFFICIENT_DATA`**
    — `AWS/SQS ApproximateNumberOfMessagesVisible` had **zero datapoints**
    in the preceding 10 minutes (confirmed via direct `get-metric-statistics`),
    because the queue had been sitting at 0 messages for the entire 48h
    soak test and SQS doesn't publish this metric when there's no activity.
    The first datapoint took roughly a minute to land after the message
    arrived, which is what delayed the alarm from firing at all.
  - ASG desired capacity flipped `0 → 1` at ~t=80s; instance reached
    `InService` shortly after; job transitioned `pending → started` at
    ~t=~369s (from submission), `success` at ~t=401s.
  - **Authoritative timing, queried directly from `var_jobs` (not
    inferred from polling)**: `created_at=08:37:04.404`,
    `completed_at=08:43:45.928` → **401.5s wall-clock**,
    `duration_ms=7063` (**~7.1s actual compute**).
  - **~394s (98.2% of total latency) was infrastructure cold-start
    overhead — CloudWatch SQS-metric latency + alarm evaluation +
    EC2 launch/boot + Celery worker startup — not compute.** This is
    dramatically longer than the ~25s EC2-boot-alone figure from earlier
    AMI verification work, because that measurement never included the
    SQS-metric-latency + alarm-evaluation stage ahead of the launch, which
    dominates here precisely because the queue had never had traffic
    before.
  - Result: `var_pct=0.021703, var_abs=21703.24, cvar_pct=0.024837,
    cvar_abs=24837.24`. **VaR>0 ✓, CVaR(0.024837) ≥ VaR(0.021703) ✓.**

**Job 2 (95% VaR, n_simulations=10,000, warm — worker already `InService`):**
- Submitted immediately after job 1. Polled once, already `success`.
- Authoritative DB timing: `created_at=08:46:35.388`,
  `completed_at=08:46:36.199` → **0.81s wall-clock**, `duration_ms=23`.
- Result: `var_pct=0.015608, cvar_pct=0.019332`.
- **Invariant check: 99% VaR (0.021703) > 95% VaR (0.015608) ✓**
  (per CLAUDE.md §5's canonical VaR properties). CVaR≥VaR holds here too.

**Cold vs warm, side by side**: 401.5s (cold, first-ever job) vs 0.81s
(warm, second job 9 minutes later) — a ~500x difference, entirely explained
by infrastructure warm-up, not compute cost (7063ms vs 23ms compute time is
itself just n_simulations/JIT-cache-state noise, not the story here).

## Unauthenticated check (reconfirmed)

- `GET /health` → `200`.
- `POST /var/compute` with no `Authorization` header → `401` (unchanged
  from the 48h soak test's own finding).

## Bottom line

**All 8 domains: PASS.** **Async VaR: PASS** (both confidence levels,
correct invariants, real DB-verified results). **New, genuinely important
finding**: prod's first real job after being idle takes **~6.7 minutes**
end-to-end, almost entirely due to SQS-metric-latency-gated scale-from-zero,
not compute. If Day 0 traffic can't tolerate a ~7 minute wait on the very
first request, consider either (a) a pre-warming ping shortly before
expected traffic, or (b) setting `worker_min_capacity` above 0 for a
window around cutover — both are policy decisions, not something changed
here. No code was changed; this was verification only.

## Resolution — root-cause fix shipped and verified live (2026-08-15)

This finding is now **closed**, not just mitigated.

**Interim step (PR #227/#228, done earlier)**: `worker_min_capacity=1` for
prod — a deliberate standing-instance workaround, explicitly marked
TEMPORARY, while the actual root cause was investigated.

**Root cause (PR #232, task #38)**: confirmed against AWS docs that an SQS
queue stops publishing *any* CloudWatch metric after 6+ hours of zero
activity, with up to a 15-minute lag on resumption once activity restarts —
a platform-level behavior of SQS's own CloudWatch integration, not specific
to `ApproximateNumberOfMessagesVisible`. Fix: `api/routes/var.py` now
publishes a custom `pyvar/job-submitted-{env}` metric via `put_metric_data`
the instant a job is enqueued (custom metrics have no activity-gating —
always accepted immediately), and `compute_stack.py`'s `ScaleFromZero`
step-scaling policy (the 0→1 transition only) watches this metric instead
of the SQS-native one. The steady-state `ScaleOnQueueDepth` target-tracking
policy is unchanged.

**Verified live against prod, not just deployed** (2026-08-15): forced a
fresh ECS deployment on `pyvar-prod-api` first (the task definition's
`:latest` tag meant `cdk deploy` alone didn't pick up the new image — caught
and corrected before testing, otherwise the test would have silently run
against the old code). Then:
- Scaled `pyvar-prod-workers` to 0 via CLI, confirmed fully drained.
- Submitted a real signed `/var/compute` job.
- Custom metric datapoint appeared within ~40s of submission (normal
  CloudWatch propagation, not the multi-minute SQS gating delay).
- ASG instance reached `InService` at **t+63s**.
- Job completed successfully at **t+145s** total end-to-end
  (`var_pct=0.019461`, `cvar_pct=0.022466` — VaR>0 ✓, CVaR≥VaR ✓).

**145s vs. the 401.5s measured in this doc's own finding above — a ~2.8x
improvement**, with the fix demonstrably addressing the actual bottleneck
(SQS metric gating), not just papering over it.

**Interim mitigation reverted (PR #233)**: `worker_min_capacity` removed
from prod's `config.py` override, restoring the base default of `0`
(scale-to-zero). Deployed and confirmed live: ASG reached
`MinSize=0`/`DesiredCapacity=0` and fully drained to 0 instances.

Prod is now back to its original scale-to-zero cost strategy with the
actual cold-start problem fixed, not masked by a standing instance.
