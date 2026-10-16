---
name: pyvar-market-risk
description: >
  Run pyvar's 71 market-risk functions on the live pyvar.com API: historical, parametric and
  filtered VaR, Expected Shortfall, stress tests, Greeks, P&L attribution, Basel backtesting
  (traffic light, Kupiec, Christoffersen), GARCH volatility and FRTB capital. Use when the
  user wants an actual VaR, ES, backtest or sensitivity number computed, not just the method
  explained. Needs a free pyvar API key; the skill explains how to get one.
version: "1.1.0"
author: "Fibtec Limited — pyvar.com"
tags: [market-risk, VaR, ES, greeks, stress-test, backtesting, FRTB, GARCH, volatility, PCA, monte-carlo]
---

# pyvar — Market Risk  (71 functions)

Market-risk calculations: VaR, Expected Shortfall, stress testing, Greeks, P&L attribution, backtesting, volatility and FRTB capital. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs a pyvar API key. Don't substitute your own numpy/scipy code and present the result
as pyvar output: these are regulatory-grade functions and the user wants pyvar's own numbers.

1. **Find the key.** Look for `PYVAR_API_KEY` in the environment. If the pyvar MCP server is
   connected, its tools (`call_pyvar_function`, `list_pyvar_functions`) already carry the key.
2. **No key? Say so, and walk the user through getting one** (free, about a minute): open
   https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when it is shown) or enter an email and
   click the link we send (single use; the same form signs returning users in). The dashboard
   opens with a first API key already created: a string starting `pyvar_`, shown once. Ask the
   user to copy it and set `PYVAR_API_KEY`. A key lasts a year and can be revoked or replaced on
   the dashboard at any time. On a `401 Invalid, revoked or expired API key`, send the user back
   to the dashboard to create a new one.
3. **Call the function** with the request body below (every example in this skill is a real,
   tested request). Use whichever of these is available:
   - Python: `pip install pyvar-client`, then
     `Client(api_key=os.environ["PYVAR_API_KEY"]).market_risk.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/market-risk/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="market-risk", function_name="<function>", params=body)`.
   If you cannot run code or reach the network (for example a sandbox with no internet), give the
   user the exact `curl` command or Python snippet to run themselves instead of guessing a result.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Monte Carlo VaR is a separate, asynchronous job

`monte_carlo_var_parametric_normal` is not one of the functions below: Monte Carlo VaR runs as a
queued job. `POST /api/v1/var/compute` returns `202` with a `task_id`; poll
`GET /api/v1/var/result/{task_id}` until `status` is `success`. The Python client does both for
you: `client.var.compute(portfolio_value=..., returns=[...], n_simulations=10000)` blocks and returns
the finished result. Simulation caps per tier are 10,000 (free), 100,000 (pro) and 500,000
(enterprise); above your cap the call fails with `403`. The job counts against the same daily
quota as every other call. Antithetic sampling is not exposed through the API.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. VaR and Expected Shortfall on a 10m portfolio

Two years of daily log-returns in; the Basel one-day 99% VaR and the FRTB 97.5% Expected Shortfall out, as a fraction and in money. ES is the mean of the losses beyond the VaR threshold, so it is never smaller than VaR.

`POST /api/v1/market-risk/historical_simulation_var`

```json
{
  "returns": [ /* your 500 daily log-returns */ ],
  "portfolio_value": 10000000,
  "confidence_level": 0.99
}
```

Returns: `var_pct`, `var_abs`, `cvar_pct`, `cvar_abs`, `confidence_level`, `n_obs`.

`POST /api/v1/market-risk/historical_expected_shortfall`

```json
{
  "returns": [ /* your 500 daily log-returns */ ],
  "portfolio_value": 10000000,
  "confidence_level": 0.975
}
```

Returns: `es_pct`, `es_abs`, `var_pct`, `n_tail`, `confidence_level`.

### 2. Backtest result: capital multiplier and Kupiec test

Six VaR breaches in 250 trading days. The first call gives the Basel traffic-light capital multiplier; the second tests whether 6 breaches is consistent with a 99% VaR model.

`POST /api/v1/market-risk/basel_capital_addon_multiplier`

```json
{
  "n_breaches": 6
}
```

Returns: `multiplier`, `zone`, `n_breaches`.

