---
name: pyvar-credit-risk
description: >
  Activate for credit risk: PD/LGD/EAD, IRB/SA capital, XVA, IFRS 9 ECL,
  CDS pricing, credit portfolio models, CCR, or credit scoring. Covers
  55 functions across 10 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [credit-risk, PD, LGD, EAD, IRB, XVA, CVA, IFRS9, ECL,
       CDS, CCR, SA-CCR, KMV, Merton, scoring]
---

# pyvar — Credit Risk  (55 functions)

## Architecture context
- **Compute**: NumPy/Numba (MC credit VaR), SciPy (optimisation)
- **Queue**: Celery (long-running IFRS 9 batch jobs)
- **Storage**: PostgreSQL/SQLAlchemy (ECL results, staging)
- **API**: FastAPI endpoint `/api/v1/credit-risk/{function}`

---

## Core Credit Metrics (EL/UL/PD/LGD/EAD)

```python
pyvar.credit_risk.probability_of_default_pd_estimation(
    # Probability of Default (PD) Estimation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.loss_given_default_lgd_model(
    # Loss Given Default (LGD) Model
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.exposure_at_default_ead_calculator(
    # Exposure at Default (EAD) Calculator
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.expected_loss_el_computation(
    # Expected Loss (EL) Computation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.unexpected_loss_ul_computation(
    # Unexpected Loss (UL) Computation
    **params
) -> float | dict | pd.DataFrame
```


## Regulatory Capital (IRB/SA)

```python
pyvar.credit_risk.irb_foundation_approach_capital(
    # IRB Foundation Approach Capital
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.irb_advanced_approach_capital(
    # IRB Advanced Approach Capital
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.basel_standardised_approach_rwa(
    # Basel Standardised Approach RWA
    **params
) -> float | dict | pd.DataFrame
```


## Portfolio Credit Models

```python
pyvar.credit_risk.credit_var_monte_carlo(
    # Credit VaR (Monte Carlo)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.credit_var_analytical_vasicek(
    # Credit VaR (Analytical Vasicek)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.creditmetrics_portfolio_model(
    # CreditMetrics Portfolio Model
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.kmv_merton_distance_to_default(
    # KMV / Merton Distance-to-Default
    **params
) -> float | dict | pd.DataFrame
```


## Credit Scoring & PD Models

```python
pyvar.credit_risk.altman_z_score_credit_scoring(
    # Altman Z-Score Credit Scoring
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.logistic_regression_pd_model(
    # Logistic Regression PD Model
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.machine_learning_pd_calibration(
    # Machine Learning PD Calibration
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.through_the_cycle_pd_adjustment(
    # Through-the-Cycle PD Adjustment
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.point_in_time_pd_estimation(
    # Point-in-Time PD Estimation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.ratings_migration_matrix(
    # Ratings Migration Matrix
    **params
) -> float | dict | pd.DataFrame
```


## Migration & Correlation

```python
pyvar.credit_risk.default_correlation_matrix(
    # Default Correlation Matrix
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.credit_concentration_risk_hhi(
    # Credit Concentration Risk (HHI)
    **params
) -> float | dict | pd.DataFrame
```


## Concentration Risk

```python
pyvar.credit_risk.counterparty_credit_risk_ccr_exposure(
    # Counterparty Credit Risk (CCR) Exposure
    **params
) -> float | dict | pd.DataFrame
```


## Counterparty Credit Risk (CCR/XVA)

```python
pyvar.credit_risk.current_exposure_method_cem(
    # Current Exposure Method (CEM)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.standardised_approach_ccr_sa_ccr(
    # Standardised Approach CCR (SA-CCR)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.potential_future_exposure_pfe(
    # Potential Future Exposure (PFE)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.expected_positive_exposure_epe(
    # Expected Positive Exposure (EPE)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.effective_epe_regulatory(
    # Effective EPE (Regulatory)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.credit_valuation_adjustment_cva(
    # Credit Valuation Adjustment (CVA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.debt_valuation_adjustment_dva(
    # Debt Valuation Adjustment (DVA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.funding_valuation_adjustment_fva(
    # Funding Valuation Adjustment (FVA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.capital_valuation_adjustment_kva(
    # Capital Valuation Adjustment (KVA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.margin_valuation_adjustment_mva(
    # Margin Valuation Adjustment (MVA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.xva_aggregation(
    # XVA Aggregation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.cva_sensitivity_cva_greeks(
    # CVA Sensitivity (CVA Greeks)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.wrong_way_risk_adjustment(
    # Wrong-Way Risk Adjustment
    **params
) -> float | dict | pd.DataFrame
```


## CDS & Credit Derivatives

```python
pyvar.credit_risk.credit_spread_curve_bootstrap(
    # Credit Spread Curve Bootstrap
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.cds_pricing_isda_standard(
    # CDS Pricing (ISDA Standard)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.cds_spread_to_pd_conversion(
    # CDS Spread to PD Conversion
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.credit_default_swap_var(
    # Credit Default Swap VaR
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.collateral_haircut_calculation(
    # Collateral Haircut Calculation
    **params
) -> float | dict | pd.DataFrame
```


## IFRS 9 & ECL

```python
pyvar.credit_risk.ifrs_9_stage_classification_pd_threshold(
    # IFRS 9 Stage Classification (PD Threshold)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.ifrs_9_lifetime_ecl_stage_2_3(
    # IFRS 9 Lifetime ECL (Stage 2/3)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.ifrs_9_12_month_ecl_stage_1(
    # IFRS 9 12-Month ECL (Stage 1)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.ifrs_9_scenario_weighted_ecl(
    # IFRS 9 Scenario-Weighted ECL
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.macroeconomic_overlays_ecl(
    # Macroeconomic Overlays (ECL)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.ifrs_9_staging_criteria_assessment(
    # IFRS 9 Staging Criteria Assessment
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.retail_scorecard_pd_model(
    # Retail Scorecard PD Model
    **params
) -> float | dict | pd.DataFrame
```


## Specialised Credit Models

```python
pyvar.credit_risk.corporate_credit_scoring_model(
    # Corporate Credit Scoring Model
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.sovereign_credit_risk_assessment(
    # Sovereign Credit Risk Assessment
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.sector_default_rate_analysis(
    # Sector Default Rate Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.credit_portfolio_optimisation(
    # Credit Portfolio Optimisation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.recovery_rate_estimation(
    # Recovery Rate Estimation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.downturn_lgd_adjustment(
    # Downturn LGD Adjustment
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.maturity_adjustment_basel_irb(
    # Maturity Adjustment (Basel IRB)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.sme_correlation_factor_basel(
    # SME Correlation Factor (Basel)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.credit_risk.credit_stress_testing(
    # Credit Stress Testing
    **params
) -> float | dict | pd.DataFrame
```


## Naming convention
- All functions under `pyvar.credit_risk.*`
- PD: probability [0,1]; LGD: loss fraction [0,1]; EAD: currency amount
- XVA functions return dict with NPV, delta, sensitivities
- IFRS 9 functions return ECL amount and staging classification

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · scikit-learn >= 1.3
statsmodels >= 0.14 · QuantLib >= 1.30
