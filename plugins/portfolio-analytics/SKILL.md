---
name: pyvar-portfolio-analytics
description: >
  Activate for portfolio construction, optimisation, performance attribution,
  factor models, risk analytics, ESG integration, or drawdown analysis. Covers
  50 functions across 7 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [portfolio, optimisation, markowitz, black-litterman, risk-parity,
       sharpe, attribution, brinson, factor-model, FF5, PCA, HMM, ESG]
---

# pyvar — Portfolio Analytics  (50 functions)

## Architecture context
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

## Portfolio Optimisation

```python
pyvar.portfolio.mean_variance_optimisation(
    # Mean-Variance Optimisation (Markowitz)
    **params
) -> dict
```

```python
pyvar.portfolio.minimum_variance_portfolio(
    # Minimum Variance Portfolio
    **params
) -> dict
```

```python
pyvar.portfolio.maximum_sharpe_ratio_portfolio(
    # Maximum Sharpe Ratio Portfolio
    **params
) -> dict
```

```python
pyvar.portfolio.risk_parity_portfolio(
    # Risk Parity Portfolio
    **params
) -> dict
```

```python
pyvar.portfolio.equal_weight_portfolio(
    # Equal Weight Portfolio
    **params
) -> dict
```

```python
pyvar.portfolio.black_litterman_model(
    # Black-Litterman Model — verified exact match to He & Litterman (1999)
    # conventions: Omega=diag(P*tau*Sigma*P'), lambda=delta=2.5, tau=0.05
    # are their specific default choices. Takes p_matrix/q_views directly
    # (no natural-language view parsing) and returns posterior_returns,
    # implied_returns and weights — NOT the weights/return/volatility/
    # sharpe shape used by the mean-variance-family functions below.
    **params
) -> dict
```

```python
pyvar.portfolio.resampled_efficient_frontier(
    # Resampled Efficient Frontier
    **params
) -> dict
```

```python
pyvar.portfolio.robust_portfolio_optimisation(
    # Robust Portfolio Optimisation
    **params
) -> dict
```

```python
pyvar.portfolio.cvar_constrained_optimisation(
    # CVaR-Constrained Optimisation
    **params
) -> dict
```

```python
pyvar.portfolio.factor_based_optimisation(
    # Factor-Based Optimisation
    **params
) -> dict
```


## Risk-Adjusted Performance

```python
pyvar.portfolio.sharpe_ratio(
    # Sharpe Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.sortino_ratio(
    # Sortino Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.calmar_ratio(
    # Calmar Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.information_ratio(
    # Information Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.treynor_ratio(
    # Treynor Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.jensens_alpha(
    # Jensen's Alpha
    **params
) -> dict
```

```python
pyvar.portfolio.omega_ratio(
    # Omega Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.maximum_drawdown(
    # Maximum Drawdown
    **params
) -> dict
```

```python
pyvar.portfolio.average_drawdown(
    # Average Drawdown
    **params
) -> dict
```

```python
pyvar.portfolio.drawdown_duration(
    # Drawdown Duration
    **params
) -> dict
```

```python
pyvar.portfolio.conditional_drawdown_at_risk(
    # Conditional Drawdown at Risk
    **params
) -> dict
```

```python
pyvar.portfolio.tail_ratio(
    # Tail Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.ulcer_index(
    # Ulcer Index
    **params
) -> dict
```


## Performance Attribution

```python
pyvar.portfolio.return_attribution_brinson(
    # Return Attribution (Brinson)
    **params
) -> dict
```

```python
pyvar.portfolio.factor_return_attribution(
    # Factor Return Attribution
    **params
) -> dict
```

```python
pyvar.portfolio.sector_attribution(
    # Sector Attribution
    **params
) -> dict
```

```python
pyvar.portfolio.currency_attribution(
    # Currency Attribution — naive geometric local/FX split via
    # base=(1+local)(1+fx)-1, with currency as the residual. This is NOT
    # Karnosky-Singer (Karnosky & Singer 1994): that method needs local
    # returns net of the local risk-free rate and moves the rate
    # differential onto the currency leg via covered interest parity;
    # this function takes no interest rates at all. A prior docstring
    # claimed "Karnosky-Singer style" — corrected in the citation cleanup
    # pass (engine/portfolio_attribution.py). See Bacon (2008), "Practical
    # Portfolio Performance Measurement and Attribution", 2nd ed., Ch. 6,
    # which presents this split as the baseline before Karnosky-Singer.
    **params
) -> dict
```

```python
pyvar.portfolio.gics_sector_exposure(
    # GICS Sector Exposure
    **params
) -> dict
```

