# pyvar plugin examples

Two worked examples for each of pyvar's Claude Code plugins (the eight domain skills, the five architecture skills and the `pyvar-mcp` server) and for the `pyvar-client` and `pyvar-jupyter` packages, then one call run through every surface. Every request, response and number below was produced by running the real pyvar code, and the prose is generated from those results by `scripts/generate_plugin_examples.py`.

## How these were produced

- **Domain plugins** POST to the real FastAPI app (`create_app()` behind an in-process HTTP transport), authenticated with a JWT, exactly as the endpoints are called in production.
- **Architecture plugins** call the real modules: the gateway routes and middleware, `engine.montecarlo`, `ingestion.loader`, `storage.s3` and `observability.setup`. The Celery queue and the audit database are replaced by stand-ins where a request would otherwise need them, and AWS is mocked with moto.
- **pyvar-mcp** is the real MCP server, started over stdio and pointed at a local pyvar API.
- **pyvar-client** and **pyvar-jupyter** are the real packages, run against a local pyvar API (a real uvicorn process). A session token stands in for an API key: both are bearer credentials and the client code path is identical.
- All inputs are synthetic (`ingestion.fixtures.generate_gbm_returns`), with the seed shown next to each call. No real market data and no real AWS services are used.

To regenerate this file: `python scripts/generate_plugin_examples.py`.

## pyvar-market-risk

*VaR, Expected Shortfall, backtesting*

### Example 1: VaR and Expected Shortfall on a 10m portfolio

Two years of daily returns go in. Out come the Basel one-day 99% VaR and the FRTB 97.5% Expected Shortfall, both in percentage and in money.

**historical_simulation_var**

```text
POST /api/v1/market-risk/historical_simulation_var
{
  "returns": <500 daily log-returns: generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7)>,
  "portfolio_value": 10000000,
  "confidence_level": 0.99
}
```

Result (HTTP 200):

```json
{
  "var_pct": 0.02380457,
  "var_abs": 238045.72,
  "cvar_pct": 0.02908383,
  "cvar_abs": 290838.34,
  "confidence_level": 0.99,
  "n_obs": 500
}
```

**historical_expected_shortfall**

```text
POST /api/v1/market-risk/historical_expected_shortfall
{
  "returns": <500 daily log-returns: generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7)>,
  "portfolio_value": 10000000,
  "confidence_level": 0.975
}
```

Result (HTTP 200):

```json
{
  "es_pct": 0.02454672,
  "es_abs": 245467.16,
  "var_pct": 0.02051345,
  "n_tail": 13,
  "confidence_level": 0.975
}
```

**What to notice.** The 99% VaR is 2.38% of the book, 238,046 on 10,000,000; the CVaR at the same level is 290,838, always at or above the VaR. The Expected Shortfall endpoint works at the FRTB level (97.5%): it averages the 13 worst days of the 500 observed and returns 245,467. Expected Shortfall is the mean of the losses beyond the threshold, not a quantile, which is why the response also reports how many observations sit in the tail.

### Example 2: Backtesting chain: traffic light, capital add-on, Kupiec test

A 99% VaR is estimated on one 250-day window and then judged against the next 250 days, drawn from the same distribution. Three calls take the breach count to a Basel zone, a capital multiplier and a statistical verdict.

**historical_simulation_var**

```text
POST /api/v1/market-risk/historical_simulation_var
{
  "returns": <250 daily log-returns: generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=11)>,
  "portfolio_value": 1000000,
  "confidence_level": 0.99
}
```

Result (HTTP 200):

```json
{
  "var_pct": 0.01508946,
  "var_abs": 15089.46,
  "cvar_pct": 0.016711,
  "cvar_abs": 16711.0,
  "confidence_level": 0.99,
  "n_obs": 250
}
```

**traffic_light_backtesting**

```text
POST /api/v1/market-risk/traffic_light_backtesting
{
  "actual_returns": <250 daily log-returns: generate_gbm_returns(250, mu=0.0003, sigma=0.008, seed=12)>,
  "var_estimates": <250 copies of 0.01508946>
}
```

Result (HTTP 200):

```json
{
  "n_breaches": 7,
  "n_observations": 250,
  "basel_zone": "yellow",
  "expected_window": 250
}
```

**basel_capital_addon_multiplier**

```text
POST /api/v1/market-risk/basel_capital_addon_multiplier
{
  "n_breaches": 7
}
```

Result (HTTP 200):

```json
{
  "multiplier": 3.65,
  "zone": "yellow",
  "n_breaches": 7
}
```

**kupiec_pof_test**

```text
POST /api/v1/market-risk/kupiec_pof_test
{
  "n_breaches": 7,
  "n_observations": 250,
  "confidence_level": 0.99
}
```

Result (HTTP 200):

```json
{
  "lr_pof": 5.49699,
  "p_value": 0.019049,
  "critical_value": 3.841459,
  "reject": true
}
```

**What to notice.** A 99% VaR should be breached about 2.5 times in 250 days. Here it is breached 7 times, which the Basel traffic light places in the yellow zone (green below 5, yellow 5-9, red 10 or more) and which carries a capital multiplier of 3.65. The Kupiec proportion-of-failures test agrees: a likelihood ratio of 5.50 against the 95% chi-squared critical value of 3.84 (p = 0.019) rejects the model. Both windows share one distribution, so the result also shows how noisy a 99% quantile is when estimated from 250 observations.

## pyvar-credit-risk

*PD/LGD/EAD, credit VaR, scoring*

### Example 1: Expected loss and Vasicek credit VaR on a 50m exposure

Expected loss is the price of the risk; the Vasicek single-factor model gives the 99.9% loss that capital has to absorb on top of it.

**expected_loss_el_computation**

```text
POST /api/v1/credit-risk/expected_loss_el_computation
{
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 50000000
}
```

Result (HTTP 200):

```json
{
  "el": 450000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 50000000.0
}
```

**credit_var_analytical_vasicek**

```text
POST /api/v1/credit-risk/credit_var_analytical_vasicek
{
  "pd": 0.02,
  "lgd": 0.45,
  "ead_total": 50000000,
  "asset_correlation": 0.15,
  "confidence_level": 0.999
}
```

Result (HTTP 200):

```json
{
  "var": 3967401.130789,
  "el": 450000.0,
  "ul": 3517401.130789,
  "loss_rate_q": 0.0793480226,
  "confidence_level": 0.999
}
```

