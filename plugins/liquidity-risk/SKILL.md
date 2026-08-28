---
name: pyvar-liquidity-risk
description: >
  Activate for liquidity risk: LCR, NSFR, cash flow ladders, stress scenarios,
  ILAAP metrics, funding risk, intraday liquidity, or liquidity VaR. Covers
  40 functions across 8 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [liquidity-risk, LCR, NSFR, HQLA, cash-flow, ILAAP,
       survival-horizon, funding-risk, intraday, stress-test]
---

# pyvar — Liquidity Risk  (40 functions)

## Architecture context
- **Compute**: NumPy (cash flow aggregation), Polars (large ladder datasets)
- **Queue**: Celery (daily LCR/NSFR batch)
- **Storage**: Redis (intraday monitor), PostgreSQL (regulatory ratios)
- **API**: FastAPI endpoint `/api/v1/liquidity-risk/{function}`

---

## Regulatory Ratios (LCR/NSFR)

```python
pyvar.liquidity_risk.liquidity_coverage_ratio_lcr(
    # Liquidity Coverage Ratio (LCR) = HQLA / net 30-day outflows. Net
    # outflows are floored so recognised inflows can offset at most 75% of
    # gross outflows (BCBS 238 §69, the default `inflow_cap`).
    # compliant = (LCR >= 1.0).
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.net_stable_funding_ratio_nsfr(
    # Net Stable Funding Ratio (NSFR) = ASF / RSF, must be >= 100% (BCBS 295)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.available_stable_funding_asf_calc(
    # Available Stable Funding (ASF) Calc = sum(funding_amount * asf_factor)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.required_stable_funding_rsf_calc(
    # Required Stable Funding (RSF) Calc = sum(asset_amount * rsf_factor)
    **params
) -> float | dict | pd.DataFrame
```


## Intraday Liquidity

(Moved out of the LCR/NSFR group above — these are BCBS 248 intraday
monitoring functions, not LCR/NSFR calculations.)

```python
pyvar.liquidity_risk.intraday_liquidity_monitor(
    # Intraday Liquidity Monitor. Returns `net_debit_peak` (largest net
    # negative cumulative position — BCBS 248's actual "daily maximum
    # intraday liquidity usage" tool) AND `max_usage` (drop below opening
    # balance). Only `net_debit_peak` is the genuine BCBS 248 figure —
    # `max_usage` is an internal metric and the two diverge whenever the
    # balance path never actually goes negative.
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.intraday_liquidity_stress_test(
    # Intraday Liquidity Stress Test — delays a fraction of inflows
    # (`delay_factor`); an internal stress design, not a specific BCBS 248
    # prescribed scenario.
    **params
) -> float | dict | pd.DataFrame
```


## HQLA Classification

```python
pyvar.liquidity_risk.hqla_level_1_asset_classifier(
    # HQLA Level 1 Asset Classifier. 0% haircut by default (BCBS 238 §50)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.hqla_level_2a_asset_classifier(
    # HQLA Level 2A Asset Classifier. Raises ValueError below the 15%
    # regulatory minimum haircut (BCBS 238 §52)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.hqla_level_2b_asset_classifier(
    # HQLA Level 2B Asset Classifier. Raises ValueError below the 25%
    # regulatory minimum haircut (BCBS 238 §54); pass haircut=0.50 for the
    # lower-grade-corporate/equity sub-bucket
    **params
) -> float | dict | pd.DataFrame
```

**Composition caps are not enforced by any function.** BCBS 238 §46-§47 caps
Level 2 assets at <= 40% of total HQLA and Level 2B at <= 15% of total HQLA.
These thresholds exist as constants in `engine/liquidity_ratios.py` but no
function combines the three classifiers' output and checks them — callers
must sum the three `post_haircut_value` results themselves and apply the
40%/15% checks.


## Cash Flow Ladder

```python
pyvar.liquidity_risk.cash_flow_ladder_30_day(
    # Cash Flow Ladder (30-day)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.cash_flow_ladder_1_year(
    # Cash Flow Ladder (1-year)
    **params
) -> float | dict | pd.DataFrame
```


## Stress Scenarios

```python
pyvar.liquidity_risk.liquidity_stress_scenario(
    # Liquidity Stress Scenario
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.idiosyncratic_stress_scenario(
    # Idiosyncratic Stress Scenario
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.market_wide_stress_scenario(
    # Market-Wide Stress Scenario
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.combined_stress_scenario(
    # Combined Stress Scenario. NOT the Basel/EBA reference combined
    # scenario: BCBS 238's own version runs off the LCR's regulator-set
    # 3%/5%/10% retail run-off categories, not this function's flat 15%
    # default (`retail_runoff`), which is an internal convention. The
    # "combined deficit never better than market-wide alone" ordering
    # property still holds regardless.
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.survival_horizon_calculator(
    # Survival Horizon Calculator
    **params
) -> float | dict | pd.DataFrame
```


## Buffer & Survival

