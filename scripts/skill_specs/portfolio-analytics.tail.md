## Naming convention
- Every function returns a plain
  `dict` (JSON-serialisable — lists/floats/ints, never a bare `float`,
  `np.ndarray` or `pd.DataFrame`, and no pandas objects anywhere in a
  response: `weights` etc. are always plain Python lists, not
  `np.ndarray`, matching the `list[float] | list[list[float]]`
  request/response schemas in `schemas/portfolio.py`).
- Weights: sum to 1.0.
- "Optimisation: returns dict with weights/return/volatility/sharpe" only
  holds for the mean-variance-family functions (`mean_variance_optimisation`,
  `minimum_variance_portfolio`, `maximum_sharpe_ratio_portfolio`,
  `risk_parity_portfolio`, `equal_weight_portfolio` when stats inputs are
  given). `black_litterman_model` returns `posterior_returns`/
  `implied_returns`/`weights`; `resampled_efficient_frontier` returns
  `weights`/`weight_std`/`n_resamples`; `robust_portfolio_optimisation`
  returns `weights`/`expected_return`/`cvar`/`success`;
  `factor_based_optimisation` returns `weights`/`volatility`/
  `factor_exposures`/`success` — check the actual keys per function rather
  than assuming this shape.
## For contributors: dependencies
numpy >= 1.24 · scipy >= 1.10 (only `scipy.optimize.minimize`/SLSQP and
`scipy.stats`; no cvxpy anywhere in this codebase — not imported, not in
`requirements*.txt`, not in the worker AMI package list)

`statsmodels` and `empyrical` are pre-baked in the worker AMI
(`requirements-heavy.txt`) but this domain's own code does not import
either: the factor regressions (`fama_french_*`, `carhart_4_factor_model`)
are a self-contained NumPy OLS via `np.linalg.lstsq`, and the ratio/
drawdown functions are hand-rolled, not `empyrical` calls — see
`engine/portfolio_factor.py`'s module docstring ("sklearn / statsmodels
are intentionally NOT used ... self-contained NumPy"). `scikit-learn` is
not a dependency of this codebase at all (not in any `requirements*.txt`,
not imported) — `correlation_clustering` is a hand-rolled single-linkage
agglomerative clusterer, not `sklearn.cluster`. `pandas` is likewise not
imported anywhere in `engine/portfolio_*.py`.

## For contributors: architecture context
- **Compute**: NumPy/Numba (matrix ops, EM/clustering kernels), SciPy
  (`scipy.optimize.minimize`, method="SLSQP", for every constrained
  optimisation — mean-variance, min-variance long-only, max-Sharpe, risk
  parity, CVaR-constrained, factor-based, ESG-constrained tilt)
- **Solver**: SLSQP via `scipy.optimize`, not CVXPY — CVXPY is not a
  dependency of this codebase (not imported anywhere in `engine/`, not in
  `requirements*.txt` or the worker AMI package list). Some closed-form
  cases (unconstrained min-variance, Black-Litterman) skip the solver
  entirely and use `np.linalg.pinv` directly.
- **Queue**: Celery (daily rebalancing, factor attribution batch)
- **Storage**: PostgreSQL (portfolio snapshots), Redis (live NAV cache)
- **API**: FastAPI endpoint `/api/v1/portfolio/{function}`

---
