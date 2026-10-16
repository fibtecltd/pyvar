# pyvar Liquidity Risk: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/liquidity/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Regulatory Ratios (LCR/NSFR)

### liquidity_coverage_ratio_lcr

`POST /api/v1/liquidity/liquidity_coverage_ratio_lcr`: Basel III Liquidity Coverage Ratio.

``LCR = HQLA / net 30-day outflows`` where net outflows are gross outflows
minus *capped* inflows. Recognised inflows are floored at ``inflow_cap`` of
gross outflows (default 75%), guaranteeing net outflows never fall below
25% of gross — the BCBS 238 §69 cap.

Formula (LaTeX): `\text{CappedInflows} = \min(GI,\ c \cdot GO) \\ NO = \max\big(GO - \text{CappedInflows},\ (1-c)\,GO\big) \\ LCR = \frac{HQLA}{NO}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `hqla`* | `number` | required |  |
| `gross_outflows`* | `number` | required |  |
| `gross_inflows`* | `number` | required |  |
| `inflow_cap` | `number` | `0.75` |  |

### net_stable_funding_ratio_nsfr

`POST /api/v1/liquidity/net_stable_funding_ratio_nsfr`: Basel III Net Stable Funding Ratio.

``NSFR = ASF / RSF`` and must be >= 100% (BCBS 295). Measures the proportion
of long-term assets funded by stable funding sources over a one-year horizon.

Formula (LaTeX): `NSFR = \frac{ASF}{RSF}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `available_stable_funding`* | `number` | required |  |
| `required_stable_funding`* | `number` | required |  |

### available_stable_funding_asf_calc

`POST /api/v1/liquidity/available_stable_funding_asf_calc`: Available Stable Funding for the NSFR numerator.

ASF is the weighted sum of funding sources by their ASF factor. Basel III
assigns higher factors to more stable funding (e.g. capital and >1y funding
= 100%, stable retail deposits = 95%, less-stable = 90%, wholesale <1y
typically 50% or 0%).

Formula (LaTeX): `ASF = \sum_i F_i \cdot \alpha_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `funding_amounts`* | `number[] or number[][]` | required |  |
| `asf_factors`* | `number[] or number[][]` | required |  |

### required_stable_funding_rsf_calc

`POST /api/v1/liquidity/required_stable_funding_rsf_calc`: Required Stable Funding for the NSFR denominator.

RSF is the weighted sum of assets by their RSF factor. More liquid / shorter
assets attract lower factors (Level 1 HQLA = 5%, Level 2A = 15%, loans = 50-
85%, illiquid assets = 100%).

Formula (LaTeX): `RSF = \sum_i A_i \cdot \beta_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_amounts`* | `number[] or number[][]` | required |  |
| `rsf_factors`* | `number[] or number[][]` | required |  |

## Intraday Liquidity

### intraday_liquidity_monitor

`POST /api/v1/liquidity/intraday_liquidity_monitor`: Intraday liquidity monitor (BCBS 248).

Of the two figures reported, only ``net_debit_peak`` (the largest negative
cumulative position) is the genuine BCBS 248 "largest net debit position"
monitoring tool — ``max_usage`` is this codebase's own additional metric,
not one of BCBS 248's own monitoring tools.

Tracks the intraday liquidity position from time-stamped net payment flows
and reports the peak usage (largest negative intraday position relative to
the opening balance) and the largest net debit position.

Formula (LaTeX): `B_t = B_0 + \sum_{s \le t} f_s \\ \text{MaxUsage} = \max(0,\ B_0 - \min_t B_t) \\ \text{NetDebitPeak} = \max(0,\ -\min_t B_t)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `timestamps`* | `number[] or number[][]` | required |  |
| `net_flows`* | `number[] or number[][]` | required |  |
| `opening_balance`* | `number` | required |  |

### intraday_liquidity_stress_test

`POST /api/v1/liquidity/intraday_liquidity_stress_test`: Intraday liquidity stress test (BCBS 248 stress scenarios).

This is this codebase's own internal stress design — delaying a fraction
of positive intraday inflows — set in the context of BCBS 248's intraday-
liquidity monitoring framework; it is not BCBS 248's own prescribed stress
design.

