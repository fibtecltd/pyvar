# pyvar Operational Risk: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/operational/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Capital Models — LDA (`engine/oprisk_lda.py`)

### frequency_distribution_fitting

`POST /api/v1/operational/frequency_distribution_fitting`: Fit a Poisson frequency distribution to annual loss-event counts.

The Poisson MLE for lambda is the sample mean of annual counts. Also reports
the variance-to-mean ratio (dispersion) — a value far above 1 signals
over-dispersion and a possible negative-binomial alternative.

Formula (LaTeX): `\hat\lambda = \frac{1}{n}\sum_i N_i \quad (\text{Poisson MLE}) \\ \text{Dispersion} = \frac{\text{Var}(N)}{\hat\lambda}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `annual_event_counts`* | `number[] or number[][]` | required |  |

### severity_distribution_fitting

`POST /api/v1/operational/severity_distribution_fitting`: Fit a severity distribution to individual loss amounts.

Supports four standard OpRisk severity families, all fit by maximum
likelihood with the location parameter pinned at zero (severities are
strictly positive, so a free location would let the MLE drift away from
the actual support):

- ``"lognormal"`` (default, the OpRisk industry standard): closed-form MLE
  of the log-loss mean/sigma, i.e. ``scipy.stats.lognorm.fit(x, floc=0)``
  reparameterised as ``mu = log(scale)``, ``sigma = shape``.
- ``"gamma"``: ``scipy.stats.gamma.fit(x, floc=0)`` — shape ``a`` and
  ``scale``; commonly used for moderate, right-skewed severities.
- ``"weibull"``: ``scipy.stats.weibull_min.fit(x, floc=0)`` — shape ``c``
  and ``scale``; flexible hazard shape, another standard severity choice.
- ``"gpd"`` (Generalized Pareto Distribution): ``scipy.stats.genpareto.fit(
  x, floc=0)`` — shape ``xi`` and ``scale``; the standard EVT/POT model for
  the tail of large losses (threshold-exceedance modelling). The mean is
  only finite for ``xi < 1``; when ``xi >= 1`` ``mean_severity`` is
  ``None`` rather than a misleading infinite/negative value.

Any other ``distribution`` value raises ``ValueError`` rather than falling
back or approximating.

Formula (LaTeX): `\hat\mu = \overline{\ln X}, \quad \hat\sigma = \text{std}(\ln X) \\ E[X] = e^{\hat\mu + \hat\sigma^2/2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `loss_amounts`* | `number[] or number[][]` | required |  |
| `distribution` | `string` | `'lognormal'` |  |

### compound_loss_distribution

`POST /api/v1/operational/compound_loss_distribution`: Simulate the compound (aggregate) annual loss distribution.

The classic frequency ⊗ severity convolution: for each simulated year draw a
Poisson(lambda) number of events, then that many lognormal(mu, sigma)
severities, and sum. Per RULE 3 all randomness is pre-drawn in pure Python;
the per-year aggregation runs in the JIT kernel.

Formula (LaTeX): `N_y \sim \text{Poisson}(\lambda), \quad X_{y,i} \sim \text{LogNormal}(\mu,\sigma) \\ L_y = \sum_{i=1}^{N_y} X_{y,i} \\ \text{mean\_annual\_loss} = \frac{1}{n}\sum_{y=1}^{n} L_y, \quad \text{std\_annual\_loss} = \text{std}(L_y)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `frequency_lambda`* | `number` | required |  |
| `severity_mu`* | `number` | required |  |
| `severity_sigma`* | `number` | required |  |
| `n_years` | `integer` | `50000` |  |
| `seed` | `integer or null` | `42` |  |

### monte_carlo_oprisk_capital

`POST /api/v1/operational/monte_carlo_oprisk_capital`: Monte Carlo OpRisk regulatory capital (OpVaR + expected shortfall).

Builds the compound loss distribution and reads the loss quantile at the
regulatory confidence (Basel AMA uses 99.9% over a one-year horizon). Capital
is the unexpected loss = OpVaR minus expected loss.

Formula (LaTeX): `L_y \sim \text{Poisson}(\lambda) \otimes \text{LogNormal}(\mu,\sigma) \ \text{(simulated over } n \text{ years)} \\ k = \lfloor \alpha n \rfloor, \quad OpVaR_\alpha = L_{(k)}, \quad EL = \overline{L} \\ Capital = \max(OpVaR_\alpha - EL,\,0), \quad ES_\alpha = \frac{1}{n-k}\sum_{i=k}^{n-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `frequency_lambda`* | `number` | required |  |
| `severity_mu`* | `number` | required |  |
| `severity_sigma`* | `number` | required |  |
| `confidence_level` | `number` | `0.999` |  |
| `n_years` | `integer` | `100000` |  |
| `seed` | `integer or null` | `42` |  |

### operational_var_opvar

`POST /api/v1/operational/operational_var_opvar`: Operational VaR from an empirical aggregate-loss sample.

Reads the loss quantile at the confidence level directly from a supplied
(e.g. simulated or historical) annual-loss array — the generic OpVaR reader.

Formula (LaTeX): `k = \lfloor \alpha n \rfloor \\ OpVaR_\alpha = L_{(k)}, \quad ES_\alpha = \frac{1}{n-k}\sum_{i=k}^{n-1} L_{(i)}, \quad EL = \overline{L}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `annual_losses`* | `number[] or number[][]` | required |  |
| `confidence_level` | `number` | `0.999` |  |

### loss_distribution_approach_lda

`POST /api/v1/operational/loss_distribution_approach_lda`: End-to-end Loss Distribution Approach capital estimate.

Fits the frequency (Poisson) and severity (lognormal) distributions from
historical data, simulates the compound distribution and reads OpVaR /
capital at the regulatory confidence — the full LDA pipeline in one call.

This is a composed pipeline, not a single closed-form equation; ``n_years``
and ``seed`` only control the internal Monte Carlo simulation, not the
capital figure itself.

Formula (LaTeX): `\hat\lambda = \overline{N}, \quad \hat\mu = \overline{\ln X}, \quad \hat\sigma = \text{std}(\ln X) \\ L_y \sim \text{Poisson}(\hat\lambda) \otimes \text{LogNormal}(\hat\mu,\hat\sigma) \ \text{(simulated)} \\ OpVaR_\alpha = L_{(k)},\ k=\lfloor \alpha n \rfloor, \quad Capital = \max(OpVaR_\alpha - \overline{L},\,0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `annual_event_counts`* | `number[] or number[][]` | required |  |
| `loss_amounts`* | `number[] or number[][]` | required |  |
| `confidence_level` | `number` | `0.999` |  |
| `n_years` | `integer` | `100000` |  |
| `seed` | `integer or null` | `42` |  |

### advanced_measurement_approach_ama

`POST /api/v1/operational/advanced_measurement_approach_ama`: Advanced Measurement Approach (AMA) capital charge — retired under Basel III/IV.

Superseded by the Standardised Measurement Approach for Basel III/IV
regulatory capital (see ``basel_standardised_measurement_sma``); retained
here for economic-capital, internal scenario analysis, and jurisdictions
still on earlier timelines only.

The AMA permits the LDA internal model. Under Basel II §669(b), if a bank can
demonstrate that expected loss (EL) is already captured in its provisioning /
pricing, capital may be set to unexpected loss only (OpVaR − EL); otherwise
capital equals the full OpVaR.

OpVaR and EL are not supplied by the caller — both are computed internally by
running the full LDA pipeline (frequency/severity MLE fit, then a Monte Carlo
quantile) over ``annual_event_counts`` and ``loss_amounts``.

Formula (LaTeX): `AMA = \begin{cases} \max(OpVaR - EL,\,0) & \text{expected\_loss\_covered} = \text{True} \\ OpVaR & \text{expected\_loss\_covered} = \text{False} \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `annual_event_counts`* | `number[] or number[][]` | required |  |
| `loss_amounts`* | `number[] or number[][]` | required |  |
| `expected_loss_covered` | `boolean` | `True` |  |
| `confidence_level` | `number` | `0.999` |  |
| `n_years` | `integer` | `100000` |  |
| `seed` | `integer or null` | `42` |  |

## Capital Models — SMA & Economic Capital (`engine/oprisk_capital.py`)

### basel_standardised_measurement_sma

`POST /api/v1/operational/basel_standardised_measurement_sma`: Basel III Standardised Measurement Approach (SMA) capital.

SMA capital = BIC × ILM, where the Business Indicator Component (BIC) is a
piecewise-linear function of the Business Indicator (12%/15%/18% marginal
coefficients across the three buckets) and the Internal Loss Multiplier
(ILM) scales by the bank's historical loss experience:
``ILM = ln(e − 1 + (LC / BIC)^0.8)``. Bucket-1 banks may set ILM = 1.

The ILM = 1.0 case (``use_ilm=False``, bucket-1 BI, or non-positive BIC) is
an explicit override in code rather than a value the log formula itself
produces.

Formula (LaTeX): `BIC = \begin{cases} 0.12\,BI & BI \le 1\text{bn} \\ 0.12(1\text{bn}) + 0.15(BI-1\text{bn}) & 1\text{bn} < BI \le 30\text{bn} \\ 0.12(1\text{bn}) + 0.15(29\text{bn}) + 0.18(BI-30\text{bn}) & BI > 30\text{bn} \end{cases} \\ ILM = \max\left(\ln\left(e-1+\left(\frac{LC}{BIC}\right)^{0.8}\right),\,0\right) \\ SMA = BIC \times ILM`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `business_indicator`* | `number` | required |  |
| `loss_component` | `number` | `0.0` |  |
| `use_ilm` | `boolean` | `True` |  |

### oprisk_capital_allocation

`POST /api/v1/operational/oprisk_capital_allocation`: Allocate total OpRisk capital across business lines (pro-rata by risk).

Distributes the firm-wide capital to business lines in proportion to their
standalone risk contributions, so the allocations sum exactly to the total —
a coherent (additive) allocation.

Formula (LaTeX): `A_i = \frac{R_i}{\sum_j R_j} \times TC`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `total_capital`* | `number` | required |  |
| `business_line_risks`* | `number[] or number[][]` | required |  |

### diversification_benefit_oprisk

`POST /api/v1/operational/diversification_benefit_oprisk`: Diversification benefit across OpRisk cells under a single correlation.

Compares the simple sum of standalone capitals (perfect-correlation, no
diversification) with the correlated aggregate
``sqrt(sum_i sum_j rho_ij K_i K_j)`` using a uniform pairwise correlation.
The benefit is the reduction from imperfect correlation.

Formula (LaTeX): `D_{div} = \sqrt{\sum_i \sum_j \rho_{ij} K_i K_j}, \quad \rho_{ii}=1,\ \rho_{ij}=\rho\ (i\ne j) \\ \text{Benefit} = \max\left(\sum_i K_i - D_{div},\,0\right)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `standalone_capitals`* | `number[] or number[][]` | required |  |
| `correlation` | `number` | `0.0` |  |

### oprisk_economic_capital

`POST /api/v1/operational/oprisk_economic_capital`: OpRisk economic capital (unexpected loss net of mitigants).

Economic capital is the unexpected loss (OpVaR − expected loss) reduced by
recognised risk mitigants (insurance recoveries and diversification), floored
at zero.

Formula (LaTeX): `EC = \max\Big(\max(OpVaR - EL,\,0) - (IO + DB),\,0\Big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `opvar`* | `number` | required |  |
| `expected_loss`* | `number` | required |  |
| `insurance_offset` | `number` | `0.0` |  |
| `diversification_benefit` | `number` | `0.0` |  |

### insurance_offset_calculation

`POST /api/v1/operational/insurance_offset_calculation`: Insurance mitigation offset for an operational loss.

Recoverable amount = ``min(max(gross_loss − deductible, 0), policy_limit)``
reduced by a supervisory haircut (Basel caps total insurance recognition at
20% of capital and applies haircuts for residual term and payment
uncertainty; the cap is applied by the caller).

Formula (LaTeX): `R = \min\big(\max(GL-D,\,0),\,PL\big) \times (1-h) \\ NL = GL - R,\quad \text{RecoveryRate} = R/GL`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `gross_loss`* | `number` | required |  |
| `policy_limit`* | `number` | required |  |
| `deductible`* | `number` | required |  |
| `haircut` | `number` | `0.0` |  |

### tail_risk_scenario_oprisk

`POST /api/v1/operational/tail_risk_scenario_oprisk`: Tail-risk scenario capital uplift for OpRisk.

Stresses the extreme tail by scaling losses beyond the tail quantile by a
``severity_multiplier`` (e.g. a "perfect-storm" amplification) and re-reading
the stressed tail expectation. Reports the uplift over the unstressed tail.

Formula (LaTeX): `k = \lfloor \alpha n \rfloor \\ ES_{base} = \frac{1}{n-k}\sum_{i=k}^{n-1} L_{(i)} \\ ES_{stressed} = ES_{base} \times m`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `annual_losses`* | `number[] or number[][]` | required |  |
| `tail_confidence` | `number` | `0.999` |  |
| `severity_multiplier` | `number` | `1.0` |  |

### oprisk_stress_testing

`POST /api/v1/operational/oprisk_stress_testing`: OpRisk stress-testing capital projection.

Projects stressed capital by scaling the base capital for shocks to event
frequency and severity. Because aggregate loss scales (approximately)
multiplicatively in both drivers, stressed capital =
``base × (1 + freq_shock) × (1 + sev_shock)``.

Formula (LaTeX): `SC = B \times (1+f) \times (1+s)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `base_capital`* | `number` | required |  |
| `frequency_shock`* | `number` | required |  |
| `severity_shock`* | `number` | required |  |

## Loss Data (`engine/oprisk_rcsa.py`)

### loss_data_collection_framework

`POST /api/v1/operational/loss_data_collection_framework`: Internal loss-data collection above a reporting threshold.

Filters loss events at or above the firm's de-minimis reporting threshold and
summarises count and total — the internal loss dataset feeding the LDA.

Formula (LaTeX): `\text{Reportable} = \{\,A_i : A_i \ge \tau\,\} \\ \text{total\_loss} = \sum_{A_i \ge \tau} A_i, \quad \text{max\_loss} = \max_{A_i \ge \tau} A_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `loss_events`* | `object[]` | required |  |
| `reporting_threshold`* | `number` | required |  |

### external_loss_data_integration

`POST /api/v1/operational/external_loss_data_integration`: Integrate scaled external loss data with internal data.

External (consortium / public) losses are scaled to the firm's size by a
``scaling_factor`` (e.g. ratio of revenues) before being pooled with internal
losses — the standard approach for enriching a sparse internal tail.

Formula (LaTeX): `X'_{ext} = s \cdot X_{ext} \\ \text{combined\_mean} = \frac{\sum X_{int} + \sum X'_{ext}}{n_{int}+n_{ext}}, \quad w_{ext} = \frac{n_{ext}}{n_{int}+n_{ext}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `internal_losses`* | `number[] or number[][]` | required |  |
| `external_losses`* | `number[] or number[][]` | required |  |
| `scaling_factor`* | `number` | required |  |

### loss_event_classification_basel

`POST /api/v1/operational/loss_event_classification_basel`: Classify a loss event into a Basel II Level-1 event-type category.

Validates the event type against the seven Basel II Level-1 categories
(BCBS 128, Annex 9) and returns its ordinal index for downstream bucketing.

This is a membership lookup against the fixed seven Basel II categories, not
a numeric equation.

Formula (LaTeX): `\text{valid} = \big(ET \in \mathcal{C}_{Basel}\big) \\ idx = \begin{cases} \text{index}(ET) & \text{valid} \\ -1 & \text{otherwise} \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `event_type`* | `string` | required |  |

## RCSA Framework (`engine/oprisk_rcsa.py`)

### rcsa_risk_identification

`POST /api/v1/operational/rcsa_risk_identification`: Validate and summarise an RCSA risk register.

Checks each risk entry exposes a ``risk_id`` and a Basel ``category`` and
summarises counts by category — the identification step of the RCSA cycle.

This is validation plus a count-by-category aggregation, not a numeric
formula; ``category`` is a per-entry dict key rather than a top-level
function parameter.

Formula (LaTeX): `\text{by\_category}[c] = \sum_i \mathbb{1}[\text{category}_i = c]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `risk_register`* | `object[]` | required |  |

### rcsa_inherent_risk_scoring

`POST /api/v1/operational/rcsa_inherent_risk_scoring`: Inherent risk score on the 5×5 RCSA heat map.

Inherent risk is the gross exposure before controls: ``likelihood × impact``
on the 1-5 scale, giving a 1-25 score mapped to a RAG band.

Formula (LaTeX): `S = L \times I`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `likelihood`* | `integer` | required |  |
| `impact`* | `integer` | required |  |

### rcsa_residual_risk_scoring

`POST /api/v1/operational/rcsa_residual_risk_scoring`: Residual risk after control mitigation.

Residual = ``inherent × (1 − control_effectiveness)``: effective controls
reduce the inherent score toward zero. The residual is mapped to a RAG band.

Formula (LaTeX): `R = I \times (1 - CE)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `inherent_score`* | `number` | required |  |
| `control_effectiveness`* | `number` | required |  |

### rcsa_control_effectiveness

`POST /api/v1/operational/rcsa_control_effectiveness`: Composite control effectiveness from design and operating effectiveness.

Combines design effectiveness (is the control well-designed?) and operating
effectiveness (does it operate as intended?) into a single [0, 1] score via a
weighted average.

Formula (LaTeX): `E = w_D \cdot D + (1-w_D) \cdot O`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `design_score`* | `number` | required |  |
| `operating_score`* | `number` | required |  |
| `design_weight` | `number` | `0.4` |  |

### control_testing_effectiveness

`POST /api/v1/operational/control_testing_effectiveness`: Control testing pass rate and effectiveness conclusion.

The empirical pass rate from control testing samples; an exception rate above
a supervisory tolerance (default >5% failures) downgrades the conclusion.

Formula (LaTeX): `PR = \frac{P}{T}, \quad \text{ExceptionRate} = 1-PR \\ \text{conclusion} = \text{effective if } PR \ge 0.95 \text{ else deficient}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `tests_passed`* | `integer` | required |  |
| `tests_total`* | `integer` | required |  |

## BEICF Factors (`engine/oprisk_rcsa.py`)

### business_environment_factor_bei

`POST /api/v1/operational/business_environment_factor_bei`: Business Environment Indicator (BEI) capital adjustment multiplier.

Translates forward-looking business-environment factor scores (e.g. on a 1-5
scale where higher = riskier) into a capital multiplier around 1.0: scores
above the baseline increase capital, below decrease it. Part of the BEICF
overlay permitted under the AMA.

Formula (LaTeX): `\overline{S} = \frac{1}{n}\sum_i S_i \\ BEI = \max\big(1 + k(\overline{S}-B),\,0\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `factor_scores`* | `number[] or number[][]` | required |  |
| `baseline` | `number` | `3.0` |  |
| `sensitivity` | `number` | `0.05` |  |

### internal_control_factor_icf

`POST /api/v1/operational/internal_control_factor_icf`: Internal Control Factor (ICF) capital adjustment multiplier.

Stronger internal controls (higher average effectiveness in [0, 1]) reduce
the capital multiplier below 1.0; weaker controls increase it. The BEICF
counterpart to :func:`business_environment_factor_bei`.

Formula (LaTeX): `\overline{C} = \frac{1}{n}\sum_i C_i \\ ICF = \max\big(1 - k(\overline{C}-B),\,0\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `control_scores`* | `number[] or number[][]` | required |  |
| `baseline` | `number` | `0.8` |  |
| `sensitivity` | `number` | `0.25` |  |

## KRI Library (`engine/oprisk_kri.py`)

### key_risk_indicator_kri_library

`POST /api/v1/operational/key_risk_indicator_kri_library`: Validate and index a KRI library.

Each KRI definition must carry a ``name``, a numeric ``amber_threshold`` and
``red_threshold``, and a ``direction`` (``"higher_breach"`` or
``"lower_breach"``). Returns a validated registry keyed by name.

This is a pure validation/indexing pass — it checks required keys and builds
the keyed registry, with no numeric computation involved.

Formula (LaTeX): `\text{Registry} = \{\,k.\text{name} \mapsto k \mid k \in \text{kri\_definitions},\ k\ \text{valid}\,\}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `kri_definitions`* | `object[]` | required |  |

### kri_threshold_breach_detection

`POST /api/v1/operational/kri_threshold_breach_detection`: Classify a KRI value into a green/amber/red status.

For ``higher_breach`` KRIs (higher = worse, e.g. failed trades) the value
crosses amber then red as it rises; for ``lower_breach`` KRIs (lower = worse,
e.g. staffing level) it crosses as it falls.

For ``lower_breach`` every inequality above is reversed (red at or below the
red threshold, amber between red and amber, green above amber).

Formula (LaTeX): `\text{status} = \begin{cases} \text{red} & V \ge R \\ \text{amber} & A \le V < R \\ \text{green} & V < A \end{cases} \quad (\text{direction}=\text{higher\_breach})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `value`* | `number` | required |  |
| `amber_threshold`* | `number` | required |  |
| `red_threshold`* | `number` | required |  |
| `direction` | `string` | `'higher_breach'` |  |

### kri_trend_analysis

`POST /api/v1/operational/kri_trend_analysis`: Linear-trend analysis of a KRI time series.

Fits an OLS slope to the observation series and classifies the trend as
``"deteriorating"``, ``"improving"`` or ``"stable"`` based on the slope sign
and the metric direction.

"Stable" is a scale-relative rule (``|slope| < 1e-4 * mean(|observations|)``),
not a fixed absolute tolerance, and the deteriorating/improving call flips
with ``higher_is_worse``.

Formula (LaTeX): `\hat\beta_1 = \arg\min_{\beta_0,\beta_1} \sum_t \big(y_t - (\beta_0+\beta_1 t)\big)^2 \quad (\text{OLS slope, } t=0,\dots,n-1) \\ \text{trend} = \text{stable if } |\hat\beta_1| < 10^{-4}\overline{|y|},\ \text{else deteriorating/improving by sign of } \hat\beta_1`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `observations`* | `number[] or number[][]` | required |  |
| `higher_is_worse` | `boolean` | `True` |  |

## Scenario Analysis (`engine/oprisk_scenario.py`)

### scenario_analysis_oprisk

`POST /api/v1/operational/scenario_analysis_oprisk`: Scenario-based OpRisk capital via a compound Monte Carlo.

Builds a single scenario's aggregate annual loss distribution from its
calibrated frequency and lognormal severity and reads the loss quantile —
the scenario's contribution to capital. Per RULE 3 randomness is pre-drawn
in pure Python.

Formula (LaTeX): `N_y \sim \text{Poisson}(\lambda), \quad X \sim \text{LogNormal}(\mu,\sigma), \quad L_y = \sum_{i=1}^{N_y} X_i \\ k = \lfloor \alpha n \rfloor, \quad \text{ScenarioVaR}_\alpha = L_{(k)} \\ EL = \overline{L}, \quad ES_\alpha = \frac{1}{n-k}\sum_{i=k}^{n-1} L_{(i)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `frequency_lambda`* | `number` | required |  |
| `severity_mu`* | `number` | required |  |
| `severity_sigma`* | `number` | required |  |
| `confidence_level` | `number` | `0.999` |  |
| `n_years` | `integer` | `50000` |  |
| `seed` | `integer or null` | `42` |  |

### scenario_expert_elicitation_model

`POST /api/v1/operational/scenario_expert_elicitation_model`: Aggregate expert loss estimates into a consensus with dispersion.

Combines multiple experts' point estimates into a weighted consensus and
reports the dispersion (weighted standard deviation) as a confidence proxy —
wide disagreement signals an unreliable scenario.

Formula (LaTeX): `C = \frac{\sum_i w_i E_i}{\sum_i w_i} \\ \sigma_{disp} = \sqrt{\frac{\sum_i w_i (E_i-C)^2}{\sum_i w_i}}, \quad CV = \frac{\sigma_{disp}}{C}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expert_estimates`* | `number[] or number[][]` | required |  |
| `expert_weights` | `number[] or number[][] or null` | `None` |  |

### scenario_severity_estimation

`POST /api/v1/operational/scenario_severity_estimation`: Calibrate a lognormal severity from expert typical / worst-case losses.

Treats ``typical_loss`` as the lognormal median (so ``mu = ln(typical)``) and
solves for ``sigma`` from the worst-case percentile:
``sigma = (ln(worst) − mu) / z_p``. This is the standard two-point expert
calibration for scenario severities.

Formula (LaTeX): `\mu = \ln(TL) \\ z_p = \Phi^{-1}(p), \quad \sigma = \frac{\ln(WL) - \mu}{z_p} \\ E[X] = e^{\mu + \sigma^2/2}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `typical_loss`* | `number` | required |  |
| `worst_case_loss`* | `number` | required |  |
| `worst_case_percentile` | `number` | `0.99` |  |

### scenario_frequency_estimation

`POST /api/v1/operational/scenario_frequency_estimation`: Estimate a scenario's annual frequency (Poisson lambda).

Uses the expert's expected events per year directly, or — if historical
occurrence data is supplied — the empirical rate ``occurrences /
observation_years``. The result is the Poisson lambda feeding the scenario's
compound loss.

Formula (LaTeX): `\lambda = \begin{cases} \dfrac{Occ}{Y} & \text{occurrences supplied (empirical)} \\ \lambda_0 & \text{otherwise (expert)} \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_events_per_year`* | `number` | required |  |
| `occurrences` | `integer or null` | `None` |  |
| `observation_years` | `number or null` | `None` |  |

## Emerging Risk Categories (`engine/oprisk_governance.py`)

### cyber_risk_loss_estimation

`POST /api/v1/operational/cyber_risk_loss_estimation`: Estimate expected and worst-case cyber loss.

Worst-case (given a breach) = ``records_exposed × cost_per_record +
business_interruption_cost``; expected loss multiplies by the annual breach
probability — a FAIR-style single-loss-expectancy estimate.

Formula (LaTeX): `L_{worst} = N \times C + BI \\ L_{exp} = L_{worst} \times p`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `records_exposed`* | `number` | required |  |
| `cost_per_record`* | `number` | required |  |
| `breach_probability`* | `number` | required |  |
| `business_interruption_cost` | `number` | `0.0` |  |

### conduct_risk_metric

`POST /api/v1/operational/conduct_risk_metric`: Composite conduct-risk metric from complaints and redress intensity.

Combines the complaints-per-1000-customers rate and the redress-to-revenue
ratio into a normalised 0-100 conduct-risk index (higher = worse) with a RAG
band.

Formula (LaTeX): `CPK = \frac{Complaints}{Customers}\times 1000,\quad RR = \frac{Redress}{Revenue} \\ Index = \min(CPK,\,50) + \min(500\,RR,\,50)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `complaints`* | `number` | required |  |
| `customers`* | `number` | required |  |
| `redress_paid`* | `number` | required |  |
| `revenue`* | `number` | required |  |

### model_risk_assessment

`POST /api/v1/operational/model_risk_assessment`: Model risk tier from materiality, complexity, and validation quality.

Combines model materiality and complexity (1-5 each) into an inherent score,
then discounts by validation quality (in [0, 1]) to a residual model-risk
tier (SR 11-7 / PRA SS1/23 style).

SR 11-7 / PRA SS1/23 are named only for the general materiality x complexity
tiering style this follows; the specific 1-5 scale, multiplication, and RAG
thresholds are pyvar's own, not values prescribed by either document.

Formula (LaTeX): `I = M \times C \\ R = I \times (1 - V)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `materiality`* | `integer` | required |  |
| `complexity`* | `integer` | required |  |
| `validation_score`* | `number` | required |  |

### it_risk_scoring

`POST /api/v1/operational/it_risk_scoring`: IT operational-risk score from availability, incidents and patching.

Blends system availability (fraction), incident frequency and patch
compliance (fraction) into a 0-100 IT-risk score (higher = worse) with a RAG
band.

Formula (LaTeX): `S = \min\Big(40(1-A) + 2\min(N,\,20) + 20(1-P),\,100\Big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `availability`* | `number` | required |  |
| `incident_count`* | `number` | required |  |
| `patch_compliance`* | `number` | required |  |

### third_party_vendor_risk

`POST /api/v1/operational/third_party_vendor_risk`: Third-party / vendor risk score.

Weighted index of vendor criticality (1-5), inverse financial health,
concentration and inverse substitutability — all normalised to a 0-100 score
(higher = worse).

Formula (LaTeX): `S = 30\,\frac{Cr}{5} + 30(1-FH) + 20\,Conc + 20(1-Sub)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `criticality`* | `integer` | required |  |
| `financial_health`* | `number` | required |  |
| `concentration`* | `number` | required |  |
| `substitutability`* | `number` | required |  |

### business_continuity_risk_score

`POST /api/v1/operational/business_continuity_risk_score`: Business-continuity risk from RTO/RPO versus tolerance and BCP maturity.

Flags where the recovery time objective (RTO) exceeds the maximum
tolerable downtime (MTD) and discounts the residual risk by BCP maturity.
A breach of either recovery objective is the dominant driver.

By default (``rpo_target_hours`` omitted) this is byte-identical to the
original RTO-only scoring: ``rpo_hours`` is still range-validated but does
not affect ``bc_risk_score``, since RPO risk has nothing to be measured
against without a target to compare it to. Pass ``rpo_target_hours`` (the
maximum tolerable period of data loss, per ISO 22301 / DRI International
BCM practice) to additionally score potential data loss: RTO and RPO are
independently critical recovery objectives — a plan can fail on either
axis — so the pre-BCP-maturity risk is the *worse* of the two, not an
average of them, consistent with this function's existing "a breach is
the dominant driver" philosophy for RTO alone.

Formula (LaTeX): `G = \min\!\left(\frac{RTO}{MTD},\,2\right)\Big/2 \\ Raw = 50\cdot\mathbb{1}[RTO>MTD] + 50\,G \\ Score = \min\big(Raw\times(1-0.5\,M),\,100\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `rto_hours`* | `number` | required |  |
| `rpo_hours`* | `number` | required |  |
| `max_tolerable_downtime`* | `number` | required |  |
| `bcp_maturity`* | `number` | required |  |
| `rpo_target_hours` | `number or null` | `None` |  |

## Governance & Reporting (`engine/oprisk_governance.py`)

### near_miss_capture_framework

`POST /api/v1/operational/near_miss_capture_framework`: Summarise captured near-miss events.

A near-miss is an event with zero actual loss but a non-zero potential loss.
Validates events and summarises the count and aggregate potential loss — a
leading indicator of control weakness.

This is a rule-based filter/count over ``events``; ``actual_loss`` and
``potential_loss`` are per-event dict keys rather than top-level function
parameters.

Formula (LaTeX): `N_{nm} = \sum_i \mathbb{1}[AL_i=0 \wedge PL_i>0] \\ TPL = \sum_i PL_i \cdot \mathbb{1}[AL_i=0 \wedge PL_i>0]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `events`* | `object[]` | required |  |

### root_cause_analysis_template

`POST /api/v1/operational/root_cause_analysis_template`: Aggregate root-cause contributions into a normalised attribution.

Normalises the supplied causal-factor weights (e.g. people, process,
systems, external) to sum to 1 and identifies the dominant root cause — the
quantitative backbone of an RCA template.

Formula (LaTeX): `A_k = \frac{w_k}{\sum_j w_j}, \quad \text{primary} = \arg\max_k A_k`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `causal_factors`* | `object` | required |  |

### risk_appetite_statement_oprisk

`POST /api/v1/operational/risk_appetite_statement_oprisk`: Assess an OpRisk metric against appetite and tolerance limits.

Maps a metric to ``within_appetite`` / ``within_tolerance`` / ``breach``
against a two-tier limit structure: appetite (the desired ceiling) and
tolerance (the absolute maximum before escalation).

When ``higher_is_worse=False`` every inequality is reversed and utilisation
is computed as ``tolerance_limit / current_metric`` rather than the
``current_metric / tolerance_limit`` used in the higher-is-worse case.

Formula (LaTeX): `\text{status} = \begin{cases} \text{within\_appetite} & X \le A \\ \text{within\_tolerance} & A < X \le T \\ \text{breach} & X > T \end{cases} \quad (\text{higher\_is\_worse=True}) \\ U = X/T`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `current_metric`* | `number` | required |  |
| `appetite_limit`* | `number` | required |  |
| `tolerance_limit`* | `number` | required |  |
| `higher_is_worse` | `boolean` | `True` |  |

### escalation_threshold_calculation

`POST /api/v1/operational/escalation_threshold_calculation`: Determine the escalation level for a loss against tiered thresholds.

Maps a loss amount to the highest governance tier whose threshold it meets or
exceeds (e.g. ``{"team": 1e3, "head": 1e4, "exco": 1e5, "board": 1e6}``).

This is a rule-based lookup: it selects the triggered tier with the
numerically largest threshold value, not necessarily the dict's declared
"highest" tier by name or insertion order, so it relies on ``thresholds``
being ordered monotonically with severity.

Formula (LaTeX): `\text{Triggered} = \{\,lvl : thr_{lvl} \mid L \ge thr_{lvl}\,\} \\ lvl^{*} = \arg\max_{lvl \in \text{Triggered}} thr_{lvl}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `loss_amount`* | `number` | required |  |
| `thresholds`* | `object` | required |  |

### oprisk_heat_map_generator

`POST /api/v1/operational/oprisk_heat_map_generator`: Generate a 5×5 OpRisk heat-map distribution.

Buckets each (likelihood, impact) risk into the 5×5 grid and computes the
score (likelihood × impact) and RAG band for each, plus a count matrix of
risks per cell.

Formula (LaTeX): `S_i = L_i \times I_i \\ \text{Matrix}_{a,b} = \#\{\,i : L_i=a,\ I_i=b\,\}, \quad a,b \in \{1,\dots,5\}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `likelihoods`* | `number[] or number[][]` | required |  |
| `impacts`* | `number[] or number[][]` | required |  |

### regulatory_compliance_score

`POST /api/v1/operational/regulatory_compliance_score`: Weighted regulatory-compliance score.

Computes the weighted fraction of regulatory requirements met (each 0 = not
met, 1 = met, or a partial value in between) as a 0-100 compliance score with
a RAG band.

Formula (LaTeX): `Score = 100 \times \frac{\sum_i w_i m_i}{\sum_i w_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `requirements_met`* | `number[] or number[][]` | required |  |
| `weights` | `number[] or number[][] or null` | `None` |  |

### audit_finding_risk_scorer

`POST /api/v1/operational/audit_finding_risk_scorer`: Score an outstanding audit finding by severity, likelihood and ageing.

Base score is severity × likelihood on the 5×5 scale; overdue remediation
escalates the score (each 30-day block adds an uplift), capped at 25.

Formula (LaTeX): `S_{base} = Sev \times Lik \\ S_{adj} = \min\left(S_{base} + 2\left\lfloor \frac{OD}{30} \right\rfloor,\,25\right)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `severity`* | `integer` | required |  |
| `likelihood`* | `integer` | required |  |
| `overdue_days`* | `number` | required |  |