**What to notice.** Expected loss is PD x LGD x EAD = 0.02 x 0.45 x 50,000,000 = 450,000, 0.9% of the exposure. The Vasicek 99.9% credit VaR is 3,967,401; subtracting the expected loss leaves an unexpected loss of 3,517,401, which is the part economic capital has to cover. The stressed loss rate of 7.93% is the conditional default rate at 99.9% multiplied by the LGD.

### Example 2: Altman Z-score across three borrowers

One endpoint scores three balance sheets and places each in an Altman zone.

**altman_z_score_credit_scoring**

```text
POST /api/v1/credit-risk/altman_z_score_credit_scoring
{
  "working_capital": 2000000,
  "retained_earnings": 3400000,
  "ebit": 1500000,
  "market_value_equity": 8000000,
  "sales": 6500000,
  "total_assets": 10000000,
  "total_liabilities": 4000000
}
```

Result (HTTP 200):

```json
{
  "z_score": 3.061,
  "zone": "safe",
  "x1": 0.2,
  "x2": 0.34,
  "x3": 0.15,
  "x4": 2.0,
  "x5": 0.65
}
```

**altman_z_score_credit_scoring**

```text
POST /api/v1/credit-risk/altman_z_score_credit_scoring
{
  "working_capital": 1200000,
  "retained_earnings": 3400000,
  "ebit": 900000,
  "market_value_equity": 8000000,
  "sales": 5500000,
  "total_assets": 10000000,
  "total_liabilities": 4000000
}
```

Result (HTTP 200):

```json
{
  "z_score": 2.667,
  "zone": "grey",
  "x1": 0.12,
  "x2": 0.34,
  "x3": 0.09,
  "x4": 2.0,
  "x5": 0.55
}
```

**altman_z_score_credit_scoring**

```text
POST /api/v1/credit-risk/altman_z_score_credit_scoring
{
  "working_capital": -300000,
  "retained_earnings": -900000,
  "ebit": -150000,
  "market_value_equity": 600000,
  "sales": 2800000,
  "total_assets": 6000000,
  "total_liabilities": 5500000
}
```

Result (HTTP 200):

```json
{
  "z_score": 0.179621,
  "zone": "distress",
  "x1": -0.05,
  "x2": -0.15,
  "x3": -0.025,
  "x4": 0.109091,
  "x5": 0.466667
}
```

**What to notice.** The same call returns a safe verdict (Z = 3.061), a grey verdict (Z = 2.667) and a distress verdict (Z = 0.179621). The response includes the five ratios x1 to x5, so the model is auditable: the distressed borrower has negative working capital, retained earnings and EBIT, and the Z-score of the middle borrower checks by hand as 1.2 x 0.12 + 1.4 x 0.34 + 3.3 x 0.09 + 0.6 x 2.0 + 1.0 x 0.55 = 2.667.

## pyvar-liquidity-risk

*LCR, NSFR, survival horizon*

### Example 1: LCR and NSFR against the 100% minimum

The two Basel III liquidity ratios for one balance sheet.

**liquidity_coverage_ratio_lcr**

```text
POST /api/v1/liquidity/liquidity_coverage_ratio_lcr
{
  "hqla": 120000000.0,
  "gross_outflows": 150000000.0,
  "gross_inflows": 40000000.0
}
```

Result (HTTP 200):

```json
{
  "lcr": 1.090909,
  "net_outflows": 110000000.0,
  "capped_inflows": 40000000.0,
  "hqla": 120000000.0,
  "compliant": true
}
```

**net_stable_funding_ratio_nsfr**

```text
POST /api/v1/liquidity/net_stable_funding_ratio_nsfr
{
  "available_stable_funding": 410000000.0,
  "required_stable_funding": 385000000.0
}
```

Result (HTTP 200):

```json
{
  "nsfr": 1.064935,
  "asf": 410000000.0,
  "rsf": 385000000.0,
  "compliant": true
}
```

**What to notice.** With 120m of HQLA against 110m of net 30-day outflows (150m outflows less 40m inflows), the LCR is 109.1%. The NSFR is 410m of available stable funding over 385m required, 106.5%. Both flags read compliant: True and True.

### Example 2: Survival horizon under a stressed outflow path

How long a 100m HQLA buffer lasts when net outflows follow a 12-day stress path.

**survival_horizon_calculator**

```text
POST /api/v1/liquidity/survival_horizon_calculator
{
  "hqla": 100000000.0,
  "daily_net_outflows": [8000000.0, 9000000.0, 11000000.0, 12000000.0, 12000000.0, 10000000.0, 9000000.0, 8000000.0, 8000000.0, 7000000.0, 7000000.0, 6000000.0]
}
```

Result (HTTP 200):

```json
{
  "survival_days": 10,
  "terminal_buffer": -1000000.0,
  "hqla": 100000000.0
}
```

**What to notice.** Cumulative outflows reach 94m after day 10 and 101m after day 11, so the buffer survives 10 full days and is exhausted during day 11, ending at -1,000,000. The full path would drain 107m.

## pyvar-operational-risk

*SMA capital, KRIs*

### Example 1: Basel SMA capital: a clean loss history and a heavy one

The Standardised Measurement Approach is the Business Indicator Component scaled by the Internal Loss Multiplier. Two banks show how the loss history moves the answer.

**basel_standardised_measurement_sma**

```text
POST /api/v1/operational/basel_standardised_measurement_sma
{
  "business_indicator": 3000000000,
  "loss_component": 0.0,
  "use_ilm": true
}
```

Result (HTTP 200):

```json
{
  "bic": 420000000.0,
  "ilm": 0.541325,
  "sma_capital": 227356438.94
}
```

**basel_standardised_measurement_sma**

```text
POST /api/v1/operational/basel_standardised_measurement_sma
{
  "business_indicator": 12000000000,
  "loss_component": 2500000000,
  "use_ilm": true
}
```

Result (HTTP 200):

```json
{
  "bic": 1770000000.0,
  "ilm": 1.110692,
  "sma_capital": 1965924205.84
}
```

**What to notice.** For a 3bn Business Indicator the BIC is 12% of the first 1bn plus 15% of the next 2bn = 420,000,000. With no loss history the ILM is ln(e - 1) = 0.541325, so SMA capital is 227,356,439. A 12bn bank with a 2.5bn loss component has a BIC of 1,770,000,000 and an ILM of 1.110692, which lifts its capital to 1,965,924,206.