Stresses the intraday profile by delaying a fraction of *inflows* (positive
flows): a ``delay_factor`` of expected inflows is removed from the intraday
path, sharpening the peak liquidity requirement. Reports the stressed peak
usage and whether the opening buffer plus any additional shock survives.

Formula (LaTeX): `f^{stress}_t = \begin{cases} f_t(1-d) & f_t > 0 \\ f_t & f_t \le 0 \end{cases} \\ B_t = (B_0 - \Delta) + \sum_{s \le t} f^{stress}_s \\ \text{StressedMaxUsage} = \max\big(0,\ (B_0-\Delta) - \min_t B_t\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `net_flows`* | `number[] or number[][]` | required |  |
| `opening_balance`* | `number` | required |  |
| `delay_factor` | `number` | `0.5` |  |
| `inflow_delay_shock` | `number` | `0.0` |  |

## HQLA Classification

### hqla_level_1_asset_classifier

`POST /api/v1/liquidity/hqla_level_1_asset_classifier`: Classify and value Level 1 HQLA.

When ``haircuts`` is not supplied it defaults to all zeros, i.e. no
haircut is applied and every asset is valued at full market value.

Level 1 assets (cash, central-bank reserves, 0%-risk-weight sovereign debt)
receive a 0% haircut by default and have no composition cap (BCBS 238 §50).

Formula (LaTeX): `V^{adj}_i = V_i(1-h_i) \\ \text{PostHaircutValue} = \sum_i V_i(1-h_i)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_values`* | `number[] or number[][]` | required |  |
| `haircuts` | `number[] or number[][] or null` | `None` |  |

### hqla_level_2a_asset_classifier

`POST /api/v1/liquidity/hqla_level_2a_asset_classifier`: Classify and value Level 2A HQLA.

Unlike Level 1's zero-by-default haircut array, ``haircut`` here is a
single scalar applied uniformly to every asset in ``asset_values``, and
the function enforces a minimum of 15%.

Level 2A assets (20%-risk-weight sovereigns, certain covered bonds, high-
grade corporates) carry a minimum 15% haircut (BCBS 238 §52).

Formula (LaTeX): `\text{PostHaircutValue} = \sum_i V_i(1-h), \quad h \ge 0.15`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_values`* | `number[] or number[][]` | required |  |
| `haircut` | `number` | `0.15` |  |

### hqla_level_2b_asset_classifier

`POST /api/v1/liquidity/hqla_level_2b_asset_classifier`: Classify and value Level 2B HQLA.

As with Level 2A, ``haircut`` is a single scalar applied uniformly to
every asset in ``asset_values`` rather than a per-asset array; the
function enforces a minimum of 25% (pass 0.50 for the lower-grade
corporate/equity sub-bucket).

Level 2B assets (RMBS 25% haircut, lower-grade corporates and qualifying
equities 50% haircut) carry a minimum 25% haircut (BCBS 238 §54).

Formula (LaTeX): `\text{PostHaircutValue} = \sum_i V_i(1-h), \quad h \ge 0.25`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_values`* | `number[] or number[][]` | required |  |
| `haircut` | `number` | `0.25` |  |

## Cash Flow Ladder

### cash_flow_ladder_30_day

`POST /api/v1/liquidity/cash_flow_ladder_30_day`: 30-day daily contractual cash-flow ladder.

Projects the daily net and cumulative liquidity position over a 30-day
horizon. The minimum cumulative balance (including the opening balance) is
the tightest liquidity point — if negative the institution faces a funding
shortfall on that day.

Formula (LaTeX): `\text{net\_gap}_t = I_t - O_t \\ \text{cumulative\_gap}_t = B_0 + \sum_{s \le t} \text{net\_gap}_s \\ \text{min\_cumulative} = \min_t(\text{cumulative\_gap}_t)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `daily_inflows`* | `number[] or number[][]` | required |  |
| `daily_outflows`* | `number[] or number[][]` | required |  |
| `opening_balance` | `number` | `0.0` |  |

### cash_flow_ladder_1_year

`POST /api/v1/liquidity/cash_flow_ladder_1_year`: One-year bucketed contractual cash-flow ladder.