```python
pyvar.portfolio.factor_exposure_analysis_barra(
    # Factor Exposure Analysis (Barra)
    **params
) -> dict
```


## Factor Models

```python
pyvar.portfolio.fama_french_3_factor_model(
    # Fama-French 3-Factor Model
    **params
) -> dict
```

```python
pyvar.portfolio.carhart_4_factor_model(
    # Carhart 4-Factor Model
    **params
) -> dict
```

```python
pyvar.portfolio.fama_french_5_factor_model(
    # Fama-French 5-Factor Model
    **params
) -> dict
```

```python
pyvar.portfolio.principal_component_analysis(
    # Principal Component Analysis (PCA)
    **params
) -> dict
```

```python
pyvar.portfolio.correlation_clustering(
    # Correlation Clustering
    **params
) -> dict
```

```python
pyvar.portfolio.regime_detection_hmm(
    # Regime Detection (HMM) — despite the name, this is a STATIONARY
    # 2-component Gaussian mixture fitted by EM, not a hidden Markov model:
    # there is no transition matrix, so regime persistence/switching
    # probability is not modelled, only the marginal mixture. A genuine
    # HMM (Hamilton 1989, Econometrica 57(2)) fits a Markov-switching
    # autoregression with an explicit 2x2 transition matrix. Flagged in
    # engine/portfolio_factor.py so the function name isn't mistaken for a
    # claim of Markov-switching behaviour; renaming it is a larger,
    # separate change than the docstring fix.
    **params
) -> dict
```


## Active Risk Analytics

```python
pyvar.portfolio.portfolio_beta(
    # Portfolio Beta
    **params
) -> dict
```

```python
pyvar.portfolio.active_share(
    # Active Share
    **params
) -> dict
```

```python
pyvar.portfolio.tracking_error(
    # Tracking Error
    **params
) -> dict
```

```python
pyvar.portfolio.residual_risk(
    # Residual Risk
    **params
) -> dict
```

```python
pyvar.portfolio.portfolio_turnover(
    # Portfolio Turnover
    **params
) -> dict
```

```python
pyvar.portfolio.transaction_cost_analysis(
    # Transaction Cost Analysis (TCA) — quantity-weighted slippage vs an
    # arrival/VWAP benchmark, in bps. A narrower measure than Perold's full
    # implementation-shortfall decomposition: no delay cost or unexecuted-
    # share opportunity-cost leg. No published source reproduces this
    # exact quantity — checked, not assumed (Tier 3 #2 audit).
    **params
) -> dict
```


## ESG & Sustainability

```python
pyvar.portfolio.rebalancing_optimiser(
    # Rebalancing Optimiser — `no_trade_band` is a user-supplied absolute
    # weight threshold, not one derived from cost/volatility parameters the
    # way Leland (1999) or Donohue & Yip (2003) derive an optimal no-trade
    # region. No published source reproduces this function's exact
    # numbers — checked, not assumed (Tier 3 #2 audit).
    **params
) -> dict
```

```python
pyvar.portfolio.esg_score_integration(
    # ESG Score Integration
    **params
) -> dict
```

```python
pyvar.portfolio.carbon_footprint_attribution(
    # Carbon Footprint Attribution — the WACI leg matches TCFD's definition
    # exactly. The total_financed_emissions leg does NOT match either
    # TCFD's or PCAF's financed-emissions standard: both use an
    # ownership-share method, whereas this function uses
    # revenue-intensity-times-invested-value. Flagged as a likely
    # correctness question for the domain owner, not merely a citation
    # gap (Tier 3 #2 audit).
    **params
) -> dict
```


## Portfolio Risk Analytics

```python
pyvar.portfolio.liquidity_adjusted_portfolio_var(
    # Liquidity-Adjusted Portfolio VaR
    **params
) -> dict
```

```python
pyvar.portfolio.marginal_contribution_to_risk(
    # Marginal Contribution to Risk
    **params
) -> dict
```

```python
pyvar.portfolio.diversification_ratio(
    # Diversification Ratio
    **params
) -> dict
```

```python
pyvar.portfolio.correlation_matrix_portfolio(
    # Correlation Matrix (Portfolio)
    **params
) -> dict
```

```python
pyvar.portfolio.concentration_risk_hhi(
    # Concentration Risk (HHI)
    **params
) -> dict
```

```python
pyvar.portfolio.monte_carlo_portfolio_simulation(
    # Monte Carlo Portfolio Simulation
    **params
) -> dict
```


## Naming convention
- All functions under `pyvar.portfolio.*`; every one returns a plain
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

## Dependencies
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
