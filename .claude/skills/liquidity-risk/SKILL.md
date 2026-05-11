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
    # Liquidity Coverage Ratio (LCR)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.net_stable_funding_ratio_nsfr(
    # Net Stable Funding Ratio (NSFR)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.intraday_liquidity_monitor(
    # Intraday Liquidity Monitor
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.intraday_liquidity_stress_test(
    # Intraday Liquidity Stress Test
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.available_stable_funding_asf_calc(
    # Available Stable Funding (ASF) Calc
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.required_stable_funding_rsf_calc(
    # Required Stable Funding (RSF) Calc
    **params
) -> float | dict | pd.DataFrame
```


## HQLA Classification

```python
pyvar.liquidity_risk.hqla_level_1_asset_classifier(
    # HQLA Level 1 Asset Classifier
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.hqla_level_2a_asset_classifier(
    # HQLA Level 2A Asset Classifier
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.liquidity_risk.hqla_level_2b_asset_classifier(
    # HQLA Level 2B Asset Classifier
    **params
) -> float | dict | pd.DataFrame
```


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
    # Combined Stress Scenario
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


## Naming convention
- All functions under `pyvar.liquidity_risk.*`
- Ratios returned as decimal (1.15 = 115%)
- Time buckets: overnight, 1w, 2w, 1m, 3m, 6m, 1y, >1y
- Stress scenarios: "idiosyncratic" | "market_wide" | "combined"

## Dependencies
numpy >= 1.24 · pandas >= 2.0 · polars >= 0.19
