# pyvar Credit Risk: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/credit-risk/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Core Credit Metrics (EL/UL/PD/LGD/EAD)

### probability_of_default_pd_estimation

`POST /api/v1/credit-risk/probability_of_default_pd_estimation`: Estimate PD from observed default cohorts (cohort / frequency method).

Computes the per-cohort default frequency and the obligor-weighted pooled
PD, then applies the Basel regulatory floor (3 bps for non-defaulted
exposures under CRR Art. 160/163).

Formula (LaTeX): `PD_{pooled} = \min\!\left(\max\!\left(\frac{\sum_i D_i}{\sum_i N_i},\ f\right),\ 1\right)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `n_defaults`* | `number[] or number[][]` | required |  |
| `n_obligors`* | `number[] or number[][]` | required |  |
| `floor` | `number` | `0.0003` |  |

### loss_given_default_lgd_model

`POST /api/v1/credit-risk/loss_given_default_lgd_model`: Workout LGD as one minus the recovery rate, net of workout costs.

``LGD = 1 - (recoveries - costs) / EAD``, exposure-weighted across the
facility sample and clipped to ``[0, 1]``.

Formula (LaTeX): `LGD_i = \text{clip}\!\left(1-\frac{R_i-c\,EAD_i}{EAD_i},\ 0,\ 1\right), \quad LGD = \frac{\sum_i LGD_i\,EAD_i}{\sum_i EAD_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `recovery_amounts`* | `number[] or number[][]` | required |  |
| `exposure_amounts`* | `number[] or number[][]` | required |  |
| `workout_cost_rate` | `number` | `0.0` |  |

### exposure_at_default_ead_calculator

`POST /api/v1/credit-risk/exposure_at_default_ead_calculator`: EAD for a revolving / committed facility via the CCF method.

``EAD = drawn + CCF * undrawn``. The CCF (a.k.a. credit-conversion factor)
captures the share of the currently undrawn commitment expected to be drawn
by the time of default. Basel F-IRB uses 0.75 for unconditionally
cancellable commitments unless otherwise specified.

Formula (LaTeX): `EAD = Drawn + CCF\cdot Undrawn`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `drawn`* | `number` | required |  |
| `undrawn`* | `number` | required |  |
| `credit_conversion_factor` | `number` | `0.75` |  |

### expected_loss_el_computation

`POST /api/v1/credit-risk/expected_loss_el_computation`: Expected Loss ``EL = PD * LGD * EAD``.

Formula (LaTeX): `EL = PD\cdot LGD\cdot EAD`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number` | required |  |
| `lgd`* | `number` | required |  |
| `ead`* | `number` | required |  |

### unexpected_loss_ul_computation

`POST /api/v1/credit-risk/unexpected_loss_ul_computation`: Stand-alone Unexpected Loss per exposure and the un-diversified sum.

For a Bernoulli default with deterministic LGD, the stand-alone UL of one
exposure is ``EAD * LGD * sqrt(PD(1-PD))`` — the loss standard deviation.
The portfolio UL reported here is the *sum* of stand-alone ULs (i.e. the
fully-correlated upper bound); correlation-aware UL is handled by the
Vasicek / CreditMetrics models in :mod:`engine.credit_var`.

Formula (LaTeX): `UL_i = EAD_i\cdot LGD_i\cdot\sqrt{PD_i(1-PD_i)}, \quad UL_{sum} = \sum_i UL_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number[] or number[][]` | required |  |
| `lgd`* | `number[] or number[][]` | required |  |
| `ead`* | `number[] or number[][]` | required |  |

### recovery_rate_estimation

`POST /api/v1/credit-risk/recovery_rate_estimation`: Estimate the recovery rate (1 - LGD) from a defaulted-facility sample.

Supports optional present-valuing of recoveries via per-facility discount
factors (workout recoveries are received some time after default).

Formula (LaTeX): `RR = \frac{\sum_i R_i\,DF_i}{\sum_i EAD_i}, \quad LGD = 1-RR`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `recovery_amounts`* | `number[] or number[][]` | required |  |
| `exposure_amounts`* | `number[] or number[][]` | required |  |
| `discount_factors` | `number[] or number[][] or null` | `None` |  |

### downturn_lgd_adjustment

`POST /api/v1/credit-risk/downturn_lgd_adjustment`: Basel downturn-LGD adjustment of a long-run average LGD.

CRR Art. 181 requires LGD to reflect economic-downturn conditions when
these are more conservative than the long-run average. Two scaling
methods are available:

- ``"multiplicative"`` (default, backward-compatible): a transparent
  multiplicative scaling, ``LGD_LR * multiplier``, clipped to
  ``[floor, 1]`` so the result never under-states the long-run LGD.
  Calibrate ``downturn_multiplier`` to your own downturn analysis —
  this is not itself a formula prescribed by CRR Art. 181 or EBA GL.
- ``"additive"``: the EBA/GL/2019/03 supervisory-style fallback add-on,
  ``LGD_downturn = LGD_LR + max(0, multiplier - 1) * (1 - LGD_LR) * 0.5``
  — here ``downturn_multiplier`` plays the same "how severe" role as in
  the multiplicative method, scaling how much of the remaining
  loss-given-default headroom (``1 - LGD_LR``) the downturn add-on
  consumes, rather than scaling ``LGD_LR`` itself directly.

Formula (LaTeX): `LGD_{DT} = \max\big(\min(LGD_{LR}\cdot m,\ 1),\ f,\ LGD_{LR}\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `lgd_long_run`* | `number` | required |  |
| `downturn_multiplier` | `number` | `1.0` |  |
| `floor` | `number` | `0.0` |  |
| `method` | `string` | `'multiplicative'` |  |

## Regulatory Capital (IRB/SA)

### irb_foundation_approach_capital

`POST /api/v1/credit-risk/irb_foundation_approach_capital`: Basel IRB Foundation-Approach capital (CRE31).

Note: unlike :func:`irb_advanced_approach_capital`, F-IRB exposes no
override at all for the asset correlation R — it is always the Basel
corporate correlation function of PD.

Under F-IRB the bank supplies its own PD but uses *supervisory* LGD: 45% for
senior unsecured and 75% for subordinated claims (CRE32). EAD and maturity
are also supervisory (M defaults to 2.5 years).

Formula (LaTeX): `LGD_{sup} = 0.45\ (\text{senior unsecured})\ \text{or}\ 0.75\ (\text{subordinated}) \\ K = \max\!\left(0,\ \left[LGD_{sup}\cdot\Phi\!\left(\frac{\Phi^{-1}(PD)+\sqrt{R}\,\Phi^{-1}(0.999)}{\sqrt{1-R}}\right) - PD\cdot LGD_{sup}\right]\cdot MA\right), \quad RWA = 12.5\cdot K\cdot EAD`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number` | required |  |
| `ead`* | `number` | required |  |
| `maturity` | `number` | `2.5` |  |
| `lgd` | `number` | `0.45` |  |
| `seniority` | `string` | `'senior_unsecured'` |  |

### irb_advanced_approach_capital

`POST /api/v1/credit-risk/irb_advanced_approach_capital`: Basel IRB Advanced-Approach capital (CRE31).

Note: when ``correlation`` is not supplied it defaults to the Basel
corporate correlation function of PD, the same formula F-IRB always uses.

Under A-IRB the bank supplies its own PD, LGD, EAD and effective maturity.
The risk-weight function is identical to F-IRB; only the parameter sources
differ.

Formula (LaTeX): `K = \max\!\left(0,\ \left[LGD\cdot\Phi\!\left(\frac{\Phi^{-1}(PD)+\sqrt{R}\,\Phi^{-1}(0.999)}{\sqrt{1-R}}\right) - PD\cdot LGD\right]\cdot MA\right), \quad RWA = 12.5\cdot K\cdot EAD \\ MA = \frac{1+(M-2.5)\,b(PD)}{1-1.5\,b(PD)}, \quad b(PD)=(0.11852-0.05478\ln PD)^2`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number` | required |  |
| `lgd`* | `number` | required |  |
| `ead`* | `number` | required |  |
| `maturity` | `number` | `2.5` |  |
| `correlation` | `number or null` | `None` |  |

### basel_standardised_approach_rwa

`POST /api/v1/credit-risk/basel_standardised_approach_rwa`: Basel Standardised-Approach RWA (CRE20).

``RWA = (EAD - CRM) * risk_weight``, where the supervisory risk weight is
set by the external rating / exposure class (e.g. 0% sovereign AAA, 20%
bank, 100% corporate unrated, 150% sub-investment grade). The minimum
capital is 8% of RWA.

Formula (LaTeX): `RWA = \max(EAD - CRM,\ 0) \cdot RW, \quad K = 0.08 \cdot RWA`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ead`* | `number` | required |  |
| `risk_weight`* | `number` | required |  |
| `credit_risk_mitigation` | `number` | `0.0` |  |

### maturity_adjustment_basel_irb

`POST /api/v1/credit-risk/maturity_adjustment_basel_irb`: Basel IRB maturity adjustment (CRE31.6).

``b(PD) = (0.11852 - 0.05478 ln PD)^2`` and
``MA = (1 + (M - 2.5) b) / (1 - 1.5 b)``. At M = 2.5 the adjustment is
exactly 1.0 by construction.

Formula (LaTeX): `b(PD) = (0.11852 - 0.05478\ln PD)^2, \quad MA = \frac{1+(M-2.5)\,b(PD)}{1-1.5\,b(PD)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number` | required |  |
| `maturity`* | `number` | required |  |

### sme_correlation_factor_basel

`POST /api/v1/credit-risk/sme_correlation_factor_basel`: Basel SME firm-size correlation adjustment (CRE31.10).

For SME corporate exposures (sales €5m-€50m) the asset correlation is
reduced by a size term:
``R_SME = R_corp - 0.04 * (1 - (S - 5)/45)`` with S clamped to ``[5, 50]``.
This lowers the capital charge for smaller, more idiosyncratic borrowers.

Formula (LaTeX): `R_{corp} = 0.12\,w + 0.24\,(1-w), \quad w=\frac{1-e^{-50PD}}{1-e^{-50}} \\ R_{SME} = R_{corp} - 0.04\left(1-\frac{S-5}{45}\right),\quad S\in[5,50]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number` | required |  |
| `annual_sales_millions`* | `number` | required |  |

## Portfolio Credit Models

### credit_var_monte_carlo

`POST /api/v1/credit-risk/credit_var_monte_carlo`: Monte-Carlo Credit VaR under a one-factor Gaussian copula.

Simulates correlated defaults, aggregates ``LGD * EAD`` losses, and reads
the loss quantile (VaR) and the mean tail loss (ES / CVaR). Expected Loss is
the simulation mean; Unexpected Loss is ``VaR - EL`` (economic-capital
convention).

Formula (LaTeX): `A_i = \sqrt{\rho_i}\,M+\sqrt{1-\rho_i}\,Z_i, \quad \text{default}_i \iff A_i<\Phi^{-1}(PD_i) \\ L = \sum_i LGD_i\,EAD_i\,\mathbb{1}[\text{default}_i], \quad VaR = \text{quantile}_q(L), \quad ES = \mathbb{E}[L\mid L\ge VaR]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number[] or number[][]` | required |  |
| `lgd`* | `number[] or number[][]` | required |  |
| `ead`* | `number[] or number[][]` | required |  |
| `asset_correlation` | `number or number[]` | `0.15` |  |
| `confidence_level` | `number` | `0.999` |  |
| `n_simulations` | `integer` | `50000` |  |
| `seed` | `integer` | `12345` |  |

### credit_var_analytical_vasicek

`POST /api/v1/credit-risk/credit_var_analytical_vasicek`: Analytical Vasicek large-homogeneous-portfolio Credit VaR.

The Vasicek (2002) asymptotic single-risk-factor loss rate at confidence q is
``L(q) = LGD * N( (N^{-1}(PD) + sqrt(rho) N^{-1}(q)) / sqrt(1-rho) )`` — the
same conditional-default formula underlying the Basel IRB charge. VaR is the
loss rate times total EAD; UL is the VaR in excess of EL.

Formula (LaTeX): `L(q) = LGD\cdot\Phi\!\left(\frac{\Phi^{-1}(PD)+\sqrt{\rho}\,\Phi^{-1}(q)}{\sqrt{1-\rho}}\right) \\ VaR = L(q)\cdot EAD_{tot}, \quad EL = PD\cdot LGD\cdot EAD_{tot}, \quad UL = VaR-EL`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number` | required |  |
| `lgd`* | `number` | required |  |
| `ead_total`* | `number` | required |  |
| `asset_correlation` | `number` | `0.15` |  |
| `confidence_level` | `number` | `0.999` |  |

### creditmetrics_portfolio_model

`POST /api/v1/credit-risk/creditmetrics_portfolio_model`: CreditMetrics portfolio loss distribution — two-state or genuine multi-state.

By default (the three transition-matrix arguments omitted) this is a
default/no-default reduction of J.P. Morgan's CreditMetrics: latent asset
returns are driven by a single common factor; an obligor defaults when its
return breaches ``N^{-1}(PD)``, incurring ``LGD * exposure``. In this mode
it is a direct pass-through to the same one-factor Gaussian-copula Monte
Carlo engine used by :func:`credit_var_monte_carlo` (identical formula,
identical code path) — unchanged from before this function supported the
multi-state mode below.

Pass ``transition_matrix``, ``current_rating`` and ``state_loss_pct``
together to switch to the genuine multi-state CreditMetrics model: each
obligor's simulated asset return is mapped through *its own*
transition-matrix row (Gupton, Finger & Bhatia 1997, the CreditMetrics
Technical Document's asset-return discretisation) to a migrated rating
state — not just default/survive — and the loss for that path is that
state's ``state_loss_pct`` of exposure (or ``LGD * exposure`` if the
migration lands in default). ``pd``/``lgd`` still drive the default
boundary and loss in multi-state mode: the caller's per-obligor ``pd``
OVERRIDES ``transition_matrix``'s own default column for that obligor's
row, rather than the two being independently averaged or the matrix's
figure silently winning. To preserve the matrix's migration *shape* under
that override, the non-default cumulative transition probabilities are
affinely rescaled from ``[matrix's own default prob, 1]`` onto
``[pd, 1]`` — so relative proportions between non-default states are
unchanged, only the total probability mass assigned to default moves to
match ``pd`` exactly.

Rating-state convention (matches
:func:`engine.credit_scoring.ratings_migration_matrix`'s own "n_states,
including default as the last"): index 0 is the best rating, index
``n_states - 2`` the worst non-default rating, and index ``n_states - 1``
is always default.

Formula (LaTeX): `A_i = \sqrt{\rho_i}\,M+\sqrt{1-\rho_i}\,Z_i, \quad \text{default}_i \iff A_i<\Phi^{-1}(PD_i) \\ L = \sum_i LGD_i\,EAD_i\,\mathbb{1}[\text{default}_i], \quad VaR = \text{quantile}_q(L), \quad ES = \mathbb{E}[L\mid L\ge VaR]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required |  |
| `pd`* | `number[] or number[][]` | required |  |
| `lgd`* | `number[] or number[][]` | required |  |
| `asset_correlation` | `number` | `0.2` |  |
| `confidence_level` | `number` | `0.99` |  |
| `n_simulations` | `integer` | `20000` |  |
| `seed` | `integer` | `2024` |  |
| `transition_matrix` | `number[][] or null` | `None` |  |
| `current_rating` | `integer[] or null` | `None` |  |
| `state_loss_pct` | `number[] or null` | `None` |  |

### kmv_merton_distance_to_default

`POST /api/v1/credit-risk/kmv_merton_distance_to_default`: Merton / KMV distance-to-default and implied PD.

Note: when ``asset_drift`` is omitted, the asset drift mu used in the
distance-to-default formula defaults to ``risk_free_rate`` (a
risk-neutral assumption), not an estimate of the firm's actual expected
asset return.

In the structural Merton model the firm defaults at horizon T if asset value
falls below the debt face value. The distance-to-default is
``DD = (ln(V/D) + (mu - 0.5 sigma^2) T) / (sigma sqrt(T))`` and the model PD
(expected default frequency) is ``N(-DD)``.

Formula (LaTeX): `DD = \frac{\ln(V/D)+(\mu-0.5\sigma^2)T}{\sigma\sqrt{T}}, \quad PD = \Phi(-DD)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_value`* | `number` | required |  |
| `debt_face_value`* | `number` | required |  |
| `asset_volatility`* | `number` | required |  |
| `risk_free_rate` | `number` | `0.0` |  |
| `asset_drift` | `number or null` | `None` |  |
| `horizon` | `number` | `1.0` |  |

## Credit Scoring & PD Models

### altman_z_score_credit_scoring

`POST /api/v1/credit-risk/altman_z_score_credit_scoring`: Altman (1968) Z-score for public manufacturers.

``Z = 1.2 X1 + 1.4 X2 + 3.3 X3 + 0.6 X4 + 1.0 X5`` with X1 = WC/TA,
X2 = RE/TA, X3 = EBIT/TA, X4 = MV equity / total liabilities, X5 = sales/TA.
Zones: ``Z > 2.99`` safe, ``1.81 <= Z <= 2.99`` grey, ``Z < 1.81`` distress.

Formula (LaTeX): `Z = 1.2\frac{WC}{TA}+1.4\frac{RE}{TA}+3.3\frac{EBIT}{TA}+0.6\frac{MVE}{TL}+1.0\frac{Sales}{TA}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `working_capital`* | `number` | required |  |
| `retained_earnings`* | `number` | required |  |
| `ebit`* | `number` | required |  |
| `market_value_equity`* | `number` | required |  |
| `sales`* | `number` | required |  |
| `total_assets`* | `number` | required |  |
| `total_liabilities`* | `number` | required |  |

### logistic_regression_pd_model

`POST /api/v1/credit-risk/logistic_regression_pd_model`: Fit a logistic-regression PD model by Newton-Raphson (IRLS) MLE.

Estimates ``PD = sigmoid(b0 + x·b)`` from a default indicator. A small ridge
term stabilises the Hessian on separable / collinear data. An intercept is
added automatically.

Coefficients are found by iterative Newton-Raphson (IRLS) convergence to
the maximum-likelihood estimate, not a closed-form solution.

Formula (LaTeX): `PD = \sigma(\beta_0+x\cdot\beta) = \frac{1}{1+e^{-(\beta_0+x\cdot\beta)}} \\ \beta^{(t+1)} = \beta^{(t)} + \big(X^\top W X+\rho I\big)^{-1} X^\top(y-\hat y)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `features`* | `number[] or number[][]` | required |  |
| `defaults`* | `number[] or number[][]` | required |  |
| `max_iter` | `integer` | `100` |  |
| `tol` | `number` | `1e-08` |  |
| `ridge` | `number` | `1e-06` |  |

### machine_learning_pd_calibration

`POST /api/v1/credit-risk/machine_learning_pd_calibration`: Platt-scaling calibration of raw ML scores into well-calibrated PDs.

Many ML classifiers (gradient boosting, random forests) emit uncalibrated
scores. Platt scaling fits a one-dimensional logistic map
``PD = sigmoid(a * score + b)`` so the output is a true probability. The fit
reuses the Newton-Raphson logistic solver on the single score feature.

No scikit-learn or other ML library is involved anywhere in this module —
the calibration is a hand-rolled fit on top of this file's own solver.

Formula (LaTeX): `PD = \sigma(a\cdot\text{score}+b) = \frac{1}{1+e^{-(a\cdot\text{score}+b)}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `raw_scores`* | `number[] or number[][]` | required |  |
| `defaults`* | `number[] or number[][]` | required |  |
| `max_iter` | `integer` | `100` |  |
| `tol` | `number` | `1e-08` |  |

### through_the_cycle_pd_adjustment

`POST /api/v1/credit-risk/through_the_cycle_pd_adjustment`: Convert a point-in-time PD to a through-the-cycle PD.

TTC PDs dampen the macro cycle for stable regulatory capital. A convex blend
in the Gaussian-score (probit) domain is used so the result stays a valid
probability: ``score_TTC = (1-w) score_PIT + w score_LRA`` with
``w = cyclicality`` and ``score = N^{-1}(PD)``.

Formula (LaTeX): `z_{TTC} = (1-w)\,\Phi^{-1}(PD_{PIT}) + w\,\Phi^{-1}(PD_{LRA}), \quad PD_{TTC} = \Phi(z_{TTC})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pit_pd`* | `number` | required |  |
| `long_run_average_pd`* | `number` | required |  |
| `cyclicality` | `number` | `0.5` |  |

### point_in_time_pd_estimation

`POST /api/v1/credit-risk/point_in_time_pd_estimation`: Derive a point-in-time PD from a TTC PD and a macro factor.

Inverse of the TTC transform: shifts the probit-domain TTC score by a
sensitivity-scaled standardised macro index ``z`` (negative ``z`` = adverse
conditions raise the PD): ``score_PIT = N^{-1}(PD_TTC) - sensitivity * z``.

Formula (LaTeX): `z_{TTC} = \Phi^{-1}(PD_{TTC}), \quad z_{PIT} = z_{TTC} - \beta\,x, \quad PD_{PIT} = \Phi(z_{PIT})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ttc_pd`* | `number` | required |  |
| `macro_index`* | `number` | required |  |
| `sensitivity` | `number` | `1.0` |  |

### retail_scorecard_pd_model

`POST /api/v1/credit-risk/retail_scorecard_pd_model`: Retail scorecard: additive points to a PD via the points-to-double-odds map.

A scorecard sums attribute points into a score; the score relates to odds by
``odds = base_odds * 2^{(score - base_score)/pdo}`` (PDO = points to double
the odds). PD = ``1 / (1 + odds)``.

Formula (LaTeX): `\text{score} = b_0+\sum_k v_k p_k, \quad \text{odds} = O_0\cdot 2^{(\text{score}-s_0)/PDO}, \quad PD = \frac{1}{1+\text{odds}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `feature_values`* | `number[] or number[][]` | required |  |
| `points_per_feature`* | `number[] or number[][]` | required |  |
| `base_points`* | `number` | required |  |
| `pdo` | `number` | `50.0` |  |
| `base_score` | `number` | `600.0` |  |
| `base_odds` | `number` | `50.0` |  |

## Migration & Correlation

### default_correlation_matrix

`POST /api/v1/credit-risk/default_correlation_matrix`: Pairwise default correlation from asset correlations (Gaussian copula).

The default correlation between two obligors is
``rho_D = (P(both default) - PD_i PD_j) / sqrt(PD_i(1-PD_i) PD_j(1-PD_j))``
where the joint default probability is the bivariate normal CDF
``Phi_2(N^{-1}(PD_i), N^{-1}(PD_j); rho_A)`` with asset correlation rho_A.

Formula (LaTeX): `p_{ij} = \Phi_2\big(\Phi^{-1}(PD_i),\Phi^{-1}(PD_j);\ \rho^A_{ij}\big), \quad \rho^D_{ij} = \frac{p_{ij}-PD_i PD_j}{\sqrt{PD_i(1-PD_i)\,PD_j(1-PD_j)}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number[] or number[][]` | required |  |
| `asset_correlation`* | `number[] or number[][]` | required |  |

### ratings_migration_matrix

`POST /api/v1/credit-risk/ratings_migration_matrix`: Estimate a row-stochastic ratings-migration matrix (cohort method).

Counts observed transitions and normalises each row to a probability
distribution. Empty rows (no obligors observed in that state) are set to the
identity (a self-transition), keeping the matrix row-stochastic.

This identity substitution for empty rows is a modelling convention, not an
observed transition — it exists purely so the returned matrix stays
row-stochastic and is safe to chain into further calculations.

Formula (LaTeX): `P_{ij} = \frac{\#\{k: f_k=i,\ t_k=j\}}{\sum_j \#\{k: f_k=i,\ t_k=j\}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `from_rating`* | `number[] or number[][]` | required |  |
| `to_rating`* | `number[] or number[][]` | required |  |
| `n_states`* | `integer` | required |  |

## Concentration Risk

### credit_concentration_risk_hhi

`POST /api/v1/credit-risk/credit_concentration_risk_hhi`: Herfindahl-Hirschman concentration index of a credit portfolio.

``HHI = sum_i (w_i)^2`` on exposure shares. HHI = 1 means a single-name
portfolio; HHI = 1/n means perfectly granular. The effective number of
independent exposures is ``1/HHI`` (the diversification score).

Formula (LaTeX): `HHI = \sum_i w_i^2, \quad w_i = \frac{e_i}{\sum_i e_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required |  |

## Counterparty Credit Risk (CCR/XVA)

### current_exposure_method_cem

`POST /api/v1/credit-risk/current_exposure_method_cem`: Basel I/II Current Exposure Method (CEM) EAD.

``EAD = max(MtM, 0) + notional * add_on_factor``. The add-on factor is the
supervisory percentage by asset class and residual maturity (e.g. 0.5% IR
< 1y, 1.5% IR 1-5y, 6% equity). CEM is superseded by SA-CCR but retained for
legacy reporting.

Formula (LaTeX): `EAD = \max(MtM,\ 0) + N\cdot\alpha`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mark_to_market`* | `number` | required |  |
| `notional`* | `number` | required |  |
| `add_on_factor`* | `number` | required |  |

### standardised_approach_ccr_sa_ccr

`POST /api/v1/credit-risk/standardised_approach_ccr_sa_ccr`: Basel SA-CCR EAD (CRE52).

``EAD = alpha * (RC + PFE)`` where the replacement cost is
``RC = max(MtM - collateral, 0)`` (unmargined) and ``PFE = multiplier *
AddOn_aggregate`` with the regulatory recognition-of-excess-collateral
multiplier ``multiplier = min(1, 0.05 + 0.95 * exp((MtM - C)/(1.9 * AddOn)))``.
The supervisory ``alpha`` is 1.4.

Formula (LaTeX): `RC = \max(MtM-C,\ 0), \quad \text{mult} = \min\!\left(1,\ 0.05+0.95\,e^{(MtM-C)/(1.9\,AddOn)}\right) \\ PFE = \text{mult}\cdot AddOn, \quad EAD = \alpha\,(RC+PFE)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mark_to_market`* | `number` | required |  |
| `collateral`* | `number` | required |  |
| `add_on_aggregate`* | `number` | required |  |
| `alpha` | `number` | `1.4` |  |

### potential_future_exposure_pfe

`POST /api/v1/credit-risk/potential_future_exposure_pfe`: Potential Future Exposure profile via Monte-Carlo (arithmetic BM proxy).

Simulates the netting-set value as ``V_t = V_0 + drift*t + sigma*sqrt(t)*Z``
and reports the per-step PFE (high quantile of positive exposure) and the
peak PFE. Randomness is pre-drawn in pure Python (RULE 3).

PFE at each time step is the empirical quantile of the simulated exposure
distribution rather than a closed-form expression, so results carry
Monte Carlo sampling noise that varies with ``n_paths`` and ``seed``.

Formula (LaTeX): `V_t = V_0 + \mu t + \sigma\sqrt{t}\,Z,\quad Z\sim N(0,1) \\ PFE(t) = Q_q\big(\max(V_t,0)\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `initial_value`* | `number` | required |  |
| `volatility`* | `number` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `quantile` | `number` | `0.95` |  |
| `drift` | `number` | `0.0` |  |
| `n_paths` | `integer` | `20000` |  |
| `seed` | `integer` | `909` |  |

### expected_positive_exposure_epe

`POST /api/v1/credit-risk/expected_positive_exposure_epe`: Expected Positive Exposure — time-weighted average expected exposure.

EPE is the time-average of the expected-exposure profile over the horizon
(CRE53): ``EPE = (1/T) * integral_0^T EE(t) dt`` approximated by the
trapezoidal rule on the supplied grid.

Formula (LaTeX): `EPE = \frac{1}{T}\int_0^T EE(t)\,dt`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_exposure`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |

### effective_epe_regulatory

`POST /api/v1/credit-risk/effective_epe_regulatory`: Basel Effective EPE (EEPE) with the non-decreasing Effective EE profile.

The Effective Expected Exposure is the running maximum of EE
``EEE(t) = max(EEE(t-1), EE(t))`` (it never decreases, capturing roll-over
risk). EEPE is the time-weighted average of EEE over the first year (CRE53).
EAD = alpha * EEPE downstream.

Formula (LaTeX): `EEE(t_k) = \max\big(EEE(t_{k-1}),\ EE(t_k)\big), \quad EEPE = \frac{1}{T}\int_0^T EEE(t)\,dt`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_exposure`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |

### credit_valuation_adjustment_cva

`POST /api/v1/credit-risk/credit_valuation_adjustment_cva`: Unilateral Credit Valuation Adjustment.

The market price of counterparty default risk:
``CVA = LGD * sum_k EPE_k * DF_k * (S_{k-1} - S_k)`` with LGD = 1 - R and a
flat hazard ``lambda = spread / LGD`` (credit-triangle approximation).

Formula (LaTeX): `LGD = 1-R, \quad \lambda = \frac{s}{LGD}, \quad S_k = e^{-\lambda t_k} \\ CVA = LGD\sum_k EPE_k\,DF_k\,(S_{k-1}-S_k)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_exposure`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `credit_spread`* | `number` | required |  |
| `recovery_rate` | `number` | `0.4` |  |

### debt_valuation_adjustment_dva

`POST /api/v1/credit-risk/debt_valuation_adjustment_dva`: Debit Valuation Adjustment — the symmetric own-default benefit.

DVA mirrors CVA using the *negative* expected exposure (the amount the bank
owes) and the bank's *own* credit spread. It is a gain to the reporting
entity (own default extinguishes a liability).

Under the hood this simply calls :func:`credit_valuation_adjustment_cva`
on the negative-exposure profile with the bank's own spread and recovery
substituted in, rather than a separately derived formula.

Formula (LaTeX): `LGD_{own} = 1-R_{own}, \quad \lambda_{own} = \frac{s_{own}}{LGD_{own}}, \quad S_k = e^{-\lambda_{own} t_k} \\ DVA = LGD_{own}\sum_k ENE_k\,DF_k\,(S_{k-1}-S_k)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_negative_exposure`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `own_credit_spread`* | `number` | required |  |
| `own_recovery_rate` | `number` | `0.4` |  |

### funding_valuation_adjustment_fva

`POST /api/v1/credit-risk/funding_valuation_adjustment_fva`: Funding Valuation Adjustment — cost of funding uncollateralised exposure.

Note: when ``survival_probability`` is omitted it defaults to 1 at every
bucket, i.e. the FVA is computed with no counterparty-default
conditioning applied.

``FVA = funding_spread * sum_k EPE_k * DF_k * S_k * dt_k`` — the present
value of the funding-spread carry on the expected exposure over each
interval, conditional on counterparty survival.

Formula (LaTeX): `\Delta t_k = t_k-t_{k-1}, \quad FVA = s_f\sum_k EPE_k\,DF_k\,S_k\,\Delta t_k`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_exposure`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `funding_spread`* | `number` | required |  |
| `survival_probability` | `number[] or number[][] or null` | `None` |  |

### capital_valuation_adjustment_kva

`POST /api/v1/credit-risk/capital_valuation_adjustment_kva`: Capital Valuation Adjustment — lifetime cost of regulatory capital.

``KVA = cost_of_capital * sum_k K_k * DF_k * dt_k`` — the present value of
the shareholders' required return on the regulatory capital held against the
trade over its life.

Formula (LaTeX): `\Delta t_k = t_k-t_{k-1}, \quad KVA = c\sum_k K_k\,DF_k\,\Delta t_k`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `capital_profile`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `cost_of_capital` | `number` | `0.1` |  |

### margin_valuation_adjustment_mva

`POST /api/v1/credit-risk/margin_valuation_adjustment_mva`: Margin Valuation Adjustment — funding cost of posted initial margin.

``MVA = spread * sum_k IM_k * DF_k * dt_k`` — present value of the carry on
posting (and funding) initial margin that earns less than the bank's funding
cost over the trade's life.

Formula (LaTeX): `\Delta t_k = t_k-t_{k-1}, \quad MVA = s_m\sum_k IM_k\,DF_k\,\Delta t_k`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `initial_margin_profile`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `margin_funding_spread`* | `number` | required |  |

### xva_aggregation

`POST /api/v1/credit-risk/xva_aggregation`: Aggregate the XVA components into a total valuation adjustment.

Sign convention (cost to the bank is positive, reducing the trade value):
``total_xva = CVA - DVA + FVA + KVA + MVA``. DVA is a benefit and so enters
negatively. The adjusted price is ``risk_free_price - total_xva`` downstream.

Formula (LaTeX): `XVA_{tot} = CVA - DVA + FVA + KVA + MVA`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cva`* | `number` | required |  |
| `dva` | `number` | `0.0` |  |
| `fva` | `number` | `0.0` |  |
| `kva` | `number` | `0.0` |  |
| `mva` | `number` | `0.0` |  |

### cva_sensitivity_cva_greeks

`POST /api/v1/credit-risk/cva_sensitivity_cva_greeks`: CVA sensitivities — CS01 (credit delta) and exposure delta.

Computes the base CVA and:
  * ``cs01``: the change in CVA for a +1 bp parallel shift in the credit
    spread (finite-difference), the dominant CVA Greek for capital and
    hedging.
  * ``exposure_delta``: sensitivity to a 1% uniform scaling of the EPE
    profile (linear, so exact = CVA * 0.01).

Formula (LaTeX): `CS01 = CVA(s+\Delta s) - CVA(s), \quad \text{exposure\_delta} = 0.01\cdot CVA(s)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_exposure`* | `number[] or number[][]` | required |  |
| `time_steps`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `credit_spread`* | `number` | required |  |
| `recovery_rate` | `number` | `0.4` |  |
| `spread_bump` | `number` | `0.0001` |  |

### wrong_way_risk_adjustment

`POST /api/v1/credit-risk/wrong_way_risk_adjustment`: Wrong-way-risk (WWR) multiplicative adjustment to CVA.

When exposure rises as the counterparty's credit deteriorates (positive
correlation), CVA is understated. A first-order alpha multiplier
``alpha = 1 + correlation * exposure_volatility`` (clamped >= 0) scales the
base CVA; negative correlation gives right-way risk (alpha < 1).

This is a first-order proxy multiplier, confirmed against the WWR
literature (Hull & White 2012; Gregory, *The xVA Challenge*) not to
reproduce a specific published WWR model — treat it as a reasonable
internal approximation.

Formula (LaTeX): `\alpha = \max(1+\rho\,\sigma_E,\ 0), \quad CVA_{adj} = \alpha\cdot CVA_{base}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `base_cva`* | `number` | required |  |
| `correlation`* | `number` | required |  |
| `exposure_volatility` | `number` | `0.3` |  |

### counterparty_credit_risk_ccr_exposure

`POST /api/v1/credit-risk/counterparty_credit_risk_ccr_exposure`: Generic CCR exposure = current exposure + add-on, net of collateral.

``Exposure = max(MtM - collateral, 0) + add_on``. The current exposure is
floored at zero (a counterparty owing you nothing has no replacement cost).

Formula (LaTeX): `Exposure = \max(MtM - C,\ 0) + AddOn`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `mark_to_market`* | `number` | required |  |
| `add_on`* | `number` | required |  |
| `collateral` | `number` | `0.0` |  |

### collateral_haircut_calculation

`POST /api/v1/credit-risk/collateral_haircut_calculation`: Supervisory collateral haircut under the comprehensive approach (CRE22).

The adjusted collateral value is
``C_adj = C * (1 - H_c - H_fx)`` where ``H_c`` is the market-price-volatility
haircut and ``H_fx`` the currency-mismatch haircut (8% standard). The
adjusted value is floored at zero.

Formula (LaTeX): `C_{adj} = \max\big(C\cdot(1-H_c-H_{fx}),\ 0\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `collateral_value`* | `number` | required |  |
| `haircut_collateral`* | `number` | required |  |
| `haircut_fx` | `number` | `0.0` |  |

## CDS & Credit Derivatives

### credit_spread_curve_bootstrap

`POST /api/v1/credit-risk/credit_spread_curve_bootstrap`: Bootstrap a piecewise-constant hazard / survival curve from CDS spreads.

Uses the credit-triangle approximation hazard ``lambda(t) = spread(t) / LGD``
on each tenor, giving survival ``S(t) = exp(-lambda * t)`` with a piecewise
hazard between consecutive tenors. This is the standard quick bootstrap;
the full ISDA bootstrap solves leg-PV = 0 per tenor (handled by
:func:`cds_pricing_isda_standard` when validating).

Formula (LaTeX): `LGD = 1-R, \quad \lambda(t) = \frac{s(t)}{LGD}, \quad S(t) = e^{-\lambda(t)\,t}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `tenors`* | `number[] or number[][]` | required |  |
| `par_spreads`* | `number[] or number[][]` | required |  |
| `recovery_rate` | `number` | `0.4` |  |

### cds_pricing_isda_standard

`POST /api/v1/credit-risk/cds_pricing_isda_standard`: ISDA-standard CDS present value (protection-buyer perspective).

PV(buyer) = protection leg - premium leg, where:
  * premium leg = spread * notional * risky annuity
    (``sum_k accrual_k DF_k S_k``),
  * protection leg = LGD * notional * ``sum_k DF_k (S_{k-1} - S_k)``.
The par spread that zeroes the PV is also returned.

Formula (LaTeX): `LGD=1-R,\quad S_k=e^{-\lambda t_k} \\ PV_{buyer} = \underbrace{LGD\cdot N\sum_k DF_k(S_{k-1}-S_k)}_{\text{protection leg}} - \underbrace{s\cdot N\sum_k \delta_k DF_k S_k}_{\text{premium leg}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `payment_times`* | `number[] or number[][]` | required |  |
| `accrual_factors`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `hazard_rate`* | `number` | required |  |
| `contract_spread`* | `number` | required |  |
| `notional` | `number` | `1.0` |  |
| `recovery_rate` | `number` | `0.4` |  |

### cds_spread_to_pd_conversion

`POST /api/v1/credit-risk/cds_spread_to_pd_conversion`: Credit-triangle conversion of a CDS spread to PD.

Hazard ``lambda = spread / (1 - R)``; cumulative default probability to
maturity is ``PD = 1 - exp(-lambda * T)``. The annualised marginal default
rate is also returned.

Formula (LaTeX): `\lambda = \frac{s}{1-R}, \quad PD = 1-e^{-\lambda T}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cds_spread`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `recovery_rate` | `number` | `0.4` |  |

### credit_default_swap_var

`POST /api/v1/credit-risk/credit_default_swap_var`: Parametric VaR of a single-name CDS position from spread risk.

The first-order MtM sensitivity to the credit spread is the spread DV01
``= notional * risky_annuity`` (per unit spread). With a normal daily spread
move of volatility ``sigma_s``, the VaR is
``z * sigma_s * sqrt(horizon) * spread_DV01``.

Formula (LaTeX): `DV01 = N\cdot RPV01, \quad z=\Phi^{-1}(q), \quad VaR = z\cdot\sigma_s\cdot\sqrt{h}\cdot DV01`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `risky_annuity`* | `number` | required |  |
| `spread_volatility`* | `number` | required |  |
| `confidence_level` | `number` | `0.99` |  |
| `horizon_days` | `integer` | `1` |  |
| `position` | `string` | `'long_protection'` |  |

## IFRS 9 & ECL

### ifrs_9_stage_classification_pd_threshold

`POST /api/v1/credit-risk/ifrs_9_stage_classification_pd_threshold`: IFRS 9 stage classification by the PD-threshold SICR rule.

Stage 3 if credit-impaired (90+ days past due, the IFRS 9 rebuttable default
presumption). Otherwise Stage 2 if a significant increase in credit risk has
occurred — either the lifetime PD has risen by at least
``sicr_relative_threshold`` times origination, OR the absolute PD increase
exceeds ``sicr_absolute_threshold``. Else Stage 1.

Formula (LaTeX): `\text{Stage} = \begin{cases} 3 & DPD\ge90 \\ 2 & PD_{cur}\ge k\,PD_{orig}\ \text{or}\ PD_{cur}-PD_{orig}\ge\tau \\ 1 & \text{otherwise} \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd_current`* | `number` | required |  |
| `pd_origination`* | `number` | required |  |
| `days_past_due` | `integer` | `0` |  |
| `sicr_relative_threshold` | `number` | `2.0` |  |
| `sicr_absolute_threshold` | `number` | `0.02` |  |

### ifrs_9_lifetime_ecl_stage_2_3

`POST /api/v1/credit-risk/ifrs_9_lifetime_ecl_stage_2_3`: IFRS 9 Stage 2/3 lifetime Expected Credit Loss.

Lifetime ECL sums discounted expected loss across all future periods using
the *marginal* (per-period) PD term structure:
``ECL = sum_t marginal_PD_t * LGD_t * EAD_t * DF_t``. For Stage 3 the PD is
effectively 1 in the first period (already defaulted); callers pass the
appropriate marginal-PD vector.

Formula (LaTeX): `ECL = \sum_t PD_t^{marg}\cdot LGD_t\cdot EAD_t\cdot DF_t`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `marginal_pd`* | `number[] or number[][]` | required |  |
| `lgd`* | `number[] or number[][]` | required |  |
| `ead`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `stage` | `integer` | `2` |  |

### ifrs_9_12_month_ecl_stage_1

`POST /api/v1/credit-risk/ifrs_9_12_month_ecl_stage_1`: IFRS 9 Stage 1 (12-month) Expected Credit Loss.

For Stage 1 exposures ECL uses the 12-month PD:
``ECL = PD_12m * LGD * EAD * DF``.

Formula (LaTeX): `ECL = PD_{12m}\cdot LGD\cdot EAD\cdot DF`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd_12m`* | `number` | required |  |
| `lgd`* | `number` | required |  |
| `ead`* | `number` | required |  |
| `discount_factor` | `number` | `1.0` |  |

### ifrs_9_scenario_weighted_ecl

`POST /api/v1/credit-risk/ifrs_9_scenario_weighted_ecl`: Probability-weighted ECL across forward-looking macro scenarios.

IFRS 9 requires ECL to reflect an unbiased probability-weighted amount over
multiple scenarios (base / upside / downside):
``ECL = sum_s weight_s * ECL_s`` with weights summing to 1.

Formula (LaTeX): `\hat w_s = \frac{w_s}{\sum_s w_s}, \quad ECL = \sum_s \hat w_s\,ECL_s`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `scenario_ecls`* | `number[] or number[][]` | required |  |
| `scenario_weights`* | `number[] or number[][]` | required |  |

### macroeconomic_overlays_ecl

`POST /api/v1/credit-risk/macroeconomic_overlays_ecl`: Apply forward-looking macroeconomic overlays to a base ECL.

Adjusts ECL for projected macro deviations via a multiplicative factor
``adj = 1 + sum_j sensitivity_j * factor_j`` (clamped at 0), then adds a
discretionary management overlay. Captures the IFRS 9 requirement to
incorporate forward-looking information not in the through-the-cycle model.

This multiplicative overlay structure is a bespoke internal design
choice, confirmed against BIS/EBA sources not to reproduce a specific
published or regulatory ECL-overlay formula.

Formula (LaTeX): `m = \max\Big(1+\sum_j \beta_j f_j,\ 0\Big), \quad ECL_{model}=ECL_{base}\cdot m, \quad ECL_{adj}=\max(ECL_{model}+O,\ 0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `base_ecl`* | `number` | required |  |
| `macro_factors`* | `number[] or number[][]` | required |  |
| `sensitivities`* | `number[] or number[][]` | required |  |
| `management_overlay` | `number` | `0.0` |  |

### ifrs_9_staging_criteria_assessment

`POST /api/v1/credit-risk/ifrs_9_staging_criteria_assessment`: Full IFRS 9 staging assessment combining quantitative and qualitative SICR.

Extends the PD-threshold rule with qualitative backstops required by IFRS 9:
forbearance and internal watchlist status force at least Stage 2, while
90+ days past due forces Stage 3. The final stage is the most severe of all
triggered criteria.

The quantitative leg reuses
:func:`ifrs_9_stage_classification_pd_threshold`'s PD-threshold rule
directly (including its ``sicr_relative_threshold`` parameter) rather
than an independently coded SICR test.

Formula (LaTeX): `\text{Stage} = \max\Big(\text{Stage}_{PD},\ 3\cdot\mathbb{1}[DPD\ge90],\ 2\cdot\mathbb{1}[\text{forbearance}],\ 2\cdot\mathbb{1}[\text{watchlist}]\Big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd_current`* | `number` | required |  |
| `pd_origination`* | `number` | required |  |
| `days_past_due` | `integer` | `0` |  |
| `forbearance` | `boolean` | `False` |  |
| `watchlist` | `boolean` | `False` |  |
| `sicr_relative_threshold` | `number` | `2.0` |  |

## Specialised Credit Models

### corporate_credit_scoring_model

`POST /api/v1/credit-risk/corporate_credit_scoring_model`: Weighted-factor corporate credit score mapped to a PD.

Combines normalised factor scores (e.g. leverage, coverage, profitability,
each in ``[0, 1]`` with 1 = strongest) into a composite ``[0, 1]`` rating
strength, then maps to PD via ``PD = pd_anchor * (1 - strength)`` floored at
``pd_floor``. A perfectly strong borrower hits the floor.

This is a bespoke internal weighted-factor model, confirmed against
BIS/EBA sources not to match any specific published or regulatory
scoring formula, so treat it as a reasonable internal model rather than
a reproduction of one.

Formula (LaTeX): `\text{strength} = \frac{\sum_k s_k w_k}{\sum_k w_k}, \quad PD = \max\big(PD_{anchor}\cdot(1-\text{strength}),\ PD_{floor}\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `factor_scores`* | `number[] or number[][]` | required |  |
| `factor_weights`* | `number[] or number[][]` | required |  |
| `pd_floor` | `number` | `0.0003` |  |
| `pd_anchor` | `number` | `0.5` |  |

### sovereign_credit_risk_assessment

`POST /api/v1/credit-risk/sovereign_credit_risk_assessment`: Composite sovereign credit-risk score from macro-fiscal indicators.

Maps standard sovereign indicators into a ``[0, 100]`` creditworthiness
score (higher = stronger): high debt/GDP and twin deficits reduce the score;
larger FX reserves and stronger governance raise it. The score is mapped to
an indicative PD via a logistic transform.

This is a bespoke internal composite-indicator model, confirmed against
BIS/EBA sources not to match any specific published sovereign-risk
methodology (e.g. a rating-agency or IMF framework).

Formula (LaTeX): `\text{score} = \text{clip}\big(50-40D+200F+100CA+3FX+40G,\ 0,\ 100\big), \quad PD = \frac{1}{1+e^{(\text{score}-30)/12}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `debt_to_gdp`* | `number` | required |  |
| `fiscal_balance_pct`* | `number` | required |  |
| `current_account_pct`* | `number` | required |  |
| `fx_reserves_months`* | `number` | required |  |
| `governance_score`* | `number` | required |  |

### sector_default_rate_analysis

`POST /api/v1/credit-risk/sector_default_rate_analysis`: Per-sector default-rate analysis with a concentration of distress.

Computes each sector's default rate, the obligor-weighted overall rate and
each sector's relative risk versus the portfolio average (lift > 1 means the
sector defaults more than average).

Formula (LaTeX): `\text{rate}_i = \frac{D_i}{O_i}, \quad \overline{\text{rate}} = \frac{\sum_i D_i}{\sum_i O_i}, \quad \text{lift}_i = \frac{\text{rate}_i}{\overline{\text{rate}}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `sector_defaults`* | `number[] or number[][]` | required |  |
| `sector_obligors`* | `number[] or number[][]` | required |  |
| `sector_names` | `string[] or null` | `None` |  |

### credit_portfolio_optimisation

`POST /api/v1/credit-risk/credit_portfolio_optimisation`: Single-period credit-portfolio weight optimisation (return vs expected loss).

Maximises a mean-EL utility ``sum_i w_i (r_i - risk_aversion * EL_i)`` subject
to ``sum w = 1`` and ``0 <= w_i <= max_weight``. With these box + simplex
constraints the solution is a greedy water-filling onto the highest
risk-adjusted scores, which is the exact optimum for a linear objective.

No generic LP/QP solver is called anywhere in this function — the
closed-form greedy allocation coded here is exact for this specific
linear-objective, box-plus-simplex problem shape only.

Formula (LaTeX): `\max_{w}\ \sum_i w_i\,(r_i-\gamma\,EL_i) \quad \text{s.t.}\ \sum_i w_i=1,\ 0\le w_i\le w_{max}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_returns`* | `number[] or number[][]` | required |  |
| `expected_losses`* | `number[] or number[][]` | required |  |
| `max_weight` | `number` | `1.0` |  |
| `risk_aversion` | `number` | `1.0` |  |

### credit_stress_testing

`POST /api/v1/credit-risk/credit_stress_testing`: Credit stress test: multiplicative PD/LGD shocks on the loss profile.

Applies a supervisory-style stress (e.g. EBA adverse scenario) by scaling
PD and LGD, clipping to ``[0, 1]``, and reports the baseline vs stressed
expected loss and the incremental impairment.

The baseline EL leg is the definitional ``PD*LGD*EAD``, but the
multiplicative PD/LGD shock structure itself is a bespoke internal
stress design, confirmed against BIS/EBA sources not to reproduce any
specific published adverse-scenario formula.

Formula (LaTeX): `EL_{base} = \sum_i PD_i LGD_i EAD_i \\ PD_i^{stress}=\text{clip}(PD_i\cdot m_{PD},0,1),\ LGD_i^{stress}=\text{clip}(LGD_i\cdot m_{LGD},0,1) \\ EL_{stress} = \sum_i PD_i^{stress} LGD_i^{stress} EAD_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pd`* | `number[] or number[][]` | required |  |
| `lgd`* | `number[] or number[][]` | required |  |
| `ead`* | `number[] or number[][]` | required |  |
| `pd_shock_multiplier` | `number` | `1.5` |  |
| `lgd_shock_multiplier` | `number` | `1.2` |  |
