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

## Dask — Large portfolio scenario matrix
```python
import dask.array as da
import dask.dataframe as dd

def scenario_pnl_dask(positions: np.ndarray,
                        scenarios: np.ndarray,
                        chunk_size: int = 1000) -> np.ndarray:
    """Compute P&L for 10k+ scenarios on large position vectors."""
    da_pos = da.from_array(positions, chunks=chunk_size)
    da_scen = da.from_array(scenarios, chunks=(chunk_size, scenarios.shape[1]))
    pnl = da_scen @ da_pos
    return pnl.compute()
```

## Ray — Multi-node scale-out
```python
import ray

@ray.remote(num_cpus=2)
class VaRWorker:
    def compute(self, returns: np.ndarray, confidence: float) -> float:
        return mc_var_kernel(returns, 100_000, 10, confidence)

# Dispatch N workers across cluster
workers = [VaRWorker.remote() for _ in range(16)]
futures = [w.compute.remote(returns_slice, 0.99) for w, returns_slice
           in zip(workers, np.array_split(returns_matrix, 16))]
results = ray.get(futures)
```

## Celery — Task dispatch pattern
```python
from celery import Celery

app = Celery("pyvar", broker="redis://localhost:6379/0",
             backend="redis://localhost:6379/1")

@app.task(bind=True, max_retries=3, soft_time_limit=300)
def compute_var_task(self, returns: list, confidence: float,
                      method: str = "historical") -> dict:
    try:
        arr = np.array(returns)
        result = pyvar.market_risk.historical_simulation_var(arr, confidence)
        return {"var": float(result), "status": "complete"}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
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
