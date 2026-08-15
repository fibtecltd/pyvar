---
name: pyvar-arch-compute
description: >
  Activate when implementing or optimising pyvar compute workers: NumPy
  vectorisation, Numba JIT for Monte Carlo loops, SciPy optimisation,
  Dask distributed DataFrames, or Ray multi-node scale-out. Also covers
  the Celery + Redis task queue dispatch pattern.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [numpy, numba, scipy, dask, ray, celery, redis, JIT, monte-carlo,
       parallelism, distributed, compute-workers, performance]
---

# pyvar — Architecture: Compute Workers

## Stack
| Worker Type | Engine | Best for |
|---|---|---|
| **JIT / MC loops** | NumPy + Numba | VaR MC, IRR, pricing inner loops |
| **Optimisation** | SciPy + statsmodels | GARCH, curve fitting, portfolio opt |
| **Large arrays** | Dask | Portfolio of 10k+ assets, scenario matrices |
| **Multi-node** | Ray + Ray Serve | Enterprise scale-out, model serving |

## NumPy / Numba — Monte Carlo VaR
```python
import numpy as np
from numba import njit, prange

@njit(parallel=True, cache=True)
def mc_var_kernel(returns: np.ndarray, n_sim: int,
                   n_days: int, confidence: float) -> float:
    """JIT-compiled MC VaR — runs ~50x faster than pure Python."""
    n = len(returns)
    portfolio_losses = np.empty(n_sim)

    for i in prange(n_sim):                        # parallel threads
        indices = np.random.randint(0, n, n_days)
        portfolio_losses[i] = -np.sum(returns[indices])

    portfolio_losses.sort()
    return float(portfolio_losses[int(n_sim * confidence)])

# Warm up JIT on first call (compile once, reuse)
_ = mc_var_kernel(np.zeros(10), 100, 1, 0.99)
```

## SciPy — GARCH optimisation
```python
from scipy.optimize import minimize
from scipy.stats import t as student_t

def fit_garch(returns: np.ndarray) -> dict:
    def neg_log_likelihood(params):
        omega, alpha, beta = params
        n = len(returns)
        sigma2 = np.var(returns) * np.ones(n)
        for t in range(1, n):
            sigma2[t] = omega + alpha * returns[t-1]**2 + beta * sigma2[t-1]
        return 0.5 * np.sum(np.log(sigma2) + returns**2 / sigma2)

    result = minimize(neg_log_likelihood, [1e-6, 0.1, 0.85],
                      method="L-BFGS-B",
                      bounds=[(1e-8,None),(0,1),(0,1)])
    return {"omega": result.x[0], "alpha": result.x[1], "beta": result.x[2]}
```

