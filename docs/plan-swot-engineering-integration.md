# Plan: presenting the engineering integration in the funding-fit SWOT

**Status: draft, 2026-11-13.** Request from Filippo (2026-11-13): present as a real innovation the integration and orchestration of NumPy and Numba (a JIT Monte Carlo engine, `@njit` parallel), Polars and PyArrow (lazy-scan ingestion), FastAPI and orjson (async REST), Celery and SQS FIFO (the job queue), and ECS Fargate and EC2 Spot (compute, in eu-west-1 and us-east-1), to achieve what pyvar delivers today in cost, speed and efficiency. This plan says how to do that so that an assessor cannot dismiss it. The SWOT itself is not changed here.

## 1. The claim, stated so that it can be defended

Every component is mainstream and widely used. A reviewer will not accept any of them as novel, and the SWOT should not suggest otherwise. What can be argued is the **integration**: one architecture that runs regulatory-grade risk computation with the marginal cost of a job close to zero, warm compute in milliseconds, workers that scale to zero on Spot capacity, and a data contract that says for each of time, cost and accuracy whether a number is real, estimated or static. Draft wording, to be used only with the evidence levels attached:

> pyvar is an engineering integration of established components. A warm Monte Carlo VaR at 100,000 simulations took 7 ms in the original benchmark (measured, and not a JIT advantage: see the update below); workers scale to zero between jobs and the first job after idle completed in 145 s (measured once); the marginal compute cost of a job is a small fraction of a cent (estimated), while the monthly bill of $900 to $1,000 is fixed infrastructure (invoice). No comparison with other architectures has been made yet.

**Update 2026-11-13 (W1: `docs/p7-numba-vs-numpy-results.md`).** A comparator now exists for the compute kernels, and it takes *speed over vectorised
NumPy* out of the claim. The compiled kernels are 2 to 14 times faster than NumPy where per-path computation dominates, but **end to end, Numba is faster
than a plain-NumPy version of the same function in one of five measured cases, at parity in one and slower in three** (Monte Carlo VaR, where a Numba sort
costs 11.5 times a NumPy sort, and rough Bergomi, whose kernel recomputes path-independent weights). So the draft wording above must not be read as a JIT
speed advantage. What remains defensible is the architecture around the kernels (scale-to-zero on Spot, marginal cost flat in volume, the data contract),
and for those there is still no comparator (W2 to W5, W6). With no comparator, the numbers show what pyvar does, not that it does it better or at lower cost
than the alternatives; that is why this is not yet "a real innovation" in an assessor's terms.

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

1. **Spot-safe queueing.** FIFO plus late acknowledgement, so a reclaimed Spot instance does not lose a job. Designed; **no interruption drill is on record**.
2. **Scale from zero on a custom metric.** SQS stops publishing its CloudWatch metrics after more than six idle hours, which delayed the first job after idle to 401.5 s; publishing a `pyvar/job-submitted-{env}` metric at enqueue time brought it to 145 s (instance in service at 63 s). Measured once on each side (`docs/p9-day-minus-3-smoketest-status.md`).
3. **Pre-baked worker image** with the compiled Numba cache, so a fresh worker avoids the first-call compile (2.47 s over ten kernels, `docs/p7-numba-profiling-results.md`). Designed; the image's own effect is not measured.
4. **The Iron Triangle data contract** (`docs/p8-iron-triangle-data.md`): time is real per job (`api_usage.duration_ms`), and the document labels each axis real, aggregate estimate or static score so an estimate is never shown as a live metric.

## 3. Evidence ledger

| Claim | Evidence | Level | Gap |
| --- | --- | --- | --- |
| Warm Monte Carlo VaR (100,000 simulations) in 7 ms | `p7-numba-profiling-results.md` (`run_monte_carlo_var`: 0.007 s warm, 1.083 s first call) | Measured, one machine, fixed seed | W1 baseline: a plain-NumPy version of the same function is as fast or faster end to end, so the 7 ms is not a JIT result |
| First-call JIT cost | Same: 2.47 s for ten kernels (0.46 s warm) | Measured | |
| First job after idle | 401.5 s before the fix, 145 s after | Measured once each | n = 1; no distribution |
| Marginal compute cost per scenario | `p9-scenario-volume-cost-audit.md`: about $0.06 to $0.12 a month of Spot compute at 1,000,000 scenarios | Bottom-up estimate | Not taken from billing |
| Monthly cost | README: $900 to $1,000, real invoice (2026-08-31), mostly fixed infrastructure; the audit's own bottom-up figure was 2.2 times too low | Measured (invoice) | Cost is flat in volume, not low at small volume |
| API reliability and latency | `p9-soak-test-status.md`: 579 canary invocations, 0 errors, ALB p95 3.9 to 6.2 ms | Measured | A p95 of a few milliseconds is far below any Monte Carlo job, so this is a light endpoint, not compute |
| Spot interruption safety | Design (`CLAUDE.md` 3.2) | Not measured | No drill |
| Throughput scaling | None (`locustfile.py` exists) | Not measured | |
| Faster than plain NumPy | `p7-numba-vs-numpy-results.md` (W1): four functions against equivalent vectorised baselines, one 4-core machine, 21 repeats | Measured: kernels 2 to 14 times faster where per-path work dominates; **end to end faster in 1 of 5 cases, parity in 1, slower in 3** | One machine and one size; not production hardware |
| Better than alternatives on cost or efficiency | None | Not measured | No on-demand, Lambda or other comparison anywhere in the repository |

