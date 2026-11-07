# pyvar Portfolio Analytics: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/portfolio/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Portfolio Optimisation

### mean_variance_optimisation

`POST /api/v1/portfolio/mean_variance_optimisation`: Mean-variance (Markowitz) optimisation.

Maximises ``w'μ - 0.5 * λ * w'Σw`` subject to weights summing to 1, with an
optional long-only constraint.

Formula (LaTeX): `\max_w\; w^\top \mu - \frac{1}{2}\lambda\, w^\top \Sigma w \quad \text{s.t. } \sum_i w_i = 1`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mean_returns`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `risk_aversion` | `number` | `1.0` |  |
| `allow_short` | `boolean` | `False` |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### minimum_variance_portfolio

`POST /api/v1/portfolio/minimum_variance_portfolio`: Global minimum-variance portfolio.

Minimises ``w'Σw`` subject to weights summing to 1. With shorting allowed
the closed-form solution ``Σ⁻¹1 / (1'Σ⁻¹1)`` is used; long-only uses SLSQP.

Formula (LaTeX): `\min_w\; w^\top \Sigma w \quad \text{s.t. } \sum_i w_i = 1 \\ w^{*} = \frac{\Sigma^{-1}\mathbf{1}}{\mathbf{1}^\top \Sigma^{-1}\mathbf{1}} \;\; \text{(closed form when shorting allowed)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `allow_short` | `boolean` | `False` |  |
| `mean_returns` | `number[] or number[][] or null` | `None` |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### maximum_sharpe_ratio_portfolio

`POST /api/v1/portfolio/maximum_sharpe_ratio_portfolio`: Maximum Sharpe ratio (tangency) portfolio.

Maximises the annualised Sharpe ratio subject to weights summing to 1.

Formula (LaTeX): `\max_w\; \frac{w^\top \mu - r_f/T}{\sqrt{w^\top \Sigma w}} \quad \text{s.t. } \sum_i w_i = 1`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mean_returns`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `risk_free` | `number` | `0.0` |  |
| `allow_short` | `boolean` | `False` |  |
| `periods_per_year` | `integer` | `252` |  |

### risk_parity_portfolio

`POST /api/v1/portfolio/risk_parity_portfolio`: Equal risk contribution (risk parity) portfolio.

Finds long-only weights so each asset contributes equally to portfolio
variance, by minimising the dispersion of risk contributions.

Dispersion is measured as the sum of squared pairwise differences
between all assets' risk contributions rather than each asset's
deviation from the mean contribution -- a stronger gradient signal for
SLSQP that converges to the same equal-risk-contribution solution.

Formula (LaTeX): `RC_i = w_i (\Sigma w)_i \\ \min_w\; \sum_{i=1}^{n}\sum_{j=1}^{n} (RC_i - RC_j)^2 \quad \text{s.t. } \sum_i w_i = 1,\; w_i \ge 10^{-6}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `mean_returns` | `number[] or number[][] or null` | `None` |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### equal_weight_portfolio

`POST /api/v1/portfolio/equal_weight_portfolio`: Equal-weight (1/N) portfolio.

Formula (LaTeX): `w_i = \frac{1}{N}, \quad i = 1,\dots,N`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `n_assets`* | `integer` | required |  |
| `mean_returns` | `number[] or number[][] or null` | `None` |  |
| `cov_matrix` | `number[] or number[][] or null` | `None` |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### black_litterman_model

`POST /api/v1/portfolio/black_litterman_model`: Black-Litterman posterior expected returns and weights.

Combines the CAPM-implied equilibrium returns ``Π = λ Σ w_mkt`` with
investor views ``P E[r] = Q`` to produce posterior expected returns and the
corresponding mean-variance weights.

Formula (LaTeX): `\Pi = \lambda \Sigma w_{mkt} \\ \Omega = \text{diag}\big(P(\tau\Sigma)P^\top\big) \;\; \text{(default)} \\ E[R] = \Big[(\tau\Sigma)^{-1} + P^\top\Omega^{-1}P\Big]^{-1}\Big[(\tau\Sigma)^{-1}\Pi + P^\top\Omega^{-1}Q\Big] \\ w^{*} = (\lambda\Sigma)^{-1} E[R]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `market_weights`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `p_matrix`* | `number[] or number[][]` | required |  |
| `q_views`* | `number[] or number[][]` | required |  |
| `risk_aversion` | `number` | `2.5` |  |
| `tau` | `number` | `0.05` |  |
| `omega` | `number[] or number[][] or null` | `None` |  |

### resampled_efficient_frontier

`POST /api/v1/portfolio/resampled_efficient_frontier`: Resampled efficient frontier (Michaud) minimum-variance point.

Bootstraps return samples from the estimated multivariate-normal, solves the
minimum-variance long-only portfolio on each resample, and averages the
weights — reducing estimation-error sensitivity. All randomness is pre-drawn
in pure Python (RULE 3).

Formula (LaTeX): `\hat\Sigma^{(k)} = \text{Cov}\big(\text{sample}^{(k)}\big), \;\; \text{sample}^{(k)} \sim \mathcal{N}(\mu, \Sigma, n_{obs}) \\ w^{(k)*} = \arg\min_w\; w^\top \hat\Sigma^{(k)} w \quad \text{s.t. } \sum_i w_i = 1,\; 0 \le w_i \le 1 \\ \bar w = \frac{1}{K}\sum_{k=1}^{K} w^{(k)*}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mean_returns`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `n_resamples` | `integer` | `50` |  |
| `n_obs` | `integer` | `250` |  |
| `seed` | `integer` | `2024` |  |

### robust_portfolio_optimisation

`POST /api/v1/portfolio/robust_portfolio_optimisation`: Robust mean-variance optimisation with a box uncertainty set on means.

Uses the worst-case expected return ``μ - κ·diag(Σ)^{1/2}`` within an
ellipsoidal/box uncertainty set (Tütüncü-Koenig style), then solves the
standard mean-variance problem — producing more conservative weights.

Formula (LaTeX): `\tilde\mu = \mu - \kappa \sqrt{\text{diag}(\Sigma)} \\ \max_w\; w^\top \tilde\mu - \frac{1}{2}\lambda\, w^\top \Sigma w \quad \text{s.t. } \sum_i w_i = 1,\; 0 \le w_i \le 1`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mean_returns`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `uncertainty` | `number` | `0.05` |  |
| `risk_aversion` | `number` | `1.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### cvar_constrained_optimisation

`POST /api/v1/portfolio/cvar_constrained_optimisation`: CVaR-constrained portfolio optimisation (Rockafellar-Uryasev).

Maximises expected return subject to the portfolio CVaR (at
``confidence_level``) not exceeding ``cvar_limit``, long-only and fully
invested. CVaR is computed empirically over the supplied scenarios.

Solved via Rockafellar & Uryasev's (2000) original auxiliary-variable
linear-programming reformulation, not a direct nonlinear CVaR
constraint. Introduce an auxiliary VaR estimate ``zeta`` and one
non-negative excess-loss variable ``u_s`` per scenario, then solve the
convex LP

    minimize    -mu^T w
    subject to  sum(w) = 1,  0 <= w_i <= 1
                zeta + (1/(S(1-alpha))) * sum_s u_s <= cvar_limit
                u_s >= -(scenario_s . w) - zeta,   u_s >= 0   (s=1..S)

via ``scipy.optimize.linprog`` (HiGHS). CVaR is a convex function of
``w`` and both this LP and the retired SLSQP-on-empirical-CVaR
formulation share the same feasible region and the same (convex)
objective, so they solve to the same global optimum — the LP just gets
there via Rockafellar-Uryasev's exact reformulation instead of SLSQP
re-evaluating the empirical quantile/tail-mean at every iterate.

Formula (LaTeX): `\min_{w,\zeta,u}\; -w^\top \mu \quad \text{s.t. } \sum_i w_i = 1,\; 0 \le w_i \le 1 \\ \zeta + \frac{1}{S(1-\alpha)}\sum_s u_s \le c, \quad u_s \ge L_s(w) - \zeta,\; u_s \ge 0 \\ L_s(w) = -R_s w, \quad CVaR_\alpha(w) = \zeta^* + \frac{1}{S(1-\alpha)}\sum_s u_s^*`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `scenario_returns`* | `number[] or number[][]` | required |  |
| `mean_returns` | `number[] or number[][] or null` | `None` |  |
| `confidence_level` | `number` | `0.95` |  |
| `cvar_limit` | `number` | `0.05` |  |
| `periods_per_year` | `integer` | `252` |  |

### factor_based_optimisation

`POST /api/v1/portfolio/factor_based_optimisation`: Factor-based minimum-risk optimisation.

Builds the asset covariance from a factor model
``Σ = B F Bᵀ + diag(specific_var)`` and finds the long-only fully-invested
minimum-variance portfolio, optionally matching ``target_exposures`` to the
factors via an equality constraint.

Formula (LaTeX): `\Sigma = B F B^\top + \text{diag}(\sigma^2_{spec}) \\ \min_w\; w^\top \Sigma w \quad \text{s.t. } \sum_i w_i = 1,\; 0 \le w_i \le 1 \;\; \big(\text{optionally } B^\top w = e_{tgt}\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `factor_exposures`* | `number[] or number[][]` | required |  |
| `factor_cov`* | `number[] or number[][]` | required |  |
| `specific_var`* | `number[] or number[][]` | required |  |
| `target_exposures` | `number[] or number[][] or null` | `None` |  |
| `periods_per_year` | `integer` | `252` |  |

### rebalancing_optimiser

`POST /api/v1/portfolio/rebalancing_optimiser`: Rebalancing optimiser with a no-trade band.

Computes the trades to move from current to target weights, suppressing
trades within a no-trade band to avoid churn, and reports turnover and
total transaction cost.

By default ``no_trade_band`` is a single user-supplied absolute weight
threshold applied uniformly to every asset (unchanged prior behaviour).
Supplying both ``asset_volatility`` and ``risk_aversion`` instead
*derives* a per-asset band from the classic Constantinides (1986) /
Davis & Norman (1990) asymptotic no-trade-region half-width — the
closed-form cube-root result that Leland's (1999) mean-variance
tracking-error approximation and Donohue & Yip's (2003) practitioner
rebalancing-band heuristic both build on:

    h_i = ( (3/4) * c_i * sigma_i^2 * w_i^tgt * (1 - w_i^tgt)^2 / gamma )^(1/3)

where ``c_i`` is the proportional transaction cost (``cost_bps_i /
1e4``), ``sigma_i`` is asset i's return volatility, ``w_i^tgt`` is asset
i's target weight (the frictionless-optimal allocation the band is
centred on) and ``gamma`` is the investor's (CRRA) risk-aversion
coefficient. The half-width widens with cost and volatility (cube-root
scaling) and narrows as risk aversion rises — more risk-averse investors
tolerate less drift before trading. This is the classic single-risky-
asset asymptotic result applied per-asset; it is not a reproduction of
Leland's or Donohue & Yip's own published numerical examples (no
published table was available to cross-check exact figures against).

When the derived-band mode is used, it *replaces* the scalar
``no_trade_band`` for that call rather than combining with it; when
either ``asset_volatility`` or ``risk_aversion`` is omitted, behaviour
is unchanged — the scalar ``no_trade_band`` is used exactly as before.

Formula (LaTeX): `\Delta_i = w_i^{tgt} - w_i^{cur} \;\; (\text{set } 0 \text{ if } |\Delta_i| < b_i) \\ Cost = \sum_i |\Delta_i| \cdot \frac{c_i}{10^4} \\ Turnover = \frac{1}{2}\sum_i |\Delta_i| \\ \text{(derived band, opt-in)}\;\; h_i = \left(\frac{3}{4}\, \frac{c_i}{10^4}\, \sigma_i^2\, w_i^{tgt}(1-w_i^{tgt})^2 \,/\, \gamma\right)^{1/3}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `current_weights`* | `number[] or number[][]` | required |  |
| `target_weights`* | `number[] or number[][]` | required |  |
| `cost_bps`* | `number[] or number[][]` | required |  |
| `no_trade_band` | `number` | `0.0` |  |
| `asset_volatility` | `number[] or number[][] or null` | `None` |  |
| `risk_aversion` | `number or null` | `None` |  |

## Risk-Adjusted Performance

### sharpe_ratio

`POST /api/v1/portfolio/sharpe_ratio`: Annualised Sharpe ratio.

Mean excess return divided by return volatility, annualised by
``sqrt(periods_per_year)``.

By default (``ddof=0``, unchanged from prior behaviour) volatility is the
*population* standard deviation (divide by n) of per-period excess
returns. Pass ``ddof=1`` to use the *sample* standard deviation (divide
by n-1) instead — the usual unbiased-estimator convention when
``returns`` is treated as a sample drawn from a larger population. The
``n``-vs-``n-1`` divisor only matters materially for small samples; for
the sample sizes typical of return series (hundreds+ of observations)
the two converge.

Formula (LaTeX): `S = \sqrt{T} \cdot \frac{\overline{r - r_f}}{\sigma_{ddof}(r - r_f)}, \quad \sigma_0 = \sqrt{\tfrac{1}{n}\sum(x-\bar x)^2}, \;\; \sigma_1 = \sqrt{\tfrac{1}{n-1}\sum(x-\bar x)^2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |
| `ddof` | `integer` | `0` |  |

### sortino_ratio

`POST /api/v1/portfolio/sortino_ratio`: Annualised Sortino ratio.

Like Sharpe but penalises only downside deviation below ``target``, so
upside volatility is not treated as risk.

The numerator's excess return is measured against ``risk_free`` while
the downside-deviation denominator measures shortfalls of the raw (not
risk-free-adjusted) returns below the separate ``target``, so when
``target != risk_free`` the two are distinct reference rates by
construction.

Formula (LaTeX): `Sortino = \sqrt{T} \cdot \frac{\overline{r - r_f}}{DD(MAR)} \\ DD(MAR) = \sqrt{\frac{1}{n}\sum_{t:\, r_t < MAR} (r_t - MAR)^2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `risk_free` | `number` | `0.0` |  |
| `target` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### calmar_ratio

`POST /api/v1/portfolio/calmar_ratio`: Calmar ratio — annualised return over maximum drawdown.

Formula (LaTeX): `CAGR = \left(\prod_{t=1}^{n}(1+r_t)\right)^{T/n} - 1 \\ Calmar = \frac{CAGR}{MDD}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `periods_per_year` | `integer` | `252` |  |

### information_ratio

`POST /api/v1/portfolio/information_ratio`: Information ratio — active return over tracking error.

Formula (LaTeX): `IR = \sqrt{T} \cdot \frac{\overline{r_p - r_b}}{\sigma(r_p - r_b)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `periods_per_year` | `integer` | `252` |  |

### treynor_ratio

`POST /api/v1/portfolio/treynor_ratio`: Treynor ratio — annualised excess return per unit of systematic risk (beta).

Formula (LaTeX): `\beta = \frac{\text{Cov}(r, b)}{\text{Var}(b)} \\ Treynor = \frac{T \cdot \overline{(r - r_f)}}{\beta}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### jensens_alpha

`POST /api/v1/portfolio/jensens_alpha`: Jensen's alpha from the CAPM single-factor regression.

``alpha = mean(r - rf) - beta * mean(b - rf)`` per period; annualised by
multiplication by ``periods_per_year``.

Formula (LaTeX): `\beta = \frac{\text{Cov}(r_p - r_f,\, r_b - r_f)}{\text{Var}(r_b - r_f)} \\ \alpha = T\left[\overline{(r_p - r_f)} - \beta\,\overline{(r_b - r_f)}\right]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `risk_free` | `number` | `0.0` |  |
| `periods_per_year` | `integer` | `252` |  |

### omega_ratio

`POST /api/v1/portfolio/omega_ratio`: Omega ratio — probability-weighted gains over losses about a threshold.

``Omega = sum(max(r - threshold, 0)) / sum(max(threshold - r, 0))``.

Formula (LaTeX): `\Omega(\theta) = \frac{\sum_t \max(r_t - \theta, 0)}{\sum_t \max(\theta - r_t, 0)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `threshold` | `number` | `0.0` |  |

### maximum_drawdown

`POST /api/v1/portfolio/maximum_drawdown`: Maximum drawdown — largest peak-to-trough decline.

Formula (LaTeX): `MDD = \max_t \frac{P_t - V_t}{P_t}, \quad P_t = \max_{s \le t} V_s`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `is_equity_curve` | `boolean` | `False` |  |

### average_drawdown

`POST /api/v1/portfolio/average_drawdown`: Average drawdown — mean of the drawdown series magnitude.

Formula (LaTeX): `DD_t = \frac{P_t - V_t}{P_t}, \quad P_t = \max_{s \le t} V_s \\ \overline{DD} = \frac{1}{T}\sum_{t=1}^{T} DD_t`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `is_equity_curve` | `boolean` | `False` |  |

### drawdown_duration

`POST /api/v1/portfolio/drawdown_duration`: Drawdown duration — longest and current underwater run lengths.

Counts consecutive periods spent below the prior peak.

Formula (LaTeX): `d_t = \begin{cases} 0 & V_t \ge P_t \\ d_{t-1} + 1 & V_t < P_t \end{cases} \\ D_{max} = \max_t d_t`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `is_equity_curve` | `boolean` | `False` |  |

### conditional_drawdown_at_risk

`POST /api/v1/portfolio/conditional_drawdown_at_risk`: Conditional Drawdown at Risk (CDaR).

The mean of the worst ``(1 - confidence_level)`` fraction of drawdowns —
the drawdown analogue of Expected Shortfall (Chekhlov, Uryasev, Zabarankin).

Formula (LaTeX): `DaR_\alpha = \text{Quantile}_\alpha(DD) \\ CDaR_\alpha = \frac{1}{\left|\{t : DD_t \ge DaR_\alpha\}\right|}\sum_{t:\,DD_t \ge DaR_\alpha} DD_t`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `confidence_level` | `number` | `0.95` |  |
| `is_equity_curve` | `boolean` | `False` |  |

### tail_ratio

`POST /api/v1/portfolio/tail_ratio`: Tail ratio — magnitude of the right tail relative to the left tail.

``|quantile(1 - tail)| / |quantile(tail)|``. A value above 1 indicates the
right (gain) tail is larger than the left (loss) tail.

Formula (LaTeX): `TR = \frac{\left|Q_{1-\tau}(r)\right|}{\left|Q_\tau(r)\right|}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `tail` | `number` | `0.05` |  |

### ulcer_index

`POST /api/v1/portfolio/ulcer_index`: Ulcer Index — root-mean-square of percentage drawdowns from peak.

A depth-and-duration-sensitive risk measure: deeper, longer drawdowns are
penalised quadratically.

Formula (LaTeX): `DD_t = 100 \times \frac{V_t - P_t}{P_t}, \quad P_t = \max_{s \le t} V_s \\ UI = \sqrt{\frac{1}{n}\sum_{t=1}^{n} DD_t^2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `is_equity_curve` | `boolean` | `False` |  |

## Performance Attribution

### return_attribution_brinson

`POST /api/v1/portfolio/return_attribution_brinson`: Brinson-Hood-Beebower return attribution.

Decomposes the active return into allocation, selection and interaction
effects per segment. The three effects sum exactly to the total active
return — the reconciliation property required for performance reporting.

Formula (LaTeX): `A_i = (w^p_i - w^b_i)(r^b_i - R^b) \\ S_i = w^b_i(r^p_i - r^b_i) \\ I_i = (w^p_i - w^b_i)(r^p_i - r^b_i) \\ R^{active} = \sum_i (A_i + S_i + I_i) = R^p - R^b`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `portfolio_weights`* | `number[] or number[][]` | required |  |
| `benchmark_weights`* | `number[] or number[][]` | required |  |
| `portfolio_returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `segment_names` | `string[] or null` | `None` |  |

### factor_return_attribution

`POST /api/v1/portfolio/factor_return_attribution`: Factor return attribution.

Decomposes the realised portfolio return into per-factor contributions
``exposure_i * factor_return_i`` plus a specific (idiosyncratic) component.

Formula (LaTeX): `C_i = b_i f_i \\ R_{factor} = \sum_i C_i \\ R_{total} = R_{factor} + \epsilon`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `factor_exposures`* | `number[] or number[][]` | required |  |
| `factor_returns`* | `number[] or number[][]` | required |  |
| `specific_return`* | `number` | required |  |
| `factor_names` | `string[] or null` | `None` |  |

### sector_attribution

`POST /api/v1/portfolio/sector_attribution`: Sector attribution — Brinson allocation/selection grouped by sector.

A thin specialisation of :func:`return_attribution_brinson` where segments
are GICS sectors. Allocation+selection+interaction reconcile to the active
return.

Formula (LaTeX): `A_i = (w^p_i - w^b_i)(r^b_i - R^b) \\ S_i = w^b_i(r^p_i - r^b_i) \\ I_i = (w^p_i - w^b_i)(r^p_i - r^b_i) \\ \text{Total}_i = A_i + S_i + I_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `portfolio_weights`* | `number[] or number[][]` | required |  |
| `benchmark_weights`* | `number[] or number[][]` | required |  |
| `portfolio_returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `sector_names` | `string[] or null` | `None` |  |

### currency_attribution

`POST /api/v1/portfolio/currency_attribution`: Currency attribution -- naive geometric split, or genuine Karnosky-Singer.

By default (``local_risk_free``/``base_risk_free`` omitted, unchanged
prior behaviour) this splits the base-currency return into a
local-market component and a currency (FX) component per holding,
weighted by exposure, via the geometric identity
``base = (1+local)(1+fx)-1`` with currency as the residual. This naive
split is NOT Karnosky-Singer -- see Bacon, C. (2008), "Practical
Portfolio Performance Measurement and Attribution", 2nd ed., Ch. 6,
which presents it as the baseline before introducing Karnosky-Singer.

Supplying BOTH ``local_risk_free`` (per-holding local-currency
risk-free/cash rate) and ``base_risk_free`` (the reporting/base
currency's own risk-free rate) switches to Karnosky & Singer's (1994)
genuine decomposition ("The Currency Dimension of Global Asset
Management and Performance Attribution", CFA Institute Research
Foundation): local returns are first netted against the *local*
risk-free rate into a local return PREMIUM (the market-selection
component the currency side must not re-capture), and the currency
side is split into the base cash return and a currency SURPRISE --
the currency return net of the covered-interest-parity forward
premium implied by the two risk-free rates -- rather than absorbing
the interest-rate differential as an unexplained residual:

    premium_i = (1+local_i)/(1+local_rf_i) - 1
    forward_premium_i = (1+base_rf)/(1+local_rf_i) - 1   (covered interest parity)
    surprise_i = (1+fx_i)/(1+forward_premium_i) - 1

These combine via the exact geometric identity
``(1+base_rf)(1+premium_i)(1+surprise_i) = (1+local_i)(1+fx_i)`` -- i.e.
Karnosky-Singer re-partitions the *same* total base-currency return
used by the naive split, it does not change it (verified in tests).
The ``currency_effect`` bucket is further broken into
``base_cash_effect`` (``base_rf``, common to every holding),
``currency_surprise_effect`` (``surprise_i``) and a small
``currency_interaction_effect`` residual capturing the compounding
cross-terms between the three multiplicative legs -- the same
reconciling-residual pattern :func:`return_attribution_brinson` uses
for its own interaction effect, so the three currency sub-effects sum
exactly to ``currency_effect`` (which itself sums with ``local_effect``
to ``total_return``, as before).

Formula (LaTeX): `\text{(default)}\;\; R^{local}_i = w_i r^{L}_i, \quad R^{fx}_i = w_i\left[(1+r^{L}_i)(1+r^{FX}_i) - 1 - r^{L}_i\right] \\ \text{(Karnosky-Singer, opt-in)}\;\; p_i = \frac{1+r^L_i}{1+r^{L,f}_i}-1, \quad f_i = \frac{1+r^{B,f}}{1+r^{L,f}_i}-1, \\ s_i = \frac{1+r^{FX}_i}{1+f_i}-1 \\ (1+r^{B,f})(1+p_i)(1+s_i) = (1+r^L_i)(1+r^{FX}_i)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `local_returns`* | `number[] or number[][]` | required |  |
| `fx_returns`* | `number[] or number[][]` | required |  |
| `weights`* | `number[] or number[][]` | required |  |
| `currency_names` | `string[] or null` | `None` |  |
| `local_risk_free` | `number[] or number[][] or null` | `None` |  |
| `base_risk_free` | `number or null` | `None` |  |

### gics_sector_exposure

`POST /api/v1/portfolio/gics_sector_exposure`: GICS sector exposure aggregation.

Aggregates position weights into GICS sector buckets and reports each
sector's share of the portfolio. Shares sum to the total invested weight.

Formula (LaTeX): `E_s = \sum_{i \,\in\, \text{sector } s} w_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `sector_codes`* | `string[]` | required |  |

### factor_exposure_analysis_barra

`POST /api/v1/portfolio/factor_exposure_analysis_barra`: Barra-style portfolio factor exposure.

Aggregates per-asset factor loadings into portfolio-level exposures
``Bᵀ w`` — the active/absolute factor tilts of the portfolio.

Formula (LaTeX): `E = B^\top w, \quad E_k = \sum_i B_{ik}\, w_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_exposures`* | `number[] or number[][]` | required |  |
| `weights`* | `number[] or number[][]` | required |  |
| `factor_names` | `string[] or null` | `None` |  |

## Factor Models

### fama_french_3_factor_model

`POST /api/v1/portfolio/fama_french_3_factor_model`: Fama-French 3-factor regression (MKT, SMB, HML).

Regresses portfolio excess returns on the market, size (SMB) and value
(HML) factors. The intercept is the factor alpha.

Formula (LaTeX): `y = \alpha + \beta_{MKT}F_{MKT} + \beta_{SMB}F_{SMB} + \beta_{HML}F_{HML} + \epsilon \\ \hat\beta = (X^\top X)^{-1}X^\top y \;\; (\text{OLS via lstsq})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `excess_returns`* | `number[] or number[][]` | required |  |
| `factors`* | `number[] or number[][]` | required |  |

### carhart_4_factor_model

`POST /api/v1/portfolio/carhart_4_factor_model`: Carhart 4-factor regression (MKT, SMB, HML, MOM).

Extends Fama-French 3-factor with the momentum (WML/MOM) factor.

Formula (LaTeX): `y = \alpha + \beta_{MKT}F_{MKT} + \beta_{SMB}F_{SMB} + \beta_{HML}F_{HML} + \beta_{MOM}F_{MOM} + \epsilon \\ \hat\beta = (X^\top X)^{-1}X^\top y \;\; (\text{OLS via lstsq}),\;\; X=[\mathbf{1}, F]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `excess_returns`* | `number[] or number[][]` | required |  |
| `factors`* | `number[] or number[][]` | required |  |

### fama_french_5_factor_model

`POST /api/v1/portfolio/fama_french_5_factor_model`: Fama-French 5-factor regression (MKT, SMB, HML, RMW, CMA).

Adds profitability (RMW) and investment (CMA) factors to the 3-factor model.

Formula (LaTeX): `y = \alpha + \beta_{MKT}F_{MKT} + \beta_{SMB}F_{SMB} + \beta_{HML}F_{HML} + \beta_{RMW}F_{RMW} + \beta_{CMA}F_{CMA} + \epsilon \\ \hat\beta = (X^\top X)^{-1}X^\top y`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `excess_returns`* | `number[] or number[][]` | required |  |
| `factors`* | `number[] or number[][]` | required |  |

### principal_component_analysis

`POST /api/v1/portfolio/principal_component_analysis`: Principal Component Analysis of an asset return matrix.

Eigendecomposes the covariance matrix to extract orthogonal principal
components ordered by explained variance.

Formula (LaTeX): `\Sigma v_k = \lambda_k v_k \\ EVR_k = \frac{\lambda_k}{\sum_j \lambda_j}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns_matrix`* | `number[] or number[][]` | required |  |
| `n_components` | `integer or null` | `None` |  |

### correlation_clustering

`POST /api/v1/portfolio/correlation_clustering`: Correlation-based clustering of assets.

Builds the correlation distance ``sqrt(2(1 - rho))`` and performs
single-linkage agglomerative clustering down to ``n_clusters`` groups —
grouping assets that co-move.

The merge itself is delegated to ``scipy.cluster.hierarchy.linkage``
(``method='single'``) followed by ``fcluster(..., criterion='maxclust')``
rather than a hand-rolled merge loop; this is the same single-linkage
algorithm (repeatedly merge the two clusters whose minimum pairwise
distance is smallest), just computed by SciPy's tested implementation.
Cluster *membership* is therefore identical to the earlier hand-rolled
version — only the arbitrary integer cluster-id labelling can differ.

Formula (LaTeX): `d_{ij} = \sqrt{2(1 - \rho_{ij})} \\ D(A,B) = \min_{i \in A,\, j \in B} d_{ij} \;\; \text{(single-linkage merge criterion)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns_matrix`* | `number[] or number[][]` | required |  |
| `n_clusters` | `integer` | `2` |  |

### regime_detection_hmm

`POST /api/v1/portfolio/regime_detection_hmm`: Two-state Gaussian regime detection via EM.

Note: despite the name, this fits a stationary 2-component Gaussian
mixture (EM, i.i.d. weights) — there is no transition matrix, so it does
not model true HMM regime persistence/switching dynamics.

Fits a two-component Gaussian mixture by EM and labels each observation by
its most likely regime. The higher-variance component is reported as the
"stress" regime — the standard calm/turbulent market characterisation.

Formula (LaTeX): `p(x_i) = \pi_0 \mathcal{N}(x_i;\mu_0,\sigma_0^2) + \pi_1 \mathcal{N}(x_i;\mu_1,\sigma_1^2) \\ r_{i,k} = \frac{\pi_k \mathcal{N}(x_i;\mu_k,\sigma_k^2)}{\sum_j \pi_j \mathcal{N}(x_i;\mu_j,\sigma_j^2)} \\ \mu_k = \frac{\sum_i r_{i,k}x_i}{\sum_i r_{i,k}}, \;\; \sigma_k^2 = \frac{\sum_i r_{i,k}(x_i-\mu_k)^2}{\sum_i r_{i,k}}, \;\; \pi_k = \frac{\sum_i r_{i,k}}{n}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `n_iter` | `integer` | `50` |  |

## Active Risk Analytics

### portfolio_beta

`POST /api/v1/portfolio/portfolio_beta`: Portfolio beta — sensitivity of portfolio returns to the benchmark.

``beta = cov(r, b) / var(b)``.

Formula (LaTeX): `\beta = \frac{\text{Cov}(r, b)}{\text{Var}(b)}, \quad \rho = \frac{\text{Cov}(r, b)}{\sigma_r \sigma_b}, \quad R^2 = \rho^2`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |

### active_share

`POST /api/v1/portfolio/active_share`: Active share — fraction of holdings differing from the benchmark.

``0.5 * sum(|w_i - b_i|)``; 0 means identical to benchmark, 1 means fully
differentiated (Cremers & Petajisto).

Formula (LaTeX): `AS = \frac{1}{2}\sum_i |w_i - b_i|`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `benchmark_weights`* | `number[] or number[][]` | required |  |

### tracking_error

`POST /api/v1/portfolio/tracking_error`: Tracking error — volatility of active (portfolio minus benchmark) return.

Formula (LaTeX): `TE = \sqrt{T} \cdot \sigma(r_p - r_b)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `periods_per_year` | `integer` | `252` |  |

### residual_risk

`POST /api/v1/portfolio/residual_risk`: Residual (idiosyncratic) risk — volatility of single-factor regression residuals.

Regresses portfolio returns on the benchmark (CAPM) and reports the
standard deviation of the residuals — the risk not explained by beta.

Formula (LaTeX): `\beta = \frac{\text{Cov}(r, b)}{\text{Var}(b)}, \quad \alpha = \bar r - \beta \bar b \\ \sigma_\epsilon = \sqrt{T} \cdot \text{std}(r_t - \alpha - \beta b_t)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `benchmark_returns`* | `number[] or number[][]` | required |  |
| `periods_per_year` | `integer` | `252` |  |

### portfolio_turnover

`POST /api/v1/portfolio/portfolio_turnover`: Portfolio turnover — one-way traded fraction between two weight vectors.

``0.5 * sum(|w_after - w_before|)`` (one-way convention).

Formula (LaTeX): `Turnover = \frac{1}{2}\sum_i \left| w_i^{after} - w_i^{before} \right|`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights_before`* | `number[] or number[][]` | required |  |
| `weights_after`* | `number[] or number[][]` | required |  |

### transaction_cost_analysis

`POST /api/v1/portfolio/transaction_cost_analysis`: Transaction Cost Analysis (TCA) — implementation shortfall vs benchmark.

Computes per-trade slippage against an arrival/VWAP benchmark and the
quantity-weighted average slippage in basis points. ``side`` is +1 for
buys (paying above benchmark is a cost) and -1 for sells.

By default (``decision_price`` omitted, unchanged prior behaviour) this
is narrower than Perold's (1988) full implementation-shortfall
decomposition -- it measures only execution slippage against the
``benchmark_prices`` (arrival/VWAP), with no delay-cost leg.

Passing ``decision_price`` -- the price at the instant the investment
decision was made, Perold's "paper" price, distinct from the
arrival/VWAP ``benchmark_prices`` used for execution slippage -- adds
the delay-cost leg: the cost incurred between the decision and the
order reaching the market (``benchmark_prices``), *before* any
execution slippage is measured. Delay cost and execution slippage sum
exactly to the executed-quantity implementation shortfall measured
directly against the decision price:
``delay_cost + total_cost == sum(side * (trade_prices - decision_price)
* trade_quantities)``.

Additionally passing ``unexecuted_quantity`` and ``cancellation_price``
together adds the opportunity-cost leg for shares that were never
executed: the paper cost of the price move between the decision instant
and the price at which the unexecuted portion of the order was marked
at cancellation/expiry, ``side * (cancellation_price - decision_price) *
unexecuted_quantity``. Delay cost + execution slippage + opportunity
cost together are the full-order implementation shortfall against the
decision price, covering every share of the original order (executed
and unexecuted alike) -- this function still does not model any
explicit commission/fee leg, which some treatments of Perold's
decomposition include as a further, separate component.

Formula (LaTeX): `Slippage_{bps} = \frac{\sum_i s \cdot (p_i - b_i) \cdot q_i}{\sum_i b_i q_i} \times 10^4 \\ \text{(opt-in)}\;\; Delay_{bps} = \frac{\sum_i s \cdot (b_i - d_i) \cdot q_i}{\sum_i d_i q_i} \times 10^4, \\ IS_{bps} = \frac{\sum_i s \cdot (p_i - d_i) \cdot q_i}{\sum_i d_i q_i} \times 10^4 \\ \text{(opt-in)}\;\; Opportunity_{bps} = \frac{s\cdot(c - d)\cdot u}{\sum_i d_i q_i + d\cdot u} \times 10^4, \\ TotalIS_{bps} = \frac{\sum_i s\cdot(p_i - d_i)\cdot q_i + s\cdot(c-d)\cdot u}{\sum_i d_i q_i + d\cdot u} \times 10^4`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `trade_prices`* | `number[] or number[][]` | required |  |
| `benchmark_prices`* | `number[] or number[][]` | required |  |
| `trade_quantities`* | `number[] or number[][]` | required |  |
| `side` | `integer` | `1` |  |
| `decision_price` | `number or number[] or null` | `None` |  |
| `unexecuted_quantity` | `number or null` | `None` |  |
| `cancellation_price` | `number or null` | `None` |  |

## ESG & Sustainability

### esg_score_integration

`POST /api/v1/portfolio/esg_score_integration`: ESG score integration — weighted score and optional ESG-constrained tilt.

Computes the weighted-average portfolio ESG score. If ``min_esg_score`` and
a covariance matrix are supplied, solves a minimum-variance long-only
portfolio subject to the weighted ESG score meeting the floor.

Formula (LaTeX): `S_{ESG} = \frac{\sum_i w_i \cdot ESG_i}{\sum_i w_i} \\ \min_w\; w^\top \Sigma w \quad \text{s.t. } \sum_i w_i = 1,\; w^\top ESG \ge S_{min},\; 0 \le w_i \le 1`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `esg_scores`* | `number[] or number[][]` | required |  |
| `min_esg_score` | `number or null` | `None` |  |
| `cov_matrix` | `number[] or number[][] or null` | `None` |  |

### carbon_footprint_attribution

`POST /api/v1/portfolio/carbon_footprint_attribution`: Carbon footprint attribution (WACI and financed emissions).

Computes the Weighted Average Carbon Intensity (WACI) -- this leg matches
TCFD's WACI definition regardless of mode.

By default (``company_total_emissions``/``company_value`` omitted,
unchanged prior behaviour) ``total_financed_emissions`` scales
revenue-intensity by invested value per holding, which does NOT match
the ownership-share method used by the TCFD/PCAF financed-emissions
standards.

Supplying BOTH ``company_total_emissions`` (each holding's investee
company's total absolute Scope 1+2 emissions, tCO2e) and
``company_value`` (each company's total enterprise value -- PCAF's EVIC,
enterprise value including cash, or market cap -- same currency unit as
``portfolio_value``) switches to the PCAF ownership-share method
(Partnership for Carbon Accounting Financials, "The Global GHG
Accounting and Reporting Standard for the Financial Industry", Part A,
2020; the same method TCFD's 2017 recommendations point to for financed
emissions):

    ownership_share_i = invested_i / company_value_i
    financed_emissions_i = ownership_share_i * company_total_emissions_i

where ``invested_i = weights_i * portfolio_value`` is the investor's
outstanding amount in company i. Unlike the default (revenue-intensity
x invested-value) leg, this correctly represents "the investor's
proportional share of the company's own total emissions" rather than an
intensity-scaled quantity with no ownership interpretation -- an
investor's ownership share can never legitimately attribute more than
the company's own total emissions (verified in tests).

Formula (LaTeX): `WACI = \sum_i w_i \cdot CI_i \\ \text{(default)}\;\; E_i = w_i \cdot V_{port} \cdot CI_i \\ \text{(PCAF, opt-in)}\;\; \text{share}_i = \frac{w_i V_{port}}{V^{company}_i}, \quad E_i = \text{share}_i \cdot E^{company}_i, \\ E_{total} = \sum_i E_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `carbon_intensities`* | `number[] or number[][]` | required |  |
| `portfolio_value`* | `number` | required |  |
| `asset_names` | `string[] or null` | `None` |  |
| `company_total_emissions` | `number[] or number[][] or null` | `None` |  |
| `company_value` | `number[] or number[][] or null` | `None` |  |

## Portfolio Risk Analytics

### liquidity_adjusted_portfolio_var

`POST /api/v1/portfolio/liquidity_adjusted_portfolio_var`: Liquidity-adjusted parametric VaR (LVaR).

Adds a liquidity cost term equal to half the weighted bid-ask spread to the
parametric delta-normal VaR (Bangia-Diebold-Schuermann simplified add-on),
capturing the cost of unwinding positions.

Formula (LaTeX): `\sigma_p = \sqrt{w^\top \Sigma w} \\ LVaR = z_\alpha \sigma_p \sqrt{h} + \frac{1}{2}\sum_i |w_i|\, s_i, \quad z_\alpha = \Phi^{-1}(\alpha)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `bid_ask_spreads`* | `number[] or number[][]` | required |  |
| `portfolio_value`* | `number` | required |  |
| `confidence_level` | `number` | `0.99` |  |
| `horizon_days` | `integer` | `1` |  |

### marginal_contribution_to_risk

`POST /api/v1/portfolio/marginal_contribution_to_risk`: Marginal and component contribution to portfolio volatility risk.

Marginal contribution ``(Σw)_i / sigma_p``; component ``w_i * marginal_i``.
Component contributions sum exactly to the portfolio volatility (Euler).

Formula (LaTeX): `\sigma_p = \sqrt{w^\top \Sigma w} \\ MCR_i = \frac{(\Sigma w)_i}{\sigma_p}, \quad CCR_i = w_i \cdot MCR_i, \quad \sum_i CCR_i = \sigma_p`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |

### diversification_ratio

`POST /api/v1/portfolio/diversification_ratio`: Diversification ratio — weighted average vol over portfolio vol.

``(w' σ) / sqrt(w' Σ w)`` where ``σ`` is the vector of asset volatilities.
Always >= 1; higher means more diversification benefit (Choueifaty).

Formula (LaTeX): `DR = \frac{\sum_i |w_i|\, \sigma_i}{\sqrt{w^\top \Sigma w}}, \quad \sigma_i = \sqrt{\Sigma_{ii}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |

### correlation_matrix_portfolio

`POST /api/v1/portfolio/correlation_matrix_portfolio`: Correlation matrix and average pairwise correlation of asset returns.

Formula (LaTeX): `\rho_{ij} = \text{Corr}(r_i, r_j) \\ \bar\rho = \frac{1}{n(n-1)}\sum_{i \ne j} \rho_{ij}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns_matrix`* | `number[] or number[][]` | required |  |

### concentration_risk_hhi

`POST /api/v1/portfolio/concentration_risk_hhi`: Concentration risk via the Herfindahl-Hirschman Index (HHI).

``HHI = sum(w_i^2)`` on absolute weights normalised to sum to 1. Ranges from
``1/n`` (equal weight) to 1 (single holding). The effective number of
holdings is ``1/HHI``.

Formula (LaTeX): `\tilde w_i = \frac{|w_i|}{\sum_j |w_j|}, \quad HHI = \sum_i \tilde w_i^2 \\ N_{eff} = \frac{1}{HHI}, \quad HHI_{norm} = \frac{HHI - 1/n}{1 - 1/n}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |

### monte_carlo_portfolio_simulation

`POST /api/v1/portfolio/monte_carlo_portfolio_simulation`: Monte Carlo portfolio simulation of terminal P&L.

Draws correlated multivariate-normal asset returns (RULE 3: pre-drawn in
pure Python via Cholesky), compounds them over the horizon in a JIT kernel,
and reports the simulated VaR / ES of terminal P&L.

Formula (LaTeX): `R_{s,t} = \mu + L z_{s,t}, \quad \Sigma = L L^\top \\ \Pi_s = V_0\left[\prod_{t=1}^{H}\big(1 + w^\top R_{s,t}\big) - 1\right] \\ VaR_\alpha = \text{Quantile}_\alpha(-\Pi), \quad ES_\alpha = \mathbb{E}\big[-\Pi \mid -\Pi \ge VaR_\alpha\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `weights`* | `number[] or number[][]` | required |  |
| `mean_returns`* | `number[] or number[][]` | required |  |
| `cov_matrix`* | `number[] or number[][]` | required |  |
| `portfolio_value` | `number` | `1000000.0` |  |
| `horizon` | `integer` | `10` |  |
| `n_simulations` | `integer` | `10000` |  |
| `confidence_level` | `number` | `0.99` |  |
| `seed` | `integer` | `12345` |  |
