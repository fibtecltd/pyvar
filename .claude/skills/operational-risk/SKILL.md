---
name: pyvar-operational-risk
description: >
  Activate for operational risk: LDA, AMA, SMA capital, RCSA, KRI monitoring,
  scenario analysis, BEICF, cyber/model/IT/vendor risk, or OpRisk reporting.
  Covers 44 functions across 9 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [operational-risk, LDA, AMA, SMA, OpVaR, RCSA, KRI, BEICF,
       scenario-analysis, cyber-risk, model-risk, EVT]
---

# pyvar — Operational Risk  (44 functions)

## Architecture context
- **Compute**: SciPy (distribution fitting, EVT), NumPy/Numba (MC OpVaR)
- **Queue**: Celery (monthly capital batch)
- **Storage**: PostgreSQL (loss database, KRI history)
- **API**: FastAPI endpoint `/api/v1/operational-risk/{function}`

---

## Capital Models (LDA/AMA/SMA)

```python
pyvar.operational_risk.loss_distribution_approach_lda(
    # Loss Distribution Approach (LDA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.advanced_measurement_approach_ama(
    # Advanced Measurement Approach (AMA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.basel_standardised_measurement_sma(
    # Basel Standardised Measurement (SMA)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.operational_var_opvar(
    # Operational VaR (OpVaR)
    **params
) -> float | dict | pd.DataFrame
```


## Loss Data

```python
pyvar.operational_risk.loss_data_collection_framework(
    # Loss Data Collection Framework
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.external_loss_data_integration(
    # External Loss Data Integration
    **params
) -> float | dict | pd.DataFrame
```


## RCSA Framework

```python
pyvar.operational_risk.rcsa_risk_identification(
    # RCSA Risk Identification
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.rcsa_inherent_risk_scoring(
    # RCSA Inherent Risk Scoring
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.rcsa_residual_risk_scoring(
    # RCSA Residual Risk Scoring
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.rcsa_control_effectiveness(
    # RCSA Control Effectiveness
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.key_risk_indicator_kri_library(
    # Key Risk Indicator (KRI) Library
    **params
) -> float | dict | pd.DataFrame
```


## KRI Library

```python
pyvar.operational_risk.kri_threshold_breach_detection(
    # KRI Threshold Breach Detection
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.kri_trend_analysis(
    # KRI Trend Analysis
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.scenario_analysis_oprisk(
    # Scenario Analysis (OpRisk)
    **params
) -> float | dict | pd.DataFrame
```


## Scenario Analysis

```python
pyvar.operational_risk.scenario_expert_elicitation_model(
    # Scenario Expert Elicitation Model
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.scenario_severity_estimation(
    # Scenario Severity Estimation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.scenario_frequency_estimation(
    # Scenario Frequency Estimation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.business_environment_factor_bei(
    # Business Environment Factor (BEI)
    **params
) -> float | dict | pd.DataFrame
```


## BEICF Factors

```python
pyvar.operational_risk.internal_control_factor_icf(
    # Internal Control Factor (ICF)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.severity_distribution_fitting(
    # Severity Distribution Fitting
    **params
) -> float | dict | pd.DataFrame
```


## Distribution Fitting & Capital

```python
pyvar.operational_risk.frequency_distribution_fitting(
    # Frequency Distribution Fitting
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.compound_loss_distribution(
    # Compound Loss Distribution
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.monte_carlo_oprisk_capital(
    # Monte Carlo OpRisk Capital
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.oprisk_capital_allocation(
    # OpRisk Capital Allocation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.cyber_risk_loss_estimation(
    # Cyber Risk Loss Estimation
    **params
) -> float | dict | pd.DataFrame
```


## Emerging Risk Categories

```python
pyvar.operational_risk.conduct_risk_metric(
    # Conduct Risk Metric
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.model_risk_assessment(
    # Model Risk Assessment
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.it_risk_scoring(
    # IT Risk Scoring
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.third_party_vendor_risk(
    # Third-Party / Vendor Risk
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.business_continuity_risk_score(
    # Business Continuity Risk Score
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.insurance_offset_calculation(
    # Insurance Offset Calculation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.loss_event_classification_basel(
    # Loss Event Classification (Basel)
    **params
) -> float | dict | pd.DataFrame
```


## Governance & Reporting

```python
pyvar.operational_risk.near_miss_capture_framework(
    # Near-Miss Capture Framework
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.root_cause_analysis_template(
    # Root Cause Analysis Template
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.risk_appetite_statement_oprisk(
    # Risk Appetite Statement (OpRisk)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.control_testing_effectiveness(
    # Control Testing Effectiveness
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.escalation_threshold_calculation(
    # Escalation Threshold Calculation
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.oprisk_heat_map_generator(
    # OpRisk Heat Map Generator
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.regulatory_compliance_score(
    # Regulatory Compliance Score
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.audit_finding_risk_scorer(
    # Audit Finding Risk Scorer
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.tail_risk_scenario_oprisk(
    # Tail Risk Scenario (OpRisk)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.oprisk_stress_testing(
    # OpRisk Stress Testing
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.diversification_benefit_oprisk(
    # Diversification Benefit (OpRisk)
    **params
) -> float | dict | pd.DataFrame
```

```python
pyvar.operational_risk.oprisk_economic_capital(
    # OpRisk Economic Capital
    **params
) -> float | dict | pd.DataFrame
```


## Naming convention
- All functions under `pyvar.operational_risk.*`
- Capital figures in base currency (USD/EUR)
- KRI status: "green" | "amber" | "red"
- RCSA scores: 1-25 (5x5 heat map scale)

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · statsmodels >= 0.14
