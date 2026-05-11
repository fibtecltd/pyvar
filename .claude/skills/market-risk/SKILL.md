---
name: pyvar-market-risk
description: >
  Activate for any market risk computation: VaR, Expected Shortfall, stress
  testing, Greeks, P&L attribution, backtesting, volatility modelling, or FRTB
  capital calculations. Covers 68 functions across 8 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [market-risk, VaR, ES, greeks, stress-test, backtesting, FRTB,
       GARCH, volatility, PCA, monte-carlo]
---

# pyvar — Market Risk  (68 functions)

## Architecture context
- **Compute**: NumPy/Numba (MC loops, JIT), SciPy/statsmodels (GARCH, PCA)
- **Queue**: Celery + Redis (async VaR jobs)
- **Storage**: Redis cache (intraday VaR), PostgreSQL (backtest results)
- **API**: FastAPI endpoint `/api/v1/market-risk/{function}`

---

## VaR Models

```python
pyvar.market_risk.monte_carlo_var_parametric_normal(
    # Monte Carlo VaR (Parametric Normal)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.historical_simulation_var(
    # Historical Simulation VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.filtered_historical_simulation_var(
    # Filtered Historical Simulation VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.parametric_delta_normal_var(
    # Parametric Delta-Normal VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.cornish_fisher_var(
    # Cornish-Fisher VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.component_var_euler_allocation(
    # Component VaR (Euler Allocation)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.marginal_var(
    # Marginal VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.incremental_var(
    # Incremental VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.var_by_risk_factor(
    # VaR by Risk Factor
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.var_fan_chart_percentile_bands(
    # VaR Fan Chart (Percentile Bands)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## Expected Shortfall

```python
pyvar.market_risk.conditional_var_cvar_es(
    # Conditional VaR (CVaR / ES)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.historical_expected_shortfall(
    # Historical Expected Shortfall
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.monte_carlo_expected_shortfall(
    # Monte Carlo Expected Shortfall
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.cvar_decomposition_euler(
    # CVaR Decomposition (Euler)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.stressed_expected_shortfall_frtb(
    # Stressed Expected Shortfall (FRTB)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.liquidity_adjusted_es_frtb_lah(
    # Liquidity-Adjusted ES (FRTB LAH)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.es_at_multiple_confidence_levels(
    # ES at Multiple Confidence Levels
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.expected_shortfall_contribution(
    # Expected Shortfall Contribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## Stress Testing

```python
pyvar.market_risk.historical_scenario_replay(
    # Historical Scenario Replay
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.hypothetical_multi_factor_scenario(
    # Hypothetical Multi-Factor Scenario
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.reverse_stress_testing(
    # Reverse Stress Testing
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.sensitivity_stress_profile(
    # Sensitivity Stress Profile
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.sector_stress_scenario(
    # Sector Stress Scenario
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.macro_scenario_generator(
    # Macro Scenario Generator
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.contagion_stress_scenario(
    # Contagion Stress Scenario
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.portfolio_delta_aggregated(
    # Portfolio Delta (Aggregated)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## Greeks & Sensitivities

```python
pyvar.market_risk.gamma_and_cross_gamma_matrix(
    # Gamma and Cross-Gamma Matrix
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.vega_surface_bucketed(
    # Vega Surface (Bucketed)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.dv01_pv01_tenor_bucketed(
    # DV01 / PV01 (Tenor Bucketed)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.cs01_credit_spread_dv01(
    # CS01 Credit Spread DV01
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.rho_interest_rate_sensitivity(
    # Rho (Interest Rate Sensitivity)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.theta_time_decay(
    # Theta (Time Decay)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.charm_delta_decay(
    # Charm (Delta Decay)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.volga_vega_convexity(
    # Volga (Vega Convexity)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.vanna_delta_vega_cross(
    # Vanna (Delta-Vega Cross)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.greeks_based_p_l_explain(
    # Greeks-based P&L Explain
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## P&L Attribution

```python
pyvar.market_risk.p_l_attribution_test_frtb_pat(
    # P&L Attribution Test (FRTB PAT)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.theta_carry_attribution(
    # Theta / Carry Attribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.gamma_p_l_attribution(
    # Gamma P&L Attribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.vega_p_l_attribution(
    # Vega P&L Attribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.fx_p_l_attribution(
    # FX P&L Attribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.rates_p_l_attribution(
    # Rates P&L Attribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.credit_p_l_attribution(
    # Credit P&L Attribution
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.residual_p_l_unexplained(
    # Residual P&L (Unexplained)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## Backtesting

```python
pyvar.market_risk.traffic_light_backtesting_basel(
    # Traffic Light Backtesting (Basel)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.kupiec_proportion_of_failures_test(
    # Kupiec Proportion of Failures Test
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.christoffersen_independence_test(
    # Christoffersen Independence Test
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.combined_backtesting_kupiec_christoffersen(
    # Combined Backtesting (Kupiec + Christoffersen)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.basel_capital_add_on_multiplier(
    # Basel Capital Add-On Multiplier
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.rolling_var_backtest_250_day(
    # Rolling VaR Backtest (250-day)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.var_breach_cluster_analysis(
    # VaR Breach Cluster Analysis
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.volatility_surface_implied_vol(
    # Volatility Surface (Implied Vol)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## Volatility & Correlation

```python
pyvar.market_risk.garch_1_1_volatility_forecast(
    # GARCH(1,1) Volatility Forecast
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.egarch_volatility_model(
    # EGARCH Volatility Model
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.gjr_garch_asymmetric_model(
    # GJR-GARCH Asymmetric Model
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.realised_volatility_rv(
    # Realised Volatility (RV)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.correlation_matrix_historical(
    # Correlation Matrix (Historical)
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.dcc_garch_dynamic_correlation(
    # DCC-GARCH Dynamic Correlation
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.risk_factor_pca_decomposition(
    # Risk Factor PCA Decomposition
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.frtb_sa_sensitivity_based_method(
    # FRTB SA Sensitivity-Based Method
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.frtb_sa_default_risk_charge(
    # FRTB SA Default Risk Charge
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## FRTB Capital

```python
pyvar.market_risk.frtb_sa_residual_risk_add_on(
    # FRTB SA Residual Risk Add-On
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_expected_shortfall(
    # FRTB IMA Expected Shortfall
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_stressed_period_finder(
    # FRTB IMA Stressed Period Finder
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_non_modellable_risk_factors(
    # FRTB IMA Non-Modellable Risk Factors
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_aggregate_capital_charge(
    # FRTB IMA Aggregate Capital Charge
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.extreme_value_theory_evt_var(
    # Extreme Value Theory (EVT) VaR
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```

```python
pyvar.market_risk.spectral_risk_measure(
    # Spectral Risk Measure
    returns: pd.Series | np.ndarray,
    confidence: float = 0.99,
    **kwargs
) -> float | dict
```


## Naming convention
- All functions live under `pyvar.market_risk.*`
- Return scalar for single metrics, dict for multi-output (e.g. decomposition)
- Confidence level: 0.95 / 0.99 / 0.999
- Horizon in trading days (default 1)
- Monte Carlo: `simulations` kwarg, default 10_000

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · statsmodels >= 0.14
numba >= 0.57 · arch >= 6.0
