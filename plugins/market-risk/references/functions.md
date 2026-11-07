# pyvar Market Risk: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/market-risk/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## VaR Models

### historical_simulation_var

`POST /api/v1/market-risk/historical_simulation_var`: Non-parametric Historical Simulation VaR.

Re-prices the portfolio under each observed historical return and reads the
empirical loss quantile — making no distributional assumption.

Formula (LaTeX): `VaR_\alpha = L_{(\lfloor \alpha n\rfloor)},\quad CVaR_\alpha = \frac{1}{n-\lfloor \alpha n\rfloor}\sum_{i=\lfloor \alpha n\rfloor}^{n-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns (fraction, not pct). |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999], e.g. 0.99. |

### filtered_historical_simulation_var

`POST /api/v1/market-risk/filtered_historical_simulation_var`: Filtered Historical Simulation VaR (Barone-Adesi & Giannopoulos).

Standardises returns by their EWMA conditional volatility, then re-scales
the standardised residuals by the *current* volatility forecast before
taking the empirical quantile. This captures volatility clustering that
plain historical simulation ignores.

Formula (LaTeX): `\sigma_t^2=\lambda\sigma_{t-1}^2+(1-\lambda)r_{t-1}^2,\quad z_t=r_t/\sigma_t \\ \sigma_{fcst}^2=\lambda\sigma_T^2+(1-\lambda)r_T^2,\quad \tilde r_t=\sigma_{fcst}\,z_t \\ VaR_\alpha,\ ES_\alpha = \text{tail-mean of } \{-\tilde r_t\}\text{ at }\alpha`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |
| `lambda_decay` | `number` | `0.94` | EWMA decay factor (RiskMetrics default 0.94). |

### parametric_delta_normal_var

`POST /api/v1/market-risk/parametric_delta_normal_var`: Variance-covariance (delta-normal) VaR.

Assumes asset returns are jointly normal so portfolio loss is normal with
standard deviation ``sqrt(w' Σ w)``. VaR is the scaled normal quantile.

Formula (LaTeX): `VaR_\alpha = z_\alpha\sqrt{w^\top\Sigma w}\,\sqrt{h}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required | Portfolio weights per asset (need not sum to 1). |
| `cov_matrix`* | `number[] or number[][]` | required | Asset return covariance matrix (per-period). |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |
| `horizon_days` | `integer` | `1` | Risk horizon in trading days (sqrt-time scaling). |

### cornish_fisher_var

`POST /api/v1/market-risk/cornish_fisher_var`: Cornish-Fisher (modified) VaR.

Expands the Gaussian quantile with the third and fourth moments so the VaR
reflects skewness and fat tails. When skewness and excess kurtosis are both
zero it collapses exactly to the parametric delta-normal VaR.

Formula (LaTeX): `z_{CF} = z_\alpha + \frac{z_\alpha^2-1}{6}S + \frac{z_\alpha^3-3z_\alpha}{24}K - \frac{2z_\alpha^3-5z_\alpha}{36}S^2 \\ VaR_\alpha = z_{CF}\,\sigma - \mu`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |
| `skewness` | `number or null` | `None` | Override sample skewness (computed from data if None). |
| `excess_kurtosis` | `number or null` | `None` | Override sample excess kurtosis (computed if None). |

### component_var

`POST /api/v1/market-risk/component_var`: Component VaR via Euler allocation.

Allocates total VaR to each position as ``w_i * marginal_i``. Because VaR is
homogeneous of degree 1 in the weights, the components sum exactly to the
total VaR (Euler's theorem) — the property regulators require for a
coherent risk decomposition.

Formula (LaTeX): `VaR_i = z_\alpha\,\frac{w_i(\Sigma w)_i}{\sigma_p},\quad \sigma_p=\sqrt{w^\top\Sigma w},\quad VaR=\sum_i VaR_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required | Portfolio weights per asset. |
| `cov_matrix`* | `number[] or number[][]` | required | Asset return covariance matrix. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |

### marginal_var

`POST /api/v1/market-risk/marginal_var`: Marginal VaR — sensitivity of portfolio VaR to each position weight.

For the delta-normal model VaR = z * sqrt(w' Σ w), the marginal VaR is the
gradient ``∂VaR/∂w_i = z * (Σ w)_i / sigma_p``.

Formula (LaTeX): `\frac{\partial VaR}{\partial w_i} = z_\alpha\,\frac{(\Sigma w)_i}{\sigma_p},\quad \sigma_p=\sqrt{w^\top\Sigma w}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required | Portfolio weights per asset. |
| `cov_matrix`* | `number[] or number[][]` | required | Asset return covariance matrix. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |

### incremental_var

`POST /api/v1/market-risk/incremental_var`: Incremental VaR of a single position.

The exact (non-marginal) effect of a position on portfolio VaR:
``VaR(full) − VaR(portfolio with position i removed)``.

Formula (LaTeX): `IVaR_i = z_\alpha\sqrt{w^\top\Sigma w} - z_\alpha\sqrt{w_{(-i)}^\top\Sigma w_{(-i)}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required | Portfolio weights per asset. |
| `cov_matrix`* | `number[] or number[][]` | required | Asset return covariance matrix. |
| `position_index`* | `integer` | required | Index of the position whose contribution is measured. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |

### var_by_risk_factor

`POST /api/v1/market-risk/var_by_risk_factor`: Decompose VaR across systematic risk factors (Euler allocation).

Identical Euler decomposition to :func:`component_var` but expressed in
risk-factor space: given portfolio factor exposures ``b`` and factor
covariance ``F``, the factor contribution is
``z * b_i * (F b)_i / sigma_p`` and contributions sum to the total VaR.

Formula (LaTeX): `VaR_i = z_\alpha\,\frac{b_i(Fb)_i}{\sigma_p},\quad \sigma_p=\sqrt{b^\top F b}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `factor_exposures`* | `number[] or number[][]` | required | Portfolio sensitivity (beta) to each risk factor. |
| `factor_cov`* | `number[] or number[][]` | required | Risk-factor covariance matrix. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |
| `factor_names` | `string[] or null` | `None` | Optional labels; defaults to ``factor_0, factor_1, ...``. |

### var_fan_chart

`POST /api/v1/market-risk/var_fan_chart`: VaR fan chart — parametric VaR bands across confidence levels and horizons.

Produces, for each confidence level, the VaR projected over 1..H days using
square-root-of-time volatility scaling — the standard visualisation of how
the loss envelope widens with the holding period.

Formula (LaTeX): `VaR_\alpha(h) = z_\alpha\sigma\sqrt{h} - \mu h,\quad h = 1,\dots,H`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_levels` | `number[]` | `[0.9, 0.95, 0.99]` | Confidence levels for the fan bands (each in [0.90, 0.9999]). |
| `horizon_days` | `integer` | `10` | Maximum projection horizon in trading days. |

### compute_loss_percentiles

`POST /api/v1/market-risk/compute_loss_percentiles`: Returns a dict of {percentile_label: loss_value} for fan chart display.

Default percentiles cover the standard regulatory range.

Formula (LaTeX): `Q_p = L_{\big(\min(\lfloor p\,n\rfloor,\ n-1)\big)} \quad \text{for each } p \in \text{percentiles}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `sorted_losses`* | `number[] or number[][]` | required | Portfolio losses sorted ascending (a loss is a positive number). |
| `percentiles` | `number[] or null` | `None` | Quantile levels between 0 and 1 to report. Defaults to 0.50, 0.75, 0.90, 0.95, 0.99 and 0.995. |

### extreme_value_theory_var

`POST /api/v1/market-risk/extreme_value_theory_var`: Extreme Value Theory VaR via Peaks-Over-Threshold (Generalised Pareto).

Fits a Generalised Pareto Distribution to losses exceeding a high threshold
u and reads the tail quantile::

    VaR_p = u + (β/ξ) · [ ((n/N_u)(1−p))^{−ξ} − 1 ]

capturing tail behaviour beyond the empirical sample range.

Formula (LaTeX): `VaR_p = u + \frac{\beta}{\xi}\left[\Big(\tfrac{n}{N_u}(1-p)\Big)^{-\xi} - 1\right],\ \xi\neq0 \\ VaR_p = u - \beta\ln\Big(\tfrac{n}{N_u}(1-p)\Big),\ \xi\approx0`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of portfolio returns. |
| `threshold_quantile` | `number` | `0.95` | Loss quantile defining the POT threshold (e.g. 0.95). |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999], above the threshold. |