`POST /api/v1/market-risk/kupiec_pof_test`

```json
{
  "n_breaches": 6,
  "n_observations": 250,
  "confidence_level": 0.99
}
```

Returns: `lr_pof`, `p_value`, `critical_value`, `reject`.

## Functions (71)

Every function is `POST /api/v1/market-risk/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in [references/functions.md](references/functions.md): read the entry before calling a function you have not used yet.

### VaR Models

- `historical_simulation_var(returns, portfolio_value, confidence_level=0.99)`: Non-parametric Historical Simulation VaR.
- `filtered_historical_simulation_var(returns, portfolio_value, confidence_level=0.99, lambda_decay=0.94)`: Filtered Historical Simulation VaR (Barone-Adesi & Giannopoulos).
- `parametric_delta_normal_var(weights, cov_matrix, portfolio_value, confidence_level=0.99, horizon_days=1)`: Variance-covariance (delta-normal) VaR.
- `cornish_fisher_var(returns, portfolio_value, confidence_level=0.99, skewness=None, excess_kurtosis=None)`: Cornish-Fisher (modified) VaR.
- `component_var(weights, cov_matrix, portfolio_value, confidence_level=0.99)`: Component VaR via Euler allocation.
- `marginal_var(weights, cov_matrix, confidence_level=0.99)`: Marginal VaR — sensitivity of portfolio VaR to each position weight.
- `incremental_var(weights, cov_matrix, position_index, portfolio_value, confidence_level=0.99)`: Incremental VaR of a single position.
- `var_by_risk_factor(factor_exposures, factor_cov, portfolio_value, confidence_level=0.99, factor_names=None)`: Decompose VaR across systematic risk factors (Euler allocation).
- `var_fan_chart(returns, portfolio_value, confidence_levels=[0.9, 0.95, 0.99], horizon_days=10)`: VaR fan chart — parametric VaR bands across confidence levels and horizons.
- `compute_loss_percentiles(sorted_losses, percentiles=None)`: Returns a dict of {percentile_label: loss_value} for fan chart display.
- `extreme_value_theory_var(returns, threshold_quantile=0.95, confidence_level=0.99)`: Extreme Value Theory VaR via Peaks-Over-Threshold (Generalised Pareto).

### Expected Shortfall

- `conditional_var_es(returns, portfolio_value, confidence_level=0.975)`: Conditional VaR (Expected Shortfall) from a return series.
- `compute_cvar(sorted_losses, confidence_level)`: Conditional VaR (Expected Shortfall) — mean of losses beyond VaR threshold.
- `historical_expected_shortfall(returns, portfolio_value, confidence_level=0.975)`: Non-parametric historical Expected Shortfall.
- `monte_carlo_expected_shortfall(returns, portfolio_value, confidence_level=0.975, n_simulations=100000, horizon_days=1, seed=42)`: Monte Carlo Expected Shortfall.
- `cvar_decomposition_euler(weights, cov_matrix, portfolio_value, confidence_level=0.975)`: Euler decomposition of Gaussian Expected Shortfall.
- `stressed_expected_shortfall(returns, stress_start, stress_end, portfolio_value, confidence_level=0.975)`: Stressed Expected Shortfall (FRTB IMA).
- `liquidity_adjusted_es(es_base, partial_es, liquidity_horizons, base_horizon=10.0)`: Liquidity-adjusted Expected Shortfall (FRTB IMA, MAR33.12).
- `es_at_multiple_confidence_levels(returns, portfolio_value, confidence_levels=[0.95, 0.975, 0.99])`: Expected Shortfall evaluated at several confidence levels at once.
- `expected_shortfall_contribution(asset_returns, weights, portfolio_value, confidence_level=0.975)`: Per-asset ES contribution by conditional expectation in the tail.
- `spectral_risk_measure(returns, risk_aversion=25.0)`: Spectral risk measure with an exponential risk-aversion spectrum.

### Stress Testing

- `historical_scenario_replay(exposures, historical_factor_returns)`: Replay historical factor moves against the current portfolio.
- `hypothetical_multi_factor_scenario(exposures, shocks)`: P&L under a single hypothetical multi-factor shock.
- `reverse_stress_testing(exposures, factor_cov, target_loss)`: Reverse stress test — find the most plausible scenario causing a target loss.
- `sensitivity_stress_profile(exposures, factor_index, shock_grid)`: One-factor sensitivity stress profile.
- `sector_stress_scenario(sector_exposures, sector_shocks, sector_names=None)`: Sector-level stress scenario.
- `macro_scenario_generator(factor_cov, n_scenarios=10000, seed=42)`: Generate correlated macro factor scenarios via the Cholesky factor.
- `contagion_stress_scenario(initial_shock, contagion_matrix, rounds=3)`: Propagate an initial shock through a contagion (spillover) network.

### Greeks & Sensitivities

- `gamma_cross_gamma_matrix(own_gammas, cross_gammas=None)`: Assemble the portfolio gamma / cross-gamma matrix.
- `vega_surface_bucketed(vegas, expiry_buckets, strike_buckets, n_expiry, n_strike)`: Aggregate option vegas onto a bucketed (expiry × strike) surface.
- `dv01_pv01_bucketed(cashflows, times, flat_yield, bucket_indices, n_buckets)`: Tenor-bucketed DV01 / PV01 of a fixed cashflow stream.
- `cs01_credit_spread(cashflows, times, risk_free_rate, credit_spread)`: CS01 — sensitivity of a risky cashflow stream to a +1bp credit spread move.
- `rho_interest_rate(spot, strike, rate, sigma, tau, option_type='call', div_yield=0.0)`: Black-Scholes Rho — option value sensitivity to the interest rate.
- `theta_time_decay(spot, strike, rate, sigma, tau, option_type='call', div_yield=0.0)`: Black-Scholes Theta — calendar time decay (∂V/∂calendar = −∂V/∂τ), per year.
- `charm_delta_decay(spot, strike, rate, sigma, tau, option_type='call', div_yield=0.0)`: Charm — sensitivity of delta to time to maturity (∂Δ/∂τ).
- `volga_vega_convexity(spot, strike, rate, sigma, tau, div_yield=0.0)`: Volga (vomma) — convexity of value in volatility (∂²V/∂σ² = ∂vega/∂σ).
- `vanna_delta_vega_cross(spot, strike, rate, sigma, tau, div_yield=0.0)`: Vanna — cross sensitivity ∂vega/∂S = ∂Δ/∂σ.
- `portfolio_delta_aggregated(deltas, quantities, spot_prices=None)`: Aggregate per-position deltas into a net portfolio delta.

### P&L Attribution

- `pnl_attribution_test_frtb_pat(risk_theoretical_pnl, hypothetical_pnl)`: FRTB P&L Attribution Test (PAT) — Spearman correlation and ratio test.
- `theta_carry_attribution(theta, time_step, funding_cost=0.0)`: Theta / carry attribution.
- `gamma_pnl_attribution(gamma, spot_move)`: Gamma (convexity) P&L component: ``½ · Γ · dS²``.
- `vega_pnl_attribution(vega, vol_move)`: Vega P&L component: ``ν · dσ``.
- `fx_pnl_attribution(fx_deltas, fx_moves, currency_names=None)`: FX P&L attribution across currency pairs.
- `rates_pnl_attribution(key_rate_sensitivities, yield_moves_bp, tenor_names=None)`: Interest-rate P&L attribution by key-rate tenor.
- `credit_pnl_attribution(cs01_sensitivities, spread_moves_bp, name_labels=None)`: Credit P&L attribution by issuer / curve.
- `residual_pnl_unexplained(actual_pnl, explained_components)`: Unexplained (residual) P&L.
- `greeks_based_pnl_explain(delta, gamma, vega, theta, rho, spot_move, vol_move, time_step, rate_move, actual_pnl)`: Second-order Greeks P&L explain.

### Backtesting

- `traffic_light_backtesting(actual_returns, var_estimates)`: Basel traffic-light backtest over the 250-day window.
- `compute_breaches(actual_returns, var_estimates)`: Backtesting: count days where actual loss exceeded VaR estimate.
- `kupiec_pof_test(n_breaches, n_observations, confidence_level=0.99)`: Kupiec Proportion-of-Failures (POF) unconditional coverage test.
- `christoffersen_independence_test(breaches)`: Christoffersen independence (clustering) test.
- `combined_backtesting(breaches, confidence_level=0.99)`: Combined (conditional coverage) backtest: Kupiec + Christoffersen.
- `basel_capital_addon_multiplier(n_breaches)`: Basel capital add-on multiplier from the backtest breach count.
- `rolling_var_backtest(returns, window=250, confidence_level=0.99)`: Rolling-window VaR backtest over the Basel 250-day window.
- `compute_rolling_var(returns, window=250, confidence_level=0.99)`: Parametric (Gaussian) rolling VaR using a fixed-length trailing window.
- `var_breach_cluster_analysis(breaches)`: Analyse the clustering of VaR breaches.

### Volatility & Correlation

- `garch_11_volatility_forecast(returns, alpha=0.1, beta=0.85, omega=None, horizon=10)`: GARCH(1,1) conditional-volatility filter and multi-step forecast.
- `egarch_volatility_model(returns, omega=-0.1, alpha=0.1, gamma=-0.05, beta=0.95)`: EGARCH(1,1) asymmetric volatility model (Nelson 1991).
- `gjr_garch_asymmetric_model(returns, alpha=0.03, gamma=0.08, beta=0.88, omega=None)`: GJR-GARCH(1,1) asymmetric volatility model (Glosten-Jagannathan-Runkle).
- `realised_volatility(returns, annualisation_factor=252)`: Realised volatility from a block of (typically high-frequency) returns.
- `correlation_matrix_historical(returns_matrix)`: Historical (Pearson) correlation matrix of asset returns.
- `dcc_garch_dynamic_correlation(returns_matrix, a=0.02, b=0.95)`: DCC-GARCH dynamic conditional correlation (Engle 2002), terminal R_T.
- `risk_factor_pca_decomposition(returns_matrix, n_components=None)`: Principal-component decomposition of the risk-factor covariance.
- `volatility_surface_implied_vol(market_prices, strikes, expiries, spot, rate, option_type='call')`: Back out the implied-volatility surface from market option prices.

### FRTB Capital

- `frtb_sa_residual_risk_addon(notionals, rrao_weights)`: FRTB SA Residual Risk Add-On (RRAO).
- `frtb_ima_expected_shortfall(returns, confidence_level=0.975)`: FRTB IMA Expected Shortfall (the regulatory ES at 97.5%).
- `frtb_ima_stressed_period_finder(returns, window=250, confidence_level=0.975)`: Locate the FRTB IMA stressed period — the worst 250-day ES window.
- `frtb_ima_non_modellable_risk_factors(individual_ses, rho=0.0)`: FRTB IMA non-modellable risk factor (NMRF) capital — aggregate SES.
- `frtb_ima_aggregate_capital_charge(imcc, ses, default_risk_charge=0.0)`: FRTB IMA aggregate capital charge.
- `frtb_sa_sensitivity_based_method(bucket_weighted_sensitivities, intra_bucket_corr, inter_bucket_corr)`: FRTB SA Sensitivities-Based Method (delta) risk charge.
- `frtb_sa_default_risk_charge(jtd_long, jtd_short, risk_weights)`: FRTB SA Default Risk Charge (DRC) with the hedge-benefit ratio.

## Naming convention
- Return dict for multi-output metrics (the large majority — decompositions,
  fan charts, backtest reports); a handful of the pure P&L-attribution helpers
  return a single-key dict too (`engine/pnl_attribution.py` never returns a bare
  float). Do not assume every function accepts `returns` + `confidence` — Greeks
  (`engine/greeks.py`), stress scenarios (`engine/stress.py`) and most of
  Volatility & Correlation (`engine/volatility.py`) take instrument- or
  exposure-shaped inputs (spot/strike/vol/tau, exposure vectors, weights +
  covariance) instead, so check each function's own parameter list above — verified
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
## For contributors: dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · statsmodels >= 0.14
numba >= 0.57 · arch >= 6.0

## For contributors: architecture context
- **Compute**: NumPy/Numba (MC loops, JIT), SciPy/statsmodels (GARCH, PCA)
- **Queue**: Celery + Redis (async VaR jobs)
- **Storage**: Redis cache (intraday VaR), PostgreSQL (backtest results)
- **API**: FastAPI endpoint `/api/v1/market-risk/{function}`

---