Aggregates inflows and outflows into the standard maturity buckets and
computes the per-bucket and cumulative liquidity gap.

Formula (LaTeX): `\text{net\_gap}_i = I_i - O_i \\ \text{cumulative\_gap}_i = B_0 + \sum_{j \le i} \text{net\_gap}_j \\ \text{min\_cumulative} = \min_i(\text{cumulative\_gap}_i)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `bucket_inflows`* | `number[] or number[][]` | required |  |
| `bucket_outflows`* | `number[] or number[][]` | required |  |
| `opening_balance` | `number` | `0.0` |  |
| `buckets` | `string[] or null` | `None` |  |

### liquidity_gap_analysis

`POST /api/v1/liquidity/liquidity_gap_analysis`: Maturity-bucket liquidity gap (assets vs liabilities).

Computes the structural maturity mismatch: ``gap_i = assets_i -
liabilities_i`` per bucket, plus the cumulative gap. A positive cumulative
gap means more assets than liabilities mature by that point (a funding
surplus); a negative gap signals a refinancing need.

Like the two cash-flow-ladder functions above, an optional opening balance
is added to every cumulative-gap entry — the starting cash / HQLA position
carried into the first bucket. It defaults to 0.0, so existing callers see
no change in behaviour.

Formula (LaTeX): `\text{Gap}_i = A_i - L_i \\ \text{CumulativeGap}_i = B_0 + \sum_{j \le i} \text{Gap}_j \\ \text{GapRatio}_i = \frac{A_i}{L_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_maturities`* | `number[] or number[][]` | required |  |
| `liability_maturities`* | `number[] or number[][]` | required |  |
| `buckets` | `string[] or null` | `None` |  |

## Stress Scenarios

### liquidity_stress_scenario

`POST /api/v1/liquidity/liquidity_stress_scenario`: Generic single liquidity stress scenario.

Applies category-specific run-off rates to funding balances to derive
stressed outflows, nets inflows, and tests whether HQLA covers the net
stressed outflow.

Formula (LaTeX): `O = \sum_i B_i r_i \\ N = O - I \\ \text{Surplus} = HQLA - N`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `balances`* | `number[] or number[][]` | required |  |
| `runoff_rates`* | `number[] or number[][]` | required |  |
| `hqla`* | `number` | required |  |
| `inflows` | `number` | `0.0` |  |

### idiosyncratic_stress_scenario

`POST /api/v1/liquidity/idiosyncratic_stress_scenario`: Idiosyncratic (name-specific) stress scenario.

Models a firm-specific crisis (e.g. rating downgrade): partial retail
deposit flight and complete loss of wholesale funding rollover. Wholesale
run-off defaults to 100% — the hallmark of a name-specific shock.

Formula (LaTeX): `O = R\cdot r_R + W\cdot r_W \\ \text{Surplus} = HQLA - O`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `retail_deposits`* | `number` | required |  |
| `wholesale_funding`* | `number` | required |  |
| `hqla`* | `number` | required |  |
| `retail_runoff` | `number` | `0.1` |  |
| `wholesale_runoff` | `number` | `1.0` |  |

### market_wide_stress_scenario

`POST /api/v1/liquidity/market_wide_stress_scenario`: Market-wide stress scenario.

Models a system-wide crisis where HQLA monetisation value falls due to
widened market haircuts (flight to quality, fire-sale discounts). Outflows
are met from the haircut-reduced HQLA value.

Formula (LaTeX): `HQLA_{stressed} = \sum_i H_i(1-h_i) \\ \text{Surplus} = HQLA_{stressed} - O`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `hqla_by_level`* | `number[] or number[][]` | required |  |
| `market_haircuts`* | `number[] or number[][]` | required |  |
| `outflow`* | `number` | required |  |

### combined_stress_scenario

`POST /api/v1/liquidity/combined_stress_scenario`: Combined idiosyncratic + market-wide stress scenario.

By default (the two retail-category arguments omitted) this is NOT the
BCBS 238 reference combined scenario: BCBS 238's own combined
idiosyncratic + market-wide scenario (§II paras 19-20) runs off the
LCR's own regulator-set retail run-off categories (stable/less-stable
deposit stability buckets, each with its own national-discretion
minimum rate), whereas this function's default applies a single flat
15% retail / 100% wholesale run-off convention instead -- a structural
gap a single scalar ``retail_runoff`` rate cannot close, since BCBS
238's categorisation requires segmenting retail deposits into multiple
stability buckets with different rates, not one blended rate.

Pass ``retail_deposits_by_category`` and ``retail_runoff_rates``
together (equal-length arrays: each category's deposit balance and its
own regulator-set run-off rate) to switch to a BCBS-238-shaped
categorised retail outflow -- ``sum(retail_deposits_by_category *
retail_runoff_rates)`` -- instead of the single-rate
``retail_deposits * retail_runoff`` convention. This function does not
hardcode specific category rates itself (BCBS 238 leaves the exact
stable/less-stable thresholds and rates to national supervisory
discretion); the caller supplies their own jurisdiction's categorised
balances and rates. ``retail_deposits_by_category`` must sum to
``retail_deposits`` -- enforced as a consistency check, not silently
ignored.

Models a firm-specific shock occurring inside a market-wide crisis:
liability run-off is aggravated (default 15% retail, 100% wholesale)
*and* HQLA value is reduced by stressed market haircuts, simultaneously.
(Found during the Tier 3 #2 audit — a prior version of this docstring
incorrectly claimed this was the Basel/EBA reference scenario.)

Formula (LaTeX): `HQLA_{stressed} = \sum_i H_i(1-h_i) \\ R_{outflow} = \begin{cases} R \cdot r_R & \text{default} \\ \sum_j C_j \cdot rc_j & \text{categorised (opt-in)} \end{cases} \\ O = R_{outflow} + W\cdot r_W \\ N = O - I \\ \text{Surplus} = HQLA_{stressed} - N`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `retail_deposits`* | `number` | required |  |
| `wholesale_funding`* | `number` | required |  |
| `hqla_by_level`* | `number[] or number[][]` | required |  |
| `market_haircuts`* | `number[] or number[][]` | required |  |
| `retail_runoff` | `number` | `0.15` |  |
| `wholesale_runoff` | `number` | `1.0` |  |
| `inflows` | `number` | `0.0` |  |
| `retail_deposits_by_category` | `number[] or number[][] or null` | `None` |  |
| `retail_runoff_rates` | `number[] or number[][] or null` | `None` |  |

## Buffer & Survival

### liquidity_buffer_sizing

`POST /api/v1/liquidity/liquidity_buffer_sizing`: Size the liquidity buffer to the peak cumulative stressed outflow.

The required buffer equals the maximum cumulative net outflow over the
stress horizon (the deepest point of the cash-flow trough), optionally
uplifted by a management ``confidence_buffer`` margin.

Formula (LaTeX): `\text{Peak} = \max\Big(0,\ \max_i \sum_{j \le i} O_j\Big) \\ \text{RequiredBuffer} = \text{Peak} \times (1 + c)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `stressed_net_outflows`* | `number[] or number[][]` | required |  |
| `confidence_buffer` | `number` | `0.0` |  |

### contingency_funding_plan_trigger

`POST /api/v1/liquidity/contingency_funding_plan_trigger`: Evaluate Contingency Funding Plan (CFP) activation triggers.

Compares current early-warning metrics against their activation thresholds.
A metric breaches when its value falls *below* the threshold (lower = worse;
e.g. LCR, survival days). Returns the list of breached triggers and the CFP
activation decision.

This is a logical breach test, not an arithmetic formula, so it is shown on
the Try-it panel as an indicator function of the comparison rather than a
computed expression.

Formula (LaTeX): `\text{Breach}_k = \mathbb{1}[m_k < \tau_k] \\ \text{CFP\_Activated} = \bigvee_k \text{Breach}_k`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `metrics`* | `object` | required |  |
| `thresholds`* | `object` | required |  |

### wholesale_funding_concentration

`POST /api/v1/liquidity/wholesale_funding_concentration`: Wholesale funding concentration via the Herfindahl-Hirschman Index.

Computes the HHI of funding shares across counterparties (sum of squared
shares, in [1/n, 1]) plus the largest single-counterparty share. Higher HHI
means more concentrated, less diversified funding.

Formula (LaTeX): `s_i = \frac{A_i}{\sum_j A_j} \\ HHI = \sum_i s_i^2 \\ \text{Top1Share} = \max_i s_i, \quad N_{eff} = \frac{1}{HHI}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `counterparty_amounts`* | `number[] or number[][]` | required |  |

### survival_horizon_calculator

`POST /api/v1/liquidity/survival_horizon_calculator`: Survival horizon — days until cumulative net outflow exhausts HQLA.

Walks forward through the daily net-outflow path subtracting from the HQLA
counterbalancing capacity. The survival horizon is the last day on which the
remaining buffer is still non-negative.

``survival_days`` is the 0-indexed day on which cumulative outflow first
drives the buffer negative, so it equals the count of full days survived
before breach (0 if the very first day breaches).

Formula (LaTeX): `B_0 = HQLA \\ B_t = B_{t-1} - O_t \\ \text{SurvivalDays} = \min\{t : B_t < 0\} \quad \text{(or the full array length if the buffer never goes negative)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `hqla`* | `number` | required |  |
| `daily_net_outflows`* | `number[] or number[][]` | required |  |

## Funding Risk

### retail_deposit_runoff_rate

`POST /api/v1/liquidity/retail_deposit_runoff_rate`: Aggregate retail deposit run-off (Basel LCR categories).

Computes the blended run-off rate across retail deposit categories (e.g.
stable 5%, less-stable 10%, non-operational higher) and the total expected
30-day run-off amount.

Formula (LaTeX): `\text{TotalRunoff} = \sum_i B_i r_i \\ \text{BlendedRate} = \frac{\sum_i B_i r_i}{\sum_i B_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `deposit_balances`* | `number[] or number[][]` | required |  |
| `runoff_rates`* | `number[] or number[][]` | required |  |

### secured_funding_rollover_risk

`POST /api/v1/liquidity/secured_funding_rollover_risk`: Secured funding (repo) rollover risk.

Estimates the funding gap from secured transactions that fail to roll: the
non-rolled portion of each maturing tranche must be replaced or repaid.

Formula (LaTeX): `\text{RolledAmount} = \sum_i M_i \rho_i \\ \text{RolloverGap} = \sum_i M_i(1-\rho_i) \\ \text{EffRolloverRate} = \frac{\sum_i M_i \rho_i}{\sum_i M_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `maturing_amounts`* | `number[] or number[][]` | required |  |
| `rollover_rates`* | `number[] or number[][]` | required |  |

### asset_encumbrance_ratio

`POST /api/v1/liquidity/asset_encumbrance_ratio`: Asset encumbrance ratio (EBA reporting).

``encumbrance = encumbered assets / total assets``. High encumbrance reduces
the unencumbered asset pool available to monetise in stress.

Formula (LaTeX): `\text{Encumbrance} = \frac{E}{T}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `encumbered_assets`* | `number` | required |  |
| `total_assets`* | `number` | required |  |

### collateral_availability_analysis

`POST /api/v1/liquidity/collateral_availability_analysis`: Collateral availability — post-haircut monetisable value.

Computes the net realisable collateral value after haircuts and netting off
already-pledged amounts — the counterbalancing capacity available to raise
secured funding.

Formula (LaTeX): `\text{Available} = \sum_i \max\big(V_i(1-h_i) - P_i,\ 0\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `collateral_values`* | `number[] or number[][]` | required |  |
| `haircuts`* | `number[] or number[][]` | required |  |
| `already_pledged` | `number[] or number[][] or null` | `None` |  |

### repo_market_stress_haircut

`POST /api/v1/liquidity/repo_market_stress_haircut`: Repo market stress — incremental margin call from widened haircuts.

Under stress, repo haircuts widen by a multiplier. The incremental margin
requirement is the extra collateral (or cash) the institution must post to
maintain the same secured borrowing.

Formula (LaTeX): `h^{stress}_i = \min(h_i \cdot m_i,\ 1) \\ \text{MarginCall}_i = V_i\,(h^{stress}_i - h_i) \\ \text{AdditionalMargin} = \sum_i \text{MarginCall}_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `base_haircuts`* | `number[] or number[][]` | required |  |
| `stress_multipliers`* | `number[] or number[][]` | required |  |
| `collateral_values`* | `number[] or number[][]` | required |  |

### fx_liquidity_risk_by_currency

`POST /api/v1/liquidity/fx_liquidity_risk_by_currency`: FX liquidity risk — net position per significant currency.

Computes the net liquidity gap in each currency (inflows - outflows). A
significant negative position signals reliance on FX swap markets to fund
the shortfall — a key vulnerability if swap markets seize.

Formula (LaTeX): `\text{Net}_{ccy} = I_{ccy} - O_{ccy}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `inflows_by_ccy`* | `object` | required |  |
| `outflows_by_ccy`* | `object` | required |  |

### intragroup_liquidity_flow

`POST /api/v1/liquidity/intragroup_liquidity_flow`: Intragroup liquidity flow netting.

Nets bilateral liquidity positions across group entities to derive each
entity's net provider/receiver status and the total internal liquidity
transferred. Positive = net provider of liquidity to the group.

Formula (LaTeX): `\text{TotalProvided} = \sum_{e:\ v_e > 0} v_e \\ \text{Balanced} \iff \Big|\sum_e v_e\Big| < 10^{-6}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `entity_positions`* | `object` | required |  |

### funding_cost_analysis

`POST /api/v1/liquidity/funding_cost_analysis`: Weighted-average funding cost.

Computes the amount-weighted average cost of the funding base and the total
annual funding cost in currency terms.

Formula (LaTeX): `\text{WAC} = \frac{\sum_i A_i r_i}{\sum_i A_i} \\ \text{TotalAnnualCost} = \sum_i A_i r_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `funding_amounts`* | `number[] or number[][]` | required |  |
| `funding_rates`* | `number[] or number[][]` | required |  |

### deposit_stability_classification

`POST /api/v1/liquidity/deposit_stability_classification`: Classify deposits as stable vs less-stable from a stability score.

Each deposit carries a stability score in [0, 1] (e.g. derived from
insurance coverage, transactional relationship, tenor). Deposits at or above
``stable_threshold`` are classified stable (lower LCR run-off), the rest
less-stable.

Formula (LaTeX): `\text{Stable}_i = \mathbb{1}[f_i \ge \tau] \\ \text{StableFraction} = \frac{1}{n}\sum_i \mathbb{1}[f_i \ge \tau]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `deposit_features`* | `number[] or number[][]` | required |  |
| `stable_threshold` | `number` | `0.5` |  |

## Internal Liquidity Metrics

### liquidity_transfer_pricing

`POST /api/v1/liquidity/liquidity_transfer_pricing`: Liquidity Transfer Pricing (LTP) charge for a funding position.

The FTP charge passes the cost of liquidity to business lines: the all-in
transfer rate is ``base_rate + term liquidity premium + contingent liquidity
premium``. The annual charge is that rate applied to notional; the lifetime
charge multiplies by tenor.

Formula (LaTeX): `r_{all\text{-}in} = r_{base} + s_{liq} + s_{cont} \\ \text{AnnualCharge} = N \cdot r_{all\text{-}in} \\ \text{LifetimeCharge} = N \cdot r_{all\text{-}in} \cdot T`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `tenor_years`* | `number` | required |  |
| `base_rate`* | `number` | required |  |
| `liquidity_spread`* | `number` | required |  |
| `contingent_spread` | `number` | `0.0` |  |

### ilaap_internal_liquidity_metric

`POST /api/v1/liquidity/ilaap_internal_liquidity_metric`: ILAAP internal liquidity adequacy metric.

Combines the institution's own counterbalancing-capacity coverage ratio
(CBC / stressed outflow) with the survival-horizon adequacy versus the
internal minimum (commonly 90 days). Both must hold for internal adequacy.

Formula (LaTeX): `\text{CoverageRatio} = \frac{CBC}{SNO} \\ \text{Adequate} \iff \text{CoverageRatio} \ge 1 \ \text{and}\ SD \ge SD_{min}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `counterbalancing_capacity`* | `number` | required |  |
| `stressed_net_outflow`* | `number` | required |  |
| `survival_days`* | `number` | required |  |
| `minimum_survival_days` | `number` | `90.0` |  |

### ilaap_stress_testing_framework

`POST /api/v1/liquidity/ilaap_stress_testing_framework`: ILAAP stress-testing framework aggregator.

Aggregates the outcomes of multiple named liquidity stress scenarios into an
ILAAP-style summary: the binding (worst) scenario, the count of scenarios
breached, and overall adequacy. Each scenario value must expose a
``surplus_deficit`` figure (as produced by the scenario functions above).

SD_k in the rendered formula denotes the ``surplus_deficit`` field each
named scenario dict must already carry — this function only aggregates
pre-computed values and performs no cash-flow arithmetic itself.

Formula (LaTeX): `\text{Binding} = \arg\min_k SD_k \\ \text{WorstSurplusDeficit} = \min_k SD_k \\ \text{Adequate} \iff \min_k SD_k \ge 0`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `scenarios`* | `object` | required |  |

### liquidity_risk_appetite_threshold

`POST /api/v1/liquidity/liquidity_risk_appetite_threshold`: Map a liquidity metric to a RAG (red/amber/green) risk-appetite zone.

For ``higher_is_better`` metrics (LCR, NSFR, survival days) green is at or
above ``green_threshold`` and red below ``amber_threshold``. For
lower-is-better metrics (e.g. funding concentration) the comparison inverts.

This is a piecewise categorical rule rather than a continuous formula, and
the Try-it panel's rendered formula shows only the higher-is-better
direction; the comparison flips (green <= amber <= metric) when
``higher_is_better`` is False.

Formula (LaTeX): `\text{Zone} = \begin{cases} \text{green} & m \ge \tau_g \\ \text{amber} & \tau_a \le m < \tau_g \\ \text{red} & m < \tau_a \end{cases} \quad (\text{higher\_is\_better case; comparisons invert when lower is better})`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `metric_value`* | `number` | required |  |
| `green_threshold`* | `number` | required |  |
| `amber_threshold`* | `number` | required |  |
| `higher_is_better` | `boolean` | `True` |  |

### early_warning_indicator_liquidity

`POST /api/v1/liquidity/early_warning_indicator_liquidity`: Liquidity early-warning indicator (EWI) dashboard.

Evaluates each EWI against its threshold and a per-indicator direction
(``"higher_breach"`` means a value above threshold is a warning, e.g. funding
spread; ``"lower_breach"`` means below threshold is a warning, e.g. LCR). The
aggregate signal escalates with the number of triggered indicators.

This is a direction-dependent logical breach test per indicator, not a
single arithmetic formula, and the aggregate signal buckets are exact:
normal (0 triggers), watch (1-2) and alert (3 or more).

Formula (LaTeX): `\text{Trigger}_k = \begin{cases} \mathbb{1}[v_k > \tau_k] & \text{higher\_breach} \\ \mathbb{1}[v_k < \tau_k] & \text{lower\_breach} \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `indicators`* | `object` | required |  |
| `thresholds`* | `object` | required |  |
| `directions` | `object or null` | `None` |  |

### central_bank_facility_eligibility

`POST /api/v1/liquidity/central_bank_facility_eligibility`: Central-bank facility collateral eligibility and borrowing capacity.

Filters assets meeting the central bank's minimum credit rating (encoded as
an ordinal where higher = better) and computes the post-central-bank-haircut
borrowing capacity from eligible assets.

Formula (LaTeX): `\text{Eligible}_i = \mathbb{1}[R_i \ge R_{min}] \\ \text{BorrowingCapacity} = \sum_{i:\ \text{Eligible}_i} V_i(1-h_i)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `asset_ratings`* | `number[] or number[][]` | required |  |
| `min_rating`* | `integer` | required |  |
| `asset_values`* | `number[] or number[][]` | required |  |
| `cb_haircuts`* | `number[] or number[][]` | required |  |

### contingent_liquidity_risk

`POST /api/v1/liquidity/contingent_liquidity_risk`: Contingent liquidity risk from undrawn commitments and guarantees.

When ``ccf`` is not supplied it defaults to 1.0 for every commitment,
i.e. full drawdown of each commitment is assumed in the expected-outflow
calculation unless a lower conversion factor is explicitly passed.

Estimates the expected contingent outflow as ``commitment * draw_probability
* credit-conversion-factor`` — the liquidity that off-balance-sheet
commitments (undrawn lines, guarantees) could absorb in stress.

Formula (LaTeX): `E[\text{Outflow}] = \sum_i C_i\, p_i\, \gamma_i \\ \text{MaxOutflow} = \sum_i C_i\, \gamma_i`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `commitment_amounts`* | `number[] or number[][]` | required |  |
| `draw_probabilities`* | `number[] or number[][]` | required |  |
| `ccf` | `number[] or number[][] or null` | `None` |  |

## Advanced Liquidity Analytics

### liquidity_var_liqvar

`POST /api/v1/liquidity/liquidity_var_liqvar`: Liquidity VaR (LiqVaR) by Monte Carlo simulation of stressed net outflows.

Simulates the distribution of stressed net cash outflows as
``base_outflow * (1 + vol * Z)`` and reads the loss quantile at the
confidence level. LiqVaR is the outflow level not exceeded with the given
confidence — the liquidity analogue of market VaR.

Per CLAUDE.md §3.1 RULE 3 the N(0,1) shocks are pre-drawn in pure Python and
passed to the JIT kernel; an analytic normal quantile is also returned for
validation.

``liqvar`` is a simulated order statistic of this floored-at-zero
normal-shock model, cross-validated only against its own analytic
counterpart ``liqvar_analytic`` rather than a regulatory reference, using
index ``floor(confidence_level * n_simulations)`` capped at
``n_simulations - 1``.

Formula (LaTeX): `X_i = \max\big(0,\ \mu(1+\sigma Z_i)\big), \quad Z_i \sim N(0,1) \\ LiqVaR = X_{(\lfloor \alpha n \rfloor)} \\ LiqVaR_{analytic} = \max\big(0,\ \mu(1+\sigma\,\Phi^{-1}(\alpha))\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `base_outflow`* | `number` | required |  |
| `outflow_vol`* | `number` | required |  |
| `confidence_level` | `number` | `0.99` |  |
| `n_simulations` | `integer` | `100000` |  |
| `seed` | `integer or null` | `42` |  |

### funding_tenor_analysis

`POST /api/v1/liquidity/funding_tenor_analysis`: Weighted-average funding tenor and short-term reliance.

Computes the amount-weighted average tenor of the funding base and the
proportion of funding maturing within 90 days — a core ILAAP structural
metric (longer WAL == more stable funding).

Formula (LaTeX): `\text{WAT} = \frac{\sum_i A_i T_i}{\sum_i A_i} \\ \text{ShortTermRatio} = \frac{\sum_{i:\ T_i \le 90} A_i}{\sum_i A_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `funding_amounts`* | `number[] or number[][]` | required |  |
| `tenors_days`* | `number[] or number[][]` | required |  |

### liquidity_scorecard_aggregation

`POST /api/v1/liquidity/liquidity_scorecard_aggregation`: Weighted liquidity scorecard aggregation.

Combines individual liquidity metric scores (each typically 0-100) into a
single weighted composite score and maps it to a RAG rating.

Formula (LaTeX): `\text{Composite} = \frac{\sum_i s_i w_i}{\sum_i w_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `scores`* | `number[] or number[][]` | required |  |
| `weights`* | `number[] or number[][]` | required |  |

### cross_currency_liquidity_bridge

`POST /api/v1/liquidity/cross_currency_liquidity_bridge`: Cross-currency liquidity bridge via FX swap.

Sizes the FX swap needed to fund a shortfall in one currency using surplus
in another. ``fx_rate`` converts one unit of the surplus currency into the
shortfall currency; a ``swap_haircut`` reduces the usable surplus to reflect
swap-market stress.

Formula (LaTeX): `S_{usable} = S\,(1-h) \\ \text{Coverable} = \min(D,\ S_{usable}\cdot X) \\ \text{Residual} = D - \text{Coverable}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `shortfall_ccy`* | `string` | required |  |
| `shortfall_amount`* | `number` | required |  |
| `surplus_ccy`* | `string` | required |  |
| `surplus_amount`* | `number` | required |  |
| `fx_rate`* | `number` | required |  |
| `swap_haircut` | `number` | `0.0` |  |