## 4. Where it goes in the SWOT, and what it changes

- **Strengths:** a new row, "Engineering integration (cost, speed, efficiency)", with the draft wording above and the level of each figure.
- **Weaknesses:** the $900 to $1,000 monthly cost is fixed infrastructure; the first job after idle takes minutes; the key figures are single measurements; and Numba is not an end-to-end speed advantage over vectorised NumPy for the functions measured (W1).
- **BridgeAI:** relevant as deployment efficiency (a deployer's cost does not grow with volume). No rating changes.
- **Eurostars:** supports an "innovative" criterion only if framed with a measured comparison; it is not the R&D question.
- **EIC:** the "Breakthrough shown" row stays a **Gap**. An integration of established components with no IP position does not meet that bar, and re-rating it without a baseline and an IP view would not survive an assessor. The readiness percentages change only if a row's rating changes.

## 5. Work that makes the claim defensible

| # | Work | Needs | Pipeline |
| --- | --- | --- | --- |
| W1 | **Done 2026-11-13** (`docs/p7-numba-vs-numpy-results.md`, `scripts/p7_vs_numpy.py`). **Fair NumPy baselines** for the hottest kernels in the p7 benchmark (`run_monte_carlo_var`, `american_option_lsm`, `rough_volatility_rbergomi_model`, `asian_option_pricer`). Rules: same algorithm and the same random draws; vectorised NumPy and SciPy; float64; same sample size; median of k runs after warm-up; hardware stated; warm and cold both reported. A pure-Python-loop baseline (`NUMBA_DISABLE_JIT=1`) may be shown only if labelled "not a fair comparator". | Nothing external; offline and free | `scripts/` and `docs/`: none |
| W2 | Cost per job from billing (cost-allocation tags or the cost and usage report), against the bottom-up estimate | AWS access: delegated agent with an assigned prompt | none |
| W3 | Latency percentiles for compute jobs, warm and cold, from `api_usage.duration_ms` over a stated window | Production database: delegated agent | none |
| W4 | A Spot interruption drill: reclaim a worker mid-job; success is the job completing exactly once (dev only) | AWS access: delegated agent | none |
| W5 | Throughput against the number of workers (`locustfile.py` or a script) (dev only) | A test environment: delegated agent | none |
| W6 | Optional: a paper comparison with an on-demand-only or Lambda-based design | Nothing external | none |

Baselines are against NumPy only. No vendor is named in this public repository (the same rule as for deployers).

## 6. Order

W1 first (free, offline, and the missing comparator). Then W2 and W3 when someone with AWS access can pull them. Draft the SWOT row after W1, upgrade its wording as W2 to W5 land, and rebuild the PDF. Each step is docs-only or `scripts/`-only.

## 7. Decisions for Filippo

| Decision | Status |
| --- | --- |
| Accept "an evidenced integration of established components" rather than "a real innovation" until a comparator exists | **Open**; W1 makes it stronger: speed over NumPy cannot be the innovation |
| Who pulls W2 to W5 from AWS | **Decided** (2026-11-13): a delegated agent with an assigned prompt (read-only on prod; the drill and the load test only in dev) |
| Run W1 now | **Done** (2026-11-13): `docs/p7-numba-vs-numpy-results.md` |
| Baselines against NumPy only, no vendor names | **Applied** in W1 |
| Review the "JIT-accelerated" wording in the GitHub description and the README | **Open** (see the W1 results) |
| Make the two engine changes W1 exposes (`np.sort` in the VaR function; lag weights computed once in rough Bergomi) | **Open**: each is its own change to `engine/` with tests, and starts a CodePipeline run |
