---
name: pyvar-regulatory
description: >
  Activate for regulatory capital, prudential reporting, MiFID II, EMIR,
  Basel III/IV, FRTB, ICAAP/SREP, Solvency II, or CRR2 calculations. Covers
  30 functions across 7 regulatory frameworks.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [regulatory, Basel-III, Basel-IV, FRTB, MiFID-II, EMIR, SFTR,
       ICAAP, SREP, CET1, LCR, Solvency-II, CRR2, XBRL, COREP]
---

# pyvar — Regulatory & Compliance  (30 functions)

## Architecture context
- **Compute**: NumPy (capital formula), pandas (report aggregation)
- **Output**: XBRL/COREP via lxml + openpyxl
- **Storage**: PostgreSQL (regulatory submissions audit trail)
- **API**: FastAPI endpoint `/api/v1/regulatory/{function}`
- **Security**: Bandit scan mandatory; all inputs validated via Pydantic

---

## Basel III/IV Capital Ratios

```python
pyvar.regulatory.basel_iii_common_equity_tier_1_cet1(
    # Basel III Common Equity Tier 1 (CET1)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.basel_iii_tier_1_capital_ratio(
    # Basel III Tier 1 Capital Ratio
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.basel_iii_total_capital_ratio(
    # Basel III Total Capital Ratio
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.basel_iii_leverage_ratio(
    # Basel III Leverage Ratio
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.basel_iv_output_floor(
    # Basel IV Output Floor
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.icaap_capital_assessment(
    # ICAAP Capital Assessment
    **params
) -> float | dict | pd.DataFrame
```


## ICAAP / SREP / Pillar 2

```python
pyvar.regulatory.srep_capital_add_on(
    # SREP Capital Add-On
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.pillar_2a_capital_calculation(
    # Pillar 2A Capital Calculation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.pillar_2b_stress_buffer(
    # Pillar 2B Stress Buffer
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.combined_buffer_requirement(
    # Combined Buffer Requirement
    **params
) -> float | dict | pd.DataFrame
```


## FRTB Capital (SA & IMA)

```python
pyvar.regulatory.frtb_sa_market_risk_capital(
    # FRTB SA Market Risk Capital
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.frtb_ima_market_risk_capital(
    # FRTB IMA Market Risk Capital
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.frtb_p_l_attribution_test(
    # FRTB P&L Attribution Test
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.frtb_trading_desk_aggregation(
    # FRTB Trading Desk Aggregation
    **params
) -> float | dict | pd.DataFrame
```


## MiFID II

```python
pyvar.regulatory.mifid_ii_transaction_report_validator(
    # MiFID II Transaction Report Validator
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.mifid_ii_pre_trade_transparency(
    # MiFID II Pre-Trade Transparency
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.mifid_ii_post_trade_transparency(
    # MiFID II Post-Trade Transparency
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.mifid_ii_best_execution_metric(
    # MiFID II Best Execution Metric
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.mifid_ii_algorithm_documentation(
    # MiFID II Algorithm Documentation
    **params
) -> float | dict | pd.DataFrame
```


## EMIR & SFTR

```python
pyvar.regulatory.emir_trade_repository_report(
    # EMIR Trade Repository Report
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.emir_clearing_obligation_check(
    # EMIR Clearing Obligation Check
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.emir_margin_requirement(
    # EMIR Margin Requirement
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.sftr_securities_finance_report(
    # SFTR Securities Finance Report
    **params
) -> float | dict | pd.DataFrame
```


## Fund Regulations (AIFMD/UCITS/Solvency II)

```python
pyvar.regulatory.aifmd_risk_metrics(
    # AIFMD Risk Metrics
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.ucits_kiid_risk_indicator(
    # UCITS KIID Risk Indicator
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.solvency_ii_scr_market_risk(
    # Solvency II SCR Market Risk
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.solvency_ii_scr_credit_risk(
    # Solvency II SCR Credit Risk
    **params
) -> float | dict | pd.DataFrame
```


## CRR2 & Capital Buffers

```python
pyvar.regulatory.crr2_large_exposure_limit(
    # CRR2 Large Exposure Limit
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.capital_conservation_buffer(
    # Capital Conservation Buffer
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.regulatory.countercyclical_capital_buffer(
    # Countercyclical Capital Buffer
    **params
) -> float | dict | pd.DataFrame
```


## Naming convention
- All functions under `pyvar.regulatory.*`
- Capital ratios: decimal (0.15 = 15%)
- RWA: currency amount
- MiFID II validators return: {"valid": bool, "errors": list, "report": dict}

## Dependencies
numpy >= 1.24 · pandas >= 2.0 · lxml >= 4.9 · openpyxl >= 3.1
