---
name: pyvar-operational-risk
description: >
  Run pyvar's 44 operational-risk functions on the live pyvar.com API: Basel SMA capital, loss
  distribution approach (LDA/AMA) and OpVaR, RCSA scoring, KRI breach detection, scenario
  analysis, BEICF and cyber, model, IT and vendor risk. Use when the user wants
  operational-risk capital or indicator results computed rather than only explained. Needs a
  free pyvar API key; the skill explains how to get one.
version: "1.1.0"
author: "Fibtec Limited — pyvar.com"
tags: [operational-risk, LDA, AMA, SMA, OpVaR, RCSA, KRI, BEICF, scenario-analysis, cyber-risk, model-risk, EVT]
---

# pyvar — Operational Risk  (44 functions)

Operational-risk calculations: SMA and LDA capital, loss data, RCSA, key risk indicators, scenario analysis and governance reporting. Pick the function in **Functions** below; the **Worked examples** show the request shape.

## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs a pyvar API key. Don't substitute your own numpy/scipy code and present the result
as pyvar output: these are regulatory-grade functions and the user wants pyvar's own numbers.

1. **Find the key.** Look for `PYVAR_API_KEY` in the environment. If the pyvar MCP server is
   connected, its tools (`call_pyvar_function`, `list_pyvar_functions`) already carry the key.
2. **No key? Say so, and walk the user through getting one** (free, about a minute): open
   https://www.pyvar.com#get-api-key, then either click "Sign in with Google" (when it is shown) or enter an email and
   click the verification link (valid 24 hours, single use). The page shows the key once. Ask the
   user to copy it and set `PYVAR_API_KEY`. Keys are short-lived (60 minutes by default). On a
   `401 Invalid or expired token`, ask for a fresh one: Google sign-in issues a new key every time,
   whereas the emailed link cannot be reused, so an address that cannot sign in with Google has to
   register a different email.
3. **Call the function** with the request body below (every example in this skill is a real,
   tested request). Use whichever of these is available:
   - Python: `pip install pyvar-client`, then
     `Client(api_key=os.environ["PYVAR_API_KEY"]).operational_risk.<function>(**body)`.
   - REST: `POST https://www.pyvar.com/api/v1/operational/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="operational", function_name="<function>", params=body)`.
   If you cannot run code or reach the network (for example a sandbox with no internet), give the
   user the exact `curl` command or Python snippet to run themselves instead of guessing a result.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.

## Worked examples

Each request body below is the same set of keyword arguments for the Python client, the REST body and the MCP `params`. They were run against the real API.

### 1. Basel SMA capital for a mid-sized bank

The Business Indicator drives the Business Indicator Component; with a loss component the Internal Loss Multiplier adjusts it. Any one currency unit.

`POST /api/v1/operational/basel_standardised_measurement_sma`

```json
{
  "business_indicator": 5000000000,
  "loss_component": 0.0,
  "use_ilm": true
}
```

Returns: `bic`, `ilm`, `sma_capital`.

### 2. KRI status, higher-is-worse and lower-is-worse

The same call classifies indicators where a rising value is bad (failed trades) and where a falling value is bad (staff coverage). Direction decides which side of the thresholds is worse.

`POST /api/v1/operational/kri_threshold_breach_detection`

```json
{
  "value": 0.07,
  "amber_threshold": 0.05,
  "red_threshold": 0.08,
  "direction": "higher_breach"
}
```

Returns: `status`, `breached`.

`POST /api/v1/operational/kri_threshold_breach_detection`

```json
{
  "value": 0.82,
  "amber_threshold": 0.9,
  "red_threshold": 0.8,
  "direction": "lower_breach"
}
```

Returns: `status`, `breached`.

## Functions (44)

Every function is `POST /api/v1/operational/<name>`. Required parameters are listed bare, optional ones with their defaults (`name=default`). Types, bounds and formulas are in [references/functions.md](references/functions.md): read the entry before calling a function you have not used yet.

### Capital Models — LDA (`engine/oprisk_lda.py`)

**Regulatory status**: `advanced_measurement_approach_ama` and the LDA/OpVaR
pipeline below are **not** valid for Basel III/IV regulatory capital. The
Standardised Measurement Approach (next section) replaced the AMA as the
sole approach permitted for internationally active banks from 1 January
2022 (BCBS d424, "Basel III: Finalising post-crisis reforms", Dec 2017).
The module's own docstring says this explicitly: AMA is "retired under
Basel III/IV ... retained here for economic-capital, internal scenario
analysis, and jurisdictions still on earlier timelines only." Use
`basel_standardised_measurement_sma` for the actual regulatory number.
`advanced_measurement_approach_ama`'s `expected_loss_covered` flag
implements the EL/UL choice in Basel II §669(b): if a bank can demonstrate
expected loss is already captured in provisioning/pricing, capital is
unexpected-loss-only (OpVaR − EL); otherwise capital is the full OpVaR.