### Example 2: KRI breach detection, higher-is-worse and lower-is-worse

One function covers indicators that breach upwards (failed trades) and downwards (straight-through rate).

**kri_threshold_breach_detection**

```text
POST /api/v1/operational/kri_threshold_breach_detection
{
  "value": 14,
  "amber_threshold": 8,
  "red_threshold": 12,
  "direction": "higher_breach"
}
```

Result (HTTP 200):

```json
{
  "status": "red",
  "breached": true
}
```

**kri_threshold_breach_detection**

```text
POST /api/v1/operational/kri_threshold_breach_detection
{
  "value": 9.5,
  "amber_threshold": 8,
  "red_threshold": 12,
  "direction": "higher_breach"
}
```

Result (HTTP 200):

```json
{
  "status": "amber",
  "breached": true
}
```

**kri_threshold_breach_detection**

```text
POST /api/v1/operational/kri_threshold_breach_detection
{
  "value": 97.2,
  "amber_threshold": 98.5,
  "red_threshold": 96.0,
  "direction": "lower_breach"
}
```

Result (HTTP 200):

```json
{
  "status": "amber",
  "breached": true
}
```

**What to notice.** Fourteen failed trades against thresholds of 8 and 12 is red; 9.5 is amber. A straight-through-processing rate of 97.2% against thresholds of 98.5% and 96.0% is amber under direction lower_breach, so the same endpoint handles metrics where falling is the danger.

## pyvar-portfolio-analytics

*allocation and performance statistics*

### Example 1: Minimum-variance and risk-parity weights on one covariance matrix

Two allocation philosophies applied to the same four assets. The optimisers take a per-period (daily) covariance matrix and annualise internally.

**minimum_variance_portfolio**

```text
POST /api/v1/portfolio/minimum_variance_portfolio
{
  "cov_matrix": <4x4 daily covariance = annual covariance / 252>
}
```

Result (HTTP 200):

```json
{
  "weights": [0.0, 0.0, 0.13483145, 0.86516855],
  "return": 0.0,
  "volatility": 0.03792364,
  "sharpe": 0.0
}
```

**risk_parity_portfolio**

```text
POST /api/v1/portfolio/risk_parity_portfolio
{
  "cov_matrix": <4x4 daily covariance = annual covariance / 252>
}
```

Result (HTTP 200):

```json
{
  "weights": [0.09331586, 0.12724816, 0.22307308, 0.5563629],
  "return": 0.0,
  "volatility": 0.05364841,
  "sharpe": 0.0,
  "risk_contributions": [2.8553e-06, 2.8553e-06, 2.8553e-06, 2.8553e-06]
}
```

**What to notice.** Minimum variance puts everything in the two calmest assets (86.5% and 13.5%) for an annualised volatility of 3.79%. Risk parity spreads the weights (9.3%, 12.7%, 22.3%, 55.6%) so that every asset contributes the same risk: the four risk contributions are all 2.8553e-06. It accepts a higher volatility, 5.36%, in exchange for that diversification.

### Example 2: Sharpe, Sortino and maximum drawdown over two years

Three performance statistics on the same return series.

**sharpe_ratio**

```text
POST /api/v1/portfolio/sharpe_ratio
{
  "returns": <504 daily log-returns: generate_gbm_returns(504, mu=0.0004, sigma=0.011, seed=21)>
}
```

Result (HTTP 200):

```json
{
  "sharpe": 0.69235817,
  "sharpe_period": 0.04361447,
  "mean_excess": 0.0004467521,
  "volatility": 0.0102432097,
  "periods_per_year": 252,
  "ddof": 0
}
```

**sortino_ratio**

```text
POST /api/v1/portfolio/sortino_ratio
{
  "returns": <504 daily log-returns: generate_gbm_returns(504, mu=0.0004, sigma=0.011, seed=21)>
}
```

Result (HTTP 200):

```json
{
  "sortino": 0.98571033,
  "sortino_period": 0.06209391,
  "mean_excess": 0.0004467521,
  "downside_deviation": 0.007194781,
  "periods_per_year": 252
}
```

**maximum_drawdown**

```text
POST /api/v1/portfolio/maximum_drawdown
{
  "returns": <504 daily log-returns: generate_gbm_returns(504, mu=0.0004, sigma=0.011, seed=21)>
}
```

Result (HTTP 200):

```json
{
  "max_drawdown": 0.29564828,
  "peak_index": 88,
  "trough_index": 291,
  "n_obs": 504
}
```

**What to notice.** The annualised Sharpe ratio is 0.69. The Sortino ratio, which only penalises downside deviation, is higher at 0.99. The maximum drawdown is 29.6%, peak at observation 88 and trough at 291, so the response tells you where the loss happened as well as how large it was.

## pyvar-regulatory

*Basel III/IV capital tests*

### Example 1: CET1, combined buffer and leverage ratio for one bank

Three Basel III capital tests, each answered with the minimum, the surplus and a compliance flag.

**basel_iii_cet1_ratio**

```text
POST /api/v1/regulatory/basel_iii_cet1_ratio
{
  "cet1_capital": 5200000000.0,
  "risk_weighted_assets": 41000000000.0
}
```

Result (HTTP 200):

```json
{
  "cet1_ratio": 0.12682927,
  "minimum": 0.045,
  "surplus": 0.08182927,
  "compliant": true
}
```

**combined_buffer_requirement**

```text
POST /api/v1/regulatory/combined_buffer_requirement
{
  "capital_conservation_buffer_ratio": 0.025,
  "countercyclical_buffer_ratio": 0.01,
  "systemic_buffer_ratio": 0.01,
  "risk_weighted_assets": 41000000000.0
}
```

Result (HTTP 200):

```json
{
  "combined_buffer_ratio": 0.045,
  "combined_buffer_capital": 1845000000.0
}
```

**basel_iii_leverage_ratio**

```text
POST /api/v1/regulatory/basel_iii_leverage_ratio
{
  "tier1_capital": 6100000000.0,
  "total_exposure": 168000000000.0
}
```

Result (HTTP 200):

```json
{
  "leverage_ratio": 0.03630952,
  "minimum": 0.03,
  "surplus": 0.00630952,
  "compliant": true
}
```

**What to notice.** CET1 of 5.2bn on 41bn of RWA is 12.68%, a surplus of 8.18% over the 4.5% minimum. Stacking the 2.5% conservation, 1% countercyclical and 1% systemic buffers gives a combined buffer of 4.5%, which is 1,845,000,000 of capital. Tier 1 of 6.1bn over 168bn of exposure is a 3.63% leverage ratio against the 3% floor.