```python
pyvar.liquidity_risk.liquidity_buffer_sizing(
    # Liquidity Buffer Sizing
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.contingency_funding_plan_trigger(
    # Contingency Funding Plan Trigger
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.wholesale_funding_concentration(
    # Wholesale Funding Concentration
    **params
) -> float | dict | pd.DataFrame
```


## Funding Risk

```python
pyvar.liquidity_risk.retail_deposit_runoff_rate(
    # Retail Deposit Runoff Rate
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.secured_funding_rollover_risk(
    # Secured Funding Rollover Risk
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.asset_encumbrance_ratio(
    # Asset Encumbrance Ratio
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.collateral_availability_analysis(
    # Collateral Availability Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.repo_market_stress_haircut(
    # Repo Market Stress Haircut
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.fx_liquidity_risk_by_currency(
    # FX Liquidity Risk by Currency
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.intragroup_liquidity_flow(
    # Intragroup Liquidity Flow
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.funding_cost_analysis(
    # Funding Cost Analysis
    **params
) -> float | dict | pd.DataFrame
```


## Internal Liquidity Metrics

```python
pyvar.liquidity_risk.liquidity_transfer_pricing(
    # Liquidity Transfer Pricing
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.ilaap_internal_liquidity_metric(
    # ILAAP Internal Liquidity Metric
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.ilaap_stress_testing_framework(
    # ILAAP Stress Testing Framework
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.liquidity_risk_appetite_threshold(
    # Liquidity Risk Appetite Threshold
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.early_warning_indicator_liquidity(
    # Early Warning Indicator (Liquidity)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.central_bank_facility_eligibility(
    # Central Bank Facility Eligibility
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.liquidity_gap_analysis(
    # Liquidity Gap Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.contingent_liquidity_risk(
    # Contingent Liquidity Risk
    **params
) -> float | dict | pd.DataFrame
```


## Advanced Liquidity Analytics

```python
pyvar.liquidity_risk.liquidity_var_liqvar(
    # Liquidity VaR (LiqVaR)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.funding_tenor_analysis(
    # Funding Tenor Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.liquidity_scorecard_aggregation(
    # Liquidity Scorecard Aggregation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.deposit_stability_classification(
    # Deposit Stability Classification
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.cross_currency_liquidity_bridge(
    # Cross-Currency Liquidity Bridge
    **params
) -> float | dict | pd.DataFrame
```


## Regulatory basis

Only a subset of these 40 functions implement a published, checkable Basel/EBA
formula; the rest are internally reasonable conventions with no regulator
worked example to validate against. This split is documented and enforced
(with `[closed-form, BCBS ...]` / `[independent hand-calc]` tags per test) in
`tests/validation/test_liquidity_ref.py`. Summary:

- **Regulator-sourced closed forms**: `liquidity_coverage_ratio_lcr`,
  `net_stable_funding_ratio_nsfr`, `available_stable_funding_asf_calc`,
  `required_stable_funding_rsf_calc`, the three `hqla_level_*_asset_classifier`
  functions (BCBS 238 §46-§54), `retail_deposit_runoff_rate`,
  `asset_encumbrance_ratio` (EBA), `wholesale_funding_concentration` (HHI —
  a standard competition-economics measure, not a Basel-specific one), and
  `intraday_liquidity_monitor`'s `net_debit_peak` field only (BCBS 248).
- **Internal conventions, tagged `[independent hand-calc]` in the validation
  suite** (BCBS 238/248/295 and EBA ILAAP guidelines checked directly, no
  source found): the cash-flow ladder and gap/tenor functions,
  `survival_horizon_calculator`, `liquidity_buffer_sizing`,
  `contingency_funding_plan_trigger`, `secured_funding_rollover_risk`,
  `collateral_availability_analysis`, `repo_market_stress_haircut`,
  `fx_liquidity_risk_by_currency`, `intragroup_liquidity_flow`,
  `funding_cost_analysis`, `liquidity_transfer_pricing`, and everything under
  Internal Liquidity Metrics / Advanced Liquidity Analytics above except
  `liquidity_var_liqvar`, plus `combined_stress_scenario` and
  `intraday_liquidity_monitor`'s `max_usage` field (see callouts above).
  `contingent_liquidity_risk` and `central_bank_facility_eligibility` have
  partial parameter-level leads (BCBS 238 §131 committed-facility drawdown
  rates; ECB/BoE collateral haircut schedules) not yet incorporated.
- **Cross-validated, not regulator-sourced**: `liquidity_var_liqvar` — its
  `liqvar` (Monte Carlo) is checked against `liqvar_analytic` (closed-form
  normal quantile via scipy), not against a regulatory reference.

## Naming convention
- All functions under `pyvar.liquidity_risk.*`
- Ratios returned as decimal (1.15 = 115%)
- Time buckets: overnight, 1w, 2w, 1m, 3m, 6m, 1y, >1y
- Stress scenarios: "idiosyncratic" | "market_wide" | "combined"

## Dependencies
numpy >= 1.24 · pandas >= 2.0 · polars >= 0.19