`frequency_distribution_fitting` is **Poisson-only** (lambda = sample
mean); the `dispersion` (var/mean) it returns is diagnostic only — a value
far from 1 flags over/under-dispersion relative to Poisson, but no
negative-binomial or other alternative frequency fit is implemented.
`severity_distribution_fitting` is **lognormal-only** and raises
`ValueError` for any other `distribution` argument — there is no Weibull,
Gamma, or EVT/generalised-Pareto alternative for the loss tail.

- `frequency_distribution_fitting(annual_event_counts)`: Fit a Poisson frequency distribution to annual loss-event counts.
  Note: Poisson MLE only (lambda, dispersion)
- `severity_distribution_fitting(loss_amounts, distribution='lognormal')`: Fit a severity distribution to individual loss amounts.
  Note: Lognormal only; ValueError otherwise
- `compound_loss_distribution(frequency_lambda, severity_mu, severity_sigma, n_years=50000, seed=42)`: Simulate the compound (aggregate) annual loss distribution.
  Note: Poisson(freq) x lognormal(severity) MC
- `monte_carlo_oprisk_capital(frequency_lambda, severity_mu, severity_sigma, confidence_level=0.999, n_years=100000, seed=42)`: Monte Carlo OpRisk regulatory capital (OpVaR + expected shortfall).
  Note: OpVaR quantile + ES; default confidence 0.999 (Basel AMA 99.9%/1yr), enforced in [0.90, 0.9999]
- `operational_var_opvar(annual_losses, confidence_level=0.999)`: Operational VaR from an empirical aggregate-loss sample.
  Note: Quantile reader over a supplied annual-loss sample
- `loss_distribution_approach_lda(annual_event_counts, loss_amounts, confidence_level=0.999, n_years=100000, seed=42)`: End-to-end Loss Distribution Approach capital estimate.
  Note: Fit + simulate + capital, one call
- `advanced_measurement_approach_ama(annual_event_counts, loss_amounts, expected_loss_covered=True, confidence_level=0.999, n_years=100000, seed=42)`: Advanced Measurement Approach (AMA) capital charge — retired under Basel III/IV.
  Note: Retired for Basel III/IV regulatory capital (superseded by SMA); economic-capital use only

### Capital Models — SMA & Economic Capital (`engine/oprisk_capital.py`)

`insurance_offset_calculation`'s 20%-of-capital cap and haircut language
reflect the old **AMA** framework, where insurance mitigation was capped at
20% of the AMA capital charge. The **SMA** that has actually replaced AMA
for regulatory capital does not recognise insurance mitigation at all — a
widely noted gap in the SMA design. So this function (and the
`oprisk_economic_capital` mitigant it feeds) is only meaningful for
internal/economic capital; it has no bearing on the regulatory figure
produced by `basel_standardised_measurement_sma`.

- `basel_standardised_measurement_sma(business_indicator, loss_component=0.0, use_ilm=True)`: Basel III Standardised Measurement Approach (SMA) capital.
  Note: The only function here valid for Basel III/IV regulatory capital. BIC piecewise on Business Indicator buckets EUR [0,1bn]/(1bn,30bn]/(>30bn] at 12%/15%/18% marginal coefficients; ILM = ln(e-1+(LC/BIC)^0.8), LC = 15x average annual losses, bucket-1 banks may fix ILM=1 (BCBS d424, 2017)
- `oprisk_capital_allocation(total_capital, business_line_risks)`: Allocate total OpRisk capital across business lines (pro-rata by risk).
  Note: Pro-rata by standalone risk, sums to total
- `diversification_benefit_oprisk(standalone_capitals, correlation=0.0)`: Diversification benefit across OpRisk cells under a single correlation.
  Note: Sqrt(k @ corr @ k) under a single uniform pairwise correlation; an economic-capital technique, not a Basel-prescribed one
- `oprisk_economic_capital(opvar, expected_loss, insurance_offset=0.0, diversification_benefit=0.0)`: OpRisk economic capital (unexpected loss net of mitigants).
  Note: (OpVaR - EL) net of insurance + diversification
- `insurance_offset_calculation(gross_loss, policy_limit, deductible, haircut=0.0)`: Insurance mitigation offset for an operational loss.
  Note: AMA-era 20% cap language; not recognised under the SMA that replaced AMA for regulatory capital
