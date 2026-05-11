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
- **Compute**: NumPy/Numba (matrix ops), SciPy (optimisation solver)
- **Solver**: CVXPY for constrained optimisation
- **Queue**: Celery (daily rebalancing, factor attribution batch)
- **Storage**: PostgreSQL (portfolio snapshots), Redis (live NAV cache)
- **API**: FastAPI endpoint `/api/v1/portfolio/{function}`

---

## Portfolio Optimisation

```python
pyvar.portfolio.mean_variance_optimisation_markowitz(
    # Mean-Variance Optimisation (Markowitz)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.minimum_variance_portfolio(
    # Minimum Variance Portfolio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.maximum_sharpe_ratio_portfolio(
    # Maximum Sharpe Ratio Portfolio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.risk_parity_portfolio(
    # Risk Parity Portfolio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.equal_weight_portfolio(
    # Equal Weight Portfolio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.black_litterman_model(
    # Black-Litterman Model
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.resampled_efficient_frontier(
    # Resampled Efficient Frontier
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.robust_portfolio_optimisation(
    # Robust Portfolio Optimisation
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.cvar_constrained_optimisation(
    # CVaR-Constrained Optimisation
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.factor_based_optimisation(
    # Factor-Based Optimisation
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## Risk-Adjusted Performance

```python
pyvar.portfolio.sharpe_ratio(
    # Sharpe Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.sortino_ratio(
    # Sortino Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.calmar_ratio(
    # Calmar Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.information_ratio(
    # Information Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.treynor_ratio(
    # Treynor Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.jensen_s_alpha(
    # Jensen's Alpha
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.omega_ratio(
    # Omega Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.maximum_drawdown(
    # Maximum Drawdown
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.average_drawdown(
    # Average Drawdown
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.drawdown_duration(
    # Drawdown Duration
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.conditional_drawdown_at_risk(
    # Conditional Drawdown at Risk
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.tail_ratio(
    # Tail Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.ulcer_index(
    # Ulcer Index
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## Performance Attribution

```python
pyvar.portfolio.return_attribution_brinson(
    # Return Attribution (Brinson)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.factor_return_attribution(
    # Factor Return Attribution
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.sector_attribution(
    # Sector Attribution
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.currency_attribution(
    # Currency Attribution
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.gics_sector_exposure(
    # GICS Sector Exposure
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.factor_exposure_analysis_barra(
    # Factor Exposure Analysis (Barra)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## Factor Models

```python
pyvar.portfolio.fama_french_3_factor_model(
    # Fama-French 3-Factor Model
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.carhart_4_factor_model(
    # Carhart 4-Factor Model
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.fama_french_5_factor_model(
    # Fama-French 5-Factor Model
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.principal_component_analysis_pca(
    # Principal Component Analysis (PCA)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.correlation_clustering(
    # Correlation Clustering
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.regime_detection_hmm(
    # Regime Detection (HMM)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## Active Risk Analytics

```python
pyvar.portfolio.portfolio_beta(
    # Portfolio Beta
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.active_share(
    # Active Share
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.tracking_error(
    # Tracking Error
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.residual_risk(
    # Residual Risk
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.portfolio_turnover(
    # Portfolio Turnover
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.transaction_cost_analysis_tca(
    # Transaction Cost Analysis (TCA)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## ESG & Sustainability

```python
pyvar.portfolio.rebalancing_optimiser(
    # Rebalancing Optimiser
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.esg_score_integration(
    # ESG Score Integration
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.carbon_footprint_attribution(
    # Carbon Footprint Attribution
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## Portfolio Risk Analytics

```python
pyvar.portfolio.liquidity_adjusted_portfolio_var(
    # Liquidity-Adjusted Portfolio VaR
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.marginal_contribution_to_risk(
    # Marginal Contribution to Risk
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.diversification_ratio(
    # Diversification Ratio
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.correlation_matrix_portfolio(
    # Correlation Matrix (Portfolio)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.concentration_risk_hhi(
    # Concentration Risk (HHI)
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```

```python
pyvar.portfolio.monte_carlo_portfolio_simulation(
    # Monte Carlo Portfolio Simulation
    **params
) -> float | np.ndarray | dict | pd.DataFrame
```


## Naming convention
- All functions under `pyvar.portfolio.*`
- Weights: np.ndarray summing to 1.0
- Returns: pd.Series with DatetimeIndex
- Optimisation: returns dict with "weights", "return", "volatility", "sharpe"

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · cvxpy >= 1.4
statsmodels >= 0.14 · scikit-learn >= 1.3 · empyrical >= 0.5