## Dask / Ray — installed, not currently wired into the app
`requirements-heavy.txt` pins `dask[complete]` and `ray[default]`, and the
worker AMI build script (`pyvar-cdk/stacks/ami_stack.py`) installs both — but
as of this writing **no file under `engine/`, `tasks/`, or `api/` imports
either package**. Treat the snippets below as the intended pattern for a
future 10k+ asset / multi-node scale-out, not as something this codebase
currently exercises — don't cite them as evidence of how pyvar actually
scales today (that's the Celery + EC2 Spot ASG pattern below, which is real).

```python
# Dask — large portfolio scenario matrix (not yet used in engine/)
import dask.array as da

def scenario_pnl_dask(positions: np.ndarray, scenarios: np.ndarray,
                       chunk_size: int = 1000) -> np.ndarray:
    da_pos = da.from_array(positions, chunks=chunk_size)
    da_scen = da.from_array(scenarios, chunks=(chunk_size, scenarios.shape[1]))
    return (da_scen @ da_pos).compute()
```

```python
# Ray — multi-node scale-out (not yet used; the real scale-out unit is an
# EC2 Spot ASG instance running one Celery worker process, not a Ray actor)
import ray

@ray.remote(num_cpus=2)
class VaRWorker:
    def compute(self, returns: np.ndarray, confidence: float) -> float:
        return mc_var_kernel(returns, 100_000, 10, confidence)
```

## Celery — Task dispatch pattern (tasks/var_task.py, the real config)
```python
from celery import Celery

# Broker AND backend default to the SAME cfg.redis_url (not different db
# numbers) — overridden per-env via CELERY_BROKER_URL (sqs:// on AWS) and
# CELERY_RESULT_BACKEND (rediss://<elasticache-endpoint>:6379/0?ssl_cert_reqs=
# CERT_NONE on AWS — the ssl_cert_reqs query param needs a lowercase-rewrite
# fix, see arch-storage's Redis section for why).
celery_app = Celery(
    "pyvar",
    broker=os.environ.get("CELERY_BROKER_URL", cfg.redis_url),
    backend=os.environ.get("CELERY_RESULT_BACKEND", cfg.redis_url),
)
celery_app.conf.update(
    task_default_queue=os.environ.get("SQS_QUEUE_NAME", "celery"),
    task_track_started=True,
    result_extended=True,          # keeps dispatch kwargs on AsyncResult — the
                                    # cache layer (api/routes/caching.py) reuses
                                    # them to recompute its cache key on a hit
    worker_prefetch_multiplier=1,  # CPU-bound MC — never increase (CLAUDE.md §3.2)
    task_acks_late=True,           # non-negotiable — Spot interruption safety
    worker_max_tasks_per_child=100,
)

@celery_app.task(bind=True, name="pyvar.tasks.compute_var", max_retries=2, default_retry_delay=5)
def compute_var_task(self, payload: dict) -> dict:
    # payload is a plain JSON-serialisable dict (VaRRequest.model_dump()),
    # never a Pydantic model or np.ndarray — apply_async requires JSON-safe args.
    returns = np.array(payload["returns"], dtype=np.float64)
    result = run_monte_carlo_var(returns=returns, portfolio_value=payload["portfolio_value"], ...)
    # Above cfg.s3_result_offload_threshold simulations, loss_dist is stripped
    # and written to S3 instead (#130) — see arch-storage.
    return result
```

## Worker selection guide
```
Function runtime < 100ms    → synchronous FastAPI response
Function runtime 100ms–30s  → Celery + NumPy/Numba worker
Dataset > 1M rows           → Dask worker
Multi-node enterprise tier  → Ray cluster
```

## Dependencies
numpy >= 1.24 · numba >= 0.57 · scipy >= 1.10 · statsmodels >= 0.14
dask >= 2024.1 · ray >= 2.9 · celery >= 5.3 · redis >= 5.0

## Production lessons: EC2 Spot worker fleet (P9 launch)

### Warm Pools are flatly incompatible with a Spot MixedInstancesPolicy
`pyvar-cdk/stacks/compute_stack.py` originally tried to add an ASG Warm Pool
to `WorkerAsg` (pre-initialised stopped instances, to cut scale-out from
~90s to ~30s). AWS rejects the combination outright: *"You can't add a warm
pool to an Auto Scaling group that has a mixed instances policy or a launch
template or launch configuration that requests Spot Instances."* — confirmed
live against `pyvar-prod-compute`'s first-ever deploy (`CREATE_FAILED`, not a
config-validation error caught at synth time). Spot is the deliberate cost
strategy for this workload (`PRICE_CAPACITY_OPTIMIZED`, CLAUDE.md §3.4), so
the Warm Pool was dropped rather than switching off Spot — scale-from-zero
stays ~90s.

### EC2 Image Builder's DistributionConfiguration needs a raw PascalCase dict
`pyvar-cdk/stacks/ami_stack.py`'s `WorkerDistribution` sets
`ami_distribution_configuration` to a **raw Python dict with literal
CloudFormation PascalCase keys** (`"Name"`, `"Description"`, `"AmiTags"`) —
not the typed `AmiDistributionConfigurationProperty` class, and not a
camelCase dict. Both of those serialize the property with the wrong
(camelCase) key casing in aws-cdk-lib 2.261.0, which the real
`AWS::ImageBuilder::DistributionConfiguration` resource schema rejects
outright (`"extraneous key [name] is not permitted"`). Confirmed via an
isolated repro against the installed CDK version — this is a real bug in
that construct, not a usage error.

### SQS's own CloudWatch metrics go dark after 6+ hours idle
The `min_capacity=0` (scale-to-zero) worker ASG originally scaled its 0→1
step off `AWS/SQS ApproximateNumberOfMessagesVisible`. Day -3 smoke testing
(task #38) found a 401.5s cold start: SQS stops publishing *any* CloudWatch
metric for a queue after 6+ hours of zero activity, and delivery resumes
with up to a 15-minute lag once activity resumes. This is a platform-level
behavior of SQS's own CloudWatch integration — it applies equally to every
SQS metric, not just `ApproximateNumberOfMessagesVisible` (an earlier,
incorrect hypothesis was that switching to `NumberOfMessagesSent` would
help; it hits the identical gating). The fix
(`compute_stack.py`'s `ScaleFromZero` step-scaling policy +
`api/routes/var.py`'s `_emit_scale_kickstart_metric()`) publishes a custom,
non-SQS CloudWatch metric (`pyvar` namespace, `job-submitted-{env}`) the
instant a job is enqueued — `put_metric_data` has no such idle-queue gating.
The steady-state `ScaleOnQueueDepth` target-tracking policy is unchanged and
still reads real queue depth once ≥1 instance is running. Verified live
against prod on 2026-08-15: scaled the ASG to 0, submitted a real job,
instance `InService` at t+63s, job succeeded end-to-end at t+145s (vs. 401.5s
before).
