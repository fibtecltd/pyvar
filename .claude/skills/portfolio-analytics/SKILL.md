---
name: pyvar-portfolio-analytics
description: >
  Run pyvar's 50 portfolio-analytics functions on the live pyvar.com API: Markowitz,
  Black-Litterman and risk-parity optimisation, Sharpe/Sortino/drawdown, Brinson attribution,
  Fama-French factor models, PCA and regime detection, ESG tilts. Use when the user wants a
  portfolio optimised, attributed or measured with real numbers, not just the method
  explained. Needs a free pyvar API key; the skill explains how to get one.
version: "1.1.0"
author: "Fibtec Limited — pyvar.com"
tags: [portfolio, optimisation, markowitz, black-litterman, risk-parity, sharpe, attribution, brinson, factor-model, FF5, PCA, HMM, ESG]
---

# pyvar — Portfolio Analytics  (50 functions)

Portfolio calculations: optimisation, risk-adjusted performance, attribution, factor models, active-risk analytics, ESG and drawdown. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs a pyvar API key. Don't substitute your own numpy/scipy code and present the result
as pyvar output: these are regulatory-grade functions and the user wants pyvar's own numbers.

1. **Find the key.** Look for `PYVAR_API_KEY` in the environment. If the pyvar MCP server is
   connected, its tools (`call_pyvar_function`, `list_pyvar_functions`) already carry the key.
2. **No key? Say so, and walk the user through getting one** (free, about a minute): open
   https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when it is shown) or enter an email and
   click the verification link (valid 24 hours, single use). The page shows the key once. Ask the
   user to copy it and set `PYVAR_API_KEY`. Keys are short-lived (60 minutes by default). On a
   `401 Invalid or expired token`, ask for a fresh one: Google sign-in issues a new key every time,
   whereas the emailed link cannot be reused, so an address that cannot sign in with Google has to
   register a different email.
3. **Call the function** with the request body below (every example in this skill is a real,
   tested request). Use whichever of these is available:
   - Python: `pip install pyvar-client`, then
     `Client(api_key=os.environ["PYVAR_API_KEY"]).portfolio.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/portfolio/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="portfolio", function_name="<function>", params=body)`.
   If you cannot run code or reach the network (for example a sandbox with no internet), give the
   user the exact `curl` command or Python snippet to run themselves instead of guessing a result.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. Minimum-variance and risk-parity weights on one covariance matrix

A three-asset daily covariance matrix (the optimisers expect daily, not annual, covariance). Both calls return weights that sum to 1.

`POST /api/v1/portfolio/minimum_variance_portfolio`

```json
{
  "cov_matrix": [[0.04, 0.006, 0.002], [0.006, 0.0225, 0.004], [0.002, 0.004, 0.01]]
}
```

Returns: `weights`, `return`, `volatility`, `sharpe`.

`POST /api/v1/portfolio/risk_parity_portfolio`

```json
{
  "cov_matrix": [[0.04, 0.006, 0.002], [0.006, 0.0225, 0.004], [0.002, 0.004, 0.01]]
}
```

Returns: `weights`, `return`, `volatility`, `sharpe`, `risk_contributions`.

### 2. Sharpe ratio and maximum drawdown over two years

Daily returns in, annualised Sharpe and the worst peak-to-trough fall out.

`POST /api/v1/portfolio/sharpe_ratio`

```json
{
  "returns": [ /* your 504 daily log-returns */ ],
  "risk_free": 0.02,
  "periods_per_year": 252
}
```

Returns: `sharpe`, `sharpe_period`, `mean_excess`, `volatility`, `periods_per_year`, `ddof`.

`POST /api/v1/portfolio/maximum_drawdown`

```json
{
  "returns": [ /* your 504 daily log-returns */ ]
}
```

Returns: `max_drawdown`, `peak_index`, `trough_index`, `n_obs`.

## Functions (50)