### Example 2: Basel IV output floor

Internal-model RWA cannot fall below a fixed share of the standardised RWA.

**basel_iv_output_floor**

```text
POST /api/v1/regulatory/basel_iv_output_floor
{
  "internal_model_rwa": 28000000000.0,
  "standardised_rwa": 41000000000.0
}
```

Result (HTTP 200):

```json
{
  "floored_rwa": 29725000000.0,
  "floor_rwa": 29725000000.0,
  "binding": true,
  "rwa_uplift": 1725000000.0,
  "floor_factor": 0.725
}
```

**What to notice.** The floor is 72.5% of the 41bn standardised RWA, 29,725,000,000. That is above the 28bn internal-model figure, so the floor binds (True) and RWA rises by 1,725,000,000.

## pyvar-derivatives

*options and fixed income*

### Example 1: Black-Scholes call, put and Greeks

A six-month 105-strike option on a 100 underlying, priced both ways and differentiated.

**black_scholes_european_option**

```text
POST /api/v1/derivatives/black_scholes_european_option
{
  "spot": 100,
  "strike": 105,
  "rate": 0.04,
  "sigma": 0.22,
  "tau": 0.5,
  "option_type": "call"
}
```

Result (HTTP 200):

```json
{
  "price": 4.93714083,
  "d1": -0.10728844,
  "d2": -0.26285193
}
```

**black_scholes_european_option**

```text
POST /api/v1/derivatives/black_scholes_european_option
{
  "spot": 100,
  "strike": 105,
  "rate": 0.04,
  "sigma": 0.22,
  "tau": 0.5,
  "option_type": "put"
}
```

Result (HTTP 200):

```json
{
  "price": 7.85800153,
  "d1": -0.10728844,
  "d2": -0.26285193
}
```

**black_scholes_greeks**

```text
POST /api/v1/derivatives/black_scholes_greeks
{
  "spot": 100,
  "strike": 105,
  "rate": 0.04,
  "sigma": 0.22,
  "tau": 0.5,
  "option_type": "call"
}
```

Result (HTTP 200):

```json
{
  "delta": 0.45728008,
  "gamma": 0.02549781,
  "vega": 28.04758853,
  "theta": -7.80210416,
  "rho": 20.39543349
}
```

**What to notice.** The call is worth 4.9371 and the put 7.8580. Put-call parity holds: put - call = 2.9209, and K e^(-rT) - S = 2.9209. The Greeks follow the usual conventions: vega is per 1.00 of volatility (28.05, i.e. 0.2805 per volatility point), rho per 1.00 of rate and theta per year (-7.80, i.e. -0.0214 per day).

### Example 2: Bond price, duration, convexity and a +50bp reprice

A 10-year 4.5% semi-annual bond at a 5% yield. Duration and convexity predict the price move; a full reprice at +50bp confirms it.

**bond_pricer_fixed_coupon**

```text
POST /api/v1/derivatives/bond_pricer_fixed_coupon
{
  "face_value": 100,
  "coupon_rate": 0.045,
  "yield_rate": 0.05,
  "maturity": 10,
  "frequency": 2
}
```

Result (HTTP 200):

```json
{
  "price": 96.102709,
  "clean_price": 96.102709,
  "cashflows": [2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 102.25]
}
```

**modified_duration**

```text
POST /api/v1/derivatives/modified_duration
{
  "cashflows": <20 semi-annual cash flows: 19 x 2.25, then 102.25>,
  "times": <0.5, 1.0, ... 10.0>,
  "yield_rate": 0.05,
  "frequency": 2
}
```

Result (HTTP 200):

```json
{
  "modified_duration": 7.91914126,
  "macaulay_duration": 8.11711979,
  "price": 96.102709
}
```

**convexity**

```text
POST /api/v1/derivatives/convexity
{
  "cashflows": <20 semi-annual cash flows: 19 x 2.25, then 102.25>,
  "times": <0.5, 1.0, ... 10.0>,
  "yield_rate": 0.05,
  "frequency": 2
}
```

Result (HTTP 200):

```json
{
  "convexity": 75.29958077,
  "price": 96.102709
}
```

**bond_pricer_fixed_coupon**

```text
POST /api/v1/derivatives/bond_pricer_fixed_coupon
{
  "face_value": 100,
  "coupon_rate": 0.045,
  "yield_rate": 0.055,
  "maturity": 10,
  "frequency": 2
}
```

Result (HTTP 200):

```json
{
  "price": 92.386374,
  "clean_price": 92.386374,
  "cashflows": [2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 2.25, 102.25]
}
```

**What to notice.** The bond prices at 96.1027 with a modified duration of 7.9191 and a convexity of 75.30. The duration-plus-convexity estimate of a +50bp move is -3.7148, giving 92.3879; the full reprice gives 92.3864, a move of -3.7163. The residual is 0.0015.

## pyvar-alm

*duration gap, repricing, IRRBB*

### Example 1: Duration gap and repricing gap on one balance sheet

Two classic views of interest-rate exposure: how equity value moves, and where assets and liabilities reprice.

**duration_gap_analysis**

```text
POST /api/v1/alm/duration_gap_analysis
{
  "asset_duration": 4.2,
  "liability_duration": 3.6,
  "total_assets": 10000000000.0,
  "total_liabilities": 9200000000.0,
  "rate_shock": 0.02
}
```

Result (HTTP 200):

```json
{
  "duration_gap": 0.888,
  "leverage_adjusted_gap": 3.312,
  "delta_eve": -177600000.0,
  "equity": 800000000.0
}
```

**repricing_gap_analysis**

```text
POST /api/v1/alm/repricing_gap_analysis
{
  "bucket_assets": [1800000000.0, 1200000000.0, 2000000000.0, 3000000000.0, 2000000000.0],
  "bucket_liabilities": [3100000000.0, 1900000000.0, 1600000000.0, 1700000000.0, 900000000.0],
  "bucket_labels": ["<3m", "3-12m", "1-3y", "3-7y", ">7y"]
}
```

Result (HTTP 200):

```json
{
  "gap": {
    "<3m": -1300000000.0,
    "3-12m": -700000000.0,
    "1-3y": 400000000.0,
    "3-7y": 1300000000.0,
    ">7y": 1100000000.0
  },
  "cumulative_gap": [-1300000000.0, -2000000000.0, -1600000000.0, -300000000.0, 800000000.0],
  "total_gap": 800000000.0
}
```

