---
name: pyvar-alm
description: >
  Activate for ALM and balance sheet: duration gap, NII simulation, EVE,
  IRRBB (six shocks), repricing gap, NMD behavioural models, prepayment,
  FTP, or ALM stress testing. Covers 33 functions across 7 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [ALM, NII, EVE, IRRBB, duration, repricing-gap, NMD, prepayment,
       FTP, convexity, basis-risk, pipeline-risk, balance-sheet, ICAAP]
---

# pyvar — ALM & Balance Sheet  (33 functions)

## Architecture context
- **Compute**: NumPy (cash flow NPV), SciPy (optimisation, curve fitting)
- **Queue**: Celery (monthly NII/EVE simulation)
- **Storage**: PostgreSQL (balance sheet snapshots, EVE history)
- **API**: FastAPI endpoint `/api/v1/alm/{function}`

---

## Duration & Gap Analysis

```python
pyvar.alm.duration_gap_analysis(
    # Duration Gap Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.macaulay_duration_balance_sheet(
    # Macaulay Duration (Balance Sheet)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.modified_duration_balance_sheet(
    # Modified Duration (Balance Sheet)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.effective_duration_alm(
    # Effective Duration (ALM)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.convexity_gap(
    # Convexity Gap
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.nii_sensitivity_rate_shock(
    # NII Sensitivity (Rate Shock)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.nii_simulation_baseline(
    # NII Simulation (Baseline)
    **params
) -> float | dict | pd.DataFrame
```


## NII & EVE Simulation

```python
pyvar.alm.nii_simulation_stress(
    # NII Simulation (Stress)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.economic_value_of_equity_eve(
    # Economic Value of Equity (EVE)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.eve_sensitivity_analysis(
    # EVE Sensitivity Analysis
    **params
) -> float | dict | pd.DataFrame
```


## IRRBB Framework

```python
pyvar.alm.irrbb_standardised_framework(
    # IRRBB Standardised Framework
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.irrbb_internal_model(
    # IRRBB Internal Model
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.irrbb_six_standard_rate_shocks(
    # IRRBB Six Standard Rate Shocks
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.repricing_gap_analysis(
    # Repricing Gap Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.repricing_maturity_profile(
    # Repricing Maturity Profile
    **params
) -> float | dict | pd.DataFrame
```


## Repricing & Gap

```python
pyvar.alm.static_gap_analysis(
    # Static Gap Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.dynamic_gap_analysis(
    # Dynamic Gap Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.basis_risk_irrbb(
    # Basis Risk (IRRBB)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.option_risk_irrbb(
    # Option Risk (IRRBB)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.pipeline_risk_measurement(
    # Pipeline Risk Measurement
    **params
) -> float | dict | pd.DataFrame
```


## Behavioural & Prepayment Models

```python
pyvar.alm.prepayment_model_mortgages(
    # Prepayment Model (Mortgages)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.behavioural_modelling_nmds(
    # Behavioural Modelling (NMDs)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.non_maturity_deposit_stability(
    # Non-Maturity Deposit Stability
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.core_deposit_duration(
    # Core Deposit Duration
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.loan_prepayment_rate_cpr(
    # Loan Prepayment Rate (CPR)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.liquidity_adjusted_nii(
    # Liquidity-Adjusted NII
    **params
) -> float | dict | pd.DataFrame
```


## Funds Transfer Pricing (FTP)

```python
pyvar.alm.funds_transfer_pricing_ftp(
    # Funds Transfer Pricing (FTP)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.ftp_curve_construction(
    # FTP Curve Construction
    **params
) -> float | dict | pd.DataFrame
```


## ALM Strategic Analytics

```python
pyvar.alm.asset_liability_mismatch_index(
    # Asset-Liability Mismatch Index
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.interest_rate_risk_capital_irrbb(
    # Interest Rate Risk Capital (IRRBB)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.structural_hedge_optimisation(
    # Structural Hedge Optimisation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.alm_stress_test(
    # ALM Stress Test
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.alm.balance_sheet_projection_model(
    # Balance Sheet Projection Model
    **params
) -> float | dict | pd.DataFrame
```


## Naming convention
- All functions under `pyvar.alm.*`
- NII/EVE: currency amounts
- Duration: years (decimal)
- Rate shocks: basis points (int) or decimal
- IRRBB shocks: "parallel_up" | "parallel_down" | "steepener" |
                "flattener" | "short_up" | "short_down"

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · QuantLib >= 1.30
