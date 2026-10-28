# pyvar Regulatory Capital: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/regulatory/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Basel III/IV Capital Ratios

### basel_iii_cet1_ratio

`POST /api/v1/regulatory/basel_iii_cet1_ratio`: Basel III Common Equity Tier 1 (CET1) ratio.

``CET1 ratio = CET1 capital / RWA``; minimum 4.5% (Basel III §50).

Formula (LaTeX): `CET1\ ratio = \frac{CET1_{capital}}{RWA}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cet1_capital`* | `number` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### basel_iii_tier1_ratio

`POST /api/v1/regulatory/basel_iii_tier1_ratio`: Basel III Tier 1 capital ratio.

``Tier 1 ratio = Tier 1 capital / RWA``; minimum 6.0% (Basel III §50).

Formula (LaTeX): `Tier\ 1\ ratio = \frac{Tier1_{capital}}{RWA}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `tier1_capital`* | `number` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### basel_iii_total_capital_ratio

`POST /api/v1/regulatory/basel_iii_total_capital_ratio`: Basel III Total capital ratio.

``Total ratio = (Tier 1 + Tier 2) / RWA``; minimum 8.0% (Basel III §50).

Formula (LaTeX): `Total\ capital\ ratio = \frac{Total\ Capital}{RWA}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `total_capital`* | `number` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### basel_iii_leverage_ratio

`POST /api/v1/regulatory/basel_iii_leverage_ratio`: Basel III leverage ratio.

``Leverage ratio = Tier 1 capital / total exposure measure``; minimum 3.0%.
The exposure measure is non-risk-weighted (on + off balance sheet).