- `tail_risk_scenario_oprisk(annual_losses, tail_confidence=0.999, severity_multiplier=1.0)`: Tail-risk scenario capital uplift for OpRisk.
  Note: Tail ES scaled by a severity multiplier
- `oprisk_stress_testing(base_capital, frequency_shock, severity_shock)`: OpRisk stress-testing capital projection.
  Note: Base capital x (1+freq_shock) x (1+sev_shock)

### Loss Data (`engine/oprisk_rcsa.py`)

- `loss_data_collection_framework(loss_events, reporting_threshold)`: Internal loss-data collection above a reporting threshold.
  Note: Filters events at/above a reporting threshold
- `external_loss_data_integration(internal_losses, external_losses, scaling_factor)`: Integrate scaled external loss data with internal data.
  Note: Pools internal + size-scaled external losses
- `loss_event_classification_basel(event_type)`: Classify a loss event into a Basel II Level-1 event-type category.
  Note: Validates against the 7 Basel II Level-1 event-type categories (BCBS 128, Annex 9)

### RCSA Framework (`engine/oprisk_rcsa.py`)

- `rcsa_risk_identification(risk_register)`: Validate and summarise an RCSA risk register.
  Note: Validates/summarises a risk register by Basel category
- `rcsa_inherent_risk_scoring(likelihood, impact)`: Inherent risk score on the 5×5 RCSA heat map.
  Note: Likelihood x impact, 1-25 on the 5x5 heat map
- `rcsa_residual_risk_scoring(inherent_score, control_effectiveness)`: Residual risk after control mitigation.
  Note: Inherent x (1 - control_effectiveness)
- `rcsa_control_effectiveness(design_score, operating_score, design_weight=0.4)`: Composite control effectiveness from design and operating effectiveness.
  Note: Weighted design/operating effectiveness
- `control_testing_effectiveness(tests_passed, tests_total)`: Control testing pass rate and effectiveness conclusion.
  Note: Pass rate; "effective" at >= 95%

### BEICF Factors (`engine/oprisk_rcsa.py`)

- `business_environment_factor_bei(factor_scores, baseline=3.0, sensitivity=0.05)`: Business Environment Indicator (BEI) capital adjustment multiplier.
  Note: Capital multiplier around 1.0 from forward-looking business-environment scores
- `internal_control_factor_icf(control_scores, baseline=0.8, sensitivity=0.25)`: Internal Control Factor (ICF) capital adjustment multiplier.
  Note: Capital multiplier; stronger controls reduce it

### KRI Library (`engine/oprisk_kri.py`)

- `key_risk_indicator_kri_library(kri_definitions)`: Validate and index a KRI library.
  Note: Validates/indexes a KRI registry
- `kri_threshold_breach_detection(value, amber_threshold, red_threshold, direction='higher_breach')`: Classify a KRI value into a green/amber/red status.
  Note: Green/amber/red vs two-tier thresholds
- `kri_trend_analysis(observations, higher_is_worse=True)`: Linear-trend analysis of a KRI time series.
  Note: OLS slope -> deteriorating/improving/stable

### Scenario Analysis (`engine/oprisk_scenario.py`)

- `scenario_analysis_oprisk(frequency_lambda, severity_mu, severity_sigma, confidence_level=0.999, n_years=50000, seed=42)`: Scenario-based OpRisk capital via a compound Monte Carlo.
  Note: Single-scenario compound-loss Monte Carlo capital
- `scenario_expert_elicitation_model(expert_estimates, expert_weights=None)`: Aggregate expert loss estimates into a consensus with dispersion.
  Note: Weighted consensus + dispersion across experts
- `scenario_severity_estimation(typical_loss, worst_case_loss, worst_case_percentile=0.99)`: Calibrate a lognormal severity from expert typical / worst-case losses.
  Note: Lognormal calibrated from typical/worst-case (two-point)
- `scenario_frequency_estimation(expected_events_per_year, occurrences=None, observation_years=None)`: Estimate a scenario's annual frequency (Poisson lambda).
  Note: Expert lambda, or occurrences/observation_years

### Emerging Risk Categories (`engine/oprisk_governance.py`)

These six are self-authored composite scores (weighted indices / caps
chosen in this codebase) — none of them cite, or claim to implement, a
specific Basel/BCBS formula, unlike the Capital Models and Loss Data
sections above. `model_risk_assessment` and `cyber_risk_loss_estimation`
name the frameworks they take their *shape* from (SR 11-7 / PRA SS1/23-style
materiality x complexity tiering; a FAIR-style single-loss-expectancy
estimate) but the specific weights and thresholds are pyvar's own, not
values prescribed by those frameworks.

