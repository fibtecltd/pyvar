# Fourteen Claude Code Plugins, Twenty-Eight Worked Examples

*What pyvar actually does when you ask it a risk question — one real request and one real result at a time.*

---

pyvar.com is an open-source (Apache-2.0), Numba-accelerated risk platform: 385 functions across eight domains — market risk, credit risk, liquidity, operational risk, portfolio analytics, regulatory capital, derivatives and ALM — behind a single REST API. It reaches Claude Code through fourteen plugins: eight domain skills, five architecture skills and the `pyvar-mcp` server.

```
/plugin marketplace add fibtecltd/pyvar
/plugin install pyvar-market-risk@pyvar-marketplace
```

A plugin list tells you what exists. This article shows what each one does. Every plugin gets two worked examples — twenty-eight in all — and every number below was produced by running pyvar's own code on synthetic data, with the seed shown.

## Part one: the eight domain plugins

The domain plugins teach Claude which of pyvar's functions answer which question. Ask in plain language, and the request resolves to a call like the ones below.

### pyvar-market-risk

**"What is the 99% VaR of a 10 million portfolio, and what is the FRTB Expected Shortfall?"**

Two years of daily returns (500 observations, `generate_gbm_returns(500, mu=0.0004, sigma=0.011, seed=7)`) go to `historical_simulation_var`:

```
POST /api/v1/market-risk/historical_simulation_var
{"returns": [... 500 values ...], "portfolio_value": 10000000, "confidence_level": 0.99}

{"var_pct": 0.02380457, "var_abs": 238045.72,
 "cvar_pct": 0.02908383, "cvar_abs": 290838.34, "n_obs": 500}
```

The 99% VaR is 2.38% of the book, 238,046. `historical_expected_shortfall` at the FRTB level of 97.5% averages the 13 worst days of the 500 and returns 245,467. Expected Shortfall is the mean of the tail, not a quantile — which is why the response reports `n_tail` alongside the number.

**"Backtest this VaR against the next year and tell me the capital consequence."**

A 99% VaR of 1.51% is estimated on one 250-day window, then judged against the next 250 days drawn from the same distribution. Three chained calls do the rest:

```
traffic_light_backtesting     → {"n_breaches": 7, "basel_zone": "yellow"}
basel_capital_addon_multiplier → {"multiplier": 3.65, "zone": "yellow"}
kupiec_pof_test               → {"lr_pof": 5.49699, "p_value": 0.019049,
                                 "critical_value": 3.841459, "reject": true}
```

A 99% VaR should be breached about 2.5 times in 250 days. Seven breaches is yellow, carries a 3.65 multiplier, and the Kupiec test rejects the model at 95%. Both windows came from one distribution, so the example doubles as a reminder of how noisy a 99% quantile is when it rests on 250 observations.

### pyvar-credit-risk

**"What is the expected loss and the 99.9% credit VaR on a 50 million exposure?"**

```
expected_loss_el_computation  {"pd": 0.02, "lgd": 0.45, "ead": 50000000}
→ {"el": 450000.0, "el_rate": 0.009}

credit_var_analytical_vasicek {"pd": 0.02, "lgd": 0.45, "ead_total": 50000000,
                               "asset_correlation": 0.15, "confidence_level": 0.999}
→ {"var": 3967401.13, "el": 450000.0, "ul": 3517401.13, "loss_rate_q": 0.0793480226}
```

Expected loss is 0.02 × 0.45 × 50,000,000 = 450,000. The Vasicek 99.9% loss is 3,967,401, which leaves an unexpected loss of 3,517,401 for economic capital to cover.

**"Score these three borrowers."**

`altman_z_score_credit_scoring` takes seven balance-sheet figures and returns the Z-score, the zone and the five ratios behind it, so the model can be audited:

```
borrower A → {"z_score": 3.061,    "zone": "safe"}
borrower B → {"z_score": 2.667,    "zone": "grey"}
borrower C → {"z_score": 0.179621, "zone": "distress"}
```

