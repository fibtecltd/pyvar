# pyvar ALM and Balance Sheet: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/alm/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Duration & Gap Analysis

### duration_gap_analysis

`POST /api/v1/alm/duration_gap_analysis`: Duration-gap analysis of the banking book.

Duration gap ``DGAP = D_A − (L/A)·D_L``. The change in economic value of
equity for a rate shock is approximately ``ΔEVE ≈ −DGAP · A · Δy``.

Formula (LaTeX): `DGAP = D_A - \dfrac{L}{A}D_L \quad \Delta EVE \approx -DGAP\cdot A\cdot \Delta y`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_duration`* | `number` | required |  |
| `liability_duration`* | `number` | required |  |
| `total_assets`* | `number` | required |  |
| `total_liabilities`* | `number` | required |  |
| `rate_shock` | `number` | `0.01` |  |

### macaulay_duration_balance_sheet

`POST /api/v1/alm/macaulay_duration_balance_sheet`: Macaulay duration of a balance-sheet cashflow stream (years).

Formula (LaTeX): `D_{mac} = \dfrac{\sum_i t_i\,CF_i\,e^{-y t_i}}{\sum_i CF_i\,e^{-y t_i}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `discount_rate`* | `number` | required |  |

### modified_duration_balance_sheet

`POST /api/v1/alm/modified_duration_balance_sheet`: Modified duration of a balance-sheet position.

``D_mod = D_mac / (1 + y/m)``; with continuous discounting (frequency large)
modified ≈ Macaulay.

Formula (LaTeX): `D_{mac} = \dfrac{\sum_i t_i\,CF_i\,e^{-y t_i}}{\sum_i CF_i\,e^{-y t_i}} \quad D_{mod} = \dfrac{D_{mac}}{1+y/m}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `discount_rate`* | `number` | required |  |
| `frequency` | `integer` | `1` |  |

### effective_duration_alm

`POST /api/v1/alm/effective_duration_alm`: Effective duration of an ALM position from re-valued PVs under a shock.

``D_eff = (PV− − PV+) / (2 · PV0 · Δy)`` — captures optionality in deposits,
prepayments and caps/floors that analytic duration misses.

Formula (LaTeX): `D_{eff} = \dfrac{PV_{-} - PV_{+}}{2\,PV_0\,\Delta y}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pv_base`* | `number` | required |  |
| `pv_up`* | `number` | required |  |
| `pv_down`* | `number` | required |  |
| `rate_shock`* | `number` | required |  |

### convexity_gap

`POST /api/v1/alm/convexity_gap`: Convexity gap of the banking book.

``CGAP = C_A − (L/A)·C_L`` — the second-order term refining the
duration-gap EVE estimate ``ΔEVE ≈ A(−DGAP·Δy + ½·CGAP·Δy²)``.

Formula (LaTeX): `CGAP = C_A - \dfrac{L}{A}\,C_L`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_convexity`* | `number` | required |  |
| `liability_convexity`* | `number` | required |  |
| `total_assets`* | `number` | required |  |
| `total_liabilities`* | `number` | required |  |

## NII & EVE Simulation

### nii_simulation_stress

`POST /api/v1/alm/nii_simulation_stress`: Stressed NII under a parallel rate shock with repricing betas.

Asset and liability rates reprice by ``beta · shock`` (betas capture
incomplete pass-through, especially on deposits). Returns the stressed NII
and the change versus baseline.

Formula (LaTeX): `\begin{aligned}NII_{base} &=\sum_i A_i r_i^A - \sum_j L_j r_j^L\\NII_{stress} &=\sum_i A_i(r_i^A+\beta_A\Delta y)-\sum_j L_j(r_j^L+\beta_L\Delta y)\\\Delta NII &= NII_{stress}-NII_{base}\end{aligned}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_balances`* | `number[] or number[][]` | required |  |
| `asset_rates`* | `number[] or number[][]` | required |  |
| `liability_balances`* | `number[] or number[][]` | required |  |
| `liability_rates`* | `number[] or number[][]` | required |  |
| `rate_shock`* | `number` | required |  |
| `asset_beta` | `number` | `1.0` |  |
| `liability_beta` | `number` | `0.5` |  |

### economic_value_of_equity_eve

`POST /api/v1/alm/economic_value_of_equity_eve`: Economic Value of Equity: PV(assets) − PV(liabilities).

[REGULATORY] BCBS d368. EVE is the residual economic value accruing to
equity holders after discounting all banking-book cashflows.

Formula (LaTeX): `EVE = \sum_i CF_i^A e^{-r_i^A t_i^A} - \sum_j CF_j^L e^{-r_j^L t_j^L}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_cashflows`* | `number[] or number[][]` | required |  |
| `asset_times`* | `number[] or number[][]` | required |  |
| `liability_cashflows`* | `number[] or number[][]` | required |  |
| `liability_times`* | `number[] or number[][]` | required |  |
| `asset_rates`* | `number[] or number[][]` | required |  |
| `liability_rates`* | `number[] or number[][]` | required |  |

### eve_sensitivity_analysis

`POST /api/v1/alm/eve_sensitivity_analysis`: EVE sensitivity (ΔEVE) under each of the six IRRBB rate shocks.

[REGULATORY] BCBS d368. Reports ΔEVE for every prescribed scenario and the
worst case — the headline supervisory metric.

Formula (LaTeX): `EVE(r)=\sum_k CF_k e^{-r_k t_k}, \quad \Delta EVE_s = EVE(r_0+\Delta r_s)-EVE(r_0), \\ \Delta EVE_{worst}=\min_s\Delta EVE_s`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `net_cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `base_rates`* | `number[] or number[][]` | required |  |
| `parallel_bps` | `number` | `200.0` |  |
| `short_bps` | `number` | `300.0` |  |
| `long_bps` | `number` | `150.0` |  |

### nii_sensitivity_rate_shock

`POST /api/v1/alm/nii_sensitivity_rate_shock`: Net interest income sensitivity to a parallel rate shock.

``ΔNII ≈ (RSA − RSL) · Δrate`` where ``RSA − RSL`` is the cumulative
one-year repricing gap. A positive gap gains NII when rates rise.

Formula (LaTeX): `\Delta NII = (RSA-RSL)\cdot \Delta y`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `rate_sensitive_assets`* | `number` | required |  |
| `rate_sensitive_liabilities`* | `number` | required |  |
| `rate_shock`* | `number` | required |  |

### nii_simulation_baseline

`POST /api/v1/alm/nii_simulation_baseline`: Baseline (current-rate) net-interest-income projection.

``NII = Σ A_i·r^A_i − Σ L_j·r^L_j`` over the projection horizon.

Formula (LaTeX): `NII = \sum_i A_i r_i^A - \sum_j L_j r_j^L`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_balances`* | `number[] or number[][]` | required |  |
| `asset_rates`* | `number[] or number[][]` | required |  |
| `liability_balances`* | `number[] or number[][]` | required |  |
| `liability_rates`* | `number[] or number[][]` | required |  |

### liquidity_adjusted_nii

`POST /api/v1/alm/liquidity_adjusted_nii`: Liquidity-adjusted NII: base NII net of the liquidity-buffer carry cost.

Holding a high-quality liquid-asset buffer earns ``buffer_yield`` but is
funded at ``funding_cost`` plus a ``liquidity_premium`` — usually a net
drag. Adjusted NII = base + buffer·(yield − funding − premium).

Formula (LaTeX): `NII_{adj} = NII_{base} + B\,(y_B-c_F-p_{liq})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `base_nii`* | `number` | required |  |
| `liquidity_buffer`* | `number` | required |  |
| `buffer_yield`* | `number` | required |  |
| `funding_cost`* | `number` | required |  |
| `liquidity_premium`* | `number` | required |  |

## IRRBB Framework

### irrbb_standardised_framework

`POST /api/v1/alm/irrbb_standardised_framework`: Standardised IRRBB EVE measure: worst ΔEVE across the six shocks.

[REGULATORY] BCBS d368. ΔEVE per scenario is the change in the present value
of net banking-book cashflows under the shocked curve; the regulatory metric
is the maximum loss (most negative ΔEVE).

Formula (LaTeX): `EVE(r)=\sum_k CF_k e^{-r_k t_k}, \quad \Delta EVE_s = EVE(r_0+\Delta r_s)-EVE(r_0), \\ \Delta EVE_{worst}=\min_s \Delta EVE_s`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `net_cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `base_rates`* | `number[] or number[][]` | required |  |
| `parallel_bps` | `number` | `200.0` |  |
| `short_bps` | `number` | `300.0` |  |
| `long_bps` | `number` | `150.0` |  |

### irrbb_internal_model

`POST /api/v1/alm/irrbb_internal_model`: Internal-model IRRBB EVE using a bank's own rate scenarios.

Unlike the standardised framework this accepts an arbitrary matrix of
rate-shock scenarios (e.g. historical or Monte Carlo simulated) and reports
the EVE distribution and a 99% worst-case.

Formula (LaTeX): `EVE(r)=\sum_k CF_k e^{-r_k t_k}, \quad \Delta EVE_s = EVE(r_0+\Delta r_s)-EVE(r_0), \\ WorstCase_{99}=\mathrm{Percentile}_{1\%}\big(\{\Delta EVE_s\}\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `net_cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `base_rates`* | `number[] or number[][]` | required |  |
| `rate_scenarios`* | `number[] or number[][]` | required |  |

### irrbb_six_standard_rate_shocks

`POST /api/v1/alm/irrbb_six_standard_rate_shocks`: Construct the six BCBS d368 standard interest-rate shock curves.

[REGULATORY] BCBS d368 Annex 2 (not §115 -- a prior citation here named
the wrong section; Annex 2 is where the shock-construction formulas
actually live). The steepener/flattener combine scaled short and long
shocks: ``steepener = −0.65·short + 0.90·long`` and
``flattener = +0.80·short − 0.60·long`` (per-tenor short/long scalars decay
as ``e^{−t/4}``). See the module docstring for a [LIMITATION] on the
default shock magnitudes (``parallel_bps``/``short_bps``/``long_bps``) --
BCBS d578 recalibrated these in 2024, effective 2026.

Formula (LaTeX): `\begin{aligned}s_{short}(t) &= \dfrac{short_{bps}}{10^4}e^{-t/4},\\s_{long}(t) &= \dfrac{long_{bps}}{10^4}\big(1-e^{-t/4}\big)\\Steepener &= -0.65\,s_{short}+0.90\,s_{long},\\Flattener &= 0.80\,s_{short}-0.60\,s_{long},\\Parallel_{\pm} &= \pm\dfrac{parallel_{bps}}{10^4}\end{aligned}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `tenors`* | `number[] or number[][]` | required |  |
| `parallel_bps` | `number` | `200.0` |  |
| `short_bps` | `number` | `300.0` |  |
| `long_bps` | `number` | `150.0` |  |

### basis_risk_irrbb

`POST /api/v1/alm/basis_risk_irrbb`: Basis risk: NII impact of imperfectly-correlated index repricing.

[REGULATORY] BCBS d368 — basis risk arises when assets and liabilities
reprice off different indices. ΔNII = Σ A·Δi_A − Σ L·Δi_L.

Formula (LaTeX): `\Delta NII = \sum_i A_i\,\Delta i_i^A - \sum_j L_j\,\Delta i_j^L`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_balances`* | `number[] or number[][]` | required |  |
| `asset_index_shifts`* | `number[] or number[][]` | required |  |
| `liability_balances`* | `number[] or number[][]` | required |  |
| `liability_index_shifts`* | `number[] or number[][]` | required |  |

### option_risk_irrbb

`POST /api/v1/alm/option_risk_irrbb`: Option risk: value of automatic and behavioural embedded options.

[REGULATORY] BCBS d368 distinguishes automatic options (caps/floors,
prepayment options exercised optimally) from behavioural options (early
redemption, deposit withdrawal). Total option risk = sum of both.

Formula (LaTeX): `OptionRisk_{total}=V_{auto}+V_{behav},\quad Ratio=\dfrac{V_{auto}+V_{behav}}{N}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `automatic_option_value`* | `number` | required |  |
| `behavioural_option_value`* | `number` | required |  |
| `notional`* | `number` | required |  |

### pipeline_risk_measurement

`POST /api/v1/alm/pipeline_risk_measurement`: Pipeline risk of rate-locked mortgage commitments not yet on balance.

Note: ``rate_risk`` is a heuristic √time-scaled volatility exposure
proxy, not a rigorous option-pricing valuation of the rate-lock
optionality.

Exposure = ``notional · pull_through``; the rate risk scales with the
rate-lock period and rate volatility (a √time vol exposure proxy).

Formula (LaTeX): `E = N\cdot p,\quad RateRisk = E\cdot\sigma\cdot\sqrt{T}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pipeline_notional`* | `number` | required |  |
| `pull_through_rate`* | `number` | required |  |
| `rate_lock_period`* | `number` | required |  |
| `rate_volatility`* | `number` | required |  |

### interest_rate_risk_capital_irrbb

`POST /api/v1/alm/interest_rate_risk_capital_irrbb`: IRRBB supervisory outlier test against Tier-1 capital.

[REGULATORY] BCBS d368 Principle 12 (not §118 -- a prior citation here
named the wrong section; the 15%-of-Tier-1 supervisory outlier test is set
out under Principle 12): a bank is an outlier if the worst-case EVE
decline exceeds 15% of Tier-1 capital. Capital implied is the breach amount.

Formula (LaTeX): `Decline = \big|\min(\Delta EVE_{worst},0)\big|, \quad Threshold=\theta\cdot Tier1, \\ AddOn=\max(Decline-Threshold,0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `worst_delta_eve`* | `number` | required |  |
| `tier1_capital`* | `number` | required |  |
| `outlier_threshold` | `number` | `0.15` |  |

## Repricing & Gap

### static_gap_analysis

`POST /api/v1/alm/static_gap_analysis`: Static (point-in-time) repricing gap assuming a frozen balance sheet.

Formula (LaTeX): `gap_i=RSA_i-RSL_i,\quad GapRatio=\dfrac{\sum_i RSA_i}{\sum_i RSL_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `bucket_assets`* | `number[] or number[][]` | required |  |
| `bucket_liabilities`* | `number[] or number[][]` | required |  |

### dynamic_gap_analysis

`POST /api/v1/alm/dynamic_gap_analysis`: Dynamic gap projecting balance growth over future periods.

Applies per-bucket growth rates compounding over ``n_periods`` and returns
the projected gap path — capturing new business unlike a static gap.

Formula (LaTeX): `Gap_p = \sum_i A_i(1+g_i^A)^p - \sum_i L_i(1+g_i^L)^p,\quad p=1,\dots,n`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `bucket_assets`* | `number[] or number[][]` | required |  |
| `bucket_liabilities`* | `number[] or number[][]` | required |  |
| `asset_growth`* | `number[] or number[][]` | required |  |
| `liability_growth`* | `number[] or number[][]` | required |  |
| `n_periods`* | `integer` | required |  |

### repricing_gap_analysis

`POST /api/v1/alm/repricing_gap_analysis`: Repricing gap per time bucket and the cumulative gap.

``gap_i = RSA_i − RSL_i``; the cumulative gap drives NII sensitivity.

Formula (LaTeX): `gap_i = RSA_i-RSL_i,\quad CumGap_k=\sum_{i\le k}gap_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `bucket_assets`* | `number[] or number[][]` | required |  |
| `bucket_liabilities`* | `number[] or number[][]` | required |  |
| `bucket_labels` | `string[] or null` | `None` |  |

### repricing_maturity_profile

`POST /api/v1/alm/repricing_maturity_profile`: Allocate balances into repricing-time buckets.

Note: bucket allocation is a discrete binning operation (``np.digitize``
against ``bucket_edges``), not a closed-form sum in the usual sense.

Formula (LaTeX): `Profile_k = \sum_{i:\,t_i^{repr}\in[e_k,e_{k+1})} B_i \quad WAvg = \dfrac{\sum_i B_i\,t_i^{repr}}{\sum_i B_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `balances`* | `number[] or number[][]` | required |  |
| `repricing_times`* | `number[] or number[][]` | required |  |
| `n_buckets`* | `integer` | required |  |
| `bucket_edges`* | `number[] or number[][]` | required |  |

## Behavioural & Prepayment Models

### prepayment_model_mortgages

`POST /api/v1/alm/prepayment_model_mortgages`: Project mortgage cashflows under a constant CPR prepayment assumption.

Note: cashflows come from a month-by-month recursive amortisation loop
(interest, then scheduled principal, then prepayment on the remaining
balance each month), not a single closed-form cashflow expression.

Higher CPR shortens the weighted-average life (WAL) of the pool.

Formula (LaTeX): `\begin{aligned}PMT &= \dfrac{P\,r_m}{1-(1+r_m)^{-n}},\ r_m=\dfrac{r}{12},\ n=12T,\\SMM &= 1-(1-CPR)^{1/12}\\I_m &= B_{m-1}r_m,\\P_m^{sched} &= \min(PMT-I_m,\,B_{m-1}),\\Prepay_m &= SMM\,(B_{m-1}-P_m^{sched})\\CF_m &= I_m+P_m^{sched}+Prepay_m,\\B_m &= B_{m-1}-P_m^{sched}-Prepay_m\\WAL &= \dfrac{\sum_m (m/12)\,CF_m}{\sum_m CF_m}\end{aligned}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `principal`* | `number` | required |  |
| `annual_rate`* | `number` | required |  |
| `term_years`* | `integer` | required |  |
| `cpr`* | `number` | required |  |

### behavioural_modelling_nmds

`POST /api/v1/alm/behavioural_modelling_nmds`: Model non-maturity-deposit (NMD) run-off splitting core / non-core.

[LIMITATION] This is a bespoke core/non-core exponential-decay run-off
model, not an implementation of BCBS d368's standardised NMD slotting
methodology -- the BCBS d368 reference below names the regulatory context
this model addresses, not the calculation performed here.

[REGULATORY] BCBS d368 NMD treatment. Core deposits are stable and decay
slowly; non-core (volatile) deposits run off quickly. Returns the projected
surviving balance and the effective average life.

Formula (LaTeX): `B_{surv} = B\,f_{core}\,e^{-r_{core} H} + B\,(1-f_{core})\,e^{-r_{nc} H} \\ EL = \dfrac{B f_{core}/r_{core} + B(1-f_{core})/r_{nc}}{B}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `total_balance`* | `number` | required |  |
| `core_fraction`* | `number` | required |  |
| `core_runoff_rate`* | `number` | required |  |
| `non_core_runoff_rate`* | `number` | required |  |
| `horizon_years` | `number` | `5.0` |  |

### non_maturity_deposit_stability

`POST /api/v1/alm/non_maturity_deposit_stability`: Estimate the stable (core) portion of NMDs from a balance history.

Stable balance = the low percentile of the historical balance series (the
level retained with ``confidence_level`` probability); the volatile portion
is the remainder versus the current balance.

Formula (LaTeX): `B_{stable} = \mathrm{Percentile}_{(1-c)\times100\%}\big(\{B_t\}\big) \quad B_{volatile} = \max(B_{current}-B_{stable},0) \\ f_{stable} = \dfrac{B_{stable}}{B_{current}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `balance_history`* | `number[] or number[][]` | required |  |
| `confidence_level` | `number` | `0.99` |  |

### core_deposit_duration

`POST /api/v1/alm/core_deposit_duration`: Effective duration of core deposits modelled as a decaying annuity.

``core_deposit_duration`` (the primary, default figure) is a discrete
monthly Riemann sum over the exponential run-off schedule, truncated at
``max_years``:
``D = sum_t[t*B*decay_rate*e^{-(decay_rate+discount_rate)t}]
      / sum_t[B*decay_rate*e^{-(decay_rate+discount_rate)t}]``
for ``t = 1/12, 2/12, ..., max_years``.

A genuine closed form exists for the *untruncated* (``max_years`` ->
infinity) continuous-time version of the same model: the run-off density
``core_balance*decay_rate*e^{-decay_rate*t}`` is the density of an
Exponential(``decay_rate``) survival distribution, and PV-weighting it by
``e^{-discount_rate*t}`` is equivalent to re-weighting by
Exponential(``decay_rate + discount_rate``) — whose mean is exactly
``1 / (decay_rate + discount_rate)``. That value, plus its closed-form PV
``core_balance*decay_rate / (decay_rate + discount_rate)``, is returned as
``closed_form_duration`` / ``closed_form_present_value`` for reference,
but is NOT used for the primary ``core_deposit_duration`` figure.

Why the truncated discrete sum stays the default instead of switching to
the closed form (validated numerically — see
``tests/test_alm_behavioural.py::test_core_deposit_duration_closed_form``):
the two diverge materially whenever ``max_years`` is not several multiples
of the implied continuous duration ``1/(decay_rate+discount_rate)``. For
the slow-decaying "sticky" core books this function exists to model, that
ratio is often well under 3x at the ``max_years=30`` default — e.g.
``decay_rate=0.05, discount_rate=0.02`` implies a 14.3y continuous
duration against a 30y truncation, and the discrete figure understates
the closed form by ~29%. So ``max_years`` is a real, user-set truncation
of the run-off horizon here, not just a numerical implementation detail,
and silently dropping it would change the model's economics, not just its
numerics. Even where truncation is immaterial
(``max_years >> 1/(decay_rate+discount_rate)``), the monthly
right-Riemann-sum quadrature itself carries a systematic +dt/2 (~0.042y)
bias relative to the continuous integral, which is non-negligible against
a 0.1-0.5% tolerance for short-duration books (e.g. ``decay_rate=0.30,
discount_rate=0.10`` -> ~1.7% bias even with a generous horizon).

Core deposits run off at ``decay_rate`` (exponential). The duration is the
PV-weighted average life of the run-off cashflows discounted at
``discount_rate`` — typically multi-year, which is why NMDs anchor the
liability side of the duration gap.

Formula (LaTeX): `D = \dfrac{\sum_{t=1/12}^{T} t\,B\,\lambda\,e^{-(\lambda+y)t}}{\sum_{t=1/12}^{T} B\,\lambda\,e^{-(\lambda+y)t}} \quad (\Delta t = 1/12\text{ years})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `core_balance`* | `number` | required |  |
| `decay_rate`* | `number` | required |  |
| `discount_rate`* | `number` | required |  |
| `max_years` | `number` | `30.0` |  |

### loan_prepayment_rate_cpr

`POST /api/v1/alm/loan_prepayment_rate_cpr`: Convert between single-monthly mortality (SMM) and CPR.

``CPR = 1 − (1 − SMM)^12`` and ``SMM = 1 − (1 − CPR)^{1/12}``. Provide exactly
one of the two.

Formula (LaTeX): `CPR = 1-(1-SMM)^{12} \quad SMM = 1-(1-CPR)^{1/12}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `smm` | `number or null` | `None` |  |
| `cpr` | `number or null` | `None` |  |

## Funds Transfer Pricing (FTP)

### funds_transfer_pricing_ftp

`POST /api/v1/alm/funds_transfer_pricing_ftp`: Funds-transfer-price a single deal into margin components.

For an asset, the lending unit earns ``customer_rate − ftp_rate`` (credit /
commercial margin) while the central treasury earns the FTP minus its cost.
A liquidity premium is charged on the FTP. Margins sum to the total spread.

Formula (LaTeX): `\begin{aligned}r_{FTP}^{all} &= r_{FTP}+p_{liq}\\M_{comm} &= \begin{cases}(r_{cust}-r_{FTP}^{all})\,N & \text{is\_asset = True}\\(r_{FTP}^{all}-r_{cust})\,N & \text{is\_asset = False}\end{cases}\\FV &= r_{FTP}^{all}\,N,\qquad Spread = \big|r_{cust}-r_{FTP}^{all}\big|\,N\end{aligned}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `customer_rate`* | `number` | required |  |
| `ftp_rate`* | `number` | required |  |
| `liquidity_premium` | `number` | `0.0` |  |
| `is_asset` | `boolean` | `True` |  |

### ftp_curve_construction

`POST /api/v1/alm/ftp_curve_construction`: Construct a matched-maturity FTP curve = base curve + liquidity spread.

Each tenor's transfer rate adds a term-liquidity spread to the base funding
curve. The curve is non-decreasing in the spread component by construction.

Formula (LaTeX): `FTP_i = r_i^{base} + s_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `tenors`* | `number[] or number[][]` | required |  |
| `base_curve`* | `number[] or number[][]` | required |  |
| `liquidity_spreads`* | `number[] or number[][]` | required |  |

## ALM Strategic Analytics

### asset_liability_mismatch_index

`POST /api/v1/alm/asset_liability_mismatch_index`: Asset-liability mismatch index from duration-weighted exposures.

Index = normalised absolute duration gap
``|D_A·A − D_L·L| / A`` — zero when the book is perfectly immunised.

Formula (LaTeX): `I = \dfrac{\left|\sum_i D_i^A A_i - \sum_j D_j^L L_j\right|}{\sum_i A_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_durations`* | `number[] or number[][]` | required |  |
| `asset_amounts`* | `number[] or number[][]` | required |  |
| `liability_durations`* | `number[] or number[][]` | required |  |
| `liability_amounts`* | `number[] or number[][]` | required |  |

### structural_hedge_optimisation

`POST /api/v1/alm/structural_hedge_optimisation`: Optimise a structural hedge to a target equity duration.

Note: hedge notionals are solved numerically via SciPy bounded
least-squares (``scipy.optimize.lsq_linear``), not a closed-form
allocation formula.

Solves for non-negative hedge notionals (bounded by per-instrument caps)
that bring the dollar-duration of the hedge as close as possible to the
target ``equity_notional · target_duration``.

Formula (LaTeX): `x^{*} = \arg\min_{0\le x_i\le N_i^{max}}\left(\sum_i D_i x_i - N_{eq}D_{target}\right)^2`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `target_duration`* | `number` | required |  |
| `instrument_durations`* | `number[] or number[][]` | required |  |
| `instrument_max_notional`* | `number[] or number[][]` | required |  |
| `equity_notional`* | `number` | required |  |

### alm_stress_test

`POST /api/v1/alm/alm_stress_test`: Run an ALM stress test: worst-case EVE decline vs Tier-1 capital.

Note: the per-scenario ΔEVE values are computed entirely inside
:func:`~engine.alm_nii_eve.eve_sensitivity_analysis` (the same PV formula
used by ``economic_value_of_equity_eve``); this function only adds the
Tier-1 capital ratio and the 15% outlier-test check on top.

[REGULATORY] BCBS d368. Computes ΔEVE across the six standard shocks and
expresses the worst-case loss as a fraction of Tier-1 capital (the
supervisory outlier ratio).

Formula (LaTeX): `\Delta EVE_{worst} = \min_s\big(EVE(r_0+\Delta r_s)-EVE(r_0)\big) \\ Ratio = \dfrac{\big|\min(\Delta EVE_{worst},0)\big|}{Tier1}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `net_cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `base_rates`* | `number[] or number[][]` | required |  |
| `tier1_capital`* | `number` | required |  |
| `parallel_bps` | `number` | `200.0` |  |

### balance_sheet_projection_model

`POST /api/v1/alm/balance_sheet_projection_model`: Project the balance sheet and NII forward over ``n_years``.

Assets and liabilities grow geometrically; equity is the residual; NII each
year is ``assets·yield − liabilities·cost``. Returns the projected paths.

Formula (LaTeX): `A_t = A_0(1+g_A)^t, \quad L_t = L_0(1+g_L)^t, \quad E_t = A_t-L_t, \\ NII_t = A_t y_A - L_t c_L, \quad t=1,\dots,n`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `initial_assets`* | `number` | required |  |
| `initial_liabilities`* | `number` | required |  |
| `asset_growth_rate`* | `number` | required |  |
| `liability_growth_rate`* | `number` | required |  |
| `asset_yield`* | `number` | required |  |
| `liability_cost`* | `number` | required |  |
| `n_years`* | `integer` | required |  |