**What to notice.** Asset duration 4.2 minus 0.92 x liability duration 3.6 gives a duration gap of 0.888. A +200bp parallel shock then moves the economic value of equity by -177,600,000, 22.2% of the 800,000,000 of equity. The repricing ladder shows why: liabilities reprice faster than assets in the first year (gaps of -1,300,000,000 and -700,000,000), the cumulative gap bottoms out at -2,000,000,000 and the total gap is 800,000,000.

### Example 2: IRRBB outlier test across the six BCBS shocks

A cash-flow ladder and base curve are shocked six ways, and the worst loss is compared with Tier 1 capital under the 15% supervisory outlier test.

**alm_stress_test**

```text
POST /api/v1/alm/alm_stress_test
{
  "net_cashflows": [-400000000.0, -250000000.0, -100000000.0, 150000000.0, 350000000.0, 300000000.0, 250000000.0],
  "times": [0.5, 1, 2, 3, 5, 7, 10],
  "base_rates": [0.035, 0.036, 0.037, 0.038, 0.04, 0.041, 0.042],
  "tier1_capital": 900000000.0,
  "parallel_bps": 200
}
```

Result (HTTP 200):

```json
{
  "worst_case_eve": -81925909.171418,
  "eve_capital_ratio": 0.09102879,
  "breaches_15pct": false,
  "scenario_results": {
    "parallel_up": -81925909.171418,
    "parallel_down": 96004059.054543,
    "steepener": -40872598.982401,
    "flattener": 22554408.762437,
    "short_up": -15631790.089657,
    "short_down": 16479001.723791
  }
}
```

**What to notice.** The worst scenario is parallel_up, with a change in EVE of -81,925,909. Against 900m of Tier 1 capital that is 9.1%, below the 15% outlier threshold, so breaches_15pct is False. The parallel-down scenario shows the opposite sign (96,004,059): value falls when rates rise and rises when they fall, the profile of a ladder whose later, positive cash flows are the longer-dated ones.

## pyvar-arch-api-gateway

*authentication, tiers, rate limits*

### Example 1: JWT authentication and tier caps on POST /api/v1/var/compute

The same request body is sent four times with different credentials. The gateway authenticates the JWT, reads the tier from it and enforces that tier's simulation cap before anything is queued. Celery and the audit database are stood in for here, so the accepted request returns a fixed stand-in task_id.

**no token**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <252 daily log-returns: generate_gbm_returns(252, seed=5)>,
  "confidence_level": 0.99,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 401):

```json
{
  "detail": "Not authenticated"
}
```

**token signed with the wrong secret**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <252 daily log-returns: generate_gbm_returns(252, seed=5)>,
  "confidence_level": 0.99,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 401):

```json
{
  "detail": "Invalid or expired token: Signature verification failed."
}
```

**free tier asking for 50,000 simulations**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <252 daily log-returns: generate_gbm_returns(252, seed=5)>,
  "confidence_level": 0.99,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 403):

```json
{
  "detail": "Your 'free' tier allows a maximum of 10,000 simulations. Requested: 50,000."
}
```

**pro tier asking for 50,000 simulations**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <252 daily log-returns: generate_gbm_returns(252, seed=5)>,
  "confidence_level": 0.99,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 202):

```json
{
  "task_id": "3f2c9d1e-0000-4000-8000-000000000001",
  "status": "pending",
  "message": "Job queued successfully"
}
```

**What to notice.** No token and a forged token both get 401. A free-tier token is refused with 403 and a message that names the cap and the request; the identical body from a pro-tier token is accepted with 202 and a task_id to poll at GET /api/v1/var/result/{task_id}. Caps are 10,000 simulations for free, 100,000 for pro and 500,000 for enterprise.

### Example 2: One daily quota shared across every compute endpoint

A free-tier user alternates between a credit-risk and a liquidity endpoint. The daily allowance is a single shared 'compute' bucket, so the count carries across routes.

**11 requests as a free-tier user**

```text
free-tier token, alternating:
  expected_loss_el_computation
  liquidity_coverage_ratio_lcr
```

Result:

```text
request  1  expected_loss_el_computation       -> 200
request  2  liquidity_coverage_ratio_lcr       -> 200
request  3  expected_loss_el_computation       -> 200
request  4  liquidity_coverage_ratio_lcr       -> 200
request  5  expected_loss_el_computation       -> 200
request  6  liquidity_coverage_ratio_lcr       -> 200
request  7  expected_loss_el_computation       -> 200
request  8  liquidity_coverage_ratio_lcr       -> 200
request  9  expected_loss_el_computation       -> 200
request 10  liquidity_coverage_ratio_lcr       -> 200
request 11  expected_loss_el_computation       -> 429
response body: {"detail": "Rate limit exceeded. Please retry later."}
Retry-After header: 86399 seconds
```

**What to notice.** The free tier allows 10 compute requests per day. Requests 1 to 10 succeed across both endpoints; request 11 is refused with 429 and a Retry-After of about a day, rather than being counted per route.

## pyvar-arch-compute

*the Numba Monte Carlo engine*

### Example 1: Numerical properties of the Numba Monte Carlo kernel

The engine is pre-drawn random numbers fed to an @njit kernel. The properties the test-suite pins can be checked in four lines.

**run_monte_carlo_var**

```python
from engine.montecarlo import run_monte_carlo_var
returns = generate_gbm_returns(252, mu=0.0004, sigma=0.012, seed=3)
a   = run_monte_carlo_var(returns,  1_000_000, 0.99, 1, 50_000, seed=42)
b   = run_monte_carlo_var(returns,  1_000_000, 0.99, 1, 50_000, seed=42)
v95 = run_monte_carlo_var(returns,  1_000_000, 0.95, 1, 50_000, seed=42)
big = run_monte_carlo_var(returns, 10_000_000, 0.99, 1, 50_000, seed=42)
```

Result:

```text
same seed, identical VaR and loss distribution : True
99% VaR 2.794%  >  95% VaR 1.936% : True
CVaR 3.214%  >=  VaR 2.794%      : True
var_abs on 10m / var_abs on 1m                  : 10.0000
```

**What to notice.** Two runs with seed 42 are bit-identical, which is what makes a stored job reproducible. The 99% VaR (2.794%) sits above the 95% VaR (1.936%), CVaR is at least VaR, and absolute VaR scales linearly with portfolio value (a ratio of 10 for a 10x portfolio).