Borrower B checks by hand: 1.2 × 0.12 + 1.4 × 0.34 + 3.3 × 0.09 + 0.6 × 2.0 + 1.0 × 0.55 = 2.667. Borrower C has negative working capital, retained earnings and EBIT.

### pyvar-liquidity-risk

**"Are we compliant on LCR and NSFR?"**

```
liquidity_coverage_ratio_lcr   {"hqla": 120e6, "gross_outflows": 150e6, "gross_inflows": 40e6}
→ {"lcr": 1.090909, "net_outflows": 110000000.0, "compliant": true}

net_stable_funding_ratio_nsfr  {"available_stable_funding": 410e6, "required_stable_funding": 385e6}
→ {"nsfr": 1.064935, "compliant": true}
```

120m of HQLA against 110m of net 30-day outflows is an LCR of 109.1%; 410m of stable funding over 385m required is an NSFR of 106.5%.

**"How long does our buffer last under stress?"**

`survival_horizon_calculator` walks a 12-day outflow path against 100m of HQLA:

```
{"survival_days": 10, "terminal_buffer": -1000000.0, "hqla": 100000000.0}
```

Cumulative outflows reach 94m after day 10 and 101m after day 11: the buffer survives ten full days and is exhausted during the eleventh, ending 1m short.

### pyvar-operational-risk

**"What does the Basel SMA charge look like for a clean bank and a heavy-loss bank?"**

`basel_standardised_measurement_sma` multiplies the Business Indicator Component by the Internal Loss Multiplier:

```
{"business_indicator": 3e9,  "loss_component": 0.0}
→ {"bic": 420000000.0,  "ilm": 0.541325, "sma_capital": 227356438.94}

{"business_indicator": 12e9, "loss_component": 2.5e9}
→ {"bic": 1770000000.0, "ilm": 1.110692, "sma_capital": 1965924205.84}
```

For a 3bn Business Indicator, the BIC is 12% of the first 1bn plus 15% of the next 2bn = 420m. With no loss history the ILM is ln(e − 1) = 0.5413, so capital is 227m. The 12bn bank with a 2.5bn loss component has an ILM above 1, and its capital is 1.97bn.

**"Which of our key risk indicators are in breach?"**

One function, `kri_threshold_breach_detection`, handles indicators that get worse upwards and downwards:

```
value 14,   amber 8,    red 12,   higher_breach → {"status": "red",   "breached": true}
value 9.5,  amber 8,    red 12,   higher_breach → {"status": "amber", "breached": true}
value 97.2, amber 98.5, red 96.0, lower_breach  → {"status": "amber", "breached": true}
```

### pyvar-portfolio-analytics

**"Give me minimum-variance and risk-parity weights for these four assets."**

Both optimisers take a per-period covariance matrix — here the annual matrix divided by 252 — and annualise internally.

```
minimum_variance_portfolio → weights [0, 0, 0.1348, 0.8652], volatility 0.0379
risk_parity_portfolio      → weights [0.0933, 0.1272, 0.2231, 0.5564], volatility 0.0536
                             risk_contributions [2.8553e-06, 2.8553e-06, 2.8553e-06, 2.8553e-06]
```

Minimum variance concentrates in the two calmest assets for 3.79% volatility. Risk parity spreads the weights so every asset contributes exactly the same risk — the four contributions are identical — and accepts 5.36% volatility for that balance.

**"How did this strategy perform over two years?"**

Over 504 daily returns (`generate_gbm_returns(504, mu=0.0004, sigma=0.011, seed=21)`):

```
sharpe_ratio     → {"sharpe": 0.69235817}
sortino_ratio    → {"sortino": 0.98571033, "downside_deviation": 0.007194781}
maximum_drawdown → {"max_drawdown": 0.29564828, "peak_index": 88, "trough_index": 291}
```

A Sharpe ratio of 0.69, a higher Sortino of 0.99 because only downside deviation is penalised, and a 29.6% maximum drawdown — with the peak and trough positions, so you know when the loss happened as well as how large it was.

### pyvar-regulatory

**"Where do we stand on CET1, buffers and leverage?"**