## Expected Shortfall

### conditional_var_es

`POST /api/v1/market-risk/conditional_var_es`: Conditional VaR (Expected Shortfall) from a return series.

The FRTB IMA capital metric is ES at 97.5% (hence the default). ES is the
mean loss conditional on exceeding the VaR threshold and is always >= VaR.

Formula (LaTeX): `VaR_\alpha = L_{(\lfloor \alpha n\rfloor)},\quad ES_\alpha = \frac{1}{n-\lfloor \alpha n\rfloor}\sum_{i=\lfloor \alpha n\rfloor}^{n-1} L_{(i)} \\ L_{(i)} = \text{ascending-sorted losses } (-r_t),\quad ES_{abs}=ES_\alpha\cdot V`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.975` | ES confidence in [0.90, 0.9999]; FRTB uses 0.975. |

### compute_cvar

`POST /api/v1/market-risk/compute_cvar`: Conditional VaR (Expected Shortfall) — mean of losses beyond VaR threshold.

Regulatory standard under Basel III / FRTB for market risk capital.

Formula (LaTeX): `ES_\alpha = \frac{1}{n-\lfloor\alpha n\rfloor}\sum_{i=\lfloor\alpha n\rfloor}^{n-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `sorted_losses`* | `number[] or number[][]` | required | Portfolio losses sorted ascending (a loss is a positive number), so the largest losses are at the end. |
| `confidence_level`* | `number` | required | Confidence level that sets where the tail starts, for example 0.99 (0.90 to 0.9999 at the API). The result is the mean of the losses from position floor(confidence_level x n) of the sorted array to its end. |

### historical_expected_shortfall

`POST /api/v1/market-risk/historical_expected_shortfall`: Non-parametric historical Expected Shortfall.

Identical tail-mean definition as :func:`conditional_var_es` but framed as
the historical-simulation ES: no distributional assumption, the empirical
tail is averaged directly.

Formula (LaTeX): `VaR_\alpha = L_{(\lfloor \alpha n\rfloor)},\quad ES_\alpha = \frac{1}{n-\lfloor \alpha n\rfloor}\sum_{i=\lfloor \alpha n\rfloor}^{n-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.975` | ES confidence in [0.90, 0.9999]. |

### monte_carlo_expected_shortfall

`POST /api/v1/market-risk/monte_carlo_expected_shortfall`: Monte Carlo Expected Shortfall.

Runs the parametric-normal Monte Carlo engine and reads the ES (CVaR) from
the simulated loss distribution. Deterministic for a fixed seed.

Internally this delegates to ``engine.montecarlo.run_monte_carlo_var`` and
returns its ``cvar_pct``/``cvar_abs`` fields; the simulation's mean and
volatility (mu, sigma) are fitted directly from the ``returns`` argument,
not supplied as separate distribution parameters.

Formula (LaTeX): `P\&L_i = \sum_{t=1}^{h}(\mu+\sigma z_{i,t}),\ z_{i,t}\sim N(0,1),\quad L_i=-P\&L_i \\ ES_\alpha = \frac{1}{N-\lfloor\alpha N\rfloor}\sum_{i=\lfloor\alpha N\rfloor}^{N-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns (fits mu, sigma). |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.975` | ES confidence in [0.90, 0.9999]. |
| `n_simulations` | `integer` | `100000` | Number of Monte Carlo paths. |
| `horizon_days` | `integer` | `1` | Risk horizon in trading days. |
| `seed` | `integer or null` | `42` | RNG seed for reproducibility. |

### cvar_decomposition_euler

`POST /api/v1/market-risk/cvar_decomposition_euler`: Euler decomposition of Gaussian Expected Shortfall.

Under the normal model ES = sigma_p * φ(z) / (1 − α). ES is homogeneous of
degree 1 in the weights, so component ES_i = w_i * (Σ w)_i / sigma_p *
φ(z)/(1 − α) and the components sum exactly to total ES (Euler's theorem).

Formula (LaTeX): `ES_\alpha = \sigma_p\cdot\frac{\phi(z_\alpha)}{1-\alpha},\quad \sigma_p=\sqrt{w^\top\Sigma w},\ z_\alpha=\Phi^{-1}(\alpha) \\ ES_i = \frac{w_i(\Sigma w)_i}{\sigma_p}\cdot\frac{\phi(z_\alpha)}{1-\alpha},\quad \sum_i ES_i = ES_\alpha`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required | Portfolio weights per asset. |
| `cov_matrix`* | `number[] or number[][]` | required | Asset return covariance matrix. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.975` | ES confidence in [0.90, 0.9999]. |

### stressed_expected_shortfall

`POST /api/v1/market-risk/stressed_expected_shortfall`: Stressed Expected Shortfall (FRTB IMA).

FRTB requires ES to be calibrated to a historical period of significant
financial stress. This computes ES over the supplied stressed window
``returns[stress_start:stress_end]`` only.

Formula (LaTeX): `W = \text{returns}[\text{stress\_start}:\text{stress\_end}] \\ ES_\alpha^{stress} = \frac{1}{|W|-\lfloor\alpha|W|\rfloor}\sum_{i=\lfloor\alpha|W|\rfloor}^{|W|-1} L_{(i)}^{W}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | Full 1-D array of historical portfolio returns. |
| `stress_start`* | `integer` | required | Inclusive start index of the stressed window. |
| `stress_end`* | `integer` | required | Exclusive end index of the stressed window. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.975` | ES confidence in [0.90, 0.9999]; FRTB uses 0.975. |

### liquidity_adjusted_es

`POST /api/v1/market-risk/liquidity_adjusted_es`: Liquidity-adjusted Expected Shortfall (FRTB IMA, MAR33.12).

Scales the base-horizon ES up for risk factors that take longer than the
base liquidity horizon T to unwind::

    ES = sqrt( ES_base^2 + Σ_{j>=2} ( ES_j * sqrt((LH_j − LH_{j-1}) / T) )^2 )

where ``ES_base`` is the whole-portfolio ES at horizon T, and ``ES_j`` is the
ES with respect to factors in liquidity bucket j and longer.

Formula (LaTeX): `ES_{LA} = \sqrt{ ES_{base}^2 + \sum_{j=2}^{K} \Big( ES_j \sqrt{\tfrac{LH_j-LH_{j-1}}{T}} \Big)^2 }`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `es_base`* | `number` | required | Whole-portfolio ES at the base horizon T. |
| `partial_es`* | `number[]` | required | ``ES_j`` for buckets j = 2..K (length K-1). |
| `liquidity_horizons`* | `number[]` | required | Liquidity horizons ``LH_1..LH_K`` (length K, with ``LH_1 == base_horizon`` and non-decreasing). |
| `base_horizon` | `number` | `10.0` | Base liquidity horizon T in days (FRTB uses 10). |

### es_at_multiple_confidence_levels

`POST /api/v1/market-risk/es_at_multiple_confidence_levels`: Expected Shortfall evaluated at several confidence levels at once.

Useful for limit dashboards that report internal (95%), FRTB (97.5%) and
Basel (99%) ES side by side. ES is monotone non-decreasing in confidence.

Formula (LaTeX): `ES_{\alpha_k} = \frac{1}{n-\lfloor \alpha_k n\rfloor}\sum_{i=\lfloor \alpha_k n\rfloor}^{n-1} L_{(i)} \quad \text{for each } \alpha_k \in \text{confidence\_levels}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of historical portfolio returns. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_levels` | `number[]` | `[0.95, 0.975, 0.99]` | Confidence levels (each in [0.90, 0.9999]). |

### expected_shortfall_contribution

`POST /api/v1/market-risk/expected_shortfall_contribution`: Per-asset ES contribution by conditional expectation in the tail.

Each asset's ES contribution is its average loss across exactly the
scenarios where the *portfolio* breaches VaR. By construction the
contributions sum to total ES (the additive allocation FRTB expects).

Formula (LaTeX): `L_t = -\sum_i a_{t,i}w_i,\quad T_\alpha=\{t : L_t \text{ among the } n-\lfloor\alpha n\rfloor \text{ largest losses}\} \\ ES_i = \frac{1}{|T_\alpha|}\sum_{t\in T_\alpha}\big(-a_{t,i}w_i\big),\quad ES=\sum_i ES_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_returns`* | `number[] or number[][]` | required | ``(T, N)`` matrix of per-asset returns over T scenarios. |
| `weights`* | `number[] or number[][]` | required | Length-N portfolio weights. |
| `portfolio_value`* | `number` | required | Current portfolio value in base currency. |
| `confidence_level` | `number` | `0.975` | ES confidence in [0.90, 0.9999]. |

### spectral_risk_measure

`POST /api/v1/market-risk/spectral_risk_measure`: Spectral risk measure with an exponential risk-aversion spectrum.

A coherent risk measure that integrates the loss quantile against a
decreasing risk-spectrum ``φ(p) = k·e^{−k(1−p)} / (1−e^{−k})``, placing more
weight on the tail as the risk aversion k rises. SRM >= the mean loss and is
increasing in k.

Formula (LaTeX): `SRM = \sum_{i=1}^{n} w_i\,L_{(i)},\quad w_i=\frac{\phi(p_i)}{\sum_j \phi(p_j)},\ \phi(p)=\frac{k\,e^{-k(1-p)}}{1-e^{-k}},\ p_i=\frac{i-0.5}{n}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of portfolio returns. |
| `risk_aversion` | `number` | `25.0` | Risk-aversion coefficient k > 0 (higher = more tail-weighted). |

## Stress Testing

### historical_scenario_replay

`POST /api/v1/market-risk/historical_scenario_replay`: Replay historical factor moves against the current portfolio.

Applies each historical day's factor returns to the current exposures and
reports the resulting P&L path, identifying the single worst day.

Formula (LaTeX): `PnL_t = \sum_f h_{t,f}\,e_f,\quad worst = \min_t PnL_t`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required | Length-F currency P&L per unit move of each risk factor. |
| `historical_factor_returns`* | `number[] or number[][]` | required | ``(T, F)`` matrix of historical factor moves. |

### hypothetical_multi_factor_scenario

`POST /api/v1/market-risk/hypothetical_multi_factor_scenario`: P&L under a single hypothetical multi-factor shock.

First-order P&L = Σ exposure_i * shock_i. Used for ad-hoc "what if" scenarios
such as a simultaneous equity sell-off and rates spike.

Formula (LaTeX): `PnL = \sum_i e_i\,s_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required | Length-F currency P&L per unit factor move. |
| `shocks`* | `number[] or number[][]` | required | Length-F factor shocks (same units as the historical moves). |

### reverse_stress_testing

`POST /api/v1/market-risk/reverse_stress_testing`: Reverse stress test — find the most plausible scenario causing a target loss.

Among all factor shocks producing the given loss, the most plausible (lowest
Mahalanobis magnitude under the factor covariance) lies along ``-Σ e``. The
closed-form solution for loss L is ``s* = -(L / e'Σe) · Σ e`` with magnitude
``m = L / sqrt(e'Σe)``.

Formula (LaTeX): `s^{*} = -\frac{L}{e^\top\Sigma e}\,\Sigma e,\quad m=\frac{L}{\sqrt{e^\top\Sigma e}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required | Length-F currency P&L per unit factor move. |
| `factor_cov`* | `number[] or number[][]` | required | ``(F, F)`` factor covariance matrix (SPD). |
| `target_loss`* | `number` | required | Desired loss magnitude (positive number). |

### sensitivity_stress_profile

`POST /api/v1/market-risk/sensitivity_stress_profile`: One-factor sensitivity stress profile.

Sweeps a single risk factor across a grid of shocks (holding others flat)
and returns the P&L profile — the building block of a stress "ladder".

Formula (LaTeX): `PnL(s) = e_k\cdot s,\quad s\in\text{shock\_grid}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required | Length-F currency P&L per unit factor move. |
| `factor_index`* | `integer` | required | Index of the factor to stress. |
| `shock_grid`* | `number[] or number[][]` | required | 1-D grid of shock values to apply to that factor. |

### sector_stress_scenario

`POST /api/v1/market-risk/sector_stress_scenario`: Sector-level stress scenario.

Applies a shock to each sector's net exposure and aggregates. Total P&L is
the exact sum of per-sector P&L (additivity by construction).

Formula (LaTeX): `PnL_{total}=\sum_i e_i\,s_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `sector_exposures`* | `number[] or number[][]` | required | Currency P&L per unit move, per sector. |
| `sector_shocks`* | `number[] or number[][]` | required | Shock applied to each sector. |
| `sector_names` | `string[] or null` | `None` | Optional sector labels; default ``sector_0, ...``. |

### macro_scenario_generator

`POST /api/v1/market-risk/macro_scenario_generator`: Generate correlated macro factor scenarios via the Cholesky factor.

Draws standard-normal innovations in pure Python (CLAUDE.md §3.1 RULE 3) and
colours them with the Cholesky factor of the supplied covariance so the
generated scenarios reproduce the target factor correlation structure.

Formula (LaTeX): `scenarios = Z\,L^\top,\quad L=\text{chol}(\Sigma),\ Z_{i,\cdot}\sim N(0,I)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `factor_cov`* | `number[] or number[][]` | required | ``(F, F)`` macro-factor covariance matrix (SPD). |
| `n_scenarios` | `integer` | `10000` | Number of scenarios to generate. |
| `seed` | `integer or null` | `42` | RNG seed for reproducibility (None = non-deterministic). |

### contagion_stress_scenario

`POST /api/v1/market-risk/contagion_stress_scenario`: Propagate an initial shock through a contagion (spillover) network.

Each round, the current shock spills to connected nodes via the contagion
matrix C; the cumulative shock is ``shock + C·shock + C²·shock + ...`` over
the requested rounds — a truncated Neumann series of the spillover operator.

Formula (LaTeX): `shock_{cum} = \sum_{k=0}^{R} C^k x_0`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `initial_shock`* | `number[] or number[][]` | required | Length-N initial shock per node/asset. |
| `contagion_matrix`* | `number[] or number[][]` | required | ``(N, N)`` spillover coefficients (C[i, j] = effect of node j on node i). |
| `rounds` | `integer` | `3` | Number of propagation rounds (``0`` returns the initial shock). |

## Greeks & Sensitivities

### gamma_cross_gamma_matrix

`POST /api/v1/market-risk/gamma_cross_gamma_matrix`: Assemble the portfolio gamma / cross-gamma matrix.

The diagonal holds each underlying's net gamma (∂²V/∂S_i²); off-diagonals
hold cross-gammas (∂²V/∂S_i∂S_j). The matrix is symmetric (Schwarz's
theorem) — gamma P&L for a shock vector ds is ``0.5 · ds' G ds``.

Formula (LaTeX): `G_{ii}=\gamma_i,\quad G_{ij}=\tfrac12\big(\Gamma^{cross}_{ij}+\Gamma^{cross}_{ji}\big)\ (i\neq j) \\ \text{Gamma P\&L} = \tfrac12\,ds^\top G\,ds`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `own_gammas`* | `number[] or number[][]` | required | Length-U net gamma per underlying (matrix diagonal). |
| `cross_gammas` | `number[] or number[][] or null` | `None` | Optional ``(U, U)`` cross-gamma matrix; its off-diagonal entries are symmetrised into the result. Diagonal is ignored. |

### vega_surface_bucketed

`POST /api/v1/market-risk/vega_surface_bucketed`: Aggregate option vegas onto a bucketed (expiry × strike) surface.

Each option's vega is summed into its (expiry, strike) bucket. Total vega is
conserved — the surface sum equals the input vega sum.

Formula (LaTeX): `Surface_{e,s} = \sum_{k:\,expiry_k=e,\ strike_k=s} vega_k,\quad \sum_{e,s} Surface_{e,s} = \sum_k vega_k`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `vegas`* | `number[] or number[][]` | required | Per-option vega (∂V/∂σ). |
| `expiry_buckets`* | `number[] or number[][]` | required | Per-option expiry bucket index in ``[0, n_expiry)``. |
| `strike_buckets`* | `number[] or number[][]` | required | Per-option strike bucket index in ``[0, n_strike)``. |
| `n_expiry`* | `integer` | required | Number of expiry buckets. |
| `n_strike`* | `integer` | required | Number of strike buckets. |

### dv01_pv01_bucketed

`POST /api/v1/market-risk/dv01_pv01_bucketed`: Tenor-bucketed DV01 / PV01 of a fixed cashflow stream.

For continuously-discounted cashflows ``PV = Σ cf_k e^{-y t_k}`` the DV01 of
each cashflow (price change for a +1bp yield move) is
``cf_k · t_k · e^{-y t_k} · 1e-4``. Cashflows are summed into tenor buckets;
the bucket DV01s sum exactly to the total.

Formula (LaTeX): `PV = \sum_k cf_k e^{-y t_k},\quad DV01 = 10^{-4}\sum_k cf_k\,t_k\,e^{-y t_k}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required | Cashflow amounts. |
| `times`* | `number[] or number[][]` | required | Cashflow times in years. |
| `flat_yield`* | `number` | required | Flat continuously-compounded discount yield. |
| `bucket_indices`* | `number[] or number[][]` | required | Tenor bucket index per cashflow in ``[0, n_buckets)``. |
| `n_buckets`* | `integer` | required | Number of tenor buckets. |

### cs01_credit_spread

`POST /api/v1/market-risk/cs01_credit_spread`: CS01 — sensitivity of a risky cashflow stream to a +1bp credit spread move.

Cashflows are discounted at ``r + s``; CS01 is
``Σ cf_k · t_k · e^{-(r+s) t_k} · 1e-4`` — the price drop for a 1bp widening
of the credit spread.

Formula (LaTeX): `CS01 = 10^{-4}\sum_k cf_k\,t_k\,e^{-(r+s)t_k}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required | Cashflow amounts. |
| `times`* | `number[] or number[][]` | required | Cashflow times in years. |
| `risk_free_rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `credit_spread`* | `number` | required | Continuously-compounded credit spread. |

### rho_interest_rate

`POST /api/v1/market-risk/rho_interest_rate`: Black-Scholes Rho — option value sensitivity to the interest rate.

``Rho_call = K τ e^{-rτ} N(d2)``; ``Rho_put = -K τ e^{-rτ} N(-d2)``.

Formula (LaTeX): `\rho_{call}=K\tau e^{-r\tau}N(d_2),\quad \rho_{put}=-K\tau e^{-r\tau}N(-d_2)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required | Underlying spot price. |
| `strike`* | `number` | required | Strike price. |
| `rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `sigma`* | `number` | required | Volatility (annualised). |
| `tau`* | `number` | required | Time to maturity in years. |
| `option_type` | `string` | `'call'` | ``"call"`` or ``"put"``. |
| `div_yield` | `number` | `0.0` | Continuous dividend yield. |

### theta_time_decay

`POST /api/v1/market-risk/theta_time_decay`: Black-Scholes Theta — calendar time decay (∂V/∂calendar = −∂V/∂τ), per year.

Formula (LaTeX): `\Theta_{call} = -\frac{Se^{-q\tau}\phi(d_1)\sigma}{2\sqrt\tau} - rKe^{-r\tau}N(d_2) + qSe^{-q\tau}N(d_1) \\ \Theta_{put} = -\frac{Se^{-q\tau}\phi(d_1)\sigma}{2\sqrt\tau} + rKe^{-r\tau}N(-d_2) - qSe^{-q\tau}N(-d_1)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required | Underlying spot price. |
| `strike`* | `number` | required | Strike price. |
| `rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `sigma`* | `number` | required | Volatility (annualised). |
| `tau`* | `number` | required | Time to maturity in years. |
| `option_type` | `string` | `'call'` | ``"call"`` or ``"put"``. |
| `div_yield` | `number` | `0.0` | Continuous dividend yield. |

### charm_delta_decay

`POST /api/v1/market-risk/charm_delta_decay`: Charm — sensitivity of delta to time to maturity (∂Δ/∂τ).

Computed in the time-to-maturity convention so that a finite-difference of
delta with respect to τ reproduces this value. Note the sign: this is
+∂Δ/∂τ (time-to-maturity), the opposite sign from the calendar-time charm
convention −∂Δ/∂t (decay per day of calendar time elapsed) more commonly
quoted on trading desks and in textbooks — do not assume the calendar-time
sign without checking which convention a comparison source uses.

Formula (LaTeX): `\frac{\partial d_1}{\partial\tau} = \frac{b}{\sigma\sqrt\tau} - \frac{a+b\tau}{2\sigma\tau\sqrt\tau},\ a=\ln(S/K),\ b=r-q+\tfrac12\sigma^2 \\ Charm_{call} = -qe^{-q\tau}N(d_1) + e^{-q\tau}\phi(d_1)\tfrac{\partial d_1}{\partial\tau} \\ Charm_{put} = qe^{-q\tau}N(-d_1) + e^{-q\tau}\phi(d_1)\tfrac{\partial d_1}{\partial\tau}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required | Underlying spot price. |
| `strike`* | `number` | required | Strike price. |
| `rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `sigma`* | `number` | required | Volatility (annualised). |
| `tau`* | `number` | required | Time to maturity in years. |
| `option_type` | `string` | `'call'` | ``"call"`` or ``"put"``. |
| `div_yield` | `number` | `0.0` | Continuous dividend yield. |

### volga_vega_convexity

`POST /api/v1/market-risk/volga_vega_convexity`: Volga (vomma) — convexity of value in volatility (∂²V/∂σ² = ∂vega/∂σ).

``Volga = vega · d1 · d2 / σ``. Identical for calls and puts. Positive volga
means the position is long volatility-of-volatility.

Formula (LaTeX): `vega = Se^{-q\tau}\phi(d_1)\sqrt\tau,\quad Volga = vega\cdot\frac{d_1 d_2}{\sigma}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required | Underlying spot price. |
| `strike`* | `number` | required | Strike price. |
| `rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `sigma`* | `number` | required | Volatility (annualised). |
| `tau`* | `number` | required | Time to maturity in years. |
| `div_yield` | `number` | `0.0` | Continuous dividend yield. |

### vanna_delta_vega_cross

`POST /api/v1/market-risk/vanna_delta_vega_cross`: Vanna — cross sensitivity ∂vega/∂S = ∂Δ/∂σ.

``Vanna = −e^{-qτ} · φ(d1) · d2 / σ``. Identical for calls and puts. It
measures how delta drifts as volatility moves (and vice versa).

Formula (LaTeX): `Vanna = -e^{-q\tau}\phi(d_1)\frac{d_2}{\sigma}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required | Underlying spot price. |
| `strike`* | `number` | required | Strike price. |
| `rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `sigma`* | `number` | required | Volatility (annualised). |
| `tau`* | `number` | required | Time to maturity in years. |
| `div_yield` | `number` | `0.0` | Continuous dividend yield. |

### portfolio_delta_aggregated

`POST /api/v1/market-risk/portfolio_delta_aggregated`: Aggregate per-position deltas into a net portfolio delta.

Net delta = Σ delta_i * quantity_i. When spot prices are supplied the
cash (dollar) delta Σ delta_i * quantity_i * spot_i is also returned.

Formula (LaTeX): `\Delta_{net}=\sum_i \delta_i q_i,\quad \Delta_{cash}=\sum_i \delta_i q_i S_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `deltas`* | `number[] or number[][]` | required | Per-position option delta (∂V/∂S). |
| `quantities`* | `number[] or number[][]` | required | Signed position size per instrument. |
| `spot_prices` | `number[] or number[][] or null` | `None` | Optional underlying spot per position for cash delta. |

## P&L Attribution

### pnl_attribution_test_frtb_pat

`POST /api/v1/market-risk/pnl_attribution_test_frtb_pat`: FRTB P&L Attribution Test (PAT) — Spearman correlation and ratio test.

Jointly evaluates the Spearman rank correlation between risk-theoretical P&L
(RTPL) and hypothetical P&L (HPL) and the volatility ratio
``std(RTPL)/std(HPL)``, assigning the Basel traffic-light zone. These
thresholds are set by the Basel Committee and are not parameterised.

Formula (LaTeX): `\rho_s = \text{Spearman}(RTPL, HPL),\quad ratio = \frac{\sigma(RTPL)}{\sigma(HPL)} \\ \text{zone}=\begin{cases}\text{green} & |\rho_s|\ge0.80 \text{ and } 0.8\le ratio\le1.2\\ \text{amber} & |\rho_s|\ge0.70 \text{ and } 0.6\le ratio\le1.5\\ \text{red} & \text{otherwise}\end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `risk_theoretical_pnl`* | `number[] or number[][]` | required | Daily RTPL series (model-based). |
| `hypothetical_pnl`* | `number[] or number[][]` | required | Daily HPL series (full-revaluation). |

### theta_carry_attribution

`POST /api/v1/market-risk/theta_carry_attribution`: Theta / carry attribution.

Isolates the deterministic time-decay (carry) component of P&L,
``theta · dt``, optionally net of a funding cost over the same period.

Formula (LaTeX): `\text{Carry PnL} = \Theta\,dt - FC`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `theta`* | `number` | required | Portfolio theta (∂V/∂t, per the same unit as ``time_step``). |
| `time_step`* | `number` | required | Elapsed time dt. |
| `funding_cost` | `number` | `0.0` | Funding cost accrued over the period (currency). |

### gamma_pnl_attribution

`POST /api/v1/market-risk/gamma_pnl_attribution`: Gamma (convexity) P&L component: ``½ · Γ · dS²``.

Formula (LaTeX): `PnL_\Gamma = \tfrac12\,\Gamma\,(dS)^2`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `gamma`* | `number` | required | Portfolio gamma (∂²V/∂S²). |
| `spot_move`* | `number` | required | Realised underlying move dS. |

### vega_pnl_attribution

`POST /api/v1/market-risk/vega_pnl_attribution`: Vega P&L component: ``ν · dσ``.

Formula (LaTeX): `PnL_\nu = \nu\,d\sigma`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `vega`* | `number` | required | Portfolio vega (∂V/∂σ). |
| `vol_move`* | `number` | required | Realised volatility move dσ. |

### fx_pnl_attribution

`POST /api/v1/market-risk/fx_pnl_attribution`: FX P&L attribution across currency pairs.

Total FX P&L = Σ fx_delta_i · dFX_i, additive across currencies.

Formula (LaTeX): `PnL_{FX} = \sum_i \delta_i^{FX}\cdot \Delta FX_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `fx_deltas`* | `number[] or number[][]` | required | P&L per unit move of each FX rate. |
| `fx_moves`* | `number[] or number[][]` | required | Realised move in each FX rate. |
| `currency_names` | `string[] or null` | `None` | Optional labels; default ``ccy_0, ...``. |

### rates_pnl_attribution

`POST /api/v1/market-risk/rates_pnl_attribution`: Interest-rate P&L attribution by key-rate tenor.

Total rates P&L = Σ sensitivity_t · dyield_bp_t, where each sensitivity is
P&L per +1bp move at that tenor. Additive across the key-rate ladder.

Formula (LaTeX): `PnL_{rates} = \sum_t s_t\cdot \Delta y_t^{bp}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `key_rate_sensitivities`* | `number[] or number[][]` | required | P&L per +1bp move at each tenor. |
| `yield_moves_bp`* | `number[] or number[][]` | required | Realised yield move (in basis points) at each tenor. |
| `tenor_names` | `string[] or null` | `None` | Optional labels; default ``tenor_0, ...``. |

### credit_pnl_attribution

`POST /api/v1/market-risk/credit_pnl_attribution`: Credit P&L attribution by issuer / curve.

Total credit P&L = Σ cs01_i · dspread_bp_i, additive across credit names.

Formula (LaTeX): `PnL_{credit} = \sum_i CS01_i\cdot \Delta s_i^{bp}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cs01_sensitivities`* | `number[] or number[][]` | required | P&L per +1bp credit-spread move per name. |
| `spread_moves_bp`* | `number[] or number[][]` | required | Realised spread move (basis points) per name. |
| `name_labels` | `string[] or null` | `None` | Optional labels; default ``name_0, ...``. |

### residual_pnl_unexplained

`POST /api/v1/market-risk/residual_pnl_unexplained`: Unexplained (residual) P&L.

Residual = actual P&L − Σ explained components. The residual plus the sum of
explained components reconstructs the actual P&L exactly; a large residual
relative to actual P&L flags model incompleteness (an FRTB PAT concern).

Formula (LaTeX): `Residual = PnL_{actual} - \sum_i C_i,\quad ratio = \frac{\sum_i C_i}{PnL_{actual}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `actual_pnl`* | `number` | required | Observed (hypothetical) P&L for the period. |
| `explained_components`* | `number[] or number[][]` | required | The individual explained P&L components. |

### greeks_based_pnl_explain

`POST /api/v1/market-risk/greeks_based_pnl_explain`: Second-order Greeks P&L explain.

Predicted P&L = Δ·dS + ½Γ·dS² + ν·dσ + Θ·dt + ρ·dr. The unexplained residual
is ``actual_pnl − predicted`` — the quantity the FRTB PAT scrutinises.

Formula (LaTeX): `PnL_{pred} = \Delta\,dS + \tfrac12\Gamma\,dS^2 + \nu\,d\sigma + \Theta\,dt + \rho\,dr \\ Unexplained = PnL_{actual} - PnL_{pred}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `delta`* | `number` | required | Portfolio delta (∂V/∂S). |
| `gamma`* | `number` | required | Portfolio gamma (∂²V/∂S²). |
| `vega`* | `number` | required | Portfolio vega (∂V/∂σ). |
| `theta`* | `number` | required | Portfolio theta (∂V/∂t, per the same time unit as ``time_step``). |
| `rho`* | `number` | required | Portfolio rho (∂V/∂r). |
| `spot_move`* | `number` | required | Realised underlying move dS. |
| `vol_move`* | `number` | required | Realised volatility move dσ. |
| `time_step`* | `number` | required | Elapsed time dt. |
| `rate_move`* | `number` | required | Realised rate move dr. |
| `actual_pnl`* | `number` | required | Observed (hypothetical) P&L for the period. |

## Backtesting

### traffic_light_backtesting

`POST /api/v1/market-risk/traffic_light_backtesting`: Basel traffic-light backtest over the 250-day window.

Counts VaR breaches and assigns the Basel zone: green (< 5 breaches), yellow
(5-9), red (>= 10). These boundaries are set by the Basel Committee.

Formula (LaTeX): `n_{breaches}=\sum_{t=1}^{N}\mathbb{1}\big[-r_t > VaR_t\big],\quad \text{zone}=\begin{cases}\text{green} & n_{breaches}<5\\ \text{yellow} & 5\le n_{breaches}\le 9\\ \text{red} & n_{breaches}\ge 10\end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `actual_returns`* | `number[] or number[][]` | required | Realised returns over the backtest window. |
| `var_estimates`* | `number[] or number[][]` | required | VaR estimate (positive loss) aligned to each return. |

### compute_breaches

`POST /api/v1/market-risk/compute_breaches`: Backtesting: count days where actual loss exceeded VaR estimate.

Basel traffic-light zones:
  Green  < 5 breaches / 250 days
  Yellow 5-9 breaches
  Red    >= 10 breaches

Formula (LaTeX): `n_{breaches}=\sum_t \mathbb{1}[-r_t > VaR_t],\quad \text{zone}=\begin{cases}\text{green} & n<5\\ \text{yellow} & 5\le n\le9\\ \text{red} & n\ge10\end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `actual_returns`* | `number[] or number[][]` | required | Realised returns as decimals, aligned one to one with `var_estimates` (a loss is the negative of a return). |
| `var_estimates`* | `number[] or number[][]` | required | The VaR estimate for each day, as a positive loss fraction. Days where it is NaN are ignored, as the first `window` days of a rolling VaR are. |

### kupiec_pof_test

`POST /api/v1/market-risk/kupiec_pof_test`: Kupiec Proportion-of-Failures (POF) unconditional coverage test.

Likelihood-ratio test that the observed breach rate matches the expected
``p = 1 − confidence_level``. The statistic is chi-squared with 1 dof;
rejection uses the 95% critical value.

At the boundary cases ``x = 0`` or ``x = n`` (zero or 100% observed breach
rate) the likelihood ratio is computed with a simplified one-sided form to
avoid ``ln(0)``; the general two-sided expression applies for ``0 < x < n``.

Formula (LaTeX): `LR_{POF} = -2\Big[(n-x)\ln(1-p) + x\ln p - (n-x)\ln(1-\hat\pi) - x\ln\hat\pi\Big], \\ p = 1-\alpha,\ \hat\pi = x/n`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `n_breaches`* | `integer` | required | Number of VaR breaches observed. |
| `n_observations`* | `integer` | required | Number of backtest observations. |
| `confidence_level` | `number` | `0.99` | VaR confidence level the breaches were measured at. |

### christoffersen_independence_test

`POST /api/v1/market-risk/christoffersen_independence_test`: Christoffersen independence (clustering) test.

Likelihood-ratio test that breaches are serially independent (no
clustering), via a first-order Markov transition model. Chi-squared with
1 dof at the 95% critical value.

The four transition counts (n00, n01, n10, n11) that drive the likelihood
ratio are derived internally from the ``breaches`` sequence itself, not
supplied as separate arguments.

Formula (LaTeX): `LR_{ind} = -2\Big[ n_{00}\ln(1-\pi) + n_{01}\ln\pi + n_{10}\ln(1-\pi) + n_{11}\ln\pi \\ \qquad - n_{00}\ln(1-\pi_{01}) - n_{01}\ln\pi_{01} - n_{10}\ln(1-\pi_{11}) - n_{11}\ln\pi_{11} \Big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `breaches`* | `number[] or number[][]` | required | Binary breach sequence (1 = breach, 0 = no breach). |

### combined_backtesting

`POST /api/v1/market-risk/combined_backtesting`: Combined (conditional coverage) backtest: Kupiec + Christoffersen.

The Christoffersen conditional-coverage statistic ``LR_cc = LR_POF + LR_ind``
is chi-squared with 2 dof, tested at the 95% critical value. It rejects a
model that either mis-counts or clusters its breaches.

Formula (LaTeX): `LR_{cc} = LR_{POF}(x,n,\alpha) + LR_{ind}(b_t) \ \sim\ \chi^2_{2}\ \text{at the 95\% critical value}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `breaches`* | `number[] or number[][]` | required | Binary breach sequence (1 = breach, 0 = no breach). |
| `confidence_level` | `number` | `0.99` | VaR confidence level the breaches were measured at. |

### basel_capital_addon_multiplier

`POST /api/v1/market-risk/basel_capital_addon_multiplier`: Basel capital add-on multiplier from the backtest breach count.

Green zone (< 5 breaches) → 3.0; yellow zone (5-9) → the BCBS graduated
schedule (3.40 .. 3.85); red zone (>= 10) → 4.0. These values are set by the
Basel Committee (CLAUDE.md §4.3).

Formula (LaTeX): `m(n) = \begin{cases} 3.00 & n < 5 \\ 3.40,\,3.50,\,3.65,\,3.75,\,3.85 & n = 5,6,7,8,9\ \text{(BCBS schedule)} \\ 4.00 & n \geq 10 \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `n_breaches`* | `integer` | required | Number of breaches in the 250-day backtest. |

### rolling_var_backtest

`POST /api/v1/market-risk/rolling_var_backtest`: Rolling-window VaR backtest over the Basel 250-day window.

Estimates parametric VaR on each trailing window and counts breaches of the
realised next-day return, returning the Basel traffic-light zone.

Formula (LaTeX): `VaR_t = -\big(\mu_{t-w:t} - z_\alpha\,\sigma_{t-w:t}\big),\quad z_\alpha=\Phi^{-1}(\alpha) \\ n_{breaches}=\sum_{t}\mathbb{1}[-r_t > VaR_t],\quad \text{zone: green}<5,\ \text{yellow}\ 5\text{-}9,\ \text{red}\ge10`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | Full return history. |
| `window` | `integer` | `250` | Rolling estimation window (Basel standard 250 trading days). |
| `confidence_level` | `number` | `0.99` | VaR confidence in [0.90, 0.9999]. |

### compute_rolling_var

`POST /api/v1/market-risk/compute_rolling_var`: Parametric (Gaussian) rolling VaR using a fixed-length trailing window.

At each point, mean and volatility are estimated from only the most recent
`window` observations (returns[i - window : i]), not an expanding window
that grows from the start of the series.
Fast approximation for backtesting — not the full Monte Carlo.
Uses scipy.stats.norm for the quantile function.

Returns array of VaR estimates, same length as returns (NaN for first window obs).

Formula (LaTeX): `VaR_t = -\big(\mu_{t-w:t} - z_\alpha\sigma_{t-w:t}\big),\quad z_\alpha=\Phi^{-1}(\alpha)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | Periodic returns as decimals (a 1% fall is -0.01), oldest first. |
| `window` | `integer` | `250` | Number of most recent observations used to estimate the mean and volatility at each point. The first `window` entries of the result are NaN. |
| `confidence_level` | `number` | `0.99` | Confidence level of the Gaussian VaR, for example 0.99 (0.90 to 0.9999 at the API). |

### var_breach_cluster_analysis

`POST /api/v1/market-risk/var_breach_cluster_analysis`: Analyse the clustering of VaR breaches.

Reports the number of breach clusters (maximal runs of consecutive
breaches), the longest run, and the mean run length — diagnostics for the
independence assumption that the Christoffersen test formalises.

This is an algorithmic run-length computation over the breach sequence,
not a closed-form statistic.

Formula (LaTeX): `\text{clusters} = \{\text{maximal runs of consecutive } b_t=1\} \\ n_{clusters}=|\text{clusters}|, \quad \max\_len=\max_i \text{len}(run_i), \\ \overline{len}=\frac{1}{n_{clusters}}\sum_i \text{len}(run_i)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `breaches`* | `number[] or number[][]` | required | Binary breach sequence (1 = breach, 0 = no breach). |

## Volatility & Correlation

### garch_11_volatility_forecast

`POST /api/v1/market-risk/garch_11_volatility_forecast`: GARCH(1,1) conditional-volatility filter and multi-step forecast.

Filters the conditional variance and projects it forward. The h-step
forecast mean-reverts to the long-run variance ``ω/(1−α−β)`` at rate
``(α+β)`` — the defining property of a stationary GARCH(1,1). If ``omega`` is
not supplied it is set by variance targeting, ``ω = (1−α−β)·Var(returns)``.

Formula (LaTeX): `\sigma_t^2=\omega+\alpha\varepsilon_{t-1}^2+\beta\sigma_{t-1}^2 \\ \sigma_{T+k}^2 = \sigma_\infty^2 + (\alpha+\beta)^k\big(\sigma_{T+1}^2-\sigma_\infty^2\big),\quad \sigma_\infty^2=\frac{\omega}{1-\alpha-\beta}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D return series (demeaned internally to form residuals). |
| `alpha` | `number` | `0.1` | ARCH coefficient (weight on the last squared shock). |
| `beta` | `number` | `0.85` | GARCH coefficient (weight on the last variance). |
| `omega` | `number or null` | `None` | Long-run variance constant; variance-targeted if None. |
| `horizon` | `integer` | `10` | Forecast horizon in periods. |

### egarch_volatility_model

`POST /api/v1/market-risk/egarch_volatility_model`: EGARCH(1,1) asymmetric volatility model (Nelson 1991).

Models log-variance, so conditional variance is positive for any parameters.
The leverage term ``gamma`` makes negative shocks raise volatility more than
positive shocks of equal size (when ``gamma < 0``).

Formula (LaTeX): `\ln\sigma_t^2 = \omega+\beta\ln\sigma_{t-1}^2+\alpha\big(|z_{t-1}|-\sqrt{2/\pi}\big)+\gamma z_{t-1},\quad z_{t-1}=\frac{\varepsilon_{t-1}}{\sigma_{t-1}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D return series (demeaned internally). |
| `omega` | `number` | `-0.1` | Log-variance intercept. |
| `alpha` | `number` | `0.1` | Magnitude (\|z\|) coefficient. |
| `gamma` | `number` | `-0.05` | Leverage coefficient (negative => negative shocks raise vol more). |
| `beta` | `number` | `0.95` | Log-variance persistence (\|beta\| < 1 for stationarity). |

### gjr_garch_asymmetric_model

`POST /api/v1/market-risk/gjr_garch_asymmetric_model`: GJR-GARCH(1,1) asymmetric volatility model (Glosten-Jagannathan-Runkle).

A leverage indicator adds ``gamma`` to the ARCH coefficient when the prior
shock was negative, so (for ``gamma > 0``) downside shocks raise volatility
more. The long-run variance is ``ω/(1 − α − β − γ/2)``.

Formula (LaTeX): `\sigma_t^2 = \omega + (\alpha+\gamma\,\mathbb{1}[\varepsilon_{t-1}<0])\varepsilon_{t-1}^2+\beta\sigma_{t-1}^2,\quad \sigma_\infty^2=\frac{\omega}{1-\alpha-\beta-\gamma/2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D return series (demeaned internally). |
| `alpha` | `number` | `0.03` | Symmetric ARCH coefficient. |
| `gamma` | `number` | `0.08` | Asymmetry coefficient applied to negative shocks. |
| `beta` | `number` | `0.88` | GARCH persistence coefficient. |
| `omega` | `number or null` | `None` | Variance intercept; variance-targeted if None. |

### realised_volatility

`POST /api/v1/market-risk/realised_volatility`: Realised volatility from a block of (typically high-frequency) returns.

Realised variance is the sum of squared returns; realised volatility is its
square root, and the annualised figure scales by ``sqrt(annualisation_factor)``.

Formula (LaTeX): `RV=\sum_t r_t^2,\quad \sigma_{RV}=\sqrt{RV},\quad \sigma_{ann}=\sigma_{RV}\sqrt{m}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of returns over the measurement block. |
| `annualisation_factor` | `integer` | `252` | Periods per year for annualisation (e.g. 252). |

### correlation_matrix_historical

`POST /api/v1/market-risk/correlation_matrix_historical`: Historical (Pearson) correlation matrix of asset returns.

Formula (LaTeX): `\rho_{ij} = \frac{\mathrm{Cov}(r_i,r_j)}{\sigma_i\sigma_j}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns_matrix`* | `number[] or number[][]` | required | ``(T, N)`` matrix of T observations on N assets. |

### dcc_garch_dynamic_correlation

`POST /api/v1/market-risk/dcc_garch_dynamic_correlation`: DCC-GARCH dynamic conditional correlation (Engle 2002), terminal R_T.

Standardises each series, then evolves the quasi-correlation
``Q_t = (1−a−b) Q̄ + a z_{t-1} z_{t-1}' + b Q_{t-1}`` and normalises to a
correlation matrix. With ``a = b = 0`` it collapses to the constant
unconditional correlation Q̄.

Formula (LaTeX): `Q_t = (1-a-b)\bar Q + a\,z_{t-1}z_{t-1}^\top + b\,Q_{t-1} \\ R_t = D_t^{-1}Q_tD_t^{-1},\quad D_t=\mathrm{diag}(\sqrt{Q_{t,ii}})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns_matrix`* | `number[] or number[][]` | required | ``(T, N)`` matrix of T observations on N assets. |
| `a` | `number` | `0.02` | DCC news coefficient. |
| `b` | `number` | `0.95` | DCC persistence coefficient (require a + b < 1). |

### risk_factor_pca_decomposition

`POST /api/v1/market-risk/risk_factor_pca_decomposition`: Principal-component decomposition of the risk-factor covariance.

Eigen-decomposes the factor covariance matrix and orders components by
descending variance. The explained-variance ratios sum to 1 (over all
components) and the eigenvalues are non-negative (covariance is PSD).

Formula (LaTeX): `\Sigma = V\Lambda V^\top,\quad EVR_k=\frac{\lambda_k}{\sum_j\lambda_j}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns_matrix`* | `number[] or number[][]` | required | ``(T, N)`` matrix of T observations on N risk factors. |
| `n_components` | `integer or null` | `None` | Number of leading components to return (all if None). |

### volatility_surface_implied_vol

`POST /api/v1/market-risk/volatility_surface_implied_vol`: Back out the implied-volatility surface from market option prices.

For each quoted option the Black-Scholes equation is inverted for implied
volatility by bisection. Round-tripping (pricing at the recovered IV)
reproduces the input price.

Formula (LaTeX): `\sigma_{IV} : C_{BS}(S,K,r,\sigma_{IV},\tau) = P_{market}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `market_prices`* | `number[] or number[][]` | required | Observed option prices. |
| `strikes`* | `number[] or number[][]` | required | Strike of each option. |
| `expiries`* | `number[] or number[][]` | required | Time to expiry (years) of each option. |
| `spot`* | `number` | required | Underlying spot price. |
| `rate`* | `number` | required | Continuously-compounded risk-free rate. |
| `option_type` | `string` | `'call'` | ``"call"`` or ``"put"``. |

## FRTB Capital

### frtb_sa_residual_risk_addon

`POST /api/v1/market-risk/frtb_sa_residual_risk_addon`: FRTB SA Residual Risk Add-On (RRAO).

A simple notional-based add-on for instruments with residual risks not
captured by the SBM: ``RRAO = Σ notional_i · weight_i`` (MAR23, e.g. 1.0% on
exotic underlyings, 0.1% otherwise).

Formula (LaTeX): `RRAO = \sum_i notional_i \cdot w_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notionals`* | `number[] or number[][]` | required | Gross notional per instrument. |
| `rrao_weights`* | `number[] or number[][]` | required | RRAO risk weight per instrument. |

### frtb_ima_expected_shortfall

`POST /api/v1/market-risk/frtb_ima_expected_shortfall`: FRTB IMA Expected Shortfall (the regulatory ES at 97.5%).

ES is the mean loss beyond the VaR threshold at the FRTB confidence of
97.5% (CLAUDE.md §4.2) and is always >= VaR.

Formula (LaTeX): `VaR_\alpha = L_{(\lfloor \alpha n\rfloor)},\quad ES_\alpha = \frac{1}{n-\lfloor \alpha n\rfloor}\sum_{i=\lfloor \alpha n\rfloor}^{n-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | 1-D array of portfolio returns over the IMA observation set. |
| `confidence_level` | `number` | `0.975` | ES confidence; FRTB IMA uses 0.975. |

### frtb_ima_stressed_period_finder

`POST /api/v1/market-risk/frtb_ima_stressed_period_finder`: Locate the FRTB IMA stressed period — the worst 250-day ES window.

FRTB calibrates the stressed ES to the historical window of greatest stress.
This slides a 250-day window and returns the start index whose Expected
Shortfall is largest.

Formula (LaTeX): `start^{*} = \arg\max_{s}\ ES_\alpha\big(r_{s:s+w}\big)\quad\text{(tail-mean ES over each sliding window)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required | Full return history. |
| `window` | `integer` | `250` | Stress window length (FRTB standard 250 trading days). |
| `confidence_level` | `number` | `0.975` | ES confidence used to rank windows (0.975). |

### frtb_ima_non_modellable_risk_factors

`POST /api/v1/market-risk/frtb_ima_non_modellable_risk_factors`: FRTB IMA non-modellable risk factor (NMRF) capital — aggregate SES.

Aggregates per-factor stressed capital add-ons (ISES) as
``SES = sqrt( (ρ·Σ ISES)² + (1−ρ²)·Σ ISES² )`` (MAR33.16). With ρ = 0 this is
the Euclidean sum; with ρ = 1 it is the linear (fully correlated) sum.

Formula (LaTeX): `SES = \sqrt{(\rho\textstyle\sum_i ISES_i)^2 + (1-\rho^2)\sum_i ISES_i^2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `individual_ses`* | `number[] or number[][]` | required | Per-factor stressed capital add-ons (ISES). |
| `rho` | `number` | `0.0` | Prescribed correlation across NMRFs in [0, 1]. |

### frtb_ima_aggregate_capital_charge

`POST /api/v1/market-risk/frtb_ima_aggregate_capital_charge`: FRTB IMA aggregate capital charge.

Combines the internally-modelled capital charge (IMCC, from ES), the
non-modellable SES add-on, and the default risk charge (MAR33.43):
``ACC = IMCC + SES + DRC``.

Formula (LaTeX): `ACC = IMCC + SES + DRC`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `imcc`* | `number` | required | Internally-modelled capital charge (ES-based). |
| `ses`* | `number` | required | Aggregate non-modellable risk factor capital (SES). |
| `default_risk_charge` | `number` | `0.0` | Default risk charge (DRC). |

### frtb_sa_sensitivity_based_method

`POST /api/v1/market-risk/frtb_sa_sensitivity_based_method`: FRTB SA Sensitivities-Based Method (delta) risk charge.

Within each bucket the risk position is
``Kb = sqrt(Σ WS_i² + Σ_{i≠j} ρ·WS_i·WS_j)``; the charge aggregates buckets
as ``sqrt(Σ Kb² + Σ_{b≠c} γ·S_b·S_c)`` with ``S_b = Σ_i WS_i`` (MAR21).

Both the per-bucket ``Kb²`` term and the aggregate sum under the final
square root are floored at 0 before the square root is taken, guarding
against a negative value under extreme correlation inputs — a safeguard
not shown in the MAR21 formula above.

Formula (LaTeX): `K_b = \sqrt{\sum_i WS_i^2 + \rho\sum_{i\neq j} WS_i WS_j} \\ \text{Risk Charge} = \sqrt{\sum_b K_b^2 + \gamma\sum_{b\neq c} S_b S_c},\quad S_b=\sum_i WS_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `bucket_weighted_sensitivities`* | `number[][]` | required | Per-bucket lists of weighted sensitivities (risk weight already applied). |
| `intra_bucket_corr`* | `number` | required | Correlation ρ between sensitivities within a bucket. |
| `inter_bucket_corr`* | `number` | required | Correlation γ between bucket totals. |

### frtb_sa_default_risk_charge

`POST /api/v1/market-risk/frtb_sa_default_risk_charge`: FRTB SA Default Risk Charge (DRC) with the hedge-benefit ratio.

Net jump-to-default per issuer is risk-weighted; the gross short charge is
scaled by the Weighted-to-Short (hedge benefit) ratio
``WtS = Σ netLong / (Σ netLong + Σ|netShort|)`` (MAR22). DRC is floored at 0.

Formula (LaTeX): `net_i = JTD^{long}_i - JTD^{short}_i \\ WtS = \frac{\sum_{net_i>0} net_i}{\sum_{net_i>0} net_i + \sum_{net_i<0}|net_i|} \\ DRC = \max\Big(0,\ \sum_{net_i>0} RW_i\,net_i - WtS\sum_{net_i<0} RW_i\,|net_i|\Big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `jtd_long`* | `number[] or number[][]` | required | Long jump-to-default exposure per issuer. |
| `jtd_short`* | `number[] or number[][]` | required | Short jump-to-default exposure per issuer (positive numbers). |
| `risk_weights`* | `number[] or number[][]` | required | Default risk weight per issuer. |