- `cyber_risk_loss_estimation(records_exposed, cost_per_record, breach_probability, business_interruption_cost=0.0)`: Estimate expected and worst-case cyber loss.
  Note: FAIR-style single-loss-expectancy estimate
- `conduct_risk_metric(complaints, customers, redress_paid, revenue)`: Composite conduct-risk metric from complaints and redress intensity.
  Note: Complaints/1000 + redress ratio, 0-100 index (no Basel citation)
- `model_risk_assessment(materiality, complexity, validation_score)`: Model risk tier from materiality, complexity, and validation quality.
  Note: Materiality x complexity, SR 11-7 / PRA SS1/23-style tiering
- `it_risk_scoring(availability, incident_count, patch_compliance)`: IT operational-risk score from availability, incidents and patching.
  Note: Availability/incidents/patching, 0-100 index (no Basel citation)
- `third_party_vendor_risk(criticality, financial_health, concentration, substitutability)`: Third-party / vendor risk score.
  Note: Criticality/financial-health/concentration index
- `business_continuity_risk_score(rto_hours, rpo_hours, max_tolerable_downtime, bcp_maturity, rpo_target_hours=None)`: Business-continuity risk from RTO/RPO versus tolerance and BCP maturity.
  Note: RTO vs max tolerable downtime, BCP-maturity discounted

### Governance & Reporting (`engine/oprisk_governance.py`)

- `near_miss_capture_framework(events)`: Summarise captured near-miss events.
  Note: Zero-actual-loss/nonzero-potential-loss events
- `root_cause_analysis_template(causal_factors)`: Aggregate root-cause contributions into a normalised attribution.
  Note: Normalises causal-factor weights to shares
- `risk_appetite_statement_oprisk(current_metric, appetite_limit, tolerance_limit, higher_is_worse=True)`: Assess an OpRisk metric against appetite and tolerance limits.
  Note: Within_appetite/within_tolerance/breach
- `escalation_threshold_calculation(loss_amount, thresholds)`: Determine the escalation level for a loss against tiered thresholds.
  Note: Highest governance tier a loss triggers
- `oprisk_heat_map_generator(likelihoods, impacts)`: Generate a 5×5 OpRisk heat-map distribution.
  Note: 5x5 likelihood x impact grid + RAG per risk
- `regulatory_compliance_score(requirements_met, weights=None)`: Weighted regulatory-compliance score.
  Note: Weighted fraction of requirements met, 0-100
- `audit_finding_risk_scorer(severity, likelihood, overdue_days)`: Score an outstanding audit finding by severity, likelihood and ageing.
  Note: Severity x likelihood + overdue-ageing uplift, capped 25

## Naming convention
- Capital figures in base currency (USD/EUR)
- KRI status: "green" | "amber" | "red"
- RCSA scores: 1-25 (5x5 heat map scale)
## For contributors: dependencies
numpy >= 1.26 · scipy >= 1.13 · numba >= 0.59

(`pandas` and `statsmodels` are project-wide dependencies used by other
domains but are not imported anywhere in `engine/oprisk_*.py` — none of the
44 functions here use either.)

## For contributors: architecture context
- **Compute**: NumPy throughout; SciPy only in `engine/oprisk_scenario.py`
  (`scipy.stats.norm.ppf` for the two-point lognormal severity calibration —
  there is no distribution-fitting library call and no EVT/generalised-Pareto
  tail model anywhere in this domain, despite the `EVT` tag above). One
  `@njit(cache=True)` kernel exists (`_aggregate_annual_losses` in
  `engine/oprisk_lda.py`, summing pre-drawn severities into per-year
  totals); the other 43 functions are plain Python/NumPy, no Numba.
- **Queue**: none. Every one of the 44 functions executes synchronously
  inside the FastAPI request in `api/routes/operational.py` and returns its
  result directly — unlike `/var/compute`, there is no Celery task, no
  `apply_async` dispatch, and no polling flow for this domain (`tasks/`
  contains only `var_task.py`).
- **Storage**: none persisted. Results are returned in the HTTP response
  body only; `storage/models.py` has no loss-database or KRI-history table
  (its only tables are `ApiUsage`, `User`, and `VaRJob`).
- **API**: FastAPI, one `POST` route per function under
  `/api/v1/operational/{function_name}` (e.g.
  `POST /api/v1/operational/basel_standardised_measurement_sma`) — the
  router prefix is `/operational`, not `/operational-risk`, and there is no
  single templated `{function}` route; `api/routes/operational.py` and
  `schemas/operational.py` are both generated by `scripts/gen_p3.py`.
- **Return type**: every function returns a plain `dict` (JSON object) —
  none of the 44 return a bare `float` or a `pd.DataFrame`.

---