```
basel_iii_cet1_ratio        {"cet1_capital": 5.2e9, "risk_weighted_assets": 41e9}
→ {"cet1_ratio": 0.12682927, "minimum": 0.045, "surplus": 0.08182927, "compliant": true}

combined_buffer_requirement {2.5% conservation, 1% countercyclical, 1% systemic, RWA 41e9}
→ {"combined_buffer_ratio": 0.045, "combined_buffer_capital": 1845000000.0}

basel_iii_leverage_ratio    {"tier1_capital": 6.1e9, "total_exposure": 168e9}
→ {"leverage_ratio": 0.03630952, "minimum": 0.03, "compliant": true}
```

CET1 is 12.68% against a 4.5% minimum, the buffer stack is 4.5% of RWA — 1.845bn of capital — and the leverage ratio is 3.63% against the 3% floor.

**"Does the Basel IV output floor bind?"**

```
basel_iv_output_floor {"internal_model_rwa": 28e9, "standardised_rwa": 41e9}
→ {"floored_rwa": 29725000000.0, "binding": true, "rwa_uplift": 1725000000.0, "floor_factor": 0.725}
```

72.5% of the 41bn standardised RWA is 29.725bn — above the 28bn internal-model figure. The floor binds and RWA rises by 1.725bn.

### pyvar-derivatives

**"Price this option and give me the Greeks."**

A six-month, 105-strike option on a 100 underlying at 4% and 22% volatility:

```
black_scholes_european_option (call) → {"price": 4.93714083}
black_scholes_european_option (put)  → {"price": 7.85800153}
black_scholes_greeks (call)          → {"delta": 0.45728008, "gamma": 0.02549781,
                                        "vega": 28.04758853, "theta": -7.80210416,
                                        "rho": 20.39543349}
```

Put-call parity holds: put − call = 2.9209, and K·e^(−rT) − S = 2.9209. The Greeks use standard conventions — vega per 1.00 of volatility, rho per 1.00 of rate, theta per year.

**"What happens to this bond if yields rise 50 basis points?"**

A 10-year 4.5% semi-annual bond at a 5% yield prices at 96.1027, with a modified duration of 7.9191 and a convexity of 75.30. Duration and convexity predict the move; a full reprice at 5.5% confirms it:

```
duration + convexity estimate → 92.3879
full reprice at +50bp         → 92.3864   (a move of −3.7163)
```

The two agree to within 0.0015 of price.

### pyvar-alm

**"How exposed is our equity to a rate shock, and where does the exposure sit?"**

```
duration_gap_analysis  {"asset_duration": 4.2, "liability_duration": 3.6,
                        "total_assets": 10e9, "total_liabilities": 9.2e9, "rate_shock": 0.02}
→ {"duration_gap": 0.888, "delta_eve": -177600000.0, "equity": 800000000.0}
```

The duration gap is 4.2 − 0.92 × 3.6 = 0.888, so a +200bp shock takes 177.6m off the economic value of equity — 22.2% of the 800m of equity. `repricing_gap_analysis` shows where it comes from: liabilities reprice faster than assets, with gaps of −1.3bn in the under-three-months bucket and −0.7bn in three to twelve months, and a cumulative gap bottoming out at −2.0bn.

**"Run the IRRBB outlier test."**

`alm_stress_test` applies the six BCBS shocks to a cash-flow ladder and compares the worst loss with Tier 1 capital:

```
{"worst_case_eve": -81925909.17, "eve_capital_ratio": 0.09102879, "breaches_15pct": false,
 "scenario_results": {"parallel_up": -81925909.17, "parallel_down": 96004059.05, ...}}
```

The worst scenario is the parallel-up shock, at −81.9m, which is 9.1% of 900m of Tier 1 capital — under the 15% supervisory threshold.

## Part two: the five architecture plugins

The architecture plugins document how pyvar itself is built. Each example below calls the real module, not a description of it.

### pyvar-arch-api-gateway

**Authentication and tier caps.** The same VaR request is sent four times with different credentials:

