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
    **params
) -> float | dict
```
> **Routing note (verified against `api/routes/market_risk.py` / `main.py`):** this is
> the one function on this page that is *not* actually reachable at
> `/api/v1/market-risk/monte_carlo_var_parametric_normal`. The underlying kernel
> (`engine.montecarlo.run_monte_carlo_var`) is served through the separate async job
> pipeline instead — `POST /var/compute` + `GET /var/result/{task_id}`
> (`api/routes/var.py`, `tasks/var_task.py`) — and that endpoint does not accept an
> `antithetic` flag; it always calls the kernel with `antithetic=False`. To use
> antithetic-variate sampling (see below) you currently have to call
> `engine.montecarlo.run_monte_carlo_var(..., antithetic=True)` directly in Python —
> it is not yet exposed through either REST surface.

```python
pyvar.market_risk.historical_simulation_var(
    # Historical Simulation VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.filtered_historical_simulation_var(
    # Filtered Historical Simulation VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.parametric_delta_normal_var(
    # Parametric Delta-Normal VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.cornish_fisher_var(
    # Cornish-Fisher VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.component_var_euler_allocation(
    # Component VaR (Euler Allocation)
    **params
) -> float | dict
```

```python
pyvar.market_risk.marginal_var(
    # Marginal VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.incremental_var(
    # Incremental VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.var_by_risk_factor(
    # VaR by Risk Factor
    **params
) -> float | dict
```

```python
pyvar.market_risk.var_fan_chart_percentile_bands(
    # VaR Fan Chart (Percentile Bands)
    **params
) -> float | dict
```


## Expected Shortfall

```python
pyvar.market_risk.conditional_var_cvar_es(
    # Conditional VaR (CVaR / ES)
    **params
) -> float | dict
```

```python
pyvar.market_risk.historical_expected_shortfall(
    # Historical Expected Shortfall
    **params
) -> float | dict
```

```python
pyvar.market_risk.monte_carlo_expected_shortfall(
    # Monte Carlo Expected Shortfall
    **params
) -> float | dict
```

```python
pyvar.market_risk.cvar_decomposition_euler(
    # CVaR Decomposition (Euler)
    **params
) -> float | dict
```

```python
pyvar.market_risk.stressed_expected_shortfall_frtb(
    # Stressed Expected Shortfall (FRTB)
    **params
) -> float | dict
```

```python
pyvar.market_risk.liquidity_adjusted_es_frtb_lah(
    # Liquidity-Adjusted ES (FRTB LAH)
    **params
) -> float | dict
```

```python
pyvar.market_risk.es_at_multiple_confidence_levels(
    # ES at Multiple Confidence Levels
    **params
) -> float | dict
```

```python
pyvar.market_risk.expected_shortfall_contribution(
    # Expected Shortfall Contribution
    **params
) -> float | dict
```


## Stress Testing

```python
pyvar.market_risk.historical_scenario_replay(
    # Historical Scenario Replay
    **params
) -> float | dict
```

```python
pyvar.market_risk.hypothetical_multi_factor_scenario(
    # Hypothetical Multi-Factor Scenario
    **params
) -> float | dict
```

```python
pyvar.market_risk.reverse_stress_testing(
    # Reverse Stress Testing
    **params
) -> float | dict
```

```python
pyvar.market_risk.sensitivity_stress_profile(
    # Sensitivity Stress Profile
    **params
) -> float | dict
```

```python
pyvar.market_risk.sector_stress_scenario(
    # Sector Stress Scenario
    **params
) -> float | dict
```

```python
pyvar.market_risk.macro_scenario_generator(
    # Macro Scenario Generator
    **params
) -> float | dict
```

```python
pyvar.market_risk.contagion_stress_scenario(
    # Contagion Stress Scenario
    **params
) -> float | dict
```

```python
pyvar.market_risk.portfolio_delta_aggregated(
    # Portfolio Delta (Aggregated)
    **params
) -> float | dict
```


## Greeks & Sensitivities

```python
pyvar.market_risk.gamma_and_cross_gamma_matrix(
    # Gamma and Cross-Gamma Matrix
    **params
) -> float | dict
```

```python
pyvar.market_risk.vega_surface_bucketed(
    # Vega Surface (Bucketed)
    **params
) -> float | dict
```

```python
pyvar.market_risk.dv01_pv01_tenor_bucketed(
    # DV01 / PV01 (Tenor Bucketed)
    **params
) -> float | dict
```

```python
pyvar.market_risk.cs01_credit_spread_dv01(
    # CS01 Credit Spread DV01
    **params
) -> float | dict
```

```python
pyvar.market_risk.rho_interest_rate_sensitivity(
    # Rho (Interest Rate Sensitivity)
    **params
) -> float | dict
```

```python
pyvar.market_risk.theta_time_decay(
    # Theta (Time Decay)
    **params
) -> float | dict
```

```python
pyvar.market_risk.charm_delta_decay(
    # Charm (Delta Decay)
    **params
) -> float | dict
```

```python
pyvar.market_risk.volga_vega_convexity(
    # Volga (Vega Convexity)
    **params
) -> float | dict
```

```python
pyvar.market_risk.vanna_delta_vega_cross(
    # Vanna (Delta-Vega Cross)
    **params
) -> float | dict
```

```python
pyvar.market_risk.greeks_based_p_l_explain(
    # Greeks-based P&L Explain
    **params
) -> float | dict
```


## P&L Attribution

```python
pyvar.market_risk.p_l_attribution_test_frtb_pat(
    # P&L Attribution Test (FRTB PAT)
    **params
) -> float | dict
```

```python
pyvar.market_risk.theta_carry_attribution(
    # Theta / Carry Attribution
    **params
) -> float | dict
```

```python
pyvar.market_risk.gamma_p_l_attribution(
    # Gamma P&L Attribution
    **params
) -> float | dict
```

```python
pyvar.market_risk.vega_p_l_attribution(
    # Vega P&L Attribution
    **params
) -> float | dict
```

```python
pyvar.market_risk.fx_p_l_attribution(
    # FX P&L Attribution
    **params
) -> float | dict
```

```python
pyvar.market_risk.rates_p_l_attribution(
    # Rates P&L Attribution
    **params
) -> float | dict
```

```python
pyvar.market_risk.credit_p_l_attribution(
    # Credit P&L Attribution
    **params
) -> float | dict
```

```python
pyvar.market_risk.residual_p_l_unexplained(
    # Residual P&L (Unexplained)
    **params
) -> float | dict
```


## Backtesting

```python
pyvar.market_risk.traffic_light_backtesting_basel(
    # Traffic Light Backtesting (Basel)
    **params
) -> float | dict
```

```python
pyvar.market_risk.kupiec_proportion_of_failures_test(
    # Kupiec Proportion of Failures Test
    **params
) -> float | dict
```

```python
pyvar.market_risk.christoffersen_independence_test(
    # Christoffersen Independence Test
    **params
) -> float | dict
```

```python
pyvar.market_risk.combined_backtesting_kupiec_christoffersen(
    # Combined Backtesting (Kupiec + Christoffersen)
    **params
) -> float | dict
```

```python
pyvar.market_risk.basel_capital_add_on_multiplier(
    # Basel Capital Add-On Multiplier
    **params
) -> float | dict
```

```python
pyvar.market_risk.rolling_var_backtest_250_day(
    # Rolling VaR Backtest (250-day)
    **params
) -> float | dict
```

```python
pyvar.market_risk.var_breach_cluster_analysis(
    # VaR Breach Cluster Analysis
    **params
) -> float | dict
```

```python
pyvar.market_risk.volatility_surface_implied_vol(
    # Volatility Surface (Implied Vol)
    **params
) -> float | dict
```


## Volatility & Correlation

```python
pyvar.market_risk.garch_1_1_volatility_forecast(
    # GARCH(1,1) Volatility Forecast
    **params
) -> float | dict
```

```python
pyvar.market_risk.egarch_volatility_model(
    # EGARCH Volatility Model
    **params
) -> float | dict
```

```python
pyvar.market_risk.gjr_garch_asymmetric_model(
    # GJR-GARCH Asymmetric Model
    **params
) -> float | dict
```

```python
pyvar.market_risk.realised_volatility_rv(
    # Realised Volatility (RV)
    **params
) -> float | dict
```

```python
pyvar.market_risk.correlation_matrix_historical(
    # Correlation Matrix (Historical)
    **params
) -> float | dict
```

```python
pyvar.market_risk.dcc_garch_dynamic_correlation(
    # DCC-GARCH Dynamic Correlation
    **params
) -> float | dict
```

```python
pyvar.market_risk.risk_factor_pca_decomposition(
    # Risk Factor PCA Decomposition
    **params
) -> float | dict
```

```python
pyvar.market_risk.frtb_sa_sensitivity_based_method(
    # FRTB SA Sensitivity-Based Method
    **params
) -> float | dict
```

```python
pyvar.market_risk.frtb_sa_default_risk_charge(
    # FRTB SA Default Risk Charge
    **params
) -> float | dict
```


## FRTB Capital

```python
pyvar.market_risk.frtb_sa_residual_risk_add_on(
    # FRTB SA Residual Risk Add-On
    **params
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_expected_shortfall(
    # FRTB IMA Expected Shortfall
    **params
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_stressed_period_finder(
    # FRTB IMA Stressed Period Finder
    **params
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_non_modellable_risk_factors(
    # FRTB IMA Non-Modellable Risk Factors
    **params
) -> float | dict
```

```python
pyvar.market_risk.frtb_ima_aggregate_capital_charge(
    # FRTB IMA Aggregate Capital Charge
    **params
) -> float | dict
```

```python
pyvar.market_risk.extreme_value_theory_evt_var(
    # Extreme Value Theory (EVT) VaR
    **params
) -> float | dict
```

```python
pyvar.market_risk.spectral_risk_measure(
    # Spectral Risk Measure
    **params
) -> float | dict
```


## Naming convention
- All functions live under `pyvar.market_risk.*`
- Return dict for multi-output metrics (the large majority — decompositions,
  fan charts, backtest reports); a handful of the pure P&L-attribution helpers
  return a single-key dict too (`engine/pnl_attribution.py` never returns a bare
  float). Do not assume every function accepts `returns` + `confidence` — Greeks
  (`engine/greeks.py`), stress scenarios (`engine/stress.py`) and most of
  Volatility & Correlation (`engine/volatility.py`) take instrument- or
  exposure-shaped inputs (spot/strike/vol/tau, exposure vectors, weights +
  covariance) instead, which is why the signatures above are shown as generic
  `**params` rather than a fixed `(returns, confidence)` shape — verified
  per-function against `engine/var_models.py`, `engine/expected_shortfall.py`,
  `engine/backtesting.py`, `engine/pnl_attribution.py`, `engine/greeks.py`,
  `engine/stress.py`, `engine/volatility.py` and `engine/frtb.py`.
- Confidence level: enforced range is **[0.90, 0.9999]** — `schemas/var.py`'s
  `confidence_must_be_standard` validator rejects anything outside it. Standard
  values (CLAUDE.md §4.1): **0.99** for 1-day VaR (Basel III) — the default on
  every VaR-family function in `engine/var_models.py`; **0.975** for 10-day ES
  (FRTB IMA) — the default on every function in `engine/expected_shortfall.py`;
  **0.95** acceptable for internal limit monitoring only. (0.999 is used
  elsewhere in pyvar — Credit VaR, AMA OpRisk capital — but is not a
  market-risk convention; don't carry it over here.)
- Horizon in trading days. `run_monte_carlo_var` and the VaR-family functions
  default to 1 day; `var_fan_chart` defaults to a 10-day projection horizon
  (it's built to show how the band widens with holding period, not a 1-day
  point estimate) — check the individual default before assuming 1.
- Monte Carlo simulation count is config-driven, not a fixed literal, and
  differs by call site: the `/var/compute` API request defaults to
  `cfg.default_n_simulations = 10_000` (capped per account tier up to
  `cfg.max_n_simulations = 500_000`, `config.py`), while calling
  `run_monte_carlo_var` / `monte_carlo_expected_shortfall` directly in Python
  defaults to **100,000** paths if `n_simulations` is omitted.

## Regulatory constants — verbatim from CLAUDE.md §4, do not paraphrase
These are Basel-Committee-set thresholds; the engine treats them as constants,
never as configurable parameters (`engine/backtesting.py`, `engine/pnl_attribution.py`).
- **Expected Shortfall** is the arithmetic **mean** of losses at/beyond the VaR
  index — never the median or the max (`engine/expected_shortfall.py::_tail_mean`,
  `engine/metrics.py::compute_cvar`). `cvar_decomposition_euler` /
  `expected_shortfall_contribution` are Euler-additive: components sum exactly
  to total ES.
- **Basel traffic-light backtest**: window is **exactly 250** trading days
  (`BASEL_BACKTEST_WINDOW = 250` in `engine/backtesting.py`). Breach zones:
  green `< 5`, yellow `5-9`, red `>= 10`. Capital add-on multiplier: `3.0`
  green, BCBS graduated schedule `3.40/3.50/3.65/3.75/3.85` for 5-9 breaches
  respectively, `4.0` red.
- **Kupiec / Christoffersen**: both are chi-squared likelihood-ratio tests
  rejected at the **95%** critical value (`stats.chi2.ppf(0.95, df=1)`, `df=2`
  for the combined conditional-coverage test) — this significance level is not
  a function parameter.
- **FRTB P&L Attribution Test** (`pnl_attribution_test_frtb_pat`): jointly
  evaluates Spearman rank correlation between RTPL and HPL and the ratio
  `std(RTPL)/std(HPL)`. Green requires `|corr| >= 0.80` **and**
  `0.8 <= ratio <= 1.2`; amber requires `|corr| >= 0.70` **and**
  `0.6 <= ratio <= 1.5`; anything below amber is red (IMA disqualification).
  These thresholds are hard-coded, not kwargs.

## Variance reduction — verified project history (task #15)
- **Antithetic variates (Phase 1)** were added to the core Monte Carlo VaR/ES
  kernel only: `engine/montecarlo.py::run_monte_carlo_var` takes an
  `antithetic: bool = False` flag. When `True`, `_draw_random_shocks` draws
  `n_simulations // 2` independent `N(0,1)` shocks and mirrors each as `(z, -z)`
  (with one extra unmirrored draw if `n_simulations` is odd, so the output
  shape is unchanged). Opt-in and off by default so existing callers/results
  are unaffected. As noted above, this flag is Python-engine-only — neither
  `/var/compute` nor `/api/v1/market-risk/*` exposes it today.
- **Sobol quasi-Monte Carlo (Phase 2) was NOT added to any market-risk VaR/ES
  kernel.** It exists in `engine/deriv_options_exotic.py` (randomized scrambled-Sobol
  replicates, `qmc: bool` opt-in on the exotic-option MC pricers) — a
  **derivatives-pricing** kernel, a different skill/domain entirely. Don't
  assume `monte_carlo_var_parametric_normal` or `monte_carlo_expected_shortfall`
  support a `qmc` argument; they don't (`engine/var_models.py` and
  `engine/expected_shortfall.py` have no Sobol/QMC code path — verified by grep).

## Citations & numerical validation
- Market-risk engine functions are cross-checked in
  `tests/validation/test_market_ref.py` against an *external* reference computed
  independently inside the test (closed-form formulas, scipy cross-validation,
  hard-coded Basel/FRTB thresholds, or an independent hand-calculation) —
  **never against the function's own output.** Tolerance is 0.1% relative for
  VaR/ES/simulation-class figures and **zero** tolerance for regulatory zone
  boundaries and the 250-day rule.
- A citation-cleanup pass (CHANGELOG "Changed") removed misleading or
  self-authored regulatory citations from engine docstrings project-wide and
  documented genuine no-published-source gaps instead of citing sources that
  don't actually support the implementation. `test_market_ref.py` itself
  records the remaining honest limitation: Cornish-Fisher, Kupiec, EGARCH,
  GJR-GARCH, GARCH(1,1) mean-reversion, spectral risk measure, Greeks-based
  Taylor P&L, and the FRTB SBM/DRC/RRAO/liquidity-adjusted-ES/SES formulas are
  citable for *formula* provenance but BCBS publishes no end-to-end numeric
  worked example for them at these specific test inputs — don't add a fake
  "matches BCBS worked example" claim for those.

## Coverage note
`pyvar_functions.csv` (the source for the "68 functions" figure above) is a
stale P2-era snapshot. The live, generated catalogue (`portal/functions.json`,
built from the running OpenAPI schema) lists **71** market-risk routes — the
gap is largely 4 legacy `engine/metrics.py` routes (`compute_cvar`,
`compute_rolling_var`, `compute_loss_percentiles`, `compute_breaches`) that
duplicate newer, already-listed entries (`conditional_var_es`,
`rolling_var_backtest`, `expected_shortfall`/fan-chart internals,
`traffic_light_backtesting`) but are wired as separate live routes. See
`docs/p9-function-catalogue-reconciliation.md` for the full reconciliation —
treat `portal/functions.json` as canonical if the two ever disagree.

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · statsmodels >= 0.14
numba >= 0.57 · arch >= 6.0