### Example 2: Simulation count and horizon: convergence and square-root-of-time

How much the answer moves between seeds as paths are added, and how a 10-day horizon relates to a 1-day one.

**convergence and horizon scaling**

```python
for n in (1_000, 10_000, 100_000, 1_000_000):
    vs = [run_monte_carlo_var(returns, 1.0, 0.99, 1, n, seed=s)['var_pct'] for s in range(1, 6)]
    print(n, min(vs), max(vs))
one = run_monte_carlo_var(returns, 1_000_000, 0.99,  1, 200_000, seed=1)
ten = run_monte_carlo_var(returns, 1_000_000, 0.99, 10, 200_000, seed=1)
```

Result:

```text
n_simulations     1,000   VaR over 5 seeds: 0.02647 .. 0.02877   spread 0.00231
n_simulations    10,000   VaR over 5 seeds: 0.02727 .. 0.02832   spread 0.00105
n_simulations   100,000   VaR over 5 seeds: 0.02759 .. 0.02785   spread 0.00026
n_simulations 1,000,000   VaR over 5 seeds: 0.02762 .. 0.02777   spread 0.00014
1-day VaR 0.02751   10-day VaR 0.08396   ratio 3.053   (sqrt(10) = 3.162)
```

**What to notice.** The seed-to-seed spread of the 99% VaR shrinks from 0.00231 at 1,000 paths to 0.00014 at 1,000,000: more paths buy a tighter estimate, at a cost that grows with the path count. The 10-day VaR is 3.05 times the 1-day figure, close to the square-root-of-time factor of 3.16; it is a little lower because the positive daily drift accumulates over ten days.

## pyvar-arch-data-ingestion

*Polars and PyArrow I/O*

### Example 1: Lazy Parquet scan with predicate pushdown into a NumPy array

The loader never reads the whole file: the instrument and date filters travel into the Parquet scan, and the engine receives a plain float64 array.

**pl.scan_parquet + load_returns**

```python
path = generate_fixture_parquet('fixture.parquet')   # 3 instruments x 504 days
lf = (pl.scan_parquet(path)
        .filter(pl.col('instrument_id') == 'FTSE100')
        .filter(pl.col('date') >= date(2023, 6, 1))
        .select(['date', 'log_return']).sort('date'))
print(lf.explain())
arr  = load_returns(path, 'FTSE100', start_date=date(2023, 6, 1))
full = load_returns(path, 'FTSE100')
load_returns(path, 'NOPE')
```

Result:

```text
SORT BY [col("date")]
  simple π 2/2 ["date", "log_return"]
    Parquet SCAN [fixture.parquet]
    PROJECT 3/3 COLUMNS
    SELECTION: (col("date") >= 2023-06-01 00:00:00) & (col("instrument_id") == "FTSE100")
    ESTIMATED ROWS: 2016

windowed : shape (353,), dtype float64
full     : shape (504,), dtype float64
ValueError: No returns found for instrument 'NOPE' in [None, None].
```

**What to notice.** The query plan shows the date and instrument predicates as a SELECTION on the Parquet scan, so filtering happens while reading. The windowed load returns 353 observations against 504 for the full history, both as float64 arrays, and an unknown instrument raises a clear error instead of returning an empty array.

### Example 2: Schema-enforced Parquet results with PyArrow

Results are written with an explicit schema, so a wrongly typed value fails loudly rather than being coerced.

**write_result_parquet**

```python
write_result_parquet(result, 'result.parquet', task_id='task-1')
print(pq.read_schema('result.parquet'))
print(pq.ParquetFile('result.parquet').metadata.row_group(0).column(0).compression)
write_result_parquet({**result, 'var_pct': 'not-a-number'}, 'bad.parquet', 'task-2')
```

Result:

```text
task_id: string
var_pct: double
var_abs: double
cvar_pct: double
cvar_abs: double
mu: double
sigma: double
n_simulations: int64
confidence_level: double
horizon_days: int32
loss_dist: list<element: double>
compression: SNAPPY
ArrowInvalid: Could not convert 'not-a-number' with type str: tried to convert to double
```

**What to notice.** The file carries an explicit eleven-column schema (scalar metrics plus the full loss distribution as a list of doubles) and is compressed with SNAPPY. Passing a string where a double is expected raises ArrowInvalid rather than silently writing a corrupt column.

## pyvar-arch-storage

*Redis cache and S3 results*

### Example 1: Deterministic cache keys that fail open

The Redis cache key is a SHA-256 over the canonical request, and a cache that cannot be reached degrades to a miss.

**caching._cache_key / _cache_get**

```python
body = {'returns': [0.01, -0.02], 'portfolio_value': 1e6, 'confidence_level': 0.99}
k1 = _cache_key('market-risk', body)
k2 = _cache_key('market-risk', dict(reversed(body.items())))   # same fields, other order
k3 = _cache_key('market-risk', {**body, 'confidence_level': 0.95})
k4 = _cache_key('credit-risk', body)
await _cache_get('market-risk', {'never': 'cached'})            # no Redis reachable
```

Result:

```text
k1 = pyvar:market-risk:1571b407126e7a7abae19b1c373fb14512aa276ef914e4718ef1579983527096
k1 == k2 (field order ignored)   : True
k1 == k3 (other confidence level): False
k1 == k4 (other domain)          : False
_cache_get with Redis unreachable: None
```

**What to notice.** Key order in the JSON body does not change the key, while any change of parameter or domain does, so equivalent requests share one cached result and different ones never collide. With no Redis available the lookup returns None, a plain cache miss, so an unreachable cache slows a request down instead of failing it.

### Example 2: Large results go to S3 and come back as a presigned URL

Above the offload threshold the worker writes the full result, loss distribution included, to S3 as Parquet. The API attaches a fresh presigned URL whenever a result is served. AWS is mocked with moto.

**storage.s3**

```python
result = run_monte_carlo_var(returns, 1_000_000, 0.99, 1, 200_000, seed=42)   # 200,000 > threshold
key  = write_result_to_s3(result, task_id)
obj  = s3.get_object(Bucket=bucket, Key=key)
url  = generate_presigned_url(key)
hydrate_presigned_url({'s3_key': key, 'n_simulations': 200_000})
```

Result:

```text
offload threshold (config)   : 10,000 simulations
s3 key                       : results/abcdef12/abcdef12-3456-7890-abcd-ef1234567890.parquet
object                       : Parquet, ~2.1 MB, 1 row, loss_dist of 200,000 values
presigned url (without query): https://pyvar-results.s3.amazonaws.com/results/abcdef12/abcdef12-3456-7890-abcd-ef1234567890.parquet
hydrated result keys         : ['n_simulations', 'presigned_url', 's3_key']
```

**What to notice.** A 200,000-path run is above the 10,000-simulation threshold, so the full result is stored as a single-row Parquet object under results/<prefix>/<task_id>.parquet with the 200,000-value loss distribution intact, and what travels through the Celery result backend is the s3_key. hydrate_presigned_url turns that key into a time-limited link at the moment a client asks, so the link is never stale.

## pyvar-arch-observability

*validation and Prometheus metrics*

### Example 1: Input validation: regulatory bounds enforced at the edge

Bad input is stopped by the Pydantic schema before a job exists. Three requests break the rules in different ways.

**confidence_level outside the regulatory range**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <252 daily log-returns: generate_gbm_returns(252, seed=5)>,
  "confidence_level": 0.5,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 422):

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "confidence_level"],
      "msg": "Value error, Confidence level 0.5 is outside conventional range [0.90, 0.9999]. Standard values: 0.95 (internal), 0.99 (Basel III), 0.975 (FRTB ES)."
    }
  ]
}
```

**fewer than 30 observations**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <10 daily log-returns>,
  "confidence_level": 0.99,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 422):

```json
{
  "detail": [
    {
      "type": "too_short",
      "loc": ["body", "returns"],
      "msg": "List should have at least 30 items after validation, not 10"
    }
  ]
}
```

**a NaN in the returns**

```text
POST /api/v1/var/compute
{
  "portfolio_value": 1000000,
  "returns": <252 daily log-returns, the first one replaced by NaN>,
  "confidence_level": 0.99,
  "horizon_days": 1,
  "n_simulations": 50000
}
```

Result (HTTP 422):

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "returns"],
      "msg": "Value error, Returns series contains NaN or infinite values."
    }
  ]
}
```

**What to notice.** All three requests return 422. A confidence level of 0.5 is rejected with a message that lists the conventional values (0.95 internal, 0.99 Basel III, 0.975 FRTB ES) and the allowed range 0.90 to 0.9999; a 10-observation series is rejected because the minimum is 30; and a NaN inside the returns is refused with the same status. The error carries the field location, so a client can point at the offending parameter.

### Example 2: Prometheus metrics for computations and HTTP traffic

The app exposes /metrics. Domain metrics are recorded around the engine call, and request counters come from the HTTP instrumentation.

**GET /metrics**

```text
# scrape, send three valid calls and one 422, run a 50,000-path VaR inside track_computation()
with track_computation(0.99, 1, 50_000):
    run_monte_carlo_var(returns, 1e6, 0.99, 1, 50_000, seed=1)
GET /metrics
```

Result:

```text
pyvar_computation_duration_seconds_count{confidence_level="0.99",horizon_days="1"} 1
pyvar_computation_duration_seconds_sum{confidence_level="0.99",horizon_days="1"} <elapsed seconds, varies per run>
pyvar_simulation_count_count 1
pyvar_simulation_count_sum 50000
http_requests_total{handler="/api/v1/credit-risk/expected_loss_el_computation",method="POST",status="2xx"} +3
http_requests_total{handler="/api/v1/credit-risk/expected_loss_el_computation",method="POST",status="4xx"} +1
```

**What to notice.** Between two scrapes, three successful calls and one rejected one raise the HTTP counters by three 2xx and one 4xx, labelled with the route template (not the raw URL), so a dashboard groups by endpoint. The computation histogram is labelled by confidence level and horizon, and the simulation-count histogram records the 50,000 paths of the run, which is what a Grafana panel of latency per simulation size is built on.

## pyvar-mcp

*385 functions as MCP tools*

### Example 1: Discovering the catalogue from Claude Code

The MCP server starts over stdio and exposes every pyvar function as a tool, plus a generic discovery tool. This session talks to a locally running pyvar API.

**tools/list + list_pyvar_functions**

```text
list_pyvar_functions(domain="alm")
```

Result:

```text
tools exposed by the server : 387 (385 named + list_pyvar_functions, call_pyvar_function)
functions in domain 'alm'   : 33
first two entries:
[
  {
    "domain": "alm",
    "function_name": "alm_stress_test",
    "summary": "Run an ALM stress test: worst-case EVE decline vs Tier-1 capital.",
    "required_params": ["net_cashflows", "times", "base_rates", "tier1_capital"]
  },
  {
    "domain": "alm",
    "function_name": "asset_liability_mismatch_index",
    "summary": "Asset-liability mismatch index from duration-weighted exposures.",
    "required_params": ["asset_durations", "asset_amounts", "liability_durations", "liability_amounts"]
  }
]
```

**What to notice.** The server advertises 387 tools: one named tool per catalogued function (385) and the two generic ones. list_pyvar_functions returns each function's name, one-line summary and required parameter names, filtered to a domain, so the model can find the right function without holding 385 schemas in context.

### Example 2: Calling a function, and what errors look like

The generic call tool and the named tool reach the same endpoint. Mistakes come back as readable tool results, not protocol failures.

**call_pyvar_function**

```json
{
  "domain": "credit-risk",
  "function_name": "expected_loss_el_computation",
  "params": {
    "pd": 0.02,
    "lgd": 0.45,
    "ead": 1000000
  }
}
```

Result:

```json
{
  "el": 9000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 1000000.0
}
```

**same function as a named tool**

```text
expected_loss_el_computation(pd=0.02, lgd=0.45, ead=1000000)
```

Result:

```json
{
  "el": 9000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 1000000.0
}
```

**missing a required parameter**

```json
{
  "domain": "credit-risk",
  "function_name": "expected_loss_el_computation",
  "params": {
    "pd": 0.02,
    "lgd": 0.45
  }
}
```

Result:

```text
Missing required parameter(s) for expected_loss_el_computation: ead. Expected params: ead, lgd, pd.
```

**a value the API rejects**

```json
{
  "domain": "credit-risk",
  "function_name": "expected_loss_el_computation",
  "params": {
    "pd": 1.7,
    "lgd": 0.45,
    "ead": 1000000
  }
}
```

Result:

```text
pyvar API error (HTTP 422): {"detail":"pd must be in [0, 1]"}
```

**an unknown function**

```json
{
  "domain": "alm",
  "function_name": "no_such_function",
  "params": {}
}
```

Result:

```text
Unknown function 'no_such_function' in domain 'alm'. Use list_pyvar_functions to see valid names.
```

**What to notice.** The generic tool and the named tool return identical results (expected loss of 9,000). A missing parameter is caught before any request is made, with the expected parameter names listed; a value outside the allowed range comes back from the API as an HTTP 422 message; an unknown function name points the model back to list_pyvar_functions. Each is flagged is_error, so the model can read it and correct the call.

## pyvar-client

*the Python client, on PyPI*

### Example 1: A computation from Python

Client() with no arguments reads the key from PYVAR_API_KEY (this run also passes base_url to reach a local API; against pyvar.com the default is enough). Two years of daily returns (500 observations, generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7)) go to the same function the market-risk skill's first example uses.

**historical_simulation_var**

```python
from pyvar_client import Client

with Client() as client:  # reads PYVAR_API_KEY
    result = client.market_risk.historical_simulation_var(
        returns=returns,  # 500 daily log-returns
        portfolio_value=10_000_000,
        confidence_level=0.99,
    )
    result
```

Result:

```json
{
  "var_pct": 0.02380457,
  "var_abs": 238045.72,
  "cvar_pct": 0.02908383,
  "cvar_abs": 290838.34,
  "confidence_level": 0.99,
  "n_obs": 500
}
```

**What to notice.** The 99% VaR is 2.38% of the book, 238,046, the same numbers the REST call returns (checked in this run) and the market-risk skill reports. The client is a thin typed layer: one method per function, one dict back.

### Example 2: Errors you can branch on

Every non-2xx response raises a typed exception, so code can tell "fix the request" from "get a new key" from "back off".

**a key the API does not accept**

```python
with Client(api_key="not-a-valid-key") as client:
    client.credit_risk.expected_loss_el_computation(pd=0.02, lgd=0.45, ead=1_000_000)
```

Result:

```text
PyvarAuthError (HTTP 401): Authentication failed -- token missing, invalid, or expired.
```

**a value the API rejects**

```python
client.credit_risk.expected_loss_el_computation(pd=1.7, lgd=0.45, ead=1_000_000)
```

Result:

```text
PyvarValidationError (HTTP 422): Request failed validation.
response_body = {'detail': 'pd must be in [0, 1]'}
```

**What to notice.** A 401 is PyvarAuthError and a 422 is PyvarValidationError: the message names the problem, response_body holds the raw body, and detail lists per-field entries when the API sends them that way. A 429 is PyvarRateLimitError with the Retry-After seconds. Server errors are retried with backoff for idempotent calls before they surface.

## pyvar-jupyter

*%pyvar magics for notebooks, on PyPI*

### Example 1: The line magic

After %load_ext pyvar_jupyter and a key (%pyvar_key, or PYVAR_API_KEY in the environment), parameters go on the line as key=value tokens, each read as a Python literal.

**%pyvar**

```text
%pyvar market_risk.historical_simulation_var returns=[0.01,-0.02,0.015,0.008,-0.011] portfolio_value=1000000
```

Result:

```json
{
  "var_pct": 0.02,
  "var_abs": 20000.0,
  "cvar_pct": 0.02,
  "cvar_abs": 20000.0,
  "confidence_level": 0.99,
  "n_obs": 5
}
```

**What to notice.** The cell shows an HTML table and also returns the dict, so result['var_abs'] (20,000.00) works on it directly.

### Example 2: The cell magic, and asking a function what it needs

Nested or large parameters go in a JSON body. Called with no parameters, the magic prints the function's signature and docstring instead of making a doomed request.

**%%pyvar**

```text
%%pyvar credit_risk.expected_loss_el_computation
{"pd": 0.05, "lgd": 0.4, "ead": 2000000}
```

Result:

```json
{
  "el": 40000.0,
  "el_rate": 0.02,
  "pd": 0.05,
  "lgd": 0.4,
  "ead": 2000000.0
}
```

**%pyvar with no parameters**

```text
%pyvar credit_risk.expected_loss_el_computation
```

Result:

```text
expected_loss_el_computation(*, pd: 'float', lgd: 'float', ead: 'float') -> 'dict[str, Any]'

Expected Loss ``EL = PD * LGD * EAD``.

Returns:
    The raw API response as a dict.
```

**What to notice.** Expected loss is 0.05 x 0.4 x 2,000,000 = 40,000. The signature lists every parameter with its type and default, which is what to read before building a request.

## One call, every surface

*REST, pyvar-client, pyvar-jupyter and pyvar-mcp agree*

### Example 1: The same call through every surface

Expected loss for a 1,000,000 exposure with a 2% probability of default and 45% loss given default, asked four ways. The API is a local pyvar API; against pyvar.com the only differences are the host and the key.

**REST**

```bash
curl -X POST https://www.pyvar.com/api/v1/credit-risk/expected_loss_el_computation \
  -H "Authorization: Bearer $PYVAR_API_KEY" -H "Content-Type: application/json" \
  -d '{"pd": 0.02, "lgd": 0.45, "ead": 1000000}'
```

Result (HTTP 200):

```json
{
  "el": 9000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 1000000.0
}
```

**pyvar-client**

```python
from pyvar_client import Client

with Client() as client:  # reads PYVAR_API_KEY
    client.credit_risk.expected_loss_el_computation(pd=0.02, lgd=0.45, ead=1_000_000)
```

Result:

```json
{
  "el": 9000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 1000000.0
}
```

**pyvar-jupyter**

```text
%pyvar credit_risk.expected_loss_el_computation pd=0.02 lgd=0.45 ead=1000000
```

Result:

```json
{
  "el": 9000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 1000000.0
}
```

**pyvar-mcp**

```json
{
  "domain": "credit-risk",
  "function_name": "expected_loss_el_computation",
  "params": {
    "pd": 0.02,
    "lgd": 0.45,
    "ead": 1000000
  }
}
```

Result:

```json
{
  "el": 9000.0,
  "el_rate": 0.009,
  "pd": 0.02,
  "lgd": 0.45,
  "ead": 1000000.0
}
```

**What to notice.** REST, the Python client, the notebook magic and the MCP tool return identical results, and the script fails if they ever differ. Expected loss is 0.02 x 0.45 x 1,000,000 = 9,000.