```
no token                                   → 401  {"detail": "Not authenticated"}
token signed with the wrong secret         → 401
free tier, 50,000 simulations              → 403  "Your 'free' tier allows a maximum of
                                                   10,000 simulations. Requested: 50,000."
pro tier, 50,000 simulations               → 202  {"status": "pending", "message": "Job queued successfully"}
```

The JWT carries the tier, and the tier's simulation cap — 10,000 free, 100,000 pro, 500,000 enterprise — is enforced before anything is queued.

**One quota across every compute endpoint.** A free-tier user alternates between a credit-risk and a liquidity endpoint. Requests 1 to 10 succeed; request 11 is refused:

```
request 11  expected_loss_el_computation → 429
{"detail": "Rate limit exceeded. Please retry later."}   Retry-After: 86399 seconds
```

The daily allowance is a single shared bucket, so it counts across routes rather than per route.

### pyvar-arch-compute

**The properties of the Numba kernel.** Four runs of `run_monte_carlo_var` on the same returns:

```
same seed, identical VaR and loss distribution : True
99% VaR 2.794%  >  95% VaR 1.936%              : True
CVaR 3.214%  >=  VaR 2.794%                    : True
var_abs on 10m / var_abs on 1m                 : 10.0000
```

The same seed gives a bit-identical result — which is what makes a stored job reproducible. VaR rises with the confidence level, CVaR is never below VaR, and absolute VaR scales linearly with portfolio value.

**Convergence and horizon.** Across five seeds, the spread of the 99% VaR narrows as paths are added:

```
n_simulations     1,000   spread 0.00231
n_simulations    10,000   spread 0.00105
n_simulations   100,000   spread 0.00026
n_simulations 1,000,000   spread 0.00014
1-day VaR 0.02751   10-day VaR 0.08396   ratio 3.05   (sqrt(10) = 3.16)
```

More paths buy a tighter estimate at a cost that grows with the path count. The 10-day VaR is 3.05 times the 1-day figure, close to the square-root-of-time factor of 3.16; it sits a little lower because the positive daily drift accumulates over ten days.

### pyvar-arch-data-ingestion

**Lazy Parquet scans with predicate pushdown.** `load_returns` filters by instrument and date range, and the query plan shows both predicates pushed into the Parquet scan:

```
Parquet SCAN [fixture.parquet]
SELECTION: (col("date") >= 2023-06-01 00:00:00) & (col("instrument_id") == "FTSE100")

windowed : shape (353,), dtype float64
full     : shape (504,), dtype float64
ValueError: No returns found for instrument 'NOPE' in [None, None].
```

The engine receives a plain float64 array, 353 observations for the window against 504 for the full history, and an unknown instrument raises a clear error instead of returning an empty array.

**Schema-enforced results.** `write_result_parquet` writes an eleven-column schema — scalar metrics plus the full loss distribution as a list of doubles — compressed with Snappy. A string where a double belongs raises `ArrowInvalid` rather than silently writing a corrupt column.

### pyvar-arch-storage

**Deterministic cache keys that fail open.** The Redis key is a SHA-256 over the canonical request:

```
pyvar:market-risk:1571b407126e7a7abae19b1c373fb14512aa276ef914e4718ef1579983527096
same fields, other order      → same key
other confidence level        → different key
other domain                  → different key
Redis unreachable             → None  (a cache miss, never an error)
```

Equivalent requests share one cached result, different requests never collide, and an unreachable cache degrades to a miss instead of failing the request.

**Large results go to S3.** Above 10,000 simulations the worker writes the full result to S3 as Parquet. A 200,000-path run becomes a single-row object of about 2.1 MB at `results/abcdef12/abcdef12-3456-7890-abcd-ef1234567890.parquet` holding all 200,000 loss values, and what travels through the result backend is the key. `hydrate_presigned_url` turns that key into a time-limited link at the moment a client asks, so the link is never stale. (This example runs against a mocked S3.)

### pyvar-arch-observability

**Validation at the edge.** Bad input is stopped by the Pydantic schema before a job exists:

```
confidence_level 0.5 → 422  "Confidence level 0.5 is outside conventional range
                              [0.90, 0.9999]. Standard values: 0.95 (internal),
                              0.99 (Basel III), 0.975 (FRTB ES)."
10 observations      → 422  "List should have at least 30 items after validation, not 10"
a NaN in the returns → 422  "Value error, Returns series contains NaN or infinite values."
```

Each error carries the field location, so a client can point at the offending parameter. The same rule covers all 385 function endpoints: a NaN or Infinity anywhere in a request body — as a bare token or as the string `"nan"` — is a 422 naming the field.

**Prometheus metrics.** After three successful calls and one rejected one, `GET /metrics` shows the HTTP counters up by three 2xx and one 4xx — labelled with the route template, not the raw URL — and the domain metrics around the engine call:

```
http_requests_total{handler="/api/v1/credit-risk/expected_loss_el_computation",method="POST",status="2xx"} +3
http_requests_total{handler="/api/v1/credit-risk/expected_loss_el_computation",method="POST",status="4xx"} +1
pyvar_computation_duration_seconds_count{confidence_level="0.99",horizon_days="1"} 1
pyvar_simulation_count_sum 50000
```

The computation histogram is labelled by confidence level and horizon — the shape a Grafana panel of latency per simulation size is built on.

## Part three: pyvar-mcp

The MCP server turns the whole catalogue into Claude Code tools. These examples start the real server over stdio and point it at a pyvar API.

**Discovering the catalogue.** The server advertises 387 tools: one named tool per function (385) plus `list_pyvar_functions` and `call_pyvar_function`. Listing the ALM domain returns 33 functions, each with its summary and required parameters:

```
list_pyvar_functions(domain="alm")
→ alm_stress_test  — "Run an ALM stress test: worst-case EVE decline vs Tier-1 capital."
                     required: net_cashflows, times, base_rates, tier1_capital
```

The model finds the right function without holding 385 schemas in context.

**Calling a function — and what mistakes look like.** The generic tool and the named tool return the same result:

```
call_pyvar_function(domain="credit-risk", function_name="expected_loss_el_computation",
                    params={"pd": 0.02, "lgd": 0.45, "ead": 1000000})
→ {"el": 9000.0, "el_rate": 0.009, "pd": 0.02, "lgd": 0.45, "ead": 1000000.0}
```

Mistakes come back as readable tool results the model can act on:

```
missing a parameter → "Missing required parameter(s) for expected_loss_el_computation: ead.
                       Expected params: ead, lgd, pd."
pd = 1.7            → "pyvar API error (HTTP 422): {"detail":"pd must be in [0, 1]"}"
unknown function    → "Unknown function 'no_such_function' in domain 'alm'.
                       Use list_pyvar_functions to see valid names."
```

A missing parameter is caught before any request is made; an out-of-range value is rejected by the API; an unknown name points the model back to the listing.

## Reproduce every number

All twenty-eight examples, with their complete requests and responses, are in `docs/plugin-examples.md`, generated by one script from the repository root:

```bash
python scripts/generate_plugin_examples.py
```

It runs the real application, the real modules and the real MCP server on synthetic data (`ingestion.fixtures`), mocks AWS with moto, and produces identical output on every run.

---

## Sources

- [`docs/plugin-examples.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/plugin-examples.md) — all twenty-eight examples with full requests and responses.
- [`scripts/generate_plugin_examples.py`](https://github.com/fibtecltd/pyvar/blob/master/scripts/generate_plugin_examples.py) — the generator.
- [`.claude-plugin/marketplace.json`](https://github.com/fibtecltd/pyvar/blob/master/.claude-plugin/marketplace.json) — the fourteen plugins.
- [`plugins/`](https://github.com/fibtecltd/pyvar/tree/master/plugins) — the domain skills, architecture skills and the `pyvar-mcp` server.
- [`portal/functions.json`](https://github.com/fibtecltd/pyvar/blob/master/portal/functions.json) — the 385-function catalogue behind the endpoints and the MCP tools.