Formula (LaTeX): `Leverage\ ratio = \frac{Tier1_{capital}}{Total\ Exposure}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `tier1_capital`* | `number` | required |  |
| `total_exposure`* | `number` | required |  |

### basel_iv_output_floor

`POST /api/v1/regulatory/basel_iv_output_floor`: Basel IV output floor.

Floored RWA = ``max(internal_model_rwa, floor_factor * standardised_rwa)``.
The floor factor is 72.5% (Basel III finalisation) — do not relax.

Formula (LaTeX): `Floored\ RWA = \max\big(RWA_{IM},\ floor\_factor \times RWA_{SA}\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `internal_model_rwa`* | `number` | required |  |
| `standardised_rwa`* | `number` | required |  |
| `floor_factor` | `number` | `0.725` |  |

## ICAAP / SREP / Pillar 2

### srep_capital_add_on

`POST /api/v1/regulatory/srep_capital_add_on`: SREP (Supervisory Review and Evaluation Process) capital add-on.

Translates the supervisory Pillar 2A add-on ratio into a capital amount and
the Total SREP Capital Requirement (TSCR).

Formula (LaTeX): `Pillar2A_{capital} = pillar2a\_addon\_ratio \times RWA \\ TSCR = Pillar1 + Pillar2A_{capital}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pillar1_requirement`* | `number` | required |  |
| `pillar2a_addon_ratio`* | `number` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### pillar_2a_capital

`POST /api/v1/regulatory/pillar_2a_capital`: Pillar 2A capital — sum of individual risk add-ons.

Pillar 2A covers risks not (fully) captured in Pillar 1: e.g. credit
concentration, IRRBB, pension, operational. Sums the component charges.

Formula (LaTeX): `Pillar2A_{capital} = \sum_i addon_i \\ Pillar2A_{ratio} = \frac{Pillar2A_{capital}}{RWA}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `risk_addons`* | `number[] or number[][]` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### pillar_2b_stress_buffer

`POST /api/v1/regulatory/pillar_2b_stress_buffer`: Pillar 2B stress buffer (PRA buffer / capital guidance).

The forward-looking buffer to absorb the peak capital depletion projected
under the supervisory stress scenario.

Formula (LaTeX): `Pillar2B_{buffer} = \max\big(Stressed\ Capital\ Depletion,\ 0\big) \\ Buffer\ ratio = \frac{Pillar2B_{buffer}}{RWA}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `stressed_capital_depletion`* | `number` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### icaap_capital_assessment

`POST /api/v1/regulatory/icaap_capital_assessment`: ICAAP internal capital adequacy assessment.

Aggregates Pillar 1 capital with internally-assessed risk components
(credit concentration, IRRBB, etc.) and compares to available capital.

Formula (LaTeX): `Total\ Capital\ Requirement = Pillar1 + \sum_i RiskComponent_i \\ Capital\ Surplus = Available\ Capital - Total\ Capital\ Requirement`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `pillar1_capital`* | `number` | required |  |
| `risk_capital_components`* | `number[] or number[][]` | required |  |
| `available_capital`* | `number` | required |  |

## FRTB Capital (SA & IMA)

### frtb_sa_market_risk_capital

`POST /api/v1/regulatory/frtb_sa_market_risk_capital`: FRTB Standardised Approach total market-risk capital.

The SA capital is the simple sum of the Sensitivities-Based Method charge
(already aggregated across delta/vega/curvature and the three correlation
scenarios), the Default Risk Charge (DRC) and the Residual Risk Add-On
(RRAO) (BCBS d457 §2).

Formula (LaTeX): `SA_{capital} = SBM_{charge} + DRC + RRAO`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `sensitivities_charge`* | `number` | required |  |
| `default_risk_charge`* | `number` | required |  |
| `residual_risk_addon`* | `number` | required |  |

### frtb_ima_market_risk_capital

`POST /api/v1/regulatory/frtb_ima_market_risk_capital`: FRTB Internal Models Approach total market-risk capital.

The IMA charge combines the multiplier-scaled, stressed-scaled Expected
Shortfall (the "IMCC" proxy) with the non-modellable risk factor capital
(SES) and the Default Risk Charge (BCBS d457 §189). The multiplier is
floored at 1.5.

Formula (LaTeX): `m_c = \max(multiplier,\ 1.5) \\ ES_{charge} = m_c \times ES_{97.5\%} \times stressed\_es\_ratio \\ IMA_{capital} = ES_{charge} + SES_{NMRF} + DRC`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `expected_shortfall`* | `number` | required |  |
| `stressed_es_ratio`* | `number` | required |  |
| `multiplier`* | `number` | required |  |
| `non_modellable_ses` | `number` | `0.0` |  |
| `default_risk_charge` | `number` | `0.0` |  |

### frtb_pl_attribution_test

`POST /api/v1/regulatory/frtb_pl_attribution_test`: FRTB P&L Attribution Test (PAT) — Spearman correlation + variance ratio.

The green/amber/red zone is assigned by a fixed-threshold lookup on the
correlation and ratio values below, not a single closed-form equation.

Jointly evaluates the Spearman rank correlation between risk-theoretical P&L
(RTPL) and hypothetical P&L (HPL) and the volatility ratio
``std(RTPL)/std(HPL)``, assigning the Basel traffic-light zone. The
thresholds are mandated by BCBS d457 and CLAUDE.md §4.4:
green ``|corr|>=0.80 AND 0.8<=ratio<=1.2``;
amber ``|corr|>=0.70 AND 0.6<=ratio<=1.5``; otherwise red (IMA loss).

Formula (LaTeX): `\rho = Spearman(RTPL, HPL) \\ ratio = \frac{\sigma(RTPL)}{\sigma(HPL)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `risk_theoretical_pnl`* | `number[] or number[][]` | required |  |
| `hypothetical_pnl`* | `number[] or number[][]` | required |  |

### frtb_trading_desk_aggregation

`POST /api/v1/regulatory/frtb_trading_desk_aggregation`: FRTB trading-desk capital aggregation.

Aggregates per-desk capital: IMA-eligible desks contribute their IMA charge,
non-eligible (PAT-red / backtest-failed) desks fall back to the SA charge.
The total firm-wide market-risk capital is the sum across desks (BCBS d457
treats the firm charge as the sum of approved-desk IMA plus SA for the rest).

Formula (LaTeX): `Total_{capital} = \sum_{d \,\in\, eligible} IMA_d + \sum_{d \,\notin\, eligible} SA_d`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `desk_sa_charges`* | `number[] or number[][]` | required |  |
| `desk_ima_charges`* | `number[] or number[][]` | required |  |
| `desk_ima_eligible`* | `number[] or number[][]` | required |  |

## MiFID II

### mifid_ii_transaction_report_validator

`POST /api/v1/regulatory/mifid_ii_transaction_report_validator`: MiFID II / RTS 22 transaction report field validator.

This checks a representative core subset of 9 fields, not full-schema
coverage of RTS 22's roughly 65 mandatory transaction-report fields.

Checks the presence and basic validity of the mandatory transaction-report
fields (LEI length, ISIN length, positive price/quantity).

Formula (LaTeX): `valid = (\text{required fields present}) \wedge (|LEI| = 20) \wedge (|ISIN| = 12) \wedge (price > 0) \wedge (quantity > 0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `report`* | `object` | required |  |

### mifid_ii_pre_trade_transparency

`POST /api/v1/regulatory/mifid_ii_pre_trade_transparency`: MiFID II pre-trade transparency / LIS waiver assessment.

Determines whether an order qualifies for the Large-in-Scale (LIS) waiver
from pre-trade transparency (illiquid instruments and orders above the LIS
threshold may be waived).

Formula (LaTeX): `waiver = \begin{cases} \text{large\_in\_scale} & order\_size \ge LIS_{threshold} \\ \text{illiquid\_instrument} & \neg is\_liquid \\ \text{none} & \text{otherwise} \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `instrument_type`* | `string` | required |  |
| `order_size`* | `number` | required |  |
| `large_in_scale_threshold`* | `number` | required |  |
| `is_liquid` | `boolean` | `True` |  |

### mifid_ii_post_trade_transparency

`POST /api/v1/regulatory/mifid_ii_post_trade_transparency`: MiFID II post-trade transparency / deferred-publication assessment.

Trades above the size threshold (or in illiquid instruments) may benefit
from deferred publication; otherwise publication is near real-time.

Formula (LaTeX): `deferral = (trade\_size \ge threshold) \vee \neg is\_liquid`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `trade_size`* | `number` | required |  |
| `delayed_publication_threshold`* | `number` | required |  |
| `is_liquid` | `boolean` | `True` |  |

### mifid_ii_best_execution_metric

`POST /api/v1/regulatory/mifid_ii_best_execution_metric`: MiFID II best-execution TCA metric -- internal, NOT an RTS 27/28 figure.

This is an internal TCA (transaction cost analysis) metric only; neither
RTS 27 nor RTS 28 defines a prescribed quantitative figure that this
function reproduces.

Computes the quantity-weighted price improvement (or slippage) of executions
versus a reference (e.g. EBBO) price, in basis points. Positive means price
improvement for the client.

This does not correspond to any specific RTS 27/28 field: RTS 27
(Commission Delegated Regulation (EU) 2017/575) requires simple-average
and volume-weighted transaction prices/spreads/best-bid-offer (Annex
Tables 1-9), and RTS 28 (DR (EU) 2017/576) requires execution-venue
rankings -- neither defines a quantity-weighted price-improvement-in-bps
metric like this one. RTS 27 was also repealed by the 2024 MiFIR review.
A prior version of this docstring cited "RTS 27/28" directly; corrected
during the Tier 3 #2 audit. This remains a reasonable internal TCA
metric, just not a regulatory-prescribed one.

Formula (LaTeX): `PriceImprovement_{bps} = \frac{\sum_i side \times (bench_i - p_i) \times q_i}{\sum_i bench_i \times q_i} \times 10^4`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `executed_prices`* | `number[] or number[][]` | required |  |
| `benchmark_prices`* | `number[] or number[][]` | required |  |
| `quantities`* | `number[] or number[][]` | required |  |
| `side` | `integer` | `1` |  |

### mifid_ii_algorithm_documentation

`POST /api/v1/regulatory/mifid_ii_algorithm_documentation`: MiFID II RTS 6 algorithmic-trading documentation completeness check.

The 6-item checklist below is this codebase's own internal choice, not a
checklist published by RTS 6 itself.

Verifies that the mandatory governance and control documentation items for
an algorithmic trading strategy are present.

Formula (LaTeX): `completeness = 1 - \frac{|\text{missing items}|}{6}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `documentation`* | `object` | required |  |

## EMIR & SFTR

### emir_trade_repository_report

`POST /api/v1/regulatory/emir_trade_repository_report`: EMIR trade repository report builder/validator.

This validates a representative core subset of 6 fields, not full-schema
coverage of EMIR REFIT's roughly 200 reportable fields.

Validates the core EMIR reporting fields (counterparty LEIs, UTI, notional,
asset class) and echoes a normalised report.

Formula (LaTeX): `valid = (\text{required fields present}) \wedge (|LEI| = 20) \wedge (notional > 0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `trade`* | `object` | required |  |

### emir_clearing_obligation_check

`POST /api/v1/regulatory/emir_clearing_obligation_check`: EMIR clearing obligation check (Art. 4 / Art. 4a / Art. 10 / clearing thresholds).

[REGULATORY] EMIR REFIT (Regulation (EU) 2019/834) Art. 4a(1): a Financial
Counterparty (FC) that breaches its clearing threshold in ANY ONE OTC
derivative asset class becomes subject to the clearing obligation for ALL
asset classes it has positions in, not just the one that breached. Art.
10(1) evaluates a Non-Financial Counterparty above threshold (NFC+)
per-asset-class instead -- only the classes where ITS OWN threshold is
breached become subject to clearing.

A prior version of this function applied FC's per-class-only logic to
BOTH categories (took a single ``asset_class``/``notional`` pair,
identical branching for FC and NFC+ beyond the NFC- exemption). It
understated an FC's clearing scope whenever the breaching class differed
from the queried class -- masked in the original test, which happened to
query the same class that breached. Found during the Tier 3 #2 audit.

Formula (LaTeX): `any\_breached = \bigvee_{ac} \big(notional_{ac} > threshold_{ac}\big) \\ FC:\ clearing_{ac} = any\_breached\ \ \forall ac \\ NFC{+}:\ clearing_{ac} = notional_{ac} > threshold_{ac}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notionals`* | `{str: number}` | required |  |
| `counterparty_category`* | `string` | required |  |
| `clearing_thresholds`* | `{str: number}` | required |  |

### emir_margin_requirement

`POST /api/v1/regulatory/emir_margin_requirement`: EMIR (Art. 11) uncleared-derivatives margin requirement.

Computes the Initial Margin (IM) from the rate and the net margin call after
applying the Minimum Transfer Amount (MTA) to the variation margin.

Formula (LaTeX): `IM = initial\_margin\_rate \times portfolio\_value \\ VM_{call} = \begin{cases} variation\_margin & |variation\_margin| \ge MTA \\ 0 & \text{otherwise} \end{cases} \\ Total\ Margin = IM + VM_{call}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `portfolio_value`* | `number` | required |  |
| `initial_margin_rate`* | `number` | required |  |
| `variation_margin`* | `number` | required |  |
| `minimum_transfer_amount` | `number` | `0.0` |  |

### sftr_securities_finance_report

`POST /api/v1/regulatory/sftr_securities_finance_report`: SFTR securities-financing transaction report builder/validator.

This validates a representative core subset of 6 fields, not full-schema
coverage of SFTR's complete field set.

Validates the core SFTR fields for an SFT (repo, securities lending, buy-
sell back, margin lending): counterparties, UTI, collateral and the SFT
type.

Formula (LaTeX): `valid = (\text{required fields present}) \wedge \big(sft\_type \in \{repo, securities\_lending, buy\_sell\_back, margin\_lending\}\big) \wedge (collateral\_value \ge 0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `transaction`* | `object` | required |  |

## Fund Regulations (AIFMD/UCITS/Solvency II)

### aifmd_risk_metrics

`POST /api/v1/regulatory/aifmd_risk_metrics`: AIFMD Annex IV risk metrics — leverage and (optional) VaR.

"Substantially leveraged" here is a simple threshold flag (commitment
leverage > 3x NAV), not AIFMD's full leverage-calculation methodology.

Computes leverage under the gross method and the commitment method (each as
a multiple of NAV) per Delegated Regulation 231/2013 Art. 7-8. A fund is
"substantially leveraged" when commitment leverage exceeds 3x NAV.

Formula (LaTeX): `Gross\ Leverage = \frac{Gross\ Exposure}{NAV} \\ Commitment\ Leverage = \frac{Commitment\ Exposure}{NAV}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `gross_exposure`* | `number` | required |  |
| `commitment_exposure`* | `number` | required |  |
| `net_asset_value`* | `number` | required |  |
| `var_pct` | `number or null` | `None` |  |

### ucits_kiid_risk_indicator

`POST /api/v1/regulatory/ucits_kiid_risk_indicator`: UCITS KIID Synthetic Risk and Reward Indicator (SRRI), 1-7.

The SRRI class itself is a bucket lookup of the annualised volatility
against fixed CESR volatility bands, not a closed-form equation.

Maps the annualised volatility of (weekly by default) returns to the SRRI
bucket per CESR 10-673: class 1 (< 0.5%) up to class 7 (>= 25%).

Formula (LaTeX): `\sigma_{ann} = std(r,\ ddof=1) \times \sqrt{periods\_per\_year}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `returns`* | `number[] or number[][]` | required |  |
| `periods_per_year` | `integer` | `52` |  |

### solvency_ii_scr_market_risk

`POST /api/v1/regulatory/solvency_ii_scr_market_risk`: Solvency II SCR Market risk — standard-formula modular aggregation.

Aggregates the market sub-module capital charges (interest rate, equity,
property, spread, currency, concentration) using the prescribed correlation
matrix and the square-root formula ``SCR = sqrt(s' Corr s)`` (Delegated
Regulation 2015/35 Art. 164).

Formula (LaTeX): `SCR_{market} = \sqrt{\mathbf{s}^\top \mathbf{C}\, \mathbf{s}} = \sqrt{\sum_i \sum_j s_i\, Corr_{ij}\, s_j}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `sub_module_charges`* | `number[] or number[][]` | required |  |
| `correlation_matrix`* | `number[] or number[][]` | required |  |
| `sub_module_names` | `string[] or null` | `None` |  |

### solvency_ii_scr_credit_risk

`POST /api/v1/regulatory/solvency_ii_scr_credit_risk`: Solvency II SCR counterparty default (credit) risk — Type 1 exposures.

The sigma used here is the intra-counterparty (independent-Bernoulli)
variance term only; Delegated Regulation (EU) 2015/35 Art. 201's
inter-counterparty correlation term is not implemented, so the true
Art. 201 variance (and SCR) is at least as large as what this function
returns.

[REGULATORY] Delegated Regulation (EU) 2015/35 Art. 200(1)-(3) fixes the
capital charge as a TIERED multiplier on the standard deviation (sigma) of
the loss distribution, not a flat 3x: SCR = 3*sigma while
sigma <= 7% of total LGD; SCR = 5*sigma while 7% < sigma/TLGD <= 20%; SCR =
total LGD (fully capped) once sigma/TLGD exceeds 20%. An earlier version of
this function exposed a caller-configurable ``risk_factor`` defaulting to a
flat 3.0 — that understated capital by ~79% on a representative 2-exposure
case (807 vs. the correct ~1449, entirely from missing the 5x/TLGD tiers).
The multiplier is fixed by the Delegated Regulation, so it is intentionally
not a parameter here (same reasoning as CLAUDE.md §4.3/§4.4's Basel
thresholds: never parameterise regulator-set constants).

[LIMITATION] The variance (sigma^2) computed here is the intra-counterparty
term only — an independent-Bernoulli approximation summing each
counterparty's own default-loss variance. Art. 201's full formula also adds
an inter-counterparty correlation term (V_inter) between exposures carrying
different default probabilities, which this implementation does NOT
compute — that term is generally positive, so the true Art. 201 variance
(and therefore the true SCR) is at least as large as what this function
returns. Do not rely on this for statutory Solvency II reporting without an
actuarial review of that gap.

Formula (LaTeX): `LGD_i = EAD_i \times LGD^{rate}_i \\ TLGD = \sum_i LGD_i \\ \sigma = \sqrt{\sum_i LGD_i^2\, PD_i (1 - PD_i)} \\ SCR = \begin{cases} 3\sigma & \sigma / TLGD \le 0.07 \\ 5\sigma & 0.07 < \sigma / TLGD \le 0.20 \\ TLGD & \sigma / TLGD > 0.20 \end{cases}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposures`* | `number[] or number[][]` | required |  |
| `loss_given_default`* | `number[] or number[][]` | required |  |
| `default_probabilities`* | `number[] or number[][]` | required |  |

## CRR2 & Capital Buffers

### crr2_large_exposure_limit

`POST /api/v1/regulatory/crr2_large_exposure_limit`: CRR2 large exposure limit (Art. 395).

A single client / group exposure must not exceed 25% of Tier 1 capital,
or — where the counterparty is an institution (or a group of connected
clients including one) — the HIGHER of 25% of Tier 1 capital or EUR 150m
(``CRR2_INSTITUTION_ABSOLUTE_LIMIT_EUR``), per Art. 395(1)'s institution
alternative. ``exposure_value``/``tier1_capital`` are assumed
EUR-denominated, matching Art. 395(1)'s own absolute figure — this
function does not itself perform currency conversion.

Note: Art. 395(1)'s EUR 150m alternative additionally requires that the
institution's total exposure to non-institution clients connected to
this counterparty stays within the plain 25% limit — a condition that
spans a connected-client group, not a single exposure, so it is out of
scope for this single-exposure function and not checked here.

Formula (LaTeX): `Exposure\ ratio = \frac{exposure\_value}{tier1\_capital} \\ Limit = \begin{cases} 0.25 \times tier1\_capital & is\_institution=False \\ \max\big(0.25 \times tier1\_capital,\ 150{,}000{,}000\big) & is\_institution=True \end{cases} \\ Excess = \max\big(exposure\_value - Limit,\ 0\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposure_value`* | `number` | required |  |
| `tier1_capital`* | `number` | required |  |
| `is_institution` | `boolean` | `False` |  |

### capital_conservation_buffer

`POST /api/v1/regulatory/capital_conservation_buffer`: Capital Conservation Buffer (CCoB) and distribution constraint.

The 2.5% CET1 buffer above the 4.5% minimum. Breaching the buffer triggers
Maximum Distributable Amount (MDA) restrictions on dividends/bonuses.

Formula (LaTeX): `Required\ CET1 = 0.045 + buffer\_ratio \\ Buffer\ Capital = buffer\_ratio \times RWA \\ MDA\ restricted \iff CET1_{ratio} < 0.045 + buffer\_ratio`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cet1_ratio`* | `number` | required |  |
| `risk_weighted_assets`* | `number` | required |  |
| `buffer_ratio` | `number` | `0.025` |  |

### countercyclical_capital_buffer

`POST /api/v1/regulatory/countercyclical_capital_buffer`: Institution-specific Countercyclical Capital Buffer (CCyB).

The CCyB rate is the exposure-weighted average of the national CCyB rates
applied to the bank's private-sector credit exposures (CRD IV Art. 140).

Formula (LaTeX): `CCyB_{rate} = \frac{\sum_i E_i \cdot r_i}{\sum_i E_i} \\ CCyB_{capital} = CCyB_{rate} \times RWA`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `exposure_amounts`* | `number[] or number[][]` | required |  |
| `country_ccyb_rates`* | `number[] or number[][]` | required |  |
| `risk_weighted_assets`* | `number` | required |  |

### combined_buffer_requirement

`POST /api/v1/regulatory/combined_buffer_requirement`: Combined Buffer Requirement (CBR).

The max(G-SII, O-SII, SyRB) selection is expected to already be resolved
by the caller into ``systemic_buffer_ratio``; this function itself
performs only a straight sum of the three supplied buffer ratios.

``CBR = CCoB + CCyB + max(G-SII, O-SII, SyRB)`` per CRD IV. Sums the buffer
ratios and (optionally) the capital amount on the supplied RWA.

Formula (LaTeX): `CBR = CCoB + CCyB + SyRB \\ CBR_{capital} = CBR \times RWA`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `capital_conservation_buffer_ratio` | `number` | `0.025` |  |
| `countercyclical_buffer_ratio` | `number` | `0.0` |  |
| `systemic_buffer_ratio` | `number` | `0.0` |  |
| `risk_weighted_assets` | `number` | `0.0` |  |