Every function is `POST /api/v1/portfolio/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in [references/functions.md](references/functions.md): read the entry before calling a function you have not used yet.

### Portfolio Optimisation

- `mean_variance_optimisation(mean_returns, cov_matrix, risk_aversion=1.0, allow_short=False, risk_free=0.0, periods_per_year=252)`: Mean-variance (Markowitz) optimisation.
- `minimum_variance_portfolio(cov_matrix, allow_short=False, mean_returns=None, risk_free=0.0, periods_per_year=252)`: Global minimum-variance portfolio.
- `maximum_sharpe_ratio_portfolio(mean_returns, cov_matrix, risk_free=0.0, allow_short=False, periods_per_year=252)`: Maximum Sharpe ratio (tangency) portfolio.
- `risk_parity_portfolio(cov_matrix, mean_returns=None, risk_free=0.0, periods_per_year=252)`: Equal risk contribution (risk parity) portfolio.
- `equal_weight_portfolio(n_assets, mean_returns=None, cov_matrix=None, risk_free=0.0, periods_per_year=252)`: Equal-weight (1/N) portfolio.
- `black_litterman_model(market_weights, cov_matrix, p_matrix, q_views, risk_aversion=2.5, tau=0.05, omega=None)`: Black-Litterman posterior expected returns and weights.
  Note: Verified exact match to He & Litterman (1999) conventions: Omega=diag(P*tau*Sigma*P'), lambda=delta=2.5, tau=0.05 are their specific default choices. Takes p_matrix/q_views directly (no natural-language view parsing) and returns posterior_returns, implied_returns and weights — NOT the weights/return/volatility/sharpe shape used by the mean-variance-family functions below.
- `resampled_efficient_frontier(mean_returns, cov_matrix, n_resamples=50, n_obs=250, seed=2024)`: Resampled efficient frontier (Michaud) minimum-variance point.
- `robust_portfolio_optimisation(mean_returns, cov_matrix, uncertainty=0.05, risk_aversion=1.0, periods_per_year=252)`: Robust mean-variance optimisation with a box uncertainty set on means.
- `cvar_constrained_optimisation(scenario_returns, mean_returns=None, confidence_level=0.95, cvar_limit=0.05, periods_per_year=252)`: CVaR-constrained portfolio optimisation (Rockafellar-Uryasev).
- `factor_based_optimisation(factor_exposures, factor_cov, specific_var, target_exposures=None, periods_per_year=252)`: Factor-based minimum-risk optimisation.
- `rebalancing_optimiser(current_weights, target_weights, cost_bps, no_trade_band=0.0, asset_volatility=None, risk_aversion=None)`: Rebalancing optimiser with a no-trade band.
  Note: `no_trade_band` is a user-supplied absolute weight threshold, not one derived from cost/volatility parameters the way Leland (1999) or Donohue & Yip (2003) derive an optimal no-trade region. No published source reproduces this function's exact numbers — checked, not assumed (Tier 3 #2 audit).

### Risk-Adjusted Performance

- `sharpe_ratio(returns, risk_free=0.0, periods_per_year=252, ddof=0)`: Annualised Sharpe ratio.
- `sortino_ratio(returns, risk_free=0.0, target=0.0, periods_per_year=252)`: Annualised Sortino ratio.
- `calmar_ratio(returns, periods_per_year=252)`: Calmar ratio — annualised return over maximum drawdown.
- `information_ratio(returns, benchmark_returns, periods_per_year=252)`: Information ratio — active return over tracking error.
- `treynor_ratio(returns, benchmark_returns, risk_free=0.0, periods_per_year=252)`: Treynor ratio — annualised excess return per unit of systematic risk (beta).
- `jensens_alpha(returns, benchmark_returns, risk_free=0.0, periods_per_year=252)`: Jensen's alpha from the CAPM single-factor regression.
- `omega_ratio(returns, threshold=0.0)`: Omega ratio — probability-weighted gains over losses about a threshold.
- `maximum_drawdown(returns, is_equity_curve=False)`: Maximum drawdown — largest peak-to-trough decline.
- `average_drawdown(returns, is_equity_curve=False)`: Average drawdown — mean of the drawdown series magnitude.
- `drawdown_duration(returns, is_equity_curve=False)`: Drawdown duration — longest and current underwater run lengths.
- `conditional_drawdown_at_risk(returns, confidence_level=0.95, is_equity_curve=False)`: Conditional Drawdown at Risk (CDaR).
- `tail_ratio(returns, tail=0.05)`: Tail ratio — magnitude of the right tail relative to the left tail.
- `ulcer_index(returns, is_equity_curve=False)`: Ulcer Index — root-mean-square of percentage drawdowns from peak.

### Performance Attribution

- `return_attribution_brinson(portfolio_weights, benchmark_weights, portfolio_returns, benchmark_returns, segment_names=None)`: Brinson-Hood-Beebower return attribution.
- `factor_return_attribution(factor_exposures, factor_returns, specific_return, factor_names=None)`: Factor return attribution.
- `sector_attribution(portfolio_weights, benchmark_weights, portfolio_returns, benchmark_returns, sector_names=None)`: Sector attribution — Brinson allocation/selection grouped by sector.
- `currency_attribution(local_returns, fx_returns, weights, currency_names=None, local_risk_free=None, base_risk_free=None)`: Currency attribution -- naive geometric split, or genuine Karnosky-Singer.
  Note: Naive geometric local/FX split via base=(1+local)(1+fx)-1, with currency as the residual. This is NOT Karnosky-Singer (Karnosky & Singer 1994): that method needs local returns net of the local risk-free rate and moves the rate differential onto the currency leg via covered interest parity; this function takes no interest rates at all. A prior docstring claimed "Karnosky-Singer style" — corrected in the citation cleanup pass (engine/portfolio_attribution.py). See Bacon (2008), "Practical Portfolio Performance Measurement and Attribution", 2nd ed., Ch. 6, which presents this split as the baseline before Karnosky-Singer.
- `gics_sector_exposure(weights, sector_codes)`: GICS sector exposure aggregation.
- `factor_exposure_analysis_barra(asset_exposures, weights, factor_names=None)`: Barra-style portfolio factor exposure.

### Factor Models

- `fama_french_3_factor_model(excess_returns, factors)`: Fama-French 3-factor regression (MKT, SMB, HML).
- `carhart_4_factor_model(excess_returns, factors)`: Carhart 4-factor regression (MKT, SMB, HML, MOM).
- `fama_french_5_factor_model(excess_returns, factors)`: Fama-French 5-factor regression (MKT, SMB, HML, RMW, CMA).
- `principal_component_analysis(returns_matrix, n_components=None)`: Principal Component Analysis of an asset return matrix.
- `correlation_clustering(returns_matrix, n_clusters=2)`: Correlation-based clustering of assets.
- `regime_detection_hmm(returns, n_iter=50)`: Two-state Gaussian regime detection via EM.
  Note: Despite the name, this is a STATIONARY 2-component Gaussian mixture fitted by EM, not a hidden Markov model: there is no transition matrix, so regime persistence/switching probability is not modelled, only the marginal mixture. A genuine HMM (Hamilton 1989, Econometrica 57(2)) fits a Markov-switching autoregression with an explicit 2x2 transition matrix. Flagged in engine/portfolio_factor.py so the function name isn't mistaken for a claim of Markov-switching behaviour; renaming it is a larger, separate change than the docstring fix.

### Active Risk Analytics

- `portfolio_beta(returns, benchmark_returns)`: Portfolio beta — sensitivity of portfolio returns to the benchmark.
- `active_share(weights, benchmark_weights)`: Active share — fraction of holdings differing from the benchmark.
- `tracking_error(returns, benchmark_returns, periods_per_year=252)`: Tracking error — volatility of active (portfolio minus benchmark) return.
- `residual_risk(returns, benchmark_returns, periods_per_year=252)`: Residual (idiosyncratic) risk — volatility of single-factor regression residuals.
- `portfolio_turnover(weights_before, weights_after)`: Portfolio turnover — one-way traded fraction between two weight vectors.
- `transaction_cost_analysis(trade_prices, benchmark_prices, trade_quantities, side=1, decision_price=None, unexecuted_quantity=None, cancellation_price=None)`: Transaction Cost Analysis (TCA) — implementation shortfall vs benchmark.
  Note: Quantity-weighted slippage vs an arrival/VWAP benchmark, in bps. A narrower measure than Perold's full implementation-shortfall decomposition: no delay cost or unexecuted- share opportunity-cost leg. No published source reproduces this exact quantity — checked, not assumed (Tier 3 #2 audit).

### ESG & Sustainability

- `esg_score_integration(weights, esg_scores, min_esg_score=None, cov_matrix=None)`: ESG score integration — weighted score and optional ESG-constrained tilt.
- `carbon_footprint_attribution(weights, carbon_intensities, portfolio_value, asset_names=None, company_total_emissions=None, company_value=None)`: Carbon footprint attribution (WACI and financed emissions).
  Note: The WACI leg matches TCFD's definition exactly. The total_financed_emissions leg does NOT match either TCFD's or PCAF's financed-emissions standard: both use an ownership-share method, whereas this function uses revenue-intensity-times-invested-value. Flagged as a likely correctness question for the domain owner, not merely a citation gap (Tier 3 #2 audit).

### Portfolio Risk Analytics

- `liquidity_adjusted_portfolio_var(weights, cov_matrix, bid_ask_spreads, portfolio_value, confidence_level=0.99, horizon_days=1)`: Liquidity-adjusted parametric VaR (LVaR).
- `marginal_contribution_to_risk(weights, cov_matrix)`: Marginal and component contribution to portfolio volatility risk.
- `diversification_ratio(weights, cov_matrix)`: Diversification ratio — weighted average vol over portfolio vol.
- `correlation_matrix_portfolio(returns_matrix)`: Correlation matrix and average pairwise correlation of asset returns.
- `concentration_risk_hhi(weights)`: Concentration risk via the Herfindahl-Hirschman Index (HHI).
- `monte_carlo_portfolio_simulation(weights, mean_returns, cov_matrix, portfolio_value=1000000.0, horizon=10, n_simulations=10000, confidence_level=0.99, seed=12345)`: Monte Carlo portfolio simulation of terminal P&L.

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
